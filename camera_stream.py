"""
Z.A.I.N.E — Centralized CameraStream Daemon
Singleton high-performance frame capture engine.
Eliminates camera hardware contention by maintaining a single background
reader thread and serving in-memory frames (<1ms) to Face-ID, Vision,
and continuous Gesture Tracking. Includes 60s privacy idle-timeout.
"""

import os
import cv2
import time
import threading
from typing import Optional, Set
import numpy as np


# Centralized hardware mutex protecting physical DirectShow device access across all threads
CAMERA_HARDWARE_LOCK = threading.Lock()


def get_camera_hardware_lock() -> threading.Lock:
    """Returns the centralized mutex lock for DirectShow physical camera hardware access."""
    return CAMERA_HARDWARE_LOCK


class CameraStream:
    """
    Singleton Camera Streamer.
    Runs a single background daemon thread reading frames at 25-30 FPS from cv2.VideoCapture.
    Provides instant in-memory frame access to multiple concurrent consumers.
    Releases camera hardware after 60s of complete inactivity to turn off the physical LED.
    """

    IDLE_TIMEOUT_SECONDS = 60.0

    def __init__(self, camera_index: int = 0, fps: int = 30):
        self.camera_index = camera_index
        self.target_delay = 1.0 / max(fps, 1)

        self._lock = threading.Lock()
        self._frame_lock = threading.Lock()
        self._cap: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._stop_event = threading.Event()

        self._latest_frame: Optional[np.ndarray] = None
        self._latest_frame_time: float = 0.0
        self._last_access_time: float = 0.0
        self._active_consumers: Set[str] = set()

    def register_consumer(self, consumer_name: str):
        """Registers a continuous consumer (e.g. gesture_tracker) to keep stream alive."""
        with self._lock:
            self._active_consumers.add(consumer_name)
            self._last_access_time = time.time()
            if not self._running:
                self._start_capture_thread()

    def unregister_consumer(self, consumer_name: str):
        """Unregisters a continuous consumer. Stream will idle out after timeout if no other activity."""
        with self._lock:
            self._active_consumers.discard(consumer_name)
            self._last_access_time = time.time()

    def _open_camera(self) -> bool:
        """Opens webcam with DirectShow for instant initialization on Windows."""
        with CAMERA_HARDWARE_LOCK:
            if self._cap is not None and self._cap.isOpened():
                return True

            # Try DirectShow first on Windows
            cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap = cv2.VideoCapture(self.camera_index)

            if not cap.isOpened():
                print(f"[CameraStream Error]: Unable to access camera device index {self.camera_index}.")
                return False

            # Set default resolution to 640x480 for fast, low-latency CPU processing
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self._cap = cap
            return True

    def _start_capture_thread(self):
        """Starts the background frame grabber thread."""
        if self._running and self._thread is not None and self._thread.is_alive():
            return

        if not self._open_camera():
            return

        self._stop_event.clear()
        self._running = True
        self._last_access_time = time.time()

        self._thread = threading.Thread(
            target=self._capture_loop,
            name=f"CameraStream-{self.camera_index}",
            daemon=True,
        )
        self._thread.start()
        print(f"[CameraStream Online]: Camera {self.camera_index} background grabber active.")

    def _stop_capture_thread(self):
        """Stops background thread and releases hardware (turning off physical camera LED)."""
        self._running = False
        self._stop_event.set()

        with CAMERA_HARDWARE_LOCK:
            if self._cap is not None:
                try:
                    self._cap.release()
                except Exception:
                    pass
                self._cap = None

        with self._frame_lock:
            self._latest_frame = None

        print(f"[CameraStream Idle]: Camera {self.camera_index} hardware released (privacy idle timeout).")

    def _capture_loop(self):
        """Continuous background grab loop running at target FPS."""
        warm_frames = 0
        while self._running and not self._stop_event.is_set():
            loop_start = time.perf_counter()

            # Check for idle timeout if no continuous consumers are active
            with self._lock:
                no_continuous_consumers = len(self._active_consumers) == 0
                idle_duration = time.time() - self._last_access_time
                if no_continuous_consumers and idle_duration > self.IDLE_TIMEOUT_SECONDS:
                    self._stop_capture_thread()
                    break

            if self._cap is None or not self._cap.isOpened():
                if not self._open_camera():
                    time.sleep(0.5)
                    continue

            with CAMERA_HARDWARE_LOCK:
                if self._cap is not None and self._cap.isOpened():
                    ret, frame = self._cap.read()
                else:
                    ret, frame = False, None

            if ret and frame is not None:
                # Discard the first 2 warmup frames after fresh wake-up for exposure settling
                if warm_frames < 2:
                    warm_frames += 1
                else:
                    with self._frame_lock:
                        self._latest_frame = frame
                        self._latest_frame_time = time.time()
            else:
                time.sleep(0.01)

            # Regulate frame rate to ~25-30 FPS to conserve CPU
            elapsed = time.perf_counter() - loop_start
            sleep_needed = self.target_delay - elapsed
            if sleep_needed > 0:
                time.sleep(sleep_needed)

    def get_latest_frame(self, wait_timeout: float = 1.5) -> Optional[np.ndarray]:
        """
        Returns the latest BGR frame from RAM in < 1ms.
        Wakes up the camera stream if currently idle.
        Waits up to wait_timeout for the first frame if starting fresh.
        """
        with self._lock:
            self._last_access_time = time.time()
            if not self._running or self._cap is None or not self._cap.isOpened():
                self._start_capture_thread()

        # If frame is already available in buffer, return it immediately
        with self._frame_lock:
            if self._latest_frame is not None:
                return self._latest_frame.copy()

        # Wait for first frame arrival after cold start
        deadline = time.time() + wait_timeout
        while time.time() < deadline:
            with self._frame_lock:
                if self._latest_frame is not None:
                    return self._latest_frame.copy()
            time.sleep(0.02)

        return None

    def get_latest_frame_jpeg(self, quality: int = 80, wait_timeout: float = 1.5) -> bytes:
        """
        Returns latest frame encoded as JPEG bytes directly from memory.
        Compatible drop-in replacement for capture_webcam_bytes().
        """
        frame = self.get_latest_frame(wait_timeout=wait_timeout)
        if frame is None:
            return b""

        success, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if not success:
            return b""
        return encoded.tobytes()

    def is_active(self) -> bool:
        """Returns True if the camera hardware is currently open and capturing."""
        return self._running and self._cap is not None and self._cap.isOpened()

    def stop(self):
        """Explicitly stops the camera stream and releases hardware immediately."""
        with self._lock:
            self._active_consumers.clear()
            self._stop_capture_thread()


# Global singleton cache
_CAMERA_STREAMS = {}
_STREAM_LOCK = threading.Lock()


def get_camera_stream(camera_index: int = 0) -> CameraStream:
    """Returns the singleton CameraStream instance for the given camera index."""
    global _CAMERA_STREAMS
    with _STREAM_LOCK:
        if camera_index not in _CAMERA_STREAMS:
            _CAMERA_STREAMS[camera_index] = CameraStream(camera_index=camera_index)
        return _CAMERA_STREAMS[camera_index]


if __name__ == "__main__":
    print("Testing CameraStream singleton...")
    stream = get_camera_stream(0)
    print("Requesting initial frame (cold start)...")
    t0 = time.time()
    frame = stream.get_latest_frame()
    dt = (time.time() - t0) * 1000
    if frame is not None:
        print(f"Cold start succeeded: shape={frame.shape} in {dt:.1f}ms")
    else:
        print(f"Cold start returned None in {dt:.1f}ms (camera may be in use)")

    print("Requesting 5 consecutive frames (warm in-memory reads)...")
    for i in range(5):
        t0 = time.perf_counter()
        f = stream.get_latest_frame()
        dt_us = (time.perf_counter() - t0) * 1000
        print(f"Frame {i+1}: dt={dt_us:.3f}ms, valid={f is not None}")
        time.sleep(0.05)

    print("Stream active:", stream.is_active())
    stream.stop()
    print("Stream stopped. Active:", stream.is_active())

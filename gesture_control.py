"""
Z.A.I.N.E — Computer Vision Gesture Recognition Engine (Layer 2 Upgraded)
Provides both:
1. Single-shot on-demand classifier (capture_and_classify_gesture) for backward compatibility
2. Continuous hand-tracking daemon (GestureTracker) for Holographic UI manipulation:
   - Pinch-and-hold (drag): moves selected holographic glass cards
   - Pinch-and-quick-release (open/select): clicks / previews files
   - Open-palm swipe: slides the holographic file browser in/out
Uses MediaPipe on CPU (0 MB VRAM) with palm scale normalization.
"""

from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import time
import math
import threading
import numpy as np
import cv2

PROJECT_ROOT = Path(__file__).resolve().parent
MODEL_PATH = PROJECT_ROOT / "models" / "gesture_recognizer.task"

# Check if mediapipe and model are present
MEDIAPIPE_AVAILABLE = False
try:
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
    if MODEL_PATH.exists():
        MEDIAPIPE_AVAILABLE = True
except Exception:
    MEDIAPIPE_AVAILABLE = False

GESTURE_MAP = {
    "Thumb_Up": ("THUMBS_UP", "👍"),
    "Victory": ("PEACE_SIGN", "✌️"),
    "Open_Palm": ("OPEN_PALM", "✋"),
    "Closed_Fist": ("FIST", "✊"),
    "Pointing_Up": ("POINTING_UP", "☝️"),
    "Thumb_Down": ("THUMBS_DOWN", "👎"),
    "ILoveYou": ("ROCK_ON", "🤟"),
}


def _trigger_os_action_async(action: str):
    """Executes OS-level keyboard/mouse navigation asynchronously without blocking tracking loop."""
    def _worker():
        try:
            import pyautogui
            pyautogui.FAILSAFE = False
            if action == "back":
                # Navigate Back: Alt + Left Arrow (across browsers, explorers, windows)
                pyautogui.hotkey('alt', 'left')
                print("[IronHands Action]: Triggered OS BACK (Alt + Left)")
            elif action == "app_switch":
                # App Moving / Switcher: Alt + Tab
                pyautogui.hotkey('alt', 'tab')
                print("[IronHands Action]: Triggered APP SWITCH (Alt + Tab)")
        except Exception as e:
            print(f"[IronHands Action Warning]: Could not dispatch OS action '{action}': {e}")

    threading.Thread(target=_worker, daemon=True).start()


# ============================================================================
# 1. SINGLE-SHOT ON-DEMAND CLASSIFICATION (Backward Compatibility)
# ============================================================================

def capture_and_classify_gesture(camera_index: int = 0, execute_action: bool = True) -> Dict[str, Any]:
    """
    Captures a frame from the webcam (via CameraStream), detects hand landmarks and classifies the gesture,
    and optionally executes corresponding actions.
    """
    if not MEDIAPIPE_AVAILABLE:
        return {
            "status": "ERROR",
            "gesture": "NONE",
            "emoji": "⚠️",
            "confidence": 0.0,
            "message": "MediaPipe GestureRecognizer or models/gesture_recognizer.task not initialized.",
            "action_taken": "None",
        }

    # Fetch frame from shared CameraStream daemon
    frame = None
    try:
        from camera_stream import get_camera_stream
        stream = get_camera_stream(camera_index)
        frame = stream.get_latest_frame(wait_timeout=2.0)
    except Exception as e:
        print(f"[Gesture CameraStream Notice]: Falling back to direct capture: {e}")

    # Fallback to direct VideoCapture if stream is unavailable
    if frame is None:
        try:
            from camera_stream import CAMERA_HARDWARE_LOCK
        except ImportError:
            import threading
            CAMERA_HARDWARE_LOCK = threading.Lock()

        with CAMERA_HARDWARE_LOCK:
            cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap = cv2.VideoCapture(camera_index)

            if not cap.isOpened():
                return {
                    "status": "CAMERA_UNAVAILABLE",
                    "gesture": "NONE",
                    "emoji": "📷",
                    "confidence": 0.0,
                    "message": f"Could not access camera index {camera_index}. Camera may be in use by another app or disconnected.",
                    "action_taken": "None",
                }

            for _ in range(4):
                ret, f = cap.read()
                if ret and f is not None:
                    frame = f
            cap.release()

    if frame is None:
        return {
            "status": "CAPTURE_FAILED",
            "gesture": "NONE",
            "emoji": "📷",
            "confidence": 0.0,
            "message": "Failed to read image buffer from webcam.",
            "action_taken": "None",
        }

    # Convert BGR to RGB for MediaPipe
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    gesture_name = "NO_HAND_DETECTED"
    emoji = "🔍"
    confidence = 0.0
    action_taken = "None"

    try:
        base_options = python.BaseOptions(model_asset_path=str(MODEL_PATH))
        options = vision.GestureRecognizerOptions(base_options=base_options, num_hands=1)
        with vision.GestureRecognizer.create_from_options(options) as recognizer:
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
            recognition_result = recognizer.recognize(mp_image)

            if recognition_result.gestures and len(recognition_result.gestures) > 0:
                top_gesture = recognition_result.gestures[0][0]
                raw_category = top_gesture.category_name
                confidence = float(top_gesture.score)

                if raw_category in GESTURE_MAP:
                    gesture_name, emoji = GESTURE_MAP[raw_category]
                elif raw_category and raw_category != "None":
                    gesture_name = raw_category.upper()
                    emoji = "✋"
    except Exception as e:
        return {
            "status": "RECOGNITION_ERROR",
            "gesture": "NONE",
            "emoji": "⚠️",
            "confidence": 0.0,
            "message": f"Gesture recognition exception: {e}",
            "action_taken": "None",
        }

    # Trigger corresponding action if requested
    if execute_action and gesture_name != "NO_HAND_DETECTED":
        if gesture_name == "THUMBS_UP":
            action_taken = "Affirmed: Acknowledged command with Jarvis affirmation."
        elif gesture_name == "PEACE_SIGN":
            try:
                from vision import capture_screen_bytes
                sc = capture_screen_bytes()
                action_taken = f"Snapshot: Screen captured ({len(sc)} bytes)."
            except Exception as e:
                action_taken = f"Snapshot notice: {e}"
        elif gesture_name == "OPEN_PALM":
            action_taken = "Halt: Audio speech playback stopped."
        elif gesture_name == "FIST":
            try:
                from tools import toggle_ultron_mode
                res = toggle_ultron_mode(True)
                action_taken = f"Singularity Shift: {res}"
            except Exception as e:
                action_taken = f"Ultron toggle: {e}"
        elif gesture_name == "POINTING_UP":
            try:
                from tools import get_youtube_channel_stats_tool
                stats = get_youtube_channel_stats_tool()
                action_taken = f"Briefing: {stats[:120]}..."
            except Exception as e:
                action_taken = f"Stats check: {e}"

    return {
        "status": "SUCCESS" if gesture_name != "NO_HAND_DETECTED" else "NO_HAND",
        "gesture": gesture_name,
        "emoji": emoji,
        "confidence": confidence,
        "action_taken": action_taken,
        "message": f"Gesture Detected: {emoji} {gesture_name} ({confidence * 100:.1f}% confidence)",
    }


# ============================================================================
# 2. CONTINUOUS GESTURE TRACKER (Layer 2 Holographic Engine)
# ============================================================================

def _euclidean_dist(p1, p2) -> float:
    """Calculates 3D Euclidean distance between two landmarks."""
    return math.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2 + (p1.z - p2.z) ** 2)


class GestureTracker:
    """
    Continuous hand-landmark tracking daemon.
    Runs on CPU with zero VRAM impact, pulling frames from CameraStream.
    Disambiguates:
    - Pinch-and-hold (drag): moves selected glass card
    - Pinch-and-quick-release (open/select): activates/opens file card
    - Open-palm horizontal swipe: toggles holographic panel navigation
    """

    # Normalized threshold constants
    PINCH_THRESHOLD = 0.32       # Thumb-to-Index distance normalized by wrist-to-middle MCP
    PINCH_HOLD_SECONDS = 0.20    # Threshold between click (<200ms) and drag (>200ms)
    MAX_TAP_DISPLACEMENT = 0.06  # Normalized distance ceiling for quick release (~20px)
    SWIPE_MIN_DISPLACEMENT = 0.16 # Normalized X displacement for swipe gesture
    SWIPE_COOLDOWN_SECONDS = 0.8  # Prevent double-trigger on single swipe

    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._stop_event = threading.Event()
        self._recognizer = None

        # Temporal gesture tracking state
        self._is_pinching = False
        self._pinch_start_time = 0.0
        self._pinch_start_pos: Tuple[float, float] = (0.5, 0.5)
        self._last_cursor_pos: Tuple[float, float] = (0.5, 0.5)
        self._drag_active = False

        # Swipe tracking ring buffer: [(x, timestamp), ...]
        self._palm_history: List[Tuple[float, float]] = []
        self._last_swipe_time = 0.0

        # Throttling cursor broadcast to ~20Hz
        self._last_cursor_broadcast = 0.0

    def _broadcast_to_hud(self, payload: dict):
        """Sends SSE message to active HUD clients if UI is initialized."""
        try:
            from ui import get_ui
            ui = get_ui()
            if ui:
                ui.broadcast(payload)
        except Exception:
            pass

    def start(self) -> bool:
        """Starts the continuous gesture tracking loop."""
        if not MEDIAPIPE_AVAILABLE:
            print("[GestureTracker Error]: MediaPipe GestureRecognizer or model not found.")
            return False

        with self._lock:
            if self._running:
                return True

            try:
                base_options = python.BaseOptions(model_asset_path=str(MODEL_PATH))
                options = vision.GestureRecognizerOptions(base_options=base_options, num_hands=1)
                self._recognizer = vision.GestureRecognizer.create_from_options(options)
            except Exception as e:
                print(f"[GestureTracker Error]: Failed to create GestureRecognizer: {e}")
                return False

            from camera_stream import get_camera_stream
            get_camera_stream(self.camera_index).register_consumer("gesture_tracker")

            self._stop_event.clear()
            self._running = True
            self._thread = threading.Thread(
                target=self._tracking_loop,
                name="GestureTrackerDaemon",
                daemon=True,
            )
            self._thread.start()
            print("[GestureTracker Online]: Continuous hand-tracking daemon active.")
            self._broadcast_to_hud({"type": "gesture_state", "active": True})
            return True

    def stop(self):
        """Stops the tracking loop and unregisters from CameraStream."""
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._stop_event.set()

        from camera_stream import get_camera_stream
        get_camera_stream(self.camera_index).unregister_consumer("gesture_tracker")

        if self._recognizer is not None:
            try:
                self._recognizer.close()
            except Exception:
                pass
            self._recognizer = None

        print("[GestureTracker Offline]: Gesture tracking stopped.")
        self._broadcast_to_hud({"type": "gesture_state", "active": False})

    def is_active(self) -> bool:
        """Returns True if the tracking loop is currently active."""
        return self._running

    def toggle(self) -> bool:
        """Toggles tracking on or off."""
        if self.is_active():
            self.stop()
            return False
        else:
            return self.start()

    def _tracking_loop(self):
        """Main recognition and gesture disambiguation loop (~20-25 FPS)."""
        from camera_stream import get_camera_stream
        stream = get_camera_stream(self.camera_index)

        while self._running and not self._stop_event.is_set():
            loop_start = time.perf_counter()

            frame = stream.get_latest_frame(wait_timeout=0.2)
            if frame is None:
                time.sleep(0.02)
                continue

            # Convert BGR to RGB for MediaPipe
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

            try:
                result = self._recognizer.recognize(mp_image)
            except Exception:
                time.sleep(0.02)
                continue

            # Check if hand landmarks were detected
            if result.hand_landmarks and len(result.hand_landmarks) > 0:
                landmarks = result.hand_landmarks[0]
                self._process_landmarks(landmarks)
            else:
                self._handle_no_hand()

            # Target ~20-25 FPS to minimize CPU footprint
            elapsed = time.perf_counter() - loop_start
            sleep_needed = 0.045 - elapsed
            if sleep_needed > 0:
                time.sleep(sleep_needed)

    def _process_landmarks(self, lm):
        """Analyzes 21 landmarks, normalizes scales, and triggers disambiguated events."""
        now = time.time()

        # Key Landmarks:
        # 0: Wrist, 4: Thumb Tip, 8: Index Tip, 9: Middle MCP
        # 6: Index PIP, 10: Middle PIP, 14: Ring PIP, 18: Pinky PIP
        # 12: Middle Tip, 16: Ring Tip, 20: Pinky Tip
        wrist = lm[0]
        thumb_tip = lm[4]
        index_tip = lm[8]
        middle_mcp = lm[9]

        # Natural mirroring for display: x_screen = 1.0 - raw_x
        # Cursor follows midpoint between thumb and index when pinching, or index tip
        norm_x = float(np.clip(1.0 - index_tip.x, 0.0, 1.0))
        norm_y = float(np.clip(index_tip.y, 0.0, 1.0))

        # 1. Scale Normalization (distance from wrist to middle finger MCP)
        palm_scale = _euclidean_dist(wrist, middle_mcp)
        palm_scale = max(palm_scale, 0.05)  # Safeguard against zero/inf

        # 2. Normalized Pinch Metric
        thumb_index_dist = _euclidean_dist(thumb_tip, index_tip)
        normalized_pinch = thumb_index_dist / palm_scale
        is_pinched = (normalized_pinch < self.PINCH_THRESHOLD)

        # ----------------------------------------------------------------------
        # A. PINCH DISAMBIGUATION (Drag vs Quick Release Pick)
        # ----------------------------------------------------------------------
        cursor_state = "idle"

        if is_pinched:
            cursor_state = "pinch"
            if not self._is_pinching:
                # Pinch initiated
                self._is_pinching = True
                self._pinch_start_time = now
                self._pinch_start_pos = (norm_x, norm_y)
                self._last_cursor_pos = (norm_x, norm_y)
                self._drag_active = False
            else:
                # Sustained pinch
                pinch_duration = now - self._pinch_start_time
                if pinch_duration >= self.PINCH_HOLD_SECONDS:
                    self._drag_active = True
                    dx = norm_x - self._last_cursor_pos[0]
                    dy = norm_y - self._last_cursor_pos[1]
                    self._last_cursor_pos = (norm_x, norm_y)

                    self._broadcast_to_hud({
                        "type": "gesture_drag",
                        "x": norm_x,
                        "y": norm_y,
                        "dx": dx,
                        "dy": dy,
                    })
        else:
            if self._is_pinching:
                # Pinch was released!
                pinch_duration = now - self._pinch_start_time
                dx_total = norm_x - self._pinch_start_pos[0]
                dy_total = norm_y - self._pinch_start_pos[1]
                total_disp = math.sqrt(dx_total ** 2 + dy_total ** 2)

                if pinch_duration < self.PINCH_HOLD_SECONDS and total_disp < self.MAX_TAP_DISPLACEMENT:
                    # Pinch-and-quick-release -> CLICK / OPEN
                    self._broadcast_to_hud({
                        "type": "gesture_open",
                        "x": self._pinch_start_pos[0],
                        "y": self._pinch_start_pos[1],
                    })
                elif self._drag_active:
                    # Drag finished -> RELEASE DROP
                    self._broadcast_to_hud({
                        "type": "gesture_drop",
                        "x": norm_x,
                        "y": norm_y,
                    })

                self._is_pinching = False
                self._drag_active = False

        # ----------------------------------------------------------------------
        # B. OPEN-PALM HORIZONTAL SWIPE DISAMBIGUATION
        # ----------------------------------------------------------------------
        # Check if 4 main fingers are extended (Tip is significantly farther from wrist than PIP)
        fingers_extended = (
            _euclidean_dist(lm[8], wrist) > _euclidean_dist(lm[6], wrist) * 1.25 and
            _euclidean_dist(lm[12], wrist) > _euclidean_dist(lm[10], wrist) * 1.25 and
            _euclidean_dist(lm[16], wrist) > _euclidean_dist(lm[14], wrist) * 1.25 and
            _euclidean_dist(lm[20], wrist) > _euclidean_dist(lm[18], wrist) * 1.25
        )

        palm_center_x = 1.0 - middle_mcp.x

        if fingers_extended and not is_pinched:
            cursor_state = "open"
            self._palm_history.append((palm_center_x, now))
            # Keep history to past 0.4 seconds
            self._palm_history = [(x, t) for (x, t) in self._palm_history if (now - t) <= 0.4]

            if len(self._palm_history) >= 4 and (now - self._last_swipe_time) > self.SWIPE_COOLDOWN_SECONDS:
                oldest_x, oldest_t = self._palm_history[0]
                newest_x, newest_t = self._palm_history[-1]
                delta_x = newest_x - oldest_x
                duration = newest_t - oldest_t

                if duration > 0.08:
                    if delta_x < -self.SWIPE_MIN_DISPLACEMENT:
                        # Fast movement towards left -> BACK (Alt+Left)
                        self._last_swipe_time = now
                        self._palm_history.clear()
                        _trigger_os_action_async("back")
                        self._broadcast_to_hud({
                            "type": "gesture_swipe",
                            "direction": "left",
                            "action": "back",
                            "velocity": abs(delta_x / duration),
                        })
                    elif delta_x > self.SWIPE_MIN_DISPLACEMENT:
                        # Fast movement towards right -> APP SWITCH (Alt+Tab)
                        self._last_swipe_time = now
                        self._palm_history.clear()
                        _trigger_os_action_async("app_switch")
                        self._broadcast_to_hud({
                            "type": "gesture_swipe",
                            "direction": "right",
                            "action": "app_switch",
                            "velocity": abs(delta_x / duration),
                        })
        else:
            self._palm_history.clear()

        # ----------------------------------------------------------------------
        # C. REAL-TIME CURSOR POSITION BROADCAST (~20Hz)
        # ----------------------------------------------------------------------
        if (now - self._last_cursor_broadcast) > 0.05:
            self._last_cursor_broadcast = now
            self._broadcast_to_hud({
                "type": "gesture_cursor",
                "x": norm_x,
                "y": norm_y,
                "state": cursor_state,
                "pinched": is_pinched,
            })

    def _handle_no_hand(self):
        """Resets temporal tracking when no hand is in frame."""
        if self._is_pinching:
            self._is_pinching = False
            self._drag_active = False
            self._broadcast_to_hud({"type": "gesture_drop", "x": self._last_cursor_pos[0], "y": self._last_cursor_pos[1]})
        self._palm_history.clear()


# Global tracker singleton
_GESTURE_TRACKER: Optional[GestureTracker] = None
_TRACKER_LOCK = threading.Lock()


def get_gesture_tracker(camera_index: int = 0) -> GestureTracker:
    """Returns the singleton GestureTracker instance."""
    global _GESTURE_TRACKER
    with _TRACKER_LOCK:
        if _GESTURE_TRACKER is None:
            _GESTURE_TRACKER = GestureTracker(camera_index=camera_index)
        return _GESTURE_TRACKER


def start_gesture_tracker() -> bool:
    """Activates continuous gesture tracking."""
    return get_gesture_tracker().start()


def stop_gesture_tracker():
    """Deactivates continuous gesture tracking."""
    get_gesture_tracker().stop()


def toggle_gesture_tracker() -> bool:
    """Toggles continuous gesture tracking."""
    return get_gesture_tracker().toggle()


def is_gesture_tracker_active() -> bool:
    """Returns True if continuous gesture tracking is active."""
    return get_gesture_tracker().is_active()


if __name__ == "__main__":
    print("Testing GestureTracker...")
    tracker = get_gesture_tracker(0)
    print("Starting gesture tracker for 3 seconds...")
    tracker.start()
    time.sleep(3.0)
    print("Active:", tracker.is_active())
    tracker.stop()
    print("Stopped. Active:", tracker.is_active())

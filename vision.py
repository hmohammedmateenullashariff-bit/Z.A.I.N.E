"""
Z.A.I.N.E — Vision & Multimodal Perception Layer (Phase 5)
Provides 100% local, offline, and private visual perception:
- Screen Capture: In-memory RAM grab via PIL.ImageGrab with display-sleep resilience
- Webcam Capture: 1-shot DirectShow hardware frame grab with instant device release (< 500ms LED)
- Multimodal VLM: Ollama 'moondream' (ultra-lightweight vision model running on GPU)
- Desk Presence: Local VLM person detection sentinel with zero frame storage
"""

import io
import base64
import time
import requests
from PIL import Image, ImageGrab

try:
    import cv2
except ImportError:
    cv2 = None

OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"
VISION_MODEL = "moondream"


def capture_screen_bytes(max_dim: int = 1280, quality: int = 80) -> bytes:
    """
    Captures the primary display in RAM, resizes proportionally, and returns JPEG bytes.
    Gracefully handles locked workstation or sleeping display.
    """
    try:
        screenshot = ImageGrab.grab()
    except Exception as e:
        print(f"[Vision Notice]: Screen grab failed (display sleeping or locked): {e}")
        return b""

    # Convert RGBA to RGB if needed
    if screenshot.mode != "RGB":
        screenshot = screenshot.convert("RGB")

    # Proportional scaling to optimize memory & VLM token computation
    w, h = screenshot.size
    if max(w, h) > max_dim:
        scale = max_dim / float(max(w, h))
        new_w, new_h = int(w * scale), int(h * scale)
        screenshot = screenshot.resize((new_w, new_h), Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    screenshot.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def capture_screen_base64(max_dim: int = 1280, quality: int = 80) -> str:
    """Captures screen and returns base64-encoded string, or empty string if screen is locked."""
    raw_bytes = capture_screen_bytes(max_dim=max_dim, quality=quality)
    if not raw_bytes:
        return ""
    return base64.b64encode(raw_bytes).decode("utf-8")


def capture_webcam_bytes(camera_index: int = 0, quality: int = 80) -> bytes:
    """
    Captures a frame from the shared CameraStream daemon (<1ms in-memory when active).
    Maintains fallback to direct VideoCapture if stream is unavailable.
    """
    if cv2 is None:
        return b""

    try:
        from camera_stream import get_camera_stream
        stream = get_camera_stream(camera_index)
        jpeg_bytes = stream.get_latest_frame_jpeg(quality=quality)
        if jpeg_bytes:
            return jpeg_bytes
    except Exception as e:
        print(f"[Vision CameraStream Notice]: Falling back to direct capture: {e}")

    # Fallback to direct DirectShow capture if CameraStream unavailable
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
            return b""

        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            return b""

        success, encoded_img = cv2.imencode(
            ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        )
        if not success:
            return b""

        return encoded_img.tobytes()


def capture_webcam_base64(camera_index: int = 0, quality: int = 80) -> str:
    """Captures webcam 1-shot frame and returns base64-encoded string."""
    raw_bytes = capture_webcam_bytes(camera_index=camera_index, quality=quality)
    if not raw_bytes:
        return ""
    return base64.b64encode(raw_bytes).decode("utf-8")


def analyze_image_with_ollama(base64_image: str, prompt: str = "Describe what you see in detail.") -> str:
    """Sends an in-memory base64 image to Ollama's local Moondream vision model."""
    if not base64_image:
        return "Error: No image was provided for analysis."

    payload = {
        "model": VISION_MODEL,
        "prompt": prompt,
        "images": [base64_image],
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 512,
        },
    }

    try:
        resp = requests.post(OLLAMA_GENERATE_URL, json=payload, timeout=60)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("response", "").strip()
        else:
            return f"Ollama Vision API error: {resp.status_code} - {resp.text}"
    except requests.exceptions.Timeout:
        return "Vision analysis timed out. The local vision model took too long to compute."
    except Exception as e:
        return f"Error communicating with local vision model: {e}"


def see_screen(prompt: str = "Describe what is currently visible on my screen in detail.") -> str:
    """
    Takes an in-memory snapshot of the desktop screen and analyzes it using local Moondream vision.
    Used for reading error messages, inspecting code in editor, analyzing websites, or charts.
    """
    try:
        b64_img = capture_screen_base64()
        if not b64_img:
            return "The desktop screen is currently locked or the display is in sleep mode, Sir. Please wake or unlock the screen."
        analysis = analyze_image_with_ollama(b64_img, prompt=prompt)
        return analysis if analysis else "I captured your screen, but could not discern meaningful content."
    except Exception as e:
        return f"Error analyzing screen: {e}"


def see_camera(prompt: str = "Describe what you see in front of the camera in detail.") -> str:
    """
    Captures a 1-shot frame from the webcam and analyzes it using local Moondream vision.
    Used for identifying objects, reading physical documents, or checking desk items.
    """
    try:
        b64_img = capture_webcam_base64()
        if not b64_img:
            return "Could not access the webcam. Please ensure a camera is connected and not locked by another app."
        analysis = analyze_image_with_ollama(b64_img, prompt=prompt)
        return analysis if analysis else "I captured a camera frame, but could not discern the object."
    except Exception as e:
        return f"Error analyzing camera frame: {e}"


def check_desk_presence() -> dict:
    """
    Fast, 100% offline presence check using local Moondream VLM.
    Zero frames stored in storage; returns whether a user is detected in front of the workstation.
    """
    b64 = capture_webcam_base64()
    if not b64:
        return {"present": False, "reason": "Camera unavailable"}

    try:
        ans = analyze_image_with_ollama(b64, prompt="Describe any people in this image.")
        lower = ans.lower()
        has_neg = any(
            neg in lower
            for neg in [
                "no people",
                "nobody",
                "no person",
                "does not contain any people",
                "without any people",
                "devoid of any objects",
            ]
        )
        has_person = any(
            k in lower
            for k in ["man", "person", "woman", "someone", "individual", "boy", "girl", "face", "sitting", "standing"]
        )
        is_present = has_person and not has_neg

        return {
            "present": is_present,
            "description": ans,
            "timestamp": time.time(),
        }
    except Exception as e:
        return {"present": False, "error": str(e)}


if __name__ == "__main__":
    print("Testing Screen Capture...")
    scr_bytes = capture_screen_bytes()
    print(f"Captured screen bytes: {len(scr_bytes)} bytes")

    print("\nTesting Desk Presence Check...")
    pres = check_desk_presence()
    print(f"Desk presence: {pres}")

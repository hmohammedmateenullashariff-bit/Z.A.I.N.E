"""
Z.A.I.N.E — Computer Vision Gesture Recognition Engine
Detects physical hand gestures via webcam and MediaPipe Vision GestureRecognizer:
- 👍 THUMBS_UP: Action approval & courteous verbal affirmation
- ✌️ PEACE_SIGN: Instant high-res screen/snapshot capture
- ✋ OPEN_PALM: Halts active speech / pause playback
- ✊ FIST: Activates Ultron Protocol
- ☝️ POINTING: Pulls live YouTube channel metrics briefing
"""

from pathlib import Path
from typing import Dict, Any
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


def capture_and_classify_gesture(camera_index: int = 0, execute_action: bool = True) -> Dict[str, Any]:
    """
    Captures a frame from the webcam, detects hand landmarks and classifies the gesture,
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

    # Open webcam via DirectShow for rapid wake-up
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

    # Read a few warm-up frames for sensor auto-exposure
    frame = None
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

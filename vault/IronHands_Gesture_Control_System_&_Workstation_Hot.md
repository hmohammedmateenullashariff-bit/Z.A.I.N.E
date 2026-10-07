# IronHands Gesture Control System & Workstation Hotkeys

*Category: technical_architecture | Tags: ironhands, gestures, mediapipe, hotkeys, biometric_hud, swipe_controls | Added: 2026-09-13*

---

## IronHands Gesture Engine & Cybernetic HUD Control System

### 1. Architectural Foundations
Derived from the IronHands open-source repository (https://github.com/akgupta1337/IronHands), this subsystem provides real-time vision-based computer control and tactile air-gestures using MediaPipe Hands 21-landmark skeletal tracking and OpenCV.

### 2. Hand Tracking & Landmark Vectorization
- Utilizes MediaPipe Hands with max_num_hands=1, min_detection_confidence=0.7, min_tracking_confidence=0.6.
- Detects landmark indices:
  - Wrist (0)
  - Thumb: CMC (1), MCP (2), IP (3), TIP (4)
  - Index: MCP (5), PIP (6), DIP (7), TIP (8)
  - Middle: MCP (9), PIP (10), DIP (11), TIP (12)
  - Ring: MCP (13), PIP (14), DIP (15), TIP (16)
  - Pinky: MCP (17), PIP (18), DIP (19), TIP (20)
- Finger up/down binary vector [thumb, index, middle, ring, pinky]:
  - For non-thumb fingers (index, middle, ring, pinky), a finger is EXTENDED if landmark[tip].y < landmark[pip].y (in standard screen coords).
  - For thumb, extended check compares horizontal x-displacement relative to MCP.

### 3. Gesture Mapping & OS Workstation Controls
- **SWIPE LEFT**:
  - Detected when palm landmark (Wrist/MCP) executes rapid displacement dx < -0.15 within 300ms window with fingers extended or open palm.
  - OS Action: Alt + Left Arrow (`pyautogui.hotkey('alt', 'left')`).
  - Result: Browser / File Explorer / Windows Navigation BACK.
- **SWIPE RIGHT**:
  - Detected when palm executes rapid displacement dx > +0.15 within 300ms window.
  - OS Action: Alt + Tab (`pyautogui.hotkey('alt', 'tab')`).
  - Result: Windows OS Task Switcher / App Moving.
- **PINCH (INDEX TIP + THUMB TIP DISTANCE < 0.05)**:
  - Holographic File Browser: Grabs and drags file cards between directories.
- **OPEN PALM RELEASE**:
  - Drops dragged item into folder destination or clicks card to preview code.

### 4. Camera Stream Contention Architecture
- Single CameraStream background thread opens DirectShow device once.
- Face-ID and IronHands gesture control share the in-memory circular frame buffer with <1ms lock latency.
- Thread-safe, zero frame collisions.

### 5. Biometric Lock Screen Gate Protocol
- On application boot or relock, biometric lock screen renders an animated holographic radar viewfinder.
- Automated 1-shot optical facial identification triggers:
  - **Mateen Sir (Admin Recognized)**: Voice response in JARVIS (`en-GB-RyanNeural`): "Admin recognized. Privileges provided." Unlocks full administrative HUD.
  - **Unrecognized / Guest**: Voice response in ULTRON (`en-US-ChristopherNeural` pitch -24Hz): "Unknown person detected, probably a guest." Unlocks restricted guest sandbox.

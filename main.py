"""
main.py - Hand Gesture Mouse Control System
=============================================
Uses your webcam + MediaPipe HandLandmarker (Tasks API) to track
hand gestures and control your mouse, volume, brightness, and
perform OS actions.

Usage:
    python main.py

Press 'q' to quit the application.
Press 'h' to toggle the help overlay.
"""

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    HandLandmarker,
    HandLandmarkerOptions,
    HandLandmarksConnections,
    RunningMode,
)
import pyautogui
import numpy as np
import time
import sys
import os

# ─── Attempt optional imports ─────────────────────────────────────
try:
    from pynput.keyboard import Key, Controller as KeyboardController
    keyboard = KeyboardController()
    HAS_PYNPUT = True
except ImportError:
    HAS_PYNPUT = False
    print("[WARNING] pynput not installed. Keyboard shortcuts (Alt+Tab, Win+D) disabled.")

try:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    volume_control = cast(interface, POINTER(IAudioEndpointVolume))
    vol_range = volume_control.GetVolumeRange()
    VOL_MIN, VOL_MAX = vol_range[0], vol_range[1]
    HAS_VOLUME = True
except Exception as e:
    HAS_VOLUME = False
    print(f"[WARNING] pycaw not available ({e}). Volume control disabled.")

try:
    import screen_brightness_control as sbc
    HAS_BRIGHTNESS = True
except ImportError:
    HAS_BRIGHTNESS = False
    print("[WARNING] screen_brightness_control not installed. Brightness control disabled.")

import config
from gestures import Gesture, GestureRecognizer, LM


# ─── Disable PyAutoGUI fail-safe (we handle exit via 'q' key) ────
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

# ─── Hand connection pairs for drawing ───────────────────────────
# Each Connection has .start and .end (landmark indices)
HAND_CONNECTIONS = HandLandmarksConnections.HAND_CONNECTIONS


class HandGestureController:
    """
    Main controller that ties together camera capture, hand detection,
    gesture recognition, and system actions.
    """

    def __init__(self):
        # Screen dimensions
        self.screen_w, self.screen_h = pyautogui.size()

        # Resolve model path (same directory as this script)
        model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "hand_landmarker.task")
        if not os.path.exists(model_path):
            print(f"[ERROR] Model file not found: {model_path}")
            print("Download it from: https://storage.googleapis.com/mediapipe-models/"
                  "hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task")
            sys.exit(1)

        # MediaPipe HandLandmarker (Tasks API, VIDEO mode)
        options = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=RunningMode.VIDEO,
            num_hands=config.MAX_HANDS,
            min_hand_detection_confidence=config.DETECTION_CONFIDENCE,
            min_hand_presence_confidence=config.DETECTION_CONFIDENCE,
            min_tracking_confidence=config.TRACKING_CONFIDENCE,
        )
        self.hand_landmarker = HandLandmarker.create_from_options(options)

        # Gesture recognizer
        self.recognizer = GestureRecognizer(config)

        # Mouse smoothing state
        self._prev_x = 0
        self._prev_y = 0

        # UI state
        self._show_help = False
        self._current_gesture_name = "NONE"
        self._gesture_display_time = 0

        # Click state (for debounce)
        self._last_click_time = 0
        self._last_right_click_time = 0

        # FPS tracking
        self._fps_time = time.time()
        self._fps = 0

        # Desktop toggle state
        self._desktop_shown = False

        # Timestamp counter for VIDEO mode (must be monotonically increasing)
        self._timestamp_ms = 0

    # ──────────────────────────────────────────────────────────────
    # System action handlers
    # ──────────────────────────────────────────────────────────────

    def _move_cursor(self, cx, cy):
        """Move mouse cursor with smoothing."""
        fr = config.FRAME_REDUCTION
        cam_w, cam_h = config.CAMERA_WIDTH, config.CAMERA_HEIGHT

        # Normalize within reduced frame
        norm_x = (cx * cam_w - fr) / (cam_w - 2 * fr)
        norm_y = (cy * cam_h - fr) / (cam_h - 2 * fr)

        # Clamp
        norm_x = max(0, min(1, norm_x))
        norm_y = max(0, min(1, norm_y))

        # Map to screen
        target_x = norm_x * self.screen_w
        target_y = norm_y * self.screen_h

        # Apply speed multiplier
        dx = (target_x - self._prev_x) * config.MOUSE_SPEED_MULTIPLIER
        dy = (target_y - self._prev_y) * config.MOUSE_SPEED_MULTIPLIER

        # Smooth
        sf = config.SMOOTHING_FACTOR
        smooth_x = self._prev_x + dx / sf
        smooth_y = self._prev_y + dy / sf

        self._prev_x = smooth_x
        self._prev_y = smooth_y

        pyautogui.moveTo(int(smooth_x), int(smooth_y), _pause=False)

    def _left_click(self):
        """Perform a left click with cooldown."""
        now = time.time()
        if now - self._last_click_time > config.CLICK_COOLDOWN:
            self._last_click_time = now
            pyautogui.click(_pause=False)

    def _double_click(self):
        """Perform a double click."""
        pyautogui.doubleClick(_pause=False)

    def _right_click(self):
        """Perform a right click with cooldown."""
        now = time.time()
        if now - self._last_right_click_time > config.CLICK_COOLDOWN:
            self._last_right_click_time = now
            pyautogui.rightClick(_pause=False)

    def _scroll(self, direction):
        """Scroll up or down."""
        amount = config.SCROLL_SPEED if direction == 'up' else -config.SCROLL_SPEED
        pyautogui.scroll(int(amount / 10), _pause=False)

    def _zoom(self, direction):
        """Zoom in/out using Ctrl + mouse scroll."""
        amount = 3 if direction == 'in' else -3
        pyautogui.keyDown('ctrl', _pause=False)
        pyautogui.scroll(amount, _pause=False)
        pyautogui.keyUp('ctrl', _pause=False)

    def _show_desktop(self):
        """Minimize all windows (Win+D)."""
        if HAS_PYNPUT:
            keyboard.press(Key.cmd)
            keyboard.press('d')
            keyboard.release('d')
            keyboard.release(Key.cmd)
            self._desktop_shown = True

    def _restore_windows(self):
        """Restore windows (Win+D again)."""
        if HAS_PYNPUT and self._desktop_shown:
            keyboard.press(Key.cmd)
            keyboard.press('d')
            keyboard.release('d')
            keyboard.release(Key.cmd)
            self._desktop_shown = False

    def _take_screenshot(self):
        """Take a screenshot using Win+Shift+S (Snipping Tool)."""
        if HAS_PYNPUT:
            keyboard.press(Key.cmd)
            keyboard.press(Key.shift)
            keyboard.press('s')
            keyboard.release('s')
            keyboard.release(Key.shift)
            keyboard.release(Key.cmd)

    def _open_task_view(self):
        """Open Task View (Win+Tab)."""
        if HAS_PYNPUT:
            keyboard.press(Key.cmd)
            keyboard.press(Key.tab)
            keyboard.release(Key.tab)
            keyboard.release(Key.cmd)

    def _alt_tab(self):
        """Switch between windows (Alt+Tab)."""
        if HAS_PYNPUT:
            keyboard.press(Key.alt)
            keyboard.press(Key.tab)
            keyboard.release(Key.tab)
            keyboard.release(Key.alt)

    def _volume_up(self):
        """Increase system volume."""
        if HAS_VOLUME:
            current = volume_control.GetMasterVolumeLevel()
            new_vol = min(VOL_MAX, current + 2.0)
            volume_control.SetMasterVolumeLevel(new_vol, None)

    def _volume_down(self):
        """Decrease system volume."""
        if HAS_VOLUME:
            current = volume_control.GetMasterVolumeLevel()
            new_vol = max(VOL_MIN, current - 2.0)
            volume_control.SetMasterVolumeLevel(new_vol, None)

    def _brightness_up(self):
        """Increase screen brightness."""
        if HAS_BRIGHTNESS:
            try:
                current = sbc.get_brightness(display=0)[0]
                sbc.set_brightness(min(100, current + 5), display=0)
            except Exception:
                pass

    def _brightness_down(self):
        """Decrease screen brightness."""
        if HAS_BRIGHTNESS:
            try:
                current = sbc.get_brightness(display=0)[0]
                sbc.set_brightness(max(0, current - 5), display=0)
            except Exception:
                pass

    def _media_play_pause(self):
        """Toggle media play/pause."""
        if HAS_PYNPUT:
            keyboard.press(Key.media_play_pause)
            keyboard.release(Key.media_play_pause)

    # ──────────────────────────────────────────────────────────────
    # Gesture → Action dispatcher
    # ──────────────────────────────────────────────────────────────

    def _dispatch(self, gesture, meta):
        """Execute the system action corresponding to the detected gesture."""
        self._current_gesture_name = gesture.name

        if gesture == Gesture.MOVE_CURSOR:
            self._move_cursor(meta['cursor_x'], meta['cursor_y'])
        elif gesture == Gesture.LEFT_CLICK:
            self._left_click()
        elif gesture == Gesture.DOUBLE_CLICK:
            self._double_click()
        elif gesture == Gesture.RIGHT_CLICK:
            self._right_click()
        elif gesture == Gesture.SCROLL_UP:
            self._scroll('up')
        elif gesture == Gesture.SCROLL_DOWN:
            self._scroll('down')
        elif gesture == Gesture.ZOOM_IN:
            self._zoom('in')
        elif gesture == Gesture.ZOOM_OUT:
            self._zoom('out')
        elif gesture == Gesture.SHOW_DESKTOP:
            self._show_desktop()
        elif gesture == Gesture.RESTORE_WINDOWS:
            self._restore_windows()
        elif gesture == Gesture.SCREENSHOT:
            self._take_screenshot()
        elif gesture == Gesture.TASK_VIEW:
            self._open_task_view()
        elif gesture == Gesture.ALT_TAB:
            self._alt_tab()
        elif gesture == Gesture.VOLUME_UP:
            self._volume_up()
        elif gesture == Gesture.VOLUME_DOWN:
            self._volume_down()
        elif gesture == Gesture.BRIGHTNESS_UP:
            self._brightness_up()
        elif gesture == Gesture.BRIGHTNESS_DOWN:
            self._brightness_down()
        elif gesture == Gesture.MEDIA_PLAY_PAUSE:
            self._media_play_pause()

    # ──────────────────────────────────────────────────────────────
    # Drawing / UI overlay
    # ──────────────────────────────────────────────────────────────

    def _draw_hand_landmarks(self, frame, landmarks):
        """Draw hand landmarks and connections on the frame."""
        h, w, _ = frame.shape

        # Draw connections
        for connection in HAND_CONNECTIONS:
            start_lm = landmarks[connection.start]
            end_lm = landmarks[connection.end]
            x1, y1 = int(start_lm.x * w), int(start_lm.y * h)
            x2, y2 = int(end_lm.x * w), int(end_lm.y * h)
            cv2.line(frame, (x1, y1), (x2, y2), (0, 200, 100), config.OVERLAY_THICKNESS)

        # Draw landmark dots
        for i, lm in enumerate(landmarks):
            cx, cy = int(lm.x * w), int(lm.y * h)
            # Fingertips get larger dots and different color
            if i in (LM.THUMB_TIP, LM.INDEX_TIP, LM.MIDDLE_TIP, LM.RING_TIP, LM.PINKY_TIP):
                cv2.circle(frame, (cx, cy), 8, (0, 255, 255), -1)
                cv2.circle(frame, (cx, cy), 8, (0, 180, 180), 2)
            else:
                cv2.circle(frame, (cx, cy), 5, (255, 100, 100), -1)
                cv2.circle(frame, (cx, cy), 5, (200, 60, 60), 1)

    def _draw_overlay(self, frame, landmarks):
        """Draw hand landmarks, gesture label, FPS, and help overlay."""

        # Draw hand skeleton
        if config.SHOW_LANDMARKS and landmarks:
            self._draw_hand_landmarks(frame, landmarks)

        h, w, _ = frame.shape

        # Gesture label
        if config.SHOW_GESTURE_LABEL:
            label = self._current_gesture_name.replace('_', ' ')
            # Background rectangle
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)
            cv2.rectangle(frame, (10, 10), (20 + tw, 20 + th + 10), (0, 0, 0), -1)
            cv2.rectangle(frame, (10, 10), (20 + tw, 20 + th + 10), config.OVERLAY_COLOR, 2)
            cv2.putText(frame, label, (15, 15 + th),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, config.OVERLAY_COLOR, 2)

        # FPS
        if config.SHOW_FPS:
            now = time.time()
            elapsed = now - self._fps_time
            if elapsed > 0:
                self._fps = 1.0 / elapsed
            self._fps_time = now
            fps_text = f"FPS: {int(self._fps)}"
            cv2.putText(frame, fps_text, (w - 140, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        # Status bar at bottom
        status = "Press 'q' to quit  |  'h' for help"
        cv2.putText(frame, status, (10, h - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)

        # Help overlay
        if self._show_help:
            self._draw_help(frame)

    def _draw_help(self, frame):
        """Draw a semi-transparent help overlay with all gesture mappings."""
        overlay = frame.copy()
        h, w, _ = frame.shape
        cv2.rectangle(overlay, (20, 20), (w - 20, h - 20), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)

        help_lines = [
            "=== HAND GESTURE CONTROLS ===",
            "",
            "Index finger up        -> Move cursor",
            "Index touches thumb    -> Left click",
            "Quick double touch     -> Double click",
            "Peace sign (V)         -> Right click",
            "Thumb + Index pinch    -> Zoom in / out",
            "Index+Mid+Thumb up     -> Scroll (move up/down)",
            "Closed fist            -> Show Desktop (Win+D)",
            "Open palm (5 fingers)  -> Restore Windows",
            "3 fingers (I+M+R)      -> Screenshot (Win+Shift+S)",
            "4 fingers (no thumb)   -> Task View (Win+Tab)",
            "Shaka (Thumb+Pinky)    -> Alt+Tab (switch window)",
            "Thumb up only          -> Volume Up",
            "Pinky up only          -> Volume Down",
            "Thumb+Index+Mid up     -> Brightness Up",
            "Ring+Pinky up only     -> Brightness Down",
            "Open palm -> Close fist -> Play/Pause Media",
            "",
            "Press 'h' to close this help",
        ]

        y = 55
        for line in help_lines:
            color = (0, 255, 128) if '===' in line else (220, 220, 220)
            scale = 0.65 if '===' in line else 0.5
            thickness = 2 if '===' in line else 1
            cv2.putText(frame, line, (40, y),
                        cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness)
            y += 22

    # ──────────────────────────────────────────────────────────────
    # Main loop
    # ──────────────────────────────────────────────────────────────

    def run(self):
        """Start the camera feed and gesture control loop."""
        cap = cv2.VideoCapture(config.CAMERA_INDEX)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAMERA_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAMERA_HEIGHT)

        if not cap.isOpened():
            print("[ERROR] Cannot open camera. Check CAMERA_INDEX in config.py")
            sys.exit(1)

        print("+" + "=" * 52 + "+")
        print("|     Hand Gesture Mouse Control System              |")
        print("|     -----------------------------------------      |")
        print("|     Press 'q' to quit  |  'h' for help overlay     |")
        print("+" + "=" * 52 + "+")
        print()

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    print("[ERROR] Failed to read from camera.")
                    break

                # Flip horizontally for natural mirror effect
                if config.FLIP_HORIZONTAL:
                    frame = cv2.flip(frame, 1)

                # Convert BGR frame to MediaPipe Image (RGB)
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

                # Detect hand landmarks (VIDEO mode requires increasing timestamps)
                self._timestamp_ms += 33  # ~30 FPS
                result = self.hand_landmarker.detect_for_video(mp_image, self._timestamp_ms)

                landmarks = None
                if result.hand_landmarks and len(result.hand_landmarks) > 0:
                    landmarks = result.hand_landmarks[0]  # First hand
                    gesture, meta = self.recognizer.recognize(landmarks)
                    self._dispatch(gesture, meta)
                else:
                    self._current_gesture_name = "NO HAND"

                # Draw overlay
                self._draw_overlay(frame, landmarks)

                # Show frame
                cv2.imshow("Hand Gesture Control", frame)

                # Key handling
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('h'):
                    self._show_help = not self._show_help

        except KeyboardInterrupt:
            print("\n[INFO] Interrupted by user.")
        finally:
            cap.release()
            cv2.destroyAllWindows()
            self.hand_landmarker.close()
            print("[INFO] Hand Gesture Control stopped.")


# ──────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    controller = HandGestureController()
    controller.run()

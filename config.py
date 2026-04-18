"""
Configuration file for Hand Gesture Control System.
Adjust these parameters to fine-tune gesture sensitivity and behavior.
"""

# ─── Camera Settings ───────────────────────────────────────────────
CAMERA_INDEX = 0                # Camera device index (0 = default webcam)
CAMERA_WIDTH = 640              # Camera frame width
CAMERA_HEIGHT = 480             # Camera frame height
FLIP_HORIZONTAL = True          # Mirror the camera feed

# ─── MediaPipe Hand Settings ──────────────────────────────────────
MAX_HANDS = 1                   # Max number of hands to detect
DETECTION_CONFIDENCE = 0.7      # Minimum detection confidence (0.0 - 1.0)
TRACKING_CONFIDENCE = 0.7       # Minimum tracking confidence (0.0 - 1.0)

# ─── Mouse Control Settings ──────────────────────────────────────
SMOOTHING_FACTOR = 5            # Mouse movement smoothing (higher = smoother but laggier)
MOUSE_SPEED_MULTIPLIER = 1.5    # Mouse speed multiplier
FRAME_REDUCTION = 100           # Pixels to reduce from frame edges for mouse mapping zone

# ─── Gesture Thresholds ──────────────────────────────────────────
CLICK_DISTANCE_THRESHOLD = 0.04         # Distance between thumb tip & index tip for click
PINCH_DISTANCE_THRESHOLD = 0.08         # Distance for zoom pinch gesture
SCROLL_SPEED = 50                       # Scroll speed (pixels per frame)
DRAG_THRESHOLD = 0.05                   # Distance to detect drag start
FIST_THRESHOLD = 0.08                   # Max distance from fingertip to palm for fist detection
FINGER_EXTENDED_THRESHOLD = 0.15        # Min distance from tip to MCP for "finger extended"

# ─── Gesture Cooldowns (seconds) ────────────────────────────────
CLICK_COOLDOWN = 0.4                    # Cooldown between clicks
DOUBLE_CLICK_WINDOW = 0.35              # Max time window for double-click
DESKTOP_TOGGLE_COOLDOWN = 1.5           # Cooldown for show desktop / restore
SCREENSHOT_COOLDOWN = 2.0               # Cooldown for screenshot
TASK_VIEW_COOLDOWN = 1.5                # Cooldown for task view
ALT_TAB_COOLDOWN = 1.0                  # Cooldown for alt-tab switch
VOLUME_CHANGE_COOLDOWN = 0.15           # Cooldown for volume changes
BRIGHTNESS_CHANGE_COOLDOWN = 0.15       # Cooldown for brightness changes

# ─── Zoom Settings ───────────────────────────────────────────────
ZOOM_SENSITIVITY = 0.05         # How much to zoom per frame
ZOOM_MIN_DISTANCE = 0.03        # Minimum pinch distance
ZOOM_MAX_DISTANCE = 0.25        # Maximum pinch distance

# ─── Visual Overlay Settings ─────────────────────────────────────
SHOW_LANDMARKS = True           # Draw hand landmarks on camera feed
SHOW_FPS = True                 # Show FPS counter
SHOW_GESTURE_LABEL = True       # Show current detected gesture
OVERLAY_COLOR = (0, 255, 128)   # Green overlay color (BGR)
OVERLAY_THICKNESS = 2           # Line thickness for drawing
FONT_SCALE = 0.7                # Font size for text overlays

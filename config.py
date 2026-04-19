"""
Configuration file for Hand Gesture Control System.
"""

# ─── Camera ──────────────────────────────────────────────────────────
CAMERA_INDEX       = 0
CAMERA_WIDTH       = 640
CAMERA_HEIGHT      = 480
FLIP_HORIZONTAL    = True

# ─── MediaPipe ───────────────────────────────────────────────────────
MAX_HANDS            = 1
DETECTION_CONFIDENCE = 0.6
TRACKING_CONFIDENCE  = 0.6

# ─── Cursor Speed ────────────────────────────────────────────────────
# EMA alpha: 1.0 = instant/raw  |  0.0 = never moves
# 0.90 = very fast, follows finger almost 1:1 with minimal jitter
SMOOTHING_ALPHA   = 0.90
FRAME_REDUCTION   = 10      # px border crop (keep small for full-screen reach)

# ─── Gesture Thresholds ──────────────────────────────────────────────
CLICK_DISTANCE_THRESHOLD = 0.05   # Pinch distance for left-click
DOUBLE_CLICK_WINDOW      = 0.30   # Max seconds between two taps = double-click
SCROLL_SPEED             = 5      # Scroll units per trigger frame
ZOOM_DELTA_THRESHOLD     = 0.012  # Min pinch change to register zoom (avoid jitter)

# ─── Cooldowns (seconds) ─────────────────────────────────────────────
CLICK_COOLDOWN              = 0.18   # Faster click response
RIGHT_CLICK_COOLDOWN        = 0.40
DESKTOP_TOGGLE_COOLDOWN     = 2.0
SCREENSHOT_COOLDOWN         = 2.0
TASK_VIEW_COOLDOWN          = 1.5
ALT_TAB_COOLDOWN            = 1.0
VOLUME_CHANGE_COOLDOWN      = 0.12
BRIGHTNESS_CHANGE_COOLDOWN  = 0.12

# ─── Visual ──────────────────────────────────────────────────────────
SHOW_LANDMARKS     = True
SHOW_FPS           = True
SHOW_GESTURE_LABEL = True
OVERLAY_COLOR      = (0, 255, 128)
OVERLAY_THICKNESS  = 2
FONT_SCALE         = 0.7

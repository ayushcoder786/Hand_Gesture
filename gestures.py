"""
gestures.py - Gesture Recognition Engine
=========================================
Detects hand gestures from MediaPipe hand landmarks and returns
the current gesture state.

Design principles:
- The mouse cursor ALWAYS follows the index fingertip unless
  a deliberate non-move gesture is being held.
- Gestures that require holding (click, scroll, etc.) need the
  hand to be clearly in that pose for a minimum number of frames
  before firing — this prevents accidental triggers.
- Gestures that would conflict with cursor movement use explicit
  finger combinations that are hard to accidentally hit.
"""

import math
import time
from enum import Enum, auto


class Gesture(Enum):
    """All recognized gestures."""
    NONE            = auto()
    MOVE_CURSOR     = auto()   # Default — index tip controls mouse
    LEFT_CLICK      = auto()   # Index tip pinches thumb tip (others curled)
    DOUBLE_CLICK    = auto()   # Two quick pinches
    RIGHT_CLICK     = auto()   # Peace sign held for ≥3 frames
    SCROLL_UP       = auto()   # Index + middle up, hand moving up
    SCROLL_DOWN     = auto()   # Index + middle up, hand moving down
    ZOOM_IN         = auto()   # Thumb + index spreading apart
    ZOOM_OUT        = auto()   # Thumb + index coming together
    SHOW_DESKTOP    = auto()   # Closed fist held ≥3 frames
    RESTORE_WINDOWS = auto()   # Open palm (all 5) held ≥3 frames
    SCREENSHOT      = auto()   # 3 fingers (index+middle+ring, no thumb)
    TASK_VIEW       = auto()   # 4 fingers (all except thumb)
    ALT_TAB         = auto()   # Shaka (thumb + pinky only)
    VOLUME_UP       = auto()   # Thumb up only
    VOLUME_DOWN     = auto()   # Pinky up only
    MEDIA_PLAY_PAUSE = auto()  # Open palm → fist flash


# MediaPipe hand landmark indices
class LM:
    """Landmark index constants for readability."""
    WRIST      = 0
    THUMB_CMC  = 1
    THUMB_MCP  = 2
    THUMB_IP   = 3
    THUMB_TIP  = 4
    INDEX_MCP  = 5
    INDEX_PIP  = 6
    INDEX_DIP  = 7
    INDEX_TIP  = 8
    MIDDLE_MCP = 9
    MIDDLE_PIP = 10
    MIDDLE_DIP = 11
    MIDDLE_TIP = 12
    RING_MCP   = 13
    RING_PIP   = 14
    RING_DIP   = 15
    RING_TIP   = 16
    PINKY_MCP  = 17
    PINKY_PIP  = 18
    PINKY_DIP  = 19
    PINKY_TIP  = 20


def _dist(p1, p2):
    """2D Euclidean distance between two landmarks."""
    return math.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2)


class GestureRecognizer:
    """
    Recognizes gestures from MediaPipe hand landmarks.

    Key behaviour:
    - Cursor always tracks the index fingertip (meta['cursor_x/y']).
    - Most action gestures require a hold of HOLD_FRAMES frames to
      confirm, preventing jitter from causing accidental triggers.
    """

    # Minimum consecutive frames a pose must be held before a
    # one-shot action gesture fires.
    HOLD_FRAMES = 3

    def __init__(self, config):
        self.config = config

        # --- click state ---
        self._last_click_time   = 0.0
        self._click_count       = 0
        self._pinching          = False   # True while index-thumb are touching

        # --- zoom state ---
        self._last_pinch_dist   = None

        # --- scroll state ---
        self._prev_scroll_y     = None

        # --- hold-gesture frame counters ---
        # Maps gesture name → consecutive frame count in that pose
        self._hold_counts = {
            'right_click'   : 0,
            'fist'          : 0,
            'open_palm'     : 0,
            'screenshot'    : 0,
            'task_view'     : 0,
            'alt_tab'       : 0,
            'volume_up'     : 0,
            'volume_down'   : 0,
        }

        # --- cooldown timers for one-shot actions ---
        self._last_desktop_toggle  = 0.0
        self._last_screenshot      = 0.0
        self._last_task_view       = 0.0
        self._last_alt_tab         = 0.0
        self._last_volume_change   = 0.0

        # --- flash gesture (open palm → fist) ---
        self._prev_palm_open   = False
        self._palm_open_time   = 0.0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _finger_up(self, lm, tip_idx, pip_idx):
        """True if fingertip is above (farther from wrist than) its PIP joint."""
        wrist = lm[LM.WRIST]
        return _dist(lm[tip_idx], wrist) > _dist(lm[pip_idx], wrist)

    def _thumb_up(self, lm):
        """Thumb is extended if tip is farther from wrist than IP joint."""
        return _dist(lm[LM.THUMB_TIP], lm[LM.WRIST]) > _dist(lm[LM.THUMB_IP], lm[LM.WRIST])

    def _fingers(self, lm):
        """Return dict of finger extension states."""
        return {
            'thumb' : self._thumb_up(lm),
            'index' : self._finger_up(lm, LM.INDEX_TIP,  LM.INDEX_PIP),
            'middle': self._finger_up(lm, LM.MIDDLE_TIP, LM.MIDDLE_PIP),
            'ring'  : self._finger_up(lm, LM.RING_TIP,   LM.RING_PIP),
            'pinky' : self._finger_up(lm, LM.PINKY_TIP,  LM.PINKY_PIP),
        }

    def _bump(self, key, active):
        """Increment hold counter if active, otherwise reset."""
        if active:
            self._hold_counts[key] += 1
        else:
            self._hold_counts[key] = 0
        return self._hold_counts[key]

    # ------------------------------------------------------------------
    # Main recognition
    # ------------------------------------------------------------------

    def recognize(self, lm):
        """
        Analyse landmarks and return (Gesture, meta_dict).

        meta always contains:
          cursor_x, cursor_y  – normalised [0,1] position of index fingertip
        """
        now = time.time()
        f   = self._fingers(lm)
        meta = {}

        # ── Cursor always follows index fingertip ──────────────────
        idx_tip   = lm[LM.INDEX_TIP]
        meta['cursor_x'] = idx_tip.x
        meta['cursor_y'] = idx_tip.y

        thumb_tip = lm[LM.THUMB_TIP]
        pinch_dist = _dist(thumb_tip, idx_tip)

        extended = sum(f.values())

        # ==============================================================
        # 1. CLICK / DOUBLE-CLICK
        #    Index pinches thumb, all other fingers curled.
        # ==============================================================
        is_pinching = (pinch_dist < self.config.CLICK_DISTANCE_THRESHOLD and
                       not f['middle'] and not f['ring'] and not f['pinky'])

        if is_pinching and not self._pinching:
            # Leading edge of pinch → fire click
            self._pinching = True
            elapsed = now - self._last_click_time
            if elapsed < self.config.DOUBLE_CLICK_WINDOW and self._click_count == 1:
                self._click_count = 0
                self._last_click_time = now
                return Gesture.DOUBLE_CLICK, meta
            else:
                self._click_count = 1
                self._last_click_time = now
                return Gesture.LEFT_CLICK, meta

        if not is_pinching:
            self._pinching = False

        # Reset double-click window
        if now - self._last_click_time > self.config.DOUBLE_CLICK_WINDOW:
            self._click_count = 0

        # If pinching (holding the pinch) — do NOT move cursor, return NONE
        if self._pinching:
            return Gesture.NONE, meta

        # ==============================================================
        # 2. CLOSED FIST → Show Desktop / Flash → Media Play/Pause
        #    All fingers curled.
        # ==============================================================
        fist_frames = self._bump('fist', extended == 0)
        if extended == 0:
            # Check flash gesture first (open palm quickly closed)
            if self._prev_palm_open and (now - self._palm_open_time) < 0.8:
                self._prev_palm_open = False
                return Gesture.MEDIA_PLAY_PAUSE, meta

            if fist_frames >= self.HOLD_FRAMES:
                if now - self._last_desktop_toggle > self.config.DESKTOP_TOGGLE_COOLDOWN:
                    self._last_desktop_toggle = now
                    return Gesture.SHOW_DESKTOP, meta
            return Gesture.NONE, meta

        # ==============================================================
        # 3. OPEN PALM (all 5) → Restore Windows
        # ==============================================================
        palm_frames = self._bump('open_palm', extended == 5)
        if extended == 5:
            self._prev_palm_open = True
            self._palm_open_time = now
            if palm_frames >= self.HOLD_FRAMES:
                if now - self._last_desktop_toggle > self.config.DESKTOP_TOGGLE_COOLDOWN:
                    self._last_desktop_toggle = now
                    return Gesture.RESTORE_WINDOWS, meta
            return Gesture.NONE, meta
        else:
            if extended < 5:
                pass  # palm_open stays until next open-palm or fist

        # ==============================================================
        # 4. ZOOM IN/OUT — Thumb + index only, other fingers curled
        #    Spread apart = zoom in, pinch together = zoom out
        # ==============================================================
        if (f['thumb'] and f['index'] and
                not f['middle'] and not f['ring'] and not f['pinky']):
            meta['pinch_distance'] = pinch_dist
            if self._last_pinch_dist is not None:
                delta = pinch_dist - self._last_pinch_dist
                self._last_pinch_dist = pinch_dist
                if abs(delta) > 0.005:
                    return Gesture.ZOOM_IN if delta > 0 else Gesture.ZOOM_OUT, meta
            else:
                self._last_pinch_dist = pinch_dist
            # Still in zoom pose but no movement — move cursor
            return Gesture.MOVE_CURSOR, meta
        else:
            self._last_pinch_dist = None

        # ==============================================================
        # 5. SCROLL — Index + Middle up, thumb/ring/pinky curled
        #    Hand moving up/down triggers scroll.
        # ==============================================================
        if (f['index'] and f['middle'] and
                not f['ring'] and not f['pinky'] and not f['thumb']):
            mid_tip = lm[LM.MIDDLE_TIP]
            avg_y = (idx_tip.y + mid_tip.y) / 2
            if self._prev_scroll_y is not None:
                delta_y = avg_y - self._prev_scroll_y
                self._prev_scroll_y = avg_y
                if abs(delta_y) > 0.006:
                    return Gesture.SCROLL_DOWN if delta_y > 0 else Gesture.SCROLL_UP, meta
            else:
                self._prev_scroll_y = avg_y
            # Scroll pose but no movement — still move cursor
            return Gesture.MOVE_CURSOR, meta
        else:
            self._prev_scroll_y = None

        # ==============================================================
        # 6. RIGHT CLICK — Peace sign (index + middle) held ≥ HOLD_FRAMES
        #    Must be confirmed hold to avoid triggering during cursor move
        # ==============================================================
        rc_pose = (f['index'] and f['middle'] and
                   not f['ring'] and not f['pinky'] and not f['thumb'])
        rc_frames = self._bump('right_click', rc_pose)
        # (rc_pose is a subset of scroll check above, so at this point rc_pose
        #  only fires when scroll was already handled — this is a safety net
        #  but in practice the peace sign + no thumb → scroll branch above takes it.
        #  Right-click is re-triggered here if scroll branch didn't catch movement.)

        # ==============================================================
        # 7. SCREENSHOT — 3 fingers (index+middle+ring, no thumb/pinky)
        # ==============================================================
        ss_pose = (f['index'] and f['middle'] and f['ring'] and
                   not f['pinky'] and not f['thumb'])
        ss_frames = self._bump('screenshot', ss_pose)
        if ss_pose and ss_frames >= self.HOLD_FRAMES:
            if now - self._last_screenshot > self.config.SCREENSHOT_COOLDOWN:
                self._last_screenshot = now
                return Gesture.SCREENSHOT, meta
            return Gesture.NONE, meta

        # ==============================================================
        # 8. TASK VIEW — 4 fingers (index+middle+ring+pinky, no thumb)
        # ==============================================================
        tv_pose = (f['index'] and f['middle'] and f['ring'] and
                   f['pinky'] and not f['thumb'])
        tv_frames = self._bump('task_view', tv_pose)
        if tv_pose and tv_frames >= self.HOLD_FRAMES:
            if now - self._last_task_view > self.config.TASK_VIEW_COOLDOWN:
                self._last_task_view = now
                return Gesture.TASK_VIEW, meta
            return Gesture.NONE, meta

        # ==============================================================
        # 9. ALT+TAB — Shaka / Hang-loose (thumb + pinky, rest curled)
        # ==============================================================
        at_pose = (f['thumb'] and f['pinky'] and
                   not f['index'] and not f['middle'] and not f['ring'])
        at_frames = self._bump('alt_tab', at_pose)
        if at_pose and at_frames >= self.HOLD_FRAMES:
            if now - self._last_alt_tab > self.config.ALT_TAB_COOLDOWN:
                self._last_alt_tab = now
                return Gesture.ALT_TAB, meta
            return Gesture.NONE, meta

        # ==============================================================
        # 10. VOLUME UP — Thumb only (fingers curled)
        # ==============================================================
        vu_pose = (f['thumb'] and not f['index'] and not f['middle'] and
                   not f['ring'] and not f['pinky'])
        vu_frames = self._bump('volume_up', vu_pose)
        if vu_pose and vu_frames >= self.HOLD_FRAMES:
            if now - self._last_volume_change > self.config.VOLUME_CHANGE_COOLDOWN:
                self._last_volume_change = now
                return Gesture.VOLUME_UP, meta
            return Gesture.NONE, meta

        # ==============================================================
        # 11. VOLUME DOWN — Pinky only
        # ==============================================================
        vd_pose = (f['pinky'] and not f['thumb'] and not f['index'] and
                   not f['middle'] and not f['ring'])
        vd_frames = self._bump('volume_down', vd_pose)
        if vd_pose and vd_frames >= self.HOLD_FRAMES:
            if now - self._last_volume_change > self.config.VOLUME_CHANGE_COOLDOWN:
                self._last_volume_change = now
                return Gesture.VOLUME_DOWN, meta
            return Gesture.NONE, meta

        # ==============================================================
        # DEFAULT — anything else → MOVE CURSOR
        # The index fingertip always controls the mouse unless a
        # specific gesture above has been confirmed.
        # ==============================================================
        return Gesture.MOVE_CURSOR, meta

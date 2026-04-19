"""
gestures.py - Gesture Recognition Engine
=========================================

Gesture Map (non-conflicting):
  MOVE CURSOR   → Index finger pointing up (default for most poses)
  LEFT CLICK    → Index + Thumb pinch (edge-triggered, others curled)
  DOUBLE CLICK  → Two quick pinches
  RIGHT CLICK   → Middle finger only extended, hold 4 frames
  SCROLL        → Index + Middle up, NO thumb — move hand up/down
  ZOOM IN/OUT   → Thumb + Index both extended (no others), spread apart/together
  SHOW DESKTOP  → Closed fist, hold 12 frames
  RESTORE WIN   → Open palm (all 5), hold 12 frames
  SCREENSHOT    → Index + Middle + Ring (no thumb, no pinky), hold 6 frames
  TASK VIEW     → 4 fingers (index+mid+ring+pinky, no thumb), hold 6 frames
  ALT+TAB       → Shaka (thumb + pinky, rest curled), hold 4 frames
  VOLUME UP     → Thumb only, hold 4 frames
  VOLUME DOWN   → Pinky only, hold 4 frames
"""

import math
import time
from enum import Enum, auto


class Gesture(Enum):
    NONE             = auto()
    MOVE_CURSOR      = auto()
    LEFT_CLICK       = auto()
    DOUBLE_CLICK     = auto()
    RIGHT_CLICK      = auto()   # Middle finger only
    SCROLL_UP        = auto()
    SCROLL_DOWN      = auto()
    ZOOM_IN          = auto()
    ZOOM_OUT         = auto()
    SHOW_DESKTOP     = auto()
    RESTORE_WINDOWS  = auto()
    SCREENSHOT       = auto()
    TASK_VIEW        = auto()
    ALT_TAB          = auto()
    VOLUME_UP        = auto()
    VOLUME_DOWN      = auto()
    MEDIA_PLAY_PAUSE = auto()


class LM:
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
    return math.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2)


class GestureRecognizer:
    # Frames a normal gesture must be held before firing
    HOLD_FRAMES      = 4
    # Frames dangerous OS gestures (fist, open-palm) must be held
    HOLD_FRAMES_LONG = 12
    # Frames to ignore all gestures when hand first enters frame
    WARMUP_FRAMES    = 10

    def __init__(self, config):
        self.config = config

        # click
        self._last_click_time  = 0.0
        self._click_count      = 0
        self._pinching         = False

        # right-click cooldown
        self._last_right_click = 0.0

        # zoom
        self._last_pinch_dist  = None

        # scroll
        self._prev_scroll_y    = None

        # warmup
        self._warmup_counter   = 0

        # hold counters
        self._hold = {
            'right_click' : 0,
            'fist'        : 0,
            'open_palm'   : 0,
            'screenshot'  : 0,
            'task_view'   : 0,
            'alt_tab'     : 0,
            'volume_up'   : 0,
            'volume_down' : 0,
        }

        # cooldowns
        self._last_desktop  = 0.0
        self._last_ss       = 0.0
        self._last_tv       = 0.0
        self._last_at       = 0.0
        self._last_vol      = 0.0

        # flash gesture state
        self._prev_palm_open = False
        self._palm_open_time = 0.0

    # ------------------------------------------------------------------
    # Finger detection
    # ------------------------------------------------------------------

    def _finger_up(self, lm, tip, pip):
        """
        A finger is extended if its tip is significantly farther from the
        wrist than its PIP joint (10% margin removes borderline false positives).
        """
        wrist = lm[LM.WRIST]
        return _dist(lm[tip], wrist) > _dist(lm[pip], wrist) * 1.1

    def _thumb_up(self, lm):
        """Thumb extended if tip is farther from wrist than IP joint."""
        return _dist(lm[LM.THUMB_TIP], lm[LM.WRIST]) > _dist(lm[LM.THUMB_IP], lm[LM.WRIST]) * 1.05

    def _fingers(self, lm):
        return {
            'thumb' : self._thumb_up(lm),
            'index' : self._finger_up(lm, LM.INDEX_TIP,  LM.INDEX_PIP),
            'middle': self._finger_up(lm, LM.MIDDLE_TIP, LM.MIDDLE_PIP),
            'ring'  : self._finger_up(lm, LM.RING_TIP,   LM.RING_PIP),
            'pinky' : self._finger_up(lm, LM.PINKY_TIP,  LM.PINKY_PIP),
        }

    def _bump(self, key, active):
        if active:
            self._hold[key] += 1
        else:
            self._hold[key] = 0
        return self._hold[key]

    # ------------------------------------------------------------------
    # Main recognition
    # ------------------------------------------------------------------

    def recognize(self, lm):
        """Return (Gesture, meta). meta always has cursor_x, cursor_y."""
        now = time.time()
        f   = self._fingers(lm)
        meta = {}

        # Cursor tracks index fingertip every frame
        idx_tip = lm[LM.INDEX_TIP]
        meta['cursor_x'] = idx_tip.x
        meta['cursor_y'] = idx_tip.y

        thumb_tip  = lm[LM.THUMB_TIP]
        pinch_dist = _dist(thumb_tip, idx_tip)
        extended   = sum(f.values())

        # ── Warmup: ignore gestures for first N frames on hand entry ──
        self._warmup_counter += 1
        if self._warmup_counter <= self.WARMUP_FRAMES:
            return Gesture.MOVE_CURSOR, meta

        # ==============================================================
        # 1. LEFT CLICK / DOUBLE CLICK
        #    Index + Thumb pinch, all other fingers curled.
        #    Edge-triggered (fires once on contact, not held).
        # ==============================================================
        is_pinching = (
            pinch_dist < self.config.CLICK_DISTANCE_THRESHOLD and
            not f['middle'] and not f['ring'] and not f['pinky']
        )

        if is_pinching and not self._pinching:
            self._pinching = True
            elapsed = now - self._last_click_time
            if elapsed < self.config.DOUBLE_CLICK_WINDOW and self._click_count == 1:
                self._click_count      = 0
                self._last_click_time  = now
                return Gesture.DOUBLE_CLICK, meta
            else:
                self._click_count      = 1
                self._last_click_time  = now
                return Gesture.LEFT_CLICK, meta

        if not is_pinching:
            self._pinching = False

        if now - self._last_click_time > self.config.DOUBLE_CLICK_WINDOW:
            self._click_count = 0

        # While holding pinch → keep cursor still (NONE), no cursor jump
        if self._pinching:
            return Gesture.NONE, meta

        # ==============================================================
        # 2. CLOSED FIST → Show Desktop  /  flash → Media Play/Pause
        # ==============================================================
        fist_frames = self._bump('fist', extended == 0)
        if extended == 0:
            if self._prev_palm_open and (now - self._palm_open_time) < 0.8:
                self._prev_palm_open = False
                return Gesture.MEDIA_PLAY_PAUSE, meta
            if fist_frames >= self.HOLD_FRAMES_LONG:
                if now - self._last_desktop > self.config.DESKTOP_TOGGLE_COOLDOWN:
                    self._last_desktop = now
                    return Gesture.SHOW_DESKTOP, meta
            return Gesture.NONE, meta

        # ==============================================================
        # 3. OPEN PALM (all 5) → Restore Windows
        # ==============================================================
        palm_frames = self._bump('open_palm', extended == 5)
        if extended == 5:
            self._prev_palm_open = True
            self._palm_open_time = now
            if palm_frames >= self.HOLD_FRAMES_LONG:
                if now - self._last_desktop > self.config.DESKTOP_TOGGLE_COOLDOWN:
                    self._last_desktop = now
                    return Gesture.RESTORE_WINDOWS, meta
            return Gesture.MOVE_CURSOR, meta

        # ==============================================================
        # 4. RIGHT CLICK — Middle finger ONLY extended, hold HOLD_FRAMES
        #    (index/ring/pinky/thumb all down)
        #    Completely distinct from scroll — no conflict possible.
        # ==============================================================
        rc_pose = (
            f['middle'] and
            not f['index'] and not f['ring'] and
            not f['pinky'] and not f['thumb']
        )
        rc_frames = self._bump('right_click', rc_pose)
        if rc_pose and rc_frames >= self.HOLD_FRAMES:
            if now - self._last_right_click > self.config.RIGHT_CLICK_COOLDOWN:
                self._last_right_click = now
                return Gesture.RIGHT_CLICK, meta
            return Gesture.NONE, meta

        # ==============================================================
        # 5. ZOOM IN / OUT — Thumb + Index BOTH extended, no other fingers.
        #    Spread apart = zoom in, pinch together = zoom out.
        #    Only fires when pinch_dist > CLICK threshold (not a click).
        # ==============================================================
        zoom_pose = (
            f['thumb'] and f['index'] and
            not f['middle'] and not f['ring'] and not f['pinky'] and
            pinch_dist > self.config.CLICK_DISTANCE_THRESHOLD  # not a click
        )
        if zoom_pose:
            meta['pinch_distance'] = pinch_dist
            if self._last_pinch_dist is not None:
                delta = pinch_dist - self._last_pinch_dist
                self._last_pinch_dist = pinch_dist
                if abs(delta) > self.config.ZOOM_DELTA_THRESHOLD:
                    return (Gesture.ZOOM_IN if delta > 0 else Gesture.ZOOM_OUT), meta
            else:
                self._last_pinch_dist = pinch_dist
            return Gesture.MOVE_CURSOR, meta
        else:
            self._last_pinch_dist = None

        # ==============================================================
        # 6. SCROLL — Index + Middle up, NO thumb, NO ring, NO pinky.
        #    Move hand up/down while holding this pose.
        # ==============================================================
        scroll_pose = (
            f['index'] and f['middle'] and
            not f['ring'] and not f['pinky'] and not f['thumb']
        )
        if scroll_pose:
            mid_tip = lm[LM.MIDDLE_TIP]
            avg_y   = (idx_tip.y + mid_tip.y) / 2
            if self._prev_scroll_y is not None:
                delta_y = avg_y - self._prev_scroll_y
                self._prev_scroll_y = avg_y
                if abs(delta_y) > 0.006:
                    return (Gesture.SCROLL_DOWN if delta_y > 0 else Gesture.SCROLL_UP), meta
            else:
                self._prev_scroll_y = avg_y
            return Gesture.MOVE_CURSOR, meta
        else:
            self._prev_scroll_y = None

        # ==============================================================
        # 7. SCREENSHOT — Index + Middle + Ring, NO thumb, NO pinky
        #    Hold HOLD_FRAMES frames to confirm.
        # ==============================================================
        ss_pose = (
            f['index'] and f['middle'] and f['ring'] and
            not f['pinky'] and not f['thumb']
        )
        ss_frames = self._bump('screenshot', ss_pose)
        if ss_pose and ss_frames >= self.HOLD_FRAMES:
            if now - self._last_ss > self.config.SCREENSHOT_COOLDOWN:
                self._last_ss = now
                return Gesture.SCREENSHOT, meta
            return Gesture.NONE, meta

        # ==============================================================
        # 8. TASK VIEW — 4 fingers (index+middle+ring+pinky), NO thumb
        # ==============================================================
        tv_pose = (
            f['index'] and f['middle'] and f['ring'] and f['pinky'] and
            not f['thumb']
        )
        tv_frames = self._bump('task_view', tv_pose)
        if tv_pose and tv_frames >= self.HOLD_FRAMES:
            if now - self._last_tv > self.config.TASK_VIEW_COOLDOWN:
                self._last_tv = now
                return Gesture.TASK_VIEW, meta
            return Gesture.NONE, meta

        # ==============================================================
        # 9. ALT+TAB — Shaka: thumb + pinky, rest curled
        # ==============================================================
        at_pose = (
            f['thumb'] and f['pinky'] and
            not f['index'] and not f['middle'] and not f['ring']
        )
        at_frames = self._bump('alt_tab', at_pose)
        if at_pose and at_frames >= self.HOLD_FRAMES:
            if now - self._last_at > self.config.ALT_TAB_COOLDOWN:
                self._last_at = now
                return Gesture.ALT_TAB, meta
            return Gesture.NONE, meta

        # ==============================================================
        # 10. VOLUME UP — Thumb only
        # ==============================================================
        vu_pose = (
            f['thumb'] and
            not f['index'] and not f['middle'] and
            not f['ring'] and not f['pinky']
        )
        vu_frames = self._bump('volume_up', vu_pose)
        if vu_pose and vu_frames >= self.HOLD_FRAMES:
            if now - self._last_vol > self.config.VOLUME_CHANGE_COOLDOWN:
                self._last_vol = now
                return Gesture.VOLUME_UP, meta
            return Gesture.NONE, meta

        # ==============================================================
        # 11. VOLUME DOWN — Pinky only
        # ==============================================================
        vd_pose = (
            f['pinky'] and
            not f['thumb'] and not f['index'] and
            not f['middle'] and not f['ring']
        )
        vd_frames = self._bump('volume_down', vd_pose)
        if vd_pose and vd_frames >= self.HOLD_FRAMES:
            if now - self._last_vol > self.config.VOLUME_CHANGE_COOLDOWN:
                self._last_vol = now
                return Gesture.VOLUME_DOWN, meta
            return Gesture.NONE, meta

        # ==============================================================
        # DEFAULT — cursor follows finger
        # ==============================================================
        return Gesture.MOVE_CURSOR, meta

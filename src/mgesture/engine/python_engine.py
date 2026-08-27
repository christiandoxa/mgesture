from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .models import (
    Action,
    ActionBatch,
    Button,
    EngineConfig,
    GestureState,
    LandmarkFrame,
    PhysicalHand,
)

_LANDMARK_COUNT = 63
_LANDMARK_ABS_LIMIT = 2.0
_MIN_PALM_SCALE = 1e-4
_SCROLL_ENTRY_REACH = 0.85
_SCROLL_ACTIVE_REACH = 0.77
_SCROLL_RELAXED_REACH = 1.30
_SCROLL_ENTRY_STRAIGHTNESS = 0.70
_SCROLL_ACTIVE_STRAIGHTNESS = 0.60
_SCROLL_RELAXED_STRAIGHTNESS = 0.82
_SCROLL_ACTIVE_RELAXED_STRAIGHTNESS = 0.90
# ponytail: fixed normalized thresholds, calibrate per-hand geometry if camera diversity needs it


def _distance(landmarks: Sequence[float], first: int, second: int) -> float:
    a = first * 3
    b = second * 3
    return math.sqrt(
        (landmarks[a] - landmarks[b]) ** 2
        + (landmarks[a + 1] - landmarks[b + 1]) ** 2
        + (landmarks[a + 2] - landmarks[b + 2]) ** 2
    )


def _xy(landmarks: Sequence[float], index: int) -> tuple[float, float]:
    offset = index * 3
    return landmarks[offset], landmarks[offset + 1]


def _point(landmarks: Sequence[float], index: int) -> tuple[float, float, float]:
    offset = index * 3
    return landmarks[offset], landmarks[offset + 1], landmarks[offset + 2]


def _palm_scale(landmarks: Sequence[float]) -> float:
    return 0.5 * (_distance(landmarks, 0, 9) + _distance(landmarks, 5, 17))


def _palm_center(landmarks: Sequence[float]) -> tuple[float, float, float]:
    palm_points = (0, 5, 9, 13, 17)
    return (
        sum(_point(landmarks, point)[0] for point in palm_points) / len(palm_points),
        sum(_point(landmarks, point)[1] for point in palm_points) / len(palm_points),
        sum(_point(landmarks, point)[2] for point in palm_points) / len(palm_points),
    )


def _finger_geometry(
    landmarks: Sequence[float],
    tip: int,
    pip: int,
    mcp: int,
    palm_center: tuple[float, float, float],
    palm_scale: float,
) -> tuple[float, float]:
    path = _distance(landmarks, mcp, pip) + _distance(landmarks, pip, tip)
    straightness = _distance(landmarks, mcp, tip) / max(path, 1e-6)
    reach = math.dist(_point(landmarks, tip), palm_center) / max(palm_scale, 1e-6)
    return reach, straightness


def _is_extended(
    geometry: tuple[float, float],
    reach: float = _SCROLL_ENTRY_REACH,
    straightness: float = _SCROLL_ENTRY_STRAIGHTNESS,
) -> bool:
    return geometry[0] >= reach and geometry[1] >= straightness


def _is_relaxed(
    geometry: tuple[float, float],
    reach: float = _SCROLL_RELAXED_REACH,
    straightness: float = _SCROLL_RELAXED_STRAIGHTNESS,
) -> bool:
    return not (geometry[0] >= reach and geometry[1] >= straightness)


def _extension_score(geometry: tuple[float, float]) -> float:
    return min(geometry[0] / _SCROLL_ENTRY_REACH, geometry[1] / _SCROLL_ENTRY_STRAIGHTNESS)


class _LowPass:
    def __init__(self) -> None:
        self.value: float | None = None

    def reset(self) -> None:
        self.value = None

    def filter(self, value: float, alpha: float) -> float:
        if self.value is None:
            self.value = value
        else:
            self.value = alpha * value + (1.0 - alpha) * self.value
        return self.value


class OneEuroFilter:
    """Small FPS-aware adaptive filter used by both engine implementations."""

    def __init__(self, min_cutoff: float, beta: float, derivative_cutoff: float) -> None:
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.derivative_cutoff = derivative_cutoff
        self.x = _LowPass()
        self.y = _LowPass()
        self.dx = _LowPass()
        self.dy = _LowPass()
        self.last: tuple[float, float, float] | None = None

    def reset(self) -> None:
        self.x.reset()
        self.y.reset()
        self.dx.reset()
        self.dy.reset()
        self.last = None

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2.0 * math.pi * max(cutoff, 1e-6))
        return 1.0 / (1.0 + tau / max(dt, 1e-6))

    def filter(self, x: float, y: float, timestamp_s: float) -> tuple[float, float]:
        if self.last is None:
            self.last = (x, y, timestamp_s)
            return self.x.filter(x, 1.0), self.y.filter(y, 1.0)
        last_x, last_y, last_t = self.last
        if timestamp_s <= last_t:
            return (
                self.x.value if self.x.value is not None else last_x,
                self.y.value if self.y.value is not None else last_y,
            )
        dt = max(timestamp_s - last_t, 1e-4)
        raw_dx = (x - last_x) / dt
        raw_dy = (y - last_y) / dt
        dx = self.dx.filter(raw_dx, self._alpha(self.derivative_cutoff, dt))
        dy = self.dy.filter(raw_dy, self._alpha(self.derivative_cutoff, dt))
        x_cutoff = self.min_cutoff + self.beta * abs(dx)
        y_cutoff = self.min_cutoff + self.beta * abs(dy)
        filtered_x = self.x.filter(x, self._alpha(x_cutoff, dt))
        filtered_y = self.y.filter(y, self._alpha(y_cutoff, dt))
        self.last = (x, y, timestamp_s)
        return filtered_x, filtered_y


@dataclass(slots=True)
class _Measurements:
    index_pinch: float
    middle_pinch: float
    palm_x: float
    palm_y: float
    index_x: float
    index_y: float
    index_extension_score: float
    middle_extension_score: float
    ring_extension_score: float
    pinky_extension_score: float
    index_extended: bool
    middle_extended: bool
    ring_extended: bool
    pinky_extended: bool
    scroll_fingers_ready: bool
    scroll_active_fingers_ready: bool
    scroll_pinch_clear: bool
    scroll_active_pinch_clear: bool
    scroll_pose: bool
    scroll_active_pose: bool
    open_palm: bool


class PythonGestureEngine:
    name = "python"
    version = "reference-0.1"

    def __init__(self, config: EngineConfig, armed: bool = False) -> None:
        self.config = config
        self.armed = armed
        self.state = GestureState.ARMED if armed else GestureState.PAUSED
        self.filter = OneEuroFilter(
            config.filter_min_cutoff, config.filter_beta, config.filter_derivative_cutoff
        )
        self._held: Button | None = None
        self._invalid_since: float | None = None
        self._reacquire_since: float | None = None
        self._down_candidate: Button | None = None
        self._down_since: float | None = None
        self._release_since: float | None = None
        self._scroll_since: float | None = None
        self._scroll_exit_since: float | None = None
        self._scroll_anchor: tuple[float, float] | None = None
        self._scroll_delta_y = 0.0
        self._scroll_remainder = 0.0
        self._open_since: float | None = None
        self._last_toggle: float = -math.inf
        self._last_pointer: tuple[float, float] | None = None
        self._active_hand: PhysicalHand | None = None

    def _state_action(self, state: GestureState, actions: list[Action]) -> None:
        if self.state != state:
            self.state = state
            actions.append(Action.state_change(state))

    def _result(
        self, actions: list[Action], diagnostics: dict[str, object] | None = None
    ) -> ActionBatch:
        return ActionBatch(tuple(actions), self.state, self.name, diagnostics or {})

    def _release_held(self, actions: list[Action]) -> None:
        if self._held is not None:
            actions.append(Action.button_up(self._held))
            self._held = None

    def set_armed(self, armed: bool) -> ActionBatch:
        actions: list[Action] = []
        if not armed:
            self._release_held(actions)
        self.armed = armed
        self._reset_transient()
        self._active_hand = None
        self._state_action(GestureState.ARMED if armed else GestureState.PAUSED, actions)
        return self._result(actions, {"reason": "armed" if armed else "paused"})

    def reset(self, reason: str = "reset") -> ActionBatch:
        actions: list[Action] = []
        self._release_held(actions)
        self._reset_transient()
        self._active_hand = None
        self._state_action(GestureState.ARMED if self.armed else GestureState.PAUSED, actions)
        return self._result(actions, {"reason": reason})

    def _reset_transient(self) -> None:
        self.filter.reset()
        self._invalid_since = None
        self._reacquire_since = None
        self._down_candidate = None
        self._down_since = None
        self._release_since = None
        self._reset_scroll()
        self._open_since = None
        self._last_pointer = None

    def _reset_scroll(self) -> None:
        self._scroll_since = None
        self._scroll_exit_since = None
        self._scroll_anchor = None
        self._scroll_delta_y = 0.0
        self._scroll_remainder = 0.0

    @staticmethod
    def _valid_landmarks(landmarks: Sequence[float]) -> bool:
        if len(landmarks) != _LANDMARK_COUNT:
            return False
        try:
            return all(
                math.isfinite(value) and abs(value) <= _LANDMARK_ABS_LIMIT for value in landmarks
            )
        except (TypeError, ValueError, OverflowError):
            return False

    def _measure(self, landmarks: Sequence[float]) -> _Measurements:
        palm_scale = max(1e-6, _palm_scale(landmarks))
        index_pinch = _distance(landmarks, 4, 8) / palm_scale
        middle_pinch = _distance(landmarks, 4, 12) / palm_scale
        palm_points = (0, 5, 9, 13, 17)
        palm_x = sum(_xy(landmarks, point)[0] for point in palm_points) / len(palm_points)
        palm_y = sum(_xy(landmarks, point)[1] for point in palm_points) / len(palm_points)
        index_x, index_y = _xy(landmarks, 8)
        palm_center = _palm_center(landmarks)
        index_geometry = _finger_geometry(landmarks, 8, 6, 5, palm_center, palm_scale)
        middle_geometry = _finger_geometry(landmarks, 12, 10, 9, palm_center, palm_scale)
        ring_geometry = _finger_geometry(landmarks, 16, 14, 13, palm_center, palm_scale)
        pinky_geometry = _finger_geometry(landmarks, 20, 18, 17, palm_center, palm_scale)
        index_extended = _is_extended(index_geometry)
        middle_extended = _is_extended(middle_geometry)
        ring_extended = _is_extended(ring_geometry)
        pinky_extended = _is_extended(pinky_geometry)
        open_palm = index_extended and middle_extended and ring_extended and pinky_extended
        scroll_fingers_ready = (
            index_extended
            and middle_extended
            and _is_relaxed(ring_geometry)
            and _is_relaxed(pinky_geometry)
            and not open_palm
        )
        scroll_active_fingers_ready = (
            _is_extended(index_geometry, _SCROLL_ACTIVE_REACH, _SCROLL_ACTIVE_STRAIGHTNESS)
            and _is_extended(middle_geometry, _SCROLL_ACTIVE_REACH, _SCROLL_ACTIVE_STRAIGHTNESS)
            and _is_relaxed(
                ring_geometry, _SCROLL_RELAXED_REACH, _SCROLL_ACTIVE_RELAXED_STRAIGHTNESS
            )
            and _is_relaxed(
                pinky_geometry, _SCROLL_RELAXED_REACH, _SCROLL_ACTIVE_RELAXED_STRAIGHTNESS
            )
            and not open_palm
        )
        # A neutral thumb between down and release is not an active pinch; click
        # arbitration still runs first and therefore retains precedence.
        scroll_pinch_clear = (
            index_pinch > self.config.pinch_down_threshold
            and middle_pinch > self.config.pinch_down_threshold
        )
        scroll_active_pinch_clear = (
            index_pinch > self.config.pinch_down_threshold
            and middle_pinch > self.config.pinch_down_threshold
        )
        scroll_pose = scroll_fingers_ready and scroll_pinch_clear
        scroll_active_pose = scroll_active_fingers_ready and scroll_active_pinch_clear
        return _Measurements(
            index_pinch,
            middle_pinch,
            palm_x,
            palm_y,
            index_x,
            index_y,
            _extension_score(index_geometry),
            _extension_score(middle_geometry),
            _extension_score(ring_geometry),
            _extension_score(pinky_geometry),
            index_extended,
            middle_extended,
            ring_extended,
            pinky_extended,
            scroll_fingers_ready,
            scroll_active_fingers_ready,
            scroll_pinch_clear,
            scroll_active_pinch_clear,
            scroll_pose,
            scroll_active_pose,
            open_palm,
        )

    def observe(self, landmarks: Sequence[float]) -> dict[str, object]:
        """Return gesture measurements without changing engine state or emitting actions."""
        measurements = self._measure(landmarks)
        return {
            "index_pinch": measurements.index_pinch,
            "middle_pinch": measurements.middle_pinch,
            "palm_x": measurements.palm_x,
            "palm_y": measurements.palm_y,
            "index_x": measurements.index_x,
            "index_y": measurements.index_y,
            "index_extension_score": measurements.index_extension_score,
            "middle_extension_score": measurements.middle_extension_score,
            "ring_extension_score": measurements.ring_extension_score,
            "pinky_extension_score": measurements.pinky_extension_score,
            "index_extended": measurements.index_extended,
            "middle_extended": measurements.middle_extended,
            "ring_extended": measurements.ring_extended,
            "pinky_extended": measurements.pinky_extended,
            "no_active_pinch": measurements.scroll_active_pinch_clear,
            "scroll_block_reason": self._scroll_block_reason(measurements),
            "scroll_fingers_ready": measurements.scroll_fingers_ready,
            "scroll_active_fingers_ready": measurements.scroll_active_fingers_ready,
            "scroll_pinch_clear": measurements.scroll_pinch_clear,
            "scroll_active_pinch_clear": measurements.scroll_active_pinch_clear,
            "scroll_pose": measurements.scroll_pose,
            "scroll_active_pose": measurements.scroll_active_pose,
            "open_palm": measurements.open_palm,
        }

    def _open_palm_toggle(
        self, measurements: _Measurements, now: float, actions: list[Action]
    ) -> bool:
        if not self.config.activation_gesture:
            return False
        if not measurements.open_palm:
            self._open_since = None
            return False
        if self._open_since is None:
            self._open_since = now
            return False
        if now - self._open_since < self.config.activation_gesture_ms / 1000.0:
            return False
        if now - self._last_toggle < self.config.activation_cooldown_ms / 1000.0:
            return False
        self._last_toggle = now
        self._open_since = None
        self.armed = not self.armed
        if not self.armed:
            self._release_held(actions)
        self._reset_transient()
        self._state_action(GestureState.ARMED if self.armed else GestureState.PAUSED, actions)
        return True

    def _stable_press(self, button: Button, pressed: bool, now: float) -> bool:
        if not pressed:
            if self._down_candidate == button:
                self._down_candidate = None
                self._down_since = None
            return False
        if self._down_candidate != button:
            self._down_candidate = button
            self._down_since = now
            return self.config.debounce_ms <= 0
        return (
            self._down_since is not None
            and now - self._down_since >= self.config.debounce_ms / 1000.0
        )

    def _released(self, pressed: bool, now: float) -> bool:
        if pressed:
            self._release_since = None
            return False
        if self._release_since is None:
            self._release_since = now
            return self.config.release_debounce_ms <= 0
        return now - self._release_since >= self.config.release_debounce_ms / 1000.0

    def _pointer(self, measurements: _Measurements, timestamp_s: float) -> Action | None:
        filtered_x, filtered_y = self.filter.filter(
            measurements.index_x, measurements.index_y, timestamp_s
        )
        if self._last_pointer is not None:
            last_x, last_y = self._last_pointer
            if math.hypot(filtered_x - last_x, filtered_y - last_y) <= self.config.dead_zone:
                return None
        self._last_pointer = (filtered_x, filtered_y)
        x = (filtered_x - self.config.active_left) / max(
            1e-6, 1.0 - self.config.active_left - self.config.active_right
        )
        y = (filtered_y - self.config.active_top) / max(
            1e-6, 1.0 - self.config.active_top - self.config.active_bottom
        )
        if self.config.mirror:
            x = 1.0 - x
        gain = max(0.1, self.config.pointer_gain)
        x = 0.5 + (x - 0.5) * gain
        y = 0.5 + (y - 0.5) * gain
        x = min(1.0, max(0.0, x))
        y = min(1.0, max(0.0, y))
        return Action.move_absolute(
            self.config.screen_x + x * max(1, self.config.screen_width - 1),
            self.config.screen_y + y * max(1, self.config.screen_height - 1),
        )

    def _scroll(self, measurements: _Measurements, actions: list[Action]) -> None:
        current = (measurements.palm_x, measurements.palm_y)
        if self._scroll_anchor is None:
            self._scroll_anchor = current
            return
        _, last_y = self._scroll_anchor
        dy = current[1] - last_y
        self._scroll_delta_y = dy
        if abs(dy) <= self.config.scroll_dead_zone:
            return
        direction = 1.0 if dy > 0.0 else -1.0
        effective_dy = dy - direction * self.config.scroll_dead_zone
        self._scroll_anchor = (current[0], current[1] - direction * self.config.scroll_dead_zone)
        self._scroll_remainder += (
            -effective_dy * self.config.scroll_sensitivity * self.config.scroll_direction
        )
        steps = math.trunc(self._scroll_remainder)
        if steps:
            self._scroll_remainder -= steps
            actions.append(Action.scroll(0.0, float(steps)))

    @staticmethod
    def _scroll_block_reason(measurements: _Measurements) -> str:
        if not measurements.index_extended:
            return "index_not_extended"
        if not measurements.middle_extended:
            return "middle_not_extended"
        if measurements.ring_extended:
            return "ring_too_extended"
        if measurements.pinky_extended:
            return "pinky_too_extended"
        if not measurements.scroll_pinch_clear:
            return "pinch_conflict"
        return "ready"

    def _scroll_entry_progress(self, now: float) -> float:
        if self.state is GestureState.SCROLL:
            return 1.0
        if self._scroll_since is None:
            return 0.0
        duration = self.config.scroll_entry_ms / 1000.0
        return 1.0 if duration <= 0.0 else min(1.0, max(0.0, (now - self._scroll_since) / duration))

    def _finish_scroll(self, actions: list[Action]) -> None:
        self._reset_scroll()
        self.filter.reset()
        self._last_pointer = None
        self._state_action(GestureState.ARMED, actions)

    def process(self, frame: LandmarkFrame) -> ActionBatch:
        now = frame.timestamp_ms / 1000.0
        actions: list[Action] = []
        physical_hand = frame.physical_hand
        try:
            valid = (
                self.config.hand_selection.accepts(physical_hand)
                and math.isfinite(frame.handedness_confidence)
                and 0.0 <= frame.handedness_confidence <= 1.0
                and self._valid_landmarks(frame.landmarks)
            )
        except (TypeError, ValueError, OverflowError):
            valid = False
        if valid:
            try:
                palm_scale = _palm_scale(frame.landmarks)
                valid = math.isfinite(palm_scale) and palm_scale > _MIN_PALM_SCALE
            except (TypeError, ValueError, OverflowError):
                valid = False
        if not valid:
            if self._invalid_since is None:
                if self.state is not GestureState.SCROLL:
                    self._reset_transient()
                self._invalid_since = now
            if self.state is GestureState.SCROLL:
                if self._scroll_exit_since is None:
                    self._scroll_exit_since = now
                    self._scroll_anchor = None
                if now - self._scroll_exit_since >= self.config.scroll_exit_grace_ms / 1000.0:
                    self._finish_scroll(actions)
            if now - self._invalid_since >= self.config.hand_loss_timeout_ms / 1000.0:
                self._release_held(actions)
                self._reset_transient()
                self._active_hand = None
                self._state_action(
                    GestureState.ARMED if self.armed else GestureState.PAUSED, actions
                )
            return self._result(
                actions,
                {
                    "valid_hand": False,
                    "hand_loss": True,
                    "scroll_fingers_ready": False,
                    "scroll_active_fingers_ready": False,
                    "scroll_pinch_clear": False,
                    "scroll_active_pinch_clear": False,
                    "scroll_pose": False,
                    "scroll_active_pose": False,
                    "scroll_active": self.state is GestureState.SCROLL,
                    "scroll_entry_progress": self._scroll_entry_progress(now),
                    "scroll_exit_grace": self._scroll_exit_since is not None,
                    "scroll_delta_y": self._scroll_delta_y,
                    "scroll_remainder": self._scroll_remainder,
                    "scroll_block_reason": "hand_loss",
                },
            )

        if self._active_hand is not None and physical_hand is not self._active_hand:
            self._release_held(actions)
            self._reset_transient()
            self._active_hand = physical_hand
            self._state_action(GestureState.ARMED if self.armed else GestureState.PAUSED, actions)
            return self._result(
                actions,
                {
                    "valid_hand": True,
                    "hand_switched": True,
                    "hand": str(frame.handedness),
                    "hand_selection": self.config.hand_selection.value,
                },
            )

        self._active_hand = physical_hand
        self._invalid_since = None
        if self._reacquire_since is None:
            self._reacquire_since = now
            self.filter.reset()
        measurements = self._measure(frame.landmarks)
        if self._open_palm_toggle(measurements, now, actions):
            return self._result(actions, {"valid_hand": True, "reacquiring": False})
        reacquiring = now - self._reacquire_since < self.config.reacquisition_ms / 1000.0
        diagnostics: dict[str, object] = {
            "valid_hand": True,
            "hand": str(frame.handedness),
            "hand_selection": self.config.hand_selection.value,
            "reacquiring": reacquiring,
            "index_pinch": measurements.index_pinch,
            "middle_pinch": measurements.middle_pinch,
            "index_extension_score": measurements.index_extension_score,
            "middle_extension_score": measurements.middle_extension_score,
            "ring_extension_score": measurements.ring_extension_score,
            "pinky_extension_score": measurements.pinky_extension_score,
            "index_extended": measurements.index_extended,
            "middle_extended": measurements.middle_extended,
            "ring_extended": measurements.ring_extended,
            "pinky_extended": measurements.pinky_extended,
            "no_active_pinch": measurements.scroll_active_pinch_clear,
            "scroll_fingers_ready": measurements.scroll_fingers_ready,
            "scroll_active_fingers_ready": measurements.scroll_active_fingers_ready,
            "scroll_pinch_clear": measurements.scroll_pinch_clear,
            "scroll_active_pinch_clear": measurements.scroll_active_pinch_clear,
            "scroll_pose": measurements.scroll_pose,
            "scroll_active_pose": measurements.scroll_active_pose,
            "scroll_active": self.state is GestureState.SCROLL,
            "scroll_entry_progress": self._scroll_entry_progress(now),
            "scroll_exit_grace": self._scroll_exit_since is not None,
            "palm_y": measurements.palm_y,
            "scroll_delta_y": self._scroll_delta_y,
            "scroll_remainder": self._scroll_remainder,
            "scroll_block_reason": self._scroll_block_reason(measurements),
            "engine": self.name,
        }
        if not self.armed or reacquiring:
            return self._result(actions, diagnostics)

        left_pinch = measurements.index_pinch <= self.config.pinch_down_threshold
        right_pinch = measurements.middle_pinch <= self.config.pinch_down_threshold
        left_release = measurements.index_pinch <= self.config.pinch_release_threshold
        right_release = measurements.middle_pinch <= self.config.pinch_release_threshold

        if self._held is not None:
            held = self._held
            still_pressed = left_release if held is Button.LEFT else right_release
            if self._released(still_pressed, now):
                self._release_held(actions)
                self._reset_transient()
                self._state_action(GestureState.ARMED, actions)
            else:
                self._state_action(
                    GestureState.LEFT_DOWN if held is Button.LEFT else GestureState.RIGHT_DOWN,
                    actions,
                )
                pointer = self._pointer(measurements, now)
                if pointer is not None:
                    actions.append(pointer)
            return self._result(actions, diagnostics)

        # Right pinch wins frames where both down thresholds are active.
        if self._stable_press(Button.RIGHT, right_pinch, now):
            self._held = Button.RIGHT
            self._down_candidate = None
            self._down_since = None
            self._state_action(GestureState.RIGHT_DOWN, actions)
            actions.append(Action.button_down(Button.RIGHT))
            return self._result(actions, diagnostics)
        if self._stable_press(Button.LEFT, left_pinch and not right_pinch, now):
            self._held = Button.LEFT
            self._down_candidate = None
            self._down_since = None
            self._state_action(GestureState.LEFT_DOWN, actions)
            actions.append(Action.button_down(Button.LEFT))
            return self._result(actions, diagnostics)

        if self.state is GestureState.SCROLL:
            if measurements.scroll_active_pose:
                if self._scroll_exit_since is not None:
                    self._scroll_exit_since = None
                    self._scroll_anchor = (measurements.palm_x, measurements.palm_y)
                self._scroll(measurements, actions)
                diagnostics["scroll_active"] = True
                diagnostics["scroll_exit_grace"] = False
                diagnostics["scroll_entry_progress"] = 1.0
                return self._result(actions, diagnostics)
            if self._scroll_exit_since is None:
                self._scroll_exit_since = now
                self._scroll_anchor = None
            if now - self._scroll_exit_since < self.config.scroll_exit_grace_ms / 1000.0:
                diagnostics["scroll_active"] = True
                diagnostics["scroll_exit_grace"] = True
                diagnostics["scroll_entry_progress"] = 1.0
                return self._result(actions, diagnostics)
            self._finish_scroll(actions)
            diagnostics["scroll_active"] = False
            diagnostics["scroll_exit_grace"] = False
            diagnostics["scroll_entry_progress"] = 0.0
        elif measurements.scroll_pose:
            if self._scroll_since is None:
                self._scroll_since = now
            if now - self._scroll_since >= self.config.scroll_entry_ms / 1000.0:
                self._state_action(GestureState.SCROLL, actions)
                self._scroll_anchor = (measurements.palm_x, measurements.palm_y)
                self._scroll_exit_since = None
                self.filter.reset()
                self._last_pointer = None
                self._scroll(measurements, actions)
                diagnostics["scroll_active"] = True
                diagnostics["scroll_entry_progress"] = 1.0
                return self._result(actions, diagnostics)
            diagnostics["scroll_entry_progress"] = self._scroll_entry_progress(now)
            return self._result(actions, diagnostics)
        else:
            self._reset_scroll()
            diagnostics["scroll_active"] = False
            diagnostics["scroll_entry_progress"] = 0.0
            diagnostics["scroll_exit_grace"] = False
            diagnostics["scroll_delta_y"] = 0.0
            diagnostics["scroll_remainder"] = 0.0

        pointer = self._pointer(measurements, now)
        if pointer is not None:
            actions.append(pointer)
        return self._result(actions, diagnostics)

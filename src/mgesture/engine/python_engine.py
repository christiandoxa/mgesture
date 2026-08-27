from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .models import Action, ActionBatch, Button, EngineConfig, GestureState, LandmarkFrame


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
    scroll_pose: bool
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
        self._scroll_last: tuple[float, float] | None = None
        self._scroll_remainder = 0.0
        self._open_since: float | None = None
        self._last_toggle: float = -math.inf
        self._last_pointer: tuple[float, float] | None = None

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
        self._state_action(GestureState.ARMED if armed else GestureState.PAUSED, actions)
        return self._result(actions, {"reason": "armed" if armed else "paused"})

    def reset(self, reason: str = "reset") -> ActionBatch:
        actions: list[Action] = []
        self._release_held(actions)
        self._reset_transient()
        self._state_action(GestureState.ARMED if self.armed else GestureState.PAUSED, actions)
        return self._result(actions, {"reason": reason})

    def _reset_transient(self) -> None:
        self.filter.reset()
        self._invalid_since = None
        self._reacquire_since = None
        self._down_candidate = None
        self._down_since = None
        self._release_since = None
        self._scroll_since = None
        self._scroll_last = None
        self._scroll_remainder = 0.0
        self._open_since = None
        self._last_pointer = None

    def _measure(self, landmarks: Sequence[float]) -> _Measurements:
        palm_scale = max(
            1e-6,
            0.5 * (_distance(landmarks, 0, 9) + _distance(landmarks, 5, 17)),
        )
        index_pinch = _distance(landmarks, 4, 8) / palm_scale
        middle_pinch = _distance(landmarks, 4, 12) / palm_scale
        palm_points = (0, 5, 9, 13, 17)
        palm_x = sum(_xy(landmarks, point)[0] for point in palm_points) / len(palm_points)
        palm_y = sum(_xy(landmarks, point)[1] for point in palm_points) / len(palm_points)
        index_x, index_y = _xy(landmarks, 8)
        index_extended = self._finger_extended(landmarks, 8, 6, 5)
        middle_extended = self._finger_extended(landmarks, 12, 10, 9)
        ring_extended = self._finger_extended(landmarks, 16, 14, 13)
        pinky_extended = self._finger_extended(landmarks, 20, 18, 17)
        scroll_pose = (
            index_extended and middle_extended and not ring_extended and not pinky_extended
        )
        open_palm = index_extended and middle_extended and ring_extended and pinky_extended
        return _Measurements(
            index_pinch,
            middle_pinch,
            palm_x,
            palm_y,
            index_x,
            index_y,
            scroll_pose and middle_pinch > self.config.pinch_release_threshold,
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
            "scroll_pose": measurements.scroll_pose,
            "open_palm": measurements.open_palm,
        }

    @staticmethod
    def _finger_extended(landmarks: Sequence[float], tip: int, pip: int, mcp: int) -> bool:
        # Image-space y is not used: distance ratio survives mirrored input and small rotations.
        tip_to_mcp = _distance(landmarks, tip, mcp)
        pip_to_mcp = _distance(landmarks, pip, mcp)
        return tip_to_mcp > pip_to_mcp * 1.25

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
            return False
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
            return False
        return now - self._release_since >= self.config.release_debounce_ms / 1000.0

    def _pointer(self, measurements: _Measurements, timestamp_s: float) -> Action | None:
        filtered_x, filtered_y = self.filter.filter(
            measurements.index_x, measurements.index_y, timestamp_s
        )
        if self._last_pointer is not None:
            last_x, last_y = self._last_pointer
            if math.hypot(filtered_x - last_x, filtered_y - last_y) < self.config.dead_zone:
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
        if self._scroll_last is None:
            self._scroll_last = current
            return
        _, last_y = self._scroll_last
        dy = current[1] - last_y
        self._scroll_last = current
        if abs(dy) < self.config.scroll_dead_zone:
            return
        self._scroll_remainder += (
            -dy * self.config.scroll_sensitivity * self.config.scroll_direction
        )
        steps = math.trunc(self._scroll_remainder)
        if steps:
            self._scroll_remainder -= steps
            actions.append(Action.scroll(0.0, float(steps)))

    def process(self, frame: LandmarkFrame) -> ActionBatch:
        now = frame.timestamp_ms / 1000.0
        actions: list[Action] = []
        valid = (
            frame.handedness.lower() == "right"
            and frame.handedness_confidence >= self.config.handedness_confidence
        )
        if not valid:
            if self._invalid_since is None:
                self._invalid_since = now
            if now - self._invalid_since >= self.config.hand_loss_timeout_ms / 1000.0:
                self._release_held(actions)
                self._reset_transient()
                self._state_action(
                    GestureState.ARMED if self.armed else GestureState.PAUSED, actions
                )
            return self._result(
                actions, {"valid_hand": False, "hand_loss": self._invalid_since is not None}
            )

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
            "reacquiring": reacquiring,
            "index_pinch": measurements.index_pinch,
            "middle_pinch": measurements.middle_pinch,
            "scroll_pose": measurements.scroll_pose,
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

        # Priority: right pinch, then left pinch, then scroll, then movement.
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

        if measurements.scroll_pose:
            if self._scroll_since is None:
                self._scroll_since = now
            if now - self._scroll_since >= self.config.scroll_entry_ms / 1000.0:
                if self.state != GestureState.SCROLL:
                    self._state_action(GestureState.SCROLL, actions)
                    self._scroll_last = (measurements.palm_x, measurements.palm_y)
                self._scroll(measurements, actions)
                return self._result(actions, diagnostics)
        else:
            self._scroll_since = None
            self._scroll_last = None
            self._scroll_remainder = 0.0
            if self.state is GestureState.SCROLL:
                self._state_action(GestureState.ARMED, actions)

        pointer = self._pointer(measurements, now)
        if pointer is not None:
            actions.append(pointer)
        return self._result(actions, diagnostics)

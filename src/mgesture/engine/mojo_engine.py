from __future__ import annotations

import ctypes
import sys
from array import array
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import (
    Action,
    ActionBatch,
    ActionType,
    Button,
    EngineConfig,
    GestureState,
    LandmarkFrame,
)

MOJO_ABI_VERSION = 1
_LANDMARK_COUNT = 63
_ACTION_NONE = 0
_ACTION_MOVE = 1
_ACTION_BUTTON_DOWN = 2
_ACTION_BUTTON_UP = 3
_ACTION_SCROLL = 4
_STATE_NAMES = {
    0: GestureState.PAUSED,
    1: GestureState.ARMED,
    2: GestureState.LEFT_DOWN,
    3: GestureState.RIGHT_DOWN,
    4: GestureState.SCROLL,
}


class _NativeConfig(ctypes.Structure):
    _fields_ = [
        ("screen_x", ctypes.c_double),
        ("screen_y", ctypes.c_double),
        ("screen_width", ctypes.c_double),
        ("screen_height", ctypes.c_double),
        ("mirror", ctypes.c_int32),
        ("handedness_confidence", ctypes.c_double),
        ("active_left", ctypes.c_double),
        ("active_right", ctypes.c_double),
        ("active_top", ctypes.c_double),
        ("active_bottom", ctypes.c_double),
        ("pointer_gain", ctypes.c_double),
        ("pointer_acceleration", ctypes.c_double),
        ("dead_zone", ctypes.c_double),
        ("filter_min_cutoff", ctypes.c_double),
        ("filter_beta", ctypes.c_double),
        ("filter_derivative_cutoff", ctypes.c_double),
        ("pinch_down_threshold", ctypes.c_double),
        ("pinch_release_threshold", ctypes.c_double),
        ("debounce_ms", ctypes.c_int64),
        ("release_debounce_ms", ctypes.c_int64),
        ("hand_loss_timeout_ms", ctypes.c_int64),
        ("reacquisition_ms", ctypes.c_int64),
        ("scroll_entry_ms", ctypes.c_int64),
        ("scroll_sensitivity", ctypes.c_double),
        ("scroll_direction", ctypes.c_int32),
        ("scroll_dead_zone", ctypes.c_double),
        ("activation_gesture", ctypes.c_int32),
        ("activation_gesture_ms", ctypes.c_int64),
        ("activation_cooldown_ms", ctypes.c_int64),
    ]


class _NativeAction(ctypes.Structure):
    _fields_ = [
        ("action", ctypes.c_int32),
        ("state", ctypes.c_int32),
        ("button", ctypes.c_int32),
        ("state_order", ctypes.c_int32),
        ("x", ctypes.c_double),
        ("y", ctypes.c_double),
    ]


def native_library_name(os_name: str | None = None) -> str:
    value = os_name or sys.platform
    if value in ("windows", "win32"):
        return "mgesture_mojo.dll"
    if value in ("macos", "darwin"):
        return "libmgesture_mojo.dylib"
    return "libmgesture_mojo.so"


class NativeMojoGestureEngine:
    """Persistent ctypes boundary for a compiler-free native Mojo engine."""

    name = "mojo"
    version = "mojo-abi-1"

    def __init__(
        self, library_path: Path, config: EngineConfig, armed: bool = False, target: str = ""
    ) -> None:
        self._library_path = library_path
        self._library = ctypes.CDLL(str(library_path))
        self._abi_version = self._function("mgesture_mojo_abi_version", ctypes.c_int32, [])
        if self._abi_version() != MOJO_ABI_VERSION:
            raise RuntimeError(f"unsupported Mojo ABI in {library_path.name}")
        config_size = self._function("mgesture_mojo_config_size", ctypes.c_int64, [])()
        action_size = self._function("mgesture_mojo_action_size", ctypes.c_int64, [])()
        if config_size != ctypes.sizeof(_NativeConfig):
            raise RuntimeError("native Mojo config ABI layout mismatch")
        if action_size != ctypes.sizeof(_NativeAction):
            raise RuntimeError("native Mojo action ABI layout mismatch")
        self._engine_size = int(self._function("mgesture_mojo_engine_size", ctypes.c_int64, [])())
        self._engine_alignment = int(
            self._function("mgesture_mojo_engine_alignment", ctypes.c_int64, [])()
        )
        if self._engine_size <= 0 or self._engine_alignment <= 0:
            raise RuntimeError("native Mojo engine reported invalid state layout")
        self._raw_state = ctypes.create_string_buffer(
            self._engine_size + self._engine_alignment - 1
        )
        base = ctypes.addressof(self._raw_state)
        aligned = (base + self._engine_alignment - 1) & ~(self._engine_alignment - 1)
        self._state = ctypes.c_void_p(aligned)
        self._config = _NativeConfig(
            float(config.screen_x),
            float(config.screen_y),
            float(config.screen_width),
            float(config.screen_height),
            int(config.mirror),
            config.handedness_confidence,
            config.active_left,
            config.active_right,
            config.active_top,
            config.active_bottom,
            config.pointer_gain,
            config.pointer_acceleration,
            config.dead_zone,
            config.filter_min_cutoff,
            config.filter_beta,
            config.filter_derivative_cutoff,
            config.pinch_down_threshold,
            config.pinch_release_threshold,
            config.debounce_ms,
            config.release_debounce_ms,
            config.hand_loss_timeout_ms,
            config.reacquisition_ms,
            config.scroll_entry_ms,
            config.scroll_sensitivity,
            config.scroll_direction,
            config.scroll_dead_zone,
            int(config.activation_gesture),
            config.activation_gesture_ms,
            config.activation_cooldown_ms,
        )
        self._output = _NativeAction()
        self._init = self._function(
            "mgesture_mojo_engine_init",
            ctypes.c_int32,
            [ctypes.c_void_p, ctypes.POINTER(_NativeConfig), ctypes.c_int32],
        )
        self._process = self._function(
            "mgesture_mojo_engine_process",
            ctypes.c_int32,
            [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_float),
                ctypes.c_int64,
                ctypes.c_int32,
                ctypes.c_double,
                ctypes.POINTER(_NativeAction),
            ],
        )
        self._reset = self._function(
            "mgesture_mojo_engine_reset",
            ctypes.c_int32,
            [ctypes.c_void_p, ctypes.POINTER(_NativeAction)],
        )
        self._set_armed = self._function(
            "mgesture_mojo_engine_set_armed",
            ctypes.c_int32,
            [ctypes.c_void_p, ctypes.c_int32, ctypes.POINTER(_NativeAction)],
        )
        self._destroy = self._function(
            "mgesture_mojo_engine_destroy", ctypes.c_int32, [ctypes.c_void_p]
        )
        self._target = target
        self.armed = armed
        self._state_value = GestureState.ARMED if armed else GestureState.PAUSED
        self._closed = False
        self._check_status(self._init(self._state, ctypes.byref(self._config), int(armed)), "init")

    def _function(self, name: str, restype: Any, argtypes: list[Any]) -> Any:
        function = getattr(self._library, name)
        function.restype = restype
        function.argtypes = argtypes
        return function

    @staticmethod
    def _check_status(status: int, operation: str) -> None:
        if status != 0:
            raise RuntimeError(f"native Mojo {operation} failed with status {status}")

    def _actions(self) -> tuple[Action, ...]:
        try:
            state = _STATE_NAMES[self._output.state]
        except KeyError as exc:
            raise RuntimeError("native Mojo returned an unknown gesture state") from exc
        actions: list[Action] = []
        state_changed = state != self._state_value
        if state_changed and self._output.state_order == 0:
            actions.append(Action.state_change(state))
        if self._output.action == _ACTION_MOVE:
            actions.append(Action.move_absolute(self._output.x, self._output.y))
        elif self._output.action in (_ACTION_BUTTON_DOWN, _ACTION_BUTTON_UP):
            button = {1: Button.LEFT, 2: Button.RIGHT}.get(self._output.button)
            if button is None:
                raise RuntimeError("native Mojo returned an unknown mouse button")
            if self._output.action == _ACTION_BUTTON_DOWN:
                actions.append(Action.button_down(button))
            else:
                actions.append(Action.button_up(button))
        elif self._output.action == _ACTION_SCROLL:
            actions.append(Action.scroll(0.0, self._output.y))
        elif self._output.action != _ACTION_NONE:
            raise RuntimeError("native Mojo returned an unknown action")
        if state_changed and self._output.state_order == 1:
            actions.append(Action.state_change(state))
        self._state_value = state
        return tuple(actions)

    def _batch(self, operation: str) -> ActionBatch:
        actions = self._actions()
        return ActionBatch(
            actions,
            self._state_value,
            self.name,
            {
                "engine": self.name,
                "native": True,
                "abi_version": MOJO_ABI_VERSION,
                "target": self._target,
                "library": self._library_path.name,
                "state_order": int(self._output.state_order),
                "operation": operation,
            },
        )

    def process(self, frame: LandmarkFrame) -> ActionBatch:
        values = (ctypes.c_float * _LANDMARK_COUNT)(*map(float, frame.landmarks))
        self._check_status(
            self._process(
                self._state,
                values,
                frame.timestamp_ms,
                int(frame.handedness.lower() == "right"),
                frame.handedness_confidence,
                ctypes.byref(self._output),
            ),
            "process",
        )
        return self._batch("process")

    def reset(self, reason: str = "reset") -> ActionBatch:
        del reason
        self._check_status(self._reset(self._state, ctypes.byref(self._output)), "reset")
        return self._batch("reset")

    def set_armed(self, armed: bool) -> ActionBatch:
        self.armed = armed
        self._check_status(
            self._set_armed(self._state, int(armed), ctypes.byref(self._output)), "set_armed"
        )
        return self._batch("set_armed")

    def close(self) -> None:
        if not self._closed:
            self._check_status(self._destroy(self._state), "destroy")
            self._closed = True

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


class MojoGestureEngine:
    """Small Python boundary around one persistent Mojo stateful engine."""

    name = "mojo"
    version = "mojo-1.0.0"

    def __init__(self, module: Any, config: EngineConfig, armed: bool = False) -> None:
        values = asdict(config)
        values["armed"] = armed
        self._engine = module.PythonGestureEngine(values)
        self.armed = armed
        self._buffer = array("f", [0.0] * 63)
        self._state_value = GestureState.ARMED if armed else GestureState.PAUSED

    @staticmethod
    def _state(value: str) -> GestureState:
        return GestureState(value)

    def _actions(self, result: Any) -> tuple[Action, ...]:
        action_name = str(result["action"])
        state = self._state(str(result["state"]))
        actions: list[Action] = []
        state_changed = state != self._state_value
        state_order = int(result.get("state_order", 0))
        if state_changed and state_order == 0:
            actions.append(Action.state_change(state))
        button_number = int(result["button"])
        button = Button.LEFT if button_number == 1 else Button.RIGHT if button_number == 2 else None
        if action_name == ActionType.MOVE_ABSOLUTE.value:
            actions.append(Action.move_absolute(float(result["x"]), float(result["y"])))
        elif action_name == ActionType.BUTTON_DOWN.value and button is not None:
            actions.append(Action.button_down(button))
        elif action_name == ActionType.BUTTON_UP.value and button is not None:
            actions.append(Action.button_up(button))
        elif action_name == ActionType.SCROLL.value:
            actions.append(Action.scroll(0.0, float(result["y"])))
        if state_changed and state_order == 1:
            actions.append(Action.state_change(state))
        self._state_value = state
        return tuple(actions)

    def process(self, frame: LandmarkFrame) -> ActionBatch:
        self._buffer[:] = array("f", frame.landmarks)
        result = self._engine.process(
            self._buffer,
            frame.timestamp_ms,
            frame.handedness.lower() == "right",
            frame.handedness_confidence,
        )
        return ActionBatch(
            self._actions(result),
            self._state_value,
            self.name,
            {
                "engine": self.name,
                "mojo_action": str(result["action"]),
                "mojo_state": str(result["state"]),
            },
        )

    def reset(self, reason: str = "reset") -> ActionBatch:
        result = self._engine.reset(reason)
        actions = self._actions(result)
        return ActionBatch(
            actions, self._state_value, self.name, {"reason": reason, "engine": self.name}
        )

    def set_armed(self, armed: bool) -> ActionBatch:
        self.armed = armed
        result = self._engine.set_armed(armed)
        actions = self._actions(result)
        return ActionBatch(actions, self._state_value, self.name, {"engine": self.name})

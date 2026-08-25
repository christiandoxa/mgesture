from __future__ import annotations

from array import array
from dataclasses import asdict
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
        if state != self._state_value:
            actions.append(Action.state_change(state))
        self._state_value = state
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

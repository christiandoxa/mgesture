from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum


class Button(StrEnum):
    LEFT = "left"
    RIGHT = "right"


class PhysicalHand(StrEnum):
    LEFT = "Left"
    RIGHT = "Right"
    UNKNOWN = "Unknown"

    @classmethod
    def coerce(cls, value: object) -> PhysicalHand:
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            normalized = value.casefold()
            if normalized == "left":
                return cls.LEFT
            if normalized == "right":
                return cls.RIGHT
            if normalized == "unknown":
                return cls.UNKNOWN
        return cls.UNKNOWN


class HandSelection(StrEnum):
    RIGHT = "right"
    LEFT = "left"
    EITHER = "either"
    AUTO = "auto"

    @classmethod
    def coerce(cls, value: object) -> HandSelection:
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            try:
                return cls(value.casefold())
            except ValueError:
                pass
        raise ValueError("hand selection must be right, left, either, or auto")

    def accepts(self, hand: PhysicalHand | str) -> bool:
        physical = PhysicalHand.coerce(hand)
        if physical not in (PhysicalHand.RIGHT, PhysicalHand.LEFT):
            return False
        return (
            self in (HandSelection.EITHER, HandSelection.AUTO)
            or (self is HandSelection.RIGHT and physical is PhysicalHand.RIGHT)
            or (self is HandSelection.LEFT and physical is PhysicalHand.LEFT)
        )


# Keep handedness terminology available to callers while PhysicalHand remains canonical.
Handedness = PhysicalHand


class ActionType(StrEnum):
    MOVE_ABSOLUTE = "move_absolute"
    MOVE_RELATIVE = "move_relative"
    BUTTON_DOWN = "button_down"
    BUTTON_UP = "button_up"
    SCROLL = "scroll"
    STATE = "state"


class GestureState(StrEnum):
    PAUSED = "PAUSED"
    ARMED = "ARMED"
    LEFT_DOWN = "LEFT DOWN"
    RIGHT_DOWN = "RIGHT DOWN"
    SCROLL = "SCROLL"


@dataclass(frozen=True, slots=True)
class LandmarkFrame:
    timestamp_ms: int
    landmarks: Sequence[float]
    handedness: PhysicalHand | str = PhysicalHand.RIGHT
    handedness_confidence: float = 1.0
    width: int = 0
    height: int = 0

    def __post_init__(self) -> None:
        if len(self.landmarks) != 63:
            raise ValueError(f"landmarks must contain 63 values, got {len(self.landmarks)}")

    @property
    def physical_hand(self) -> PhysicalHand:
        return PhysicalHand.coerce(self.handedness)


@dataclass(frozen=True, slots=True)
class Action:
    type: ActionType
    x: float | None = None
    y: float | None = None
    dx: float | None = None
    dy: float | None = None
    button: Button | None = None
    state: GestureState | None = None
    value: float | None = None

    @classmethod
    def move_absolute(cls, x: float, y: float) -> Action:
        return cls(ActionType.MOVE_ABSOLUTE, x=x, y=y)

    @classmethod
    def button_down(cls, button: Button) -> Action:
        return cls(ActionType.BUTTON_DOWN, button=button)

    @classmethod
    def button_up(cls, button: Button) -> Action:
        return cls(ActionType.BUTTON_UP, button=button)

    @classmethod
    def scroll(cls, dx: float, dy: float) -> Action:
        return cls(ActionType.SCROLL, dx=dx, dy=dy)

    @classmethod
    def state_change(cls, state: GestureState) -> Action:
        return cls(ActionType.STATE, state=state)


@dataclass(frozen=True, slots=True)
class ActionBatch:
    actions: tuple[Action, ...] = ()
    state: GestureState = GestureState.PAUSED
    engine: str = "python"
    diagnostics: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EngineConfig:
    screen_x: int = 0
    screen_y: int = 0
    screen_width: int = 1920
    screen_height: int = 1080
    mirror: bool = True
    handedness_confidence: float = 0.70
    active_left: float = 0.10
    active_right: float = 0.10
    active_top: float = 0.10
    active_bottom: float = 0.10
    pointer_gain: float = 1.0
    pointer_acceleration: float = 0.0
    dead_zone: float = 0.002
    filter_min_cutoff: float = 1.0
    filter_beta: float = 0.007
    filter_derivative_cutoff: float = 1.0
    pinch_down_threshold: float = 0.45
    pinch_release_threshold: float = 0.60
    debounce_ms: int = 70
    release_debounce_ms: int = 35
    hand_loss_timeout_ms: int = 250
    reacquisition_ms: int = 150
    scroll_entry_ms: int = 180
    scroll_exit_grace_ms: int = 120
    scroll_sensitivity: float = 35.0
    scroll_direction: int = 1
    scroll_dead_zone: float = 0.001
    activation_gesture: bool = True
    activation_gesture_ms: int = 1000
    activation_cooldown_ms: int = 1000
    hand_selection: HandSelection = HandSelection.RIGHT

    def __post_init__(self) -> None:
        object.__setattr__(self, "hand_selection", HandSelection.coerce(self.hand_selection))

from __future__ import annotations

import logging

from mgesture.engine.models import ActionBatch, ActionType, Button

from .protocol import MouseBackend

LOGGER = logging.getLogger(__name__)


class InputDispatcher:
    """Translate typed actions and own the cross-backend held-button invariant."""

    def __init__(self, backend: MouseBackend) -> None:
        self.backend = backend
        self.held: set[Button] = set()

    def dispatch(self, batch: ActionBatch) -> None:
        for action in batch.actions:
            if action.type is ActionType.MOVE_ABSOLUTE:
                self.backend.move_absolute(action.x or 0.0, action.y or 0.0)
            elif action.type is ActionType.MOVE_RELATIVE:
                self.backend.move_relative(action.dx or 0.0, action.dy or 0.0)
            elif action.type is ActionType.BUTTON_DOWN and action.button is not None:
                self.backend.button_down(action.button)
                self.held.add(action.button)
            elif action.type is ActionType.BUTTON_UP and action.button is not None:
                self.backend.button_up(action.button)
                self.held.discard(action.button)
            elif action.type is ActionType.SCROLL:
                self.backend.scroll(action.dx or 0.0, action.dy or 0.0)

    def release_all(self) -> None:
        errors: list[Exception] = []
        for button in tuple(self.held):
            try:
                self.backend.button_up(button)
            except Exception as exc:
                errors.append(exc)
                LOGGER.exception("failed to release %s button", button.value)
        self.held.clear()
        try:
            self.backend.release_all()
        except Exception as exc:
            errors.append(exc)
            LOGGER.exception("backend release_all failed")
        if errors:
            raise RuntimeError(f"{len(errors)} mouse release operation(s) failed") from errors[0]

    def close(self) -> None:
        self.release_all()
        self.backend.close()

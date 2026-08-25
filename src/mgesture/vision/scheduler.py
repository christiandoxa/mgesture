from __future__ import annotations

import time

from ..config import PerformanceConfig


def effective_performance(config: PerformanceConfig) -> PerformanceConfig:
    if config.profile == "performance":
        return PerformanceConfig(
            config.profile,
            max(config.target_fps, 45),
            max(config.max_fps, 60),
            config.idle_fps,
            config.adaptive,
            config.preview_fps,
        )
    if config.profile == "efficiency":
        return PerformanceConfig(
            config.profile,
            min(config.target_fps, 24),
            min(config.max_fps, 30),
            min(config.idle_fps, 3),
            config.adaptive,
            min(config.preview_fps, 15),
        )
    return config


class AdaptivePerformanceController:
    def __init__(self, target_fps: int, max_fps: int, idle_fps: int, adaptive: bool = True) -> None:
        self.target_fps = max(1, target_fps)
        self.max_fps = max(self.target_fps, max_fps)
        self.idle_fps = max(1, idle_fps)
        self.adaptive = adaptive
        self._next_at = 0.0

    def wait_interval(self, paused: bool, hand_tracked: bool) -> float:
        if not self.adaptive:
            return 1.0 / self.max_fps
        fps = self.idle_fps if paused or not hand_tracked else self.target_fps
        return 1.0 / max(1, fps)

    def should_process(self, now: float, paused: bool, hand_tracked: bool) -> bool:
        if now < self._next_at:
            return False
        self._next_at = now + self.wait_interval(paused, hand_tracked)
        return True

    def remaining(self, now: float) -> float:
        return max(0.0, self._next_at - now)

    def wait(self, paused: bool, hand_tracked: bool) -> None:
        time.sleep(self.wait_interval(paused, hand_tracked))

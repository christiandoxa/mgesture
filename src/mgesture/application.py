from __future__ import annotations

import logging
import os
import signal
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from .compute import ComputePlan, detect_hardware, select_compute_plan
from .config import AppConfig
from .engine import EngineConfig, LandmarkFrame, create_engine
from .input import InputDispatcher, MouseBackend, create_backend
from .vision import Camera, HandLandmarker, available_model
from .vision.overlay import draw_overlay
from .vision.scheduler import AdaptivePerformanceController, effective_performance

LOGGER = logging.getLogger(__name__)


def engine_config(config: AppConfig, backend: MouseBackend) -> EngineConfig:
    layout = backend.get_screen_layout()
    if config.display.screen_mode == "virtual":
        x, y, width, height = layout.x, layout.y, layout.width, layout.height
    else:
        monitor = layout.monitors[min(config.display.monitor, len(layout.monitors) - 1)]
        x, y, width, height = monitor.x, monitor.y, monitor.width, monitor.height
    return EngineConfig(
        screen_x=x,
        screen_y=y,
        screen_width=width,
        screen_height=height,
        mirror=config.camera.mirror,
        handedness_confidence=config.vision.handedness_confidence,
        **{
            field: getattr(config.gesture, field)
            for field in (
                "active_left",
                "active_right",
                "active_top",
                "active_bottom",
                "pointer_gain",
                "pointer_acceleration",
                "dead_zone",
                "filter_min_cutoff",
                "filter_beta",
                "filter_derivative_cutoff",
                "pinch_down_threshold",
                "pinch_release_threshold",
                "debounce_ms",
                "release_debounce_ms",
                "hand_loss_timeout_ms",
                "reacquisition_ms",
                "scroll_entry_ms",
                "scroll_sensitivity",
                "scroll_direction",
                "scroll_dead_zone",
                "activation_gesture",
                "activation_gesture_ms",
                "activation_cooldown_ms",
            )
        },
    )


class Application:
    def __init__(
        self,
        config: AppConfig,
        engine_name: str | None = None,
        backend_name: str | None = None,
        preview: bool | None = None,
        armed: bool | None = None,
    ) -> None:
        self.config = config
        self.preview = config.preview if preview is None else preview
        self.stop_event = threading.Event()
        self.hardware = detect_hardware()
        self.compute_request = os.environ.get("MGESTURE_COMPUTE", config.compute.mode)
        self.backend = create_backend(
            backend_name or config.input.backend, config.display.width, config.display.height
        )
        self.dispatcher = InputDispatcher(self.backend)
        try:
            self.engine = create_engine(
                engine_name or config.input.engine,
                engine_config(config, self.backend),
                armed=config.armed if armed is None else armed,
            )
            self.compute_plan: ComputePlan = select_compute_plan(
                self.compute_request, self.hardware, getattr(self.engine, "name", "python")
            )
        except Exception:
            try:
                self.dispatcher.release_all()
            finally:
                self.dispatcher.backend.close()
            raise
        performance = effective_performance(config.performance)
        self.performance = AdaptivePerformanceController(
            performance.target_fps, performance.max_fps, performance.idle_fps, performance.adaptive
        )
        self._toggle_requested = threading.Event()
        self._hotkey_listener: Any = None
        self._signals_installed = False

    def _signal(self, signum: int, _frame: Any) -> None:
        LOGGER.info("received signal %s; stopping safely", signum)
        self.stop_event.set()

    def _install_signals(self) -> None:
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, self._signal)
        self._signals_installed = True

    def _dispatch(self, batch: Any) -> None:
        self.dispatcher.dispatch(batch)

    def toggle_armed(self) -> None:
        batch = self.engine.set_armed(not getattr(self.engine, "armed", False))
        self._dispatch(batch)

    def _start_hotkey(self) -> None:
        try:
            from pynput import keyboard  # type: ignore[import-untyped]

            shortcut = self.config.activation_shortcut
            for name in ("ctrl", "alt", "shift", "cmd"):
                shortcut = shortcut.replace(name, f"<{name}>")
            self._hotkey_listener = keyboard.GlobalHotKeys({shortcut: self._toggle_requested.set})
            self._hotkey_listener.start()
        except Exception as exc:
            LOGGER.info("global activation shortcut unavailable: %s", exc)

    def _cleanup(self, camera: Camera | None, landmarker: HandLandmarker | None) -> None:
        if self._hotkey_listener is not None:
            try:
                self._hotkey_listener.stop()
            except Exception:
                LOGGER.exception("global shortcut close failed")
        for resource, name in ((landmarker, "landmarker"), (camera, "camera")):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    LOGGER.exception("failed to close %s", name)
        try:
            self._dispatch(self.engine.reset("application shutdown"))
        except Exception:
            LOGGER.exception("gesture engine reset failed during shutdown")
        try:
            self.dispatcher.release_all()
        except Exception:
            LOGGER.exception("mouse button release failed during shutdown")
        try:
            self.dispatcher.backend.close()
        except Exception:
            LOGGER.exception("input backend close failed during shutdown")
        if self.preview:
            try:
                import cv2 as cv2_module

                cv2_module.destroyAllWindows()
            except Exception:
                LOGGER.exception("preview close failed during shutdown")

    def run(self) -> int:
        self._install_signals()
        model = (
            available_model(Path(self.config.vision.model_path))
            if self.config.vision.model_path
            else available_model()
        )
        if model is None:
            raise RuntimeError("hand model is not installed; run `mgesture model install`")
        camera: Camera | None = None
        landmarker: HandLandmarker | None = None
        try:
            camera = Camera(
                self.config.camera.index,
                self.config.camera.width,
                self.config.camera.height,
                self.config.camera.target_fps,
            ).open()
            try:
                landmarker = HandLandmarker(
                    str(model),
                    self.config.vision.detection_confidence,
                    self.config.vision.presence_confidence,
                    self.config.vision.tracking_confidence,
                    "gpu" if self.compute_plan.inference == "mediapipe_gpu" else "cpu",
                    self.config.vision.handedness_mirrored_input,
                )
            except Exception as exc:
                if self.compute_request != "auto":
                    raise RuntimeError(
                        f"{self.compute_plan.inference} initialization failed: {exc}"
                    ) from exc
                LOGGER.warning("GPU inference unavailable; switched to CPU inference: %s", exc)
                self.compute_plan = select_compute_plan(
                    "cpu", self.hardware, getattr(self.engine, "name", "python")
                )
                landmarker = HandLandmarker(
                    str(model),
                    self.config.vision.detection_confidence,
                    self.config.vision.presence_confidence,
                    self.config.vision.tracking_confidence,
                    "cpu",
                    self.config.vision.handedness_mirrored_input,
                )
            cv2 = None
            if self.preview:
                try:
                    import cv2 as cv2_module

                    cv2 = cv2_module
                except ImportError as exc:
                    raise RuntimeError("preview requested but OpenCV is unavailable") from exc
            LOGGER.info(
                "compute=%s inference=%s preprocessing=%s gesture=%s preview=%s",
                self.compute_request,
                self.compute_plan.inference,
                self.compute_plan.preprocessing,
                self.compute_plan.gesture,
                self.compute_plan.preview,
            )
            LOGGER.info(
                "engine=%s backend=%s armed=%s camera=%sx%s@%s (%s)",
                getattr(self.engine, "name", "unknown"),
                self.backend.name,
                getattr(self.engine, "armed", False),
                camera.actual_width,
                camera.actual_height,
                camera.actual_fps,
                camera.backend,
            )
            self._start_hotkey()
            hand_tracked = False
            last_camera_warning = 0.0
            while not self.stop_event.is_set():
                captured = camera.read_latest(0.25)
                if captured is None:
                    if camera.error and time.monotonic() - last_camera_warning >= 2.0:
                        LOGGER.warning("%s", camera.error)
                        last_camera_warning = time.monotonic()
                    continue
                now = time.monotonic()
                if self._toggle_requested.is_set():
                    self._toggle_requested.clear()
                    self.toggle_armed()
                if not self.performance.should_process(
                    now, not getattr(self.engine, "armed", False), hand_tracked
                ):
                    self.stop_event.wait(self.performance.remaining(now))
                    continue
                preprocess_start = time.perf_counter_ns()
                try:
                    landmarker.submit(captured.image, captured.timestamp_ms)
                except Exception as exc:
                    if (
                        self.compute_request != "auto"
                        or self.compute_plan.inference != "mediapipe_gpu"
                    ):
                        raise RuntimeError(
                            f"{self.compute_plan.inference} failed during processing: {exc}"
                        ) from exc
                    LOGGER.warning("GPU inference unavailable; switched to CPU inference: %s", exc)
                    try:
                        landmarker.close()
                    finally:
                        try:
                            self._dispatch(self.engine.reset("GPU inference failure"))
                        finally:
                            self.dispatcher.release_all()
                    self.compute_plan = select_compute_plan(
                        "cpu", self.hardware, getattr(self.engine, "name", "python")
                    )
                    landmarker = HandLandmarker(
                        str(model),
                        self.config.vision.detection_confidence,
                        self.config.vision.presence_confidence,
                        self.config.vision.tracking_confidence,
                        "cpu",
                        self.config.vision.handedness_mirrored_input,
                    )
                    continue
                preprocess_ms = (time.perf_counter_ns() - preprocess_start) / 1_000_000
                detected = landmarker.latest()
                if detected is None:
                    frame = LandmarkFrame(
                        captured.timestamp_ms,
                        (0.0,) * 63,
                        "Unknown",
                        0.0,
                        captured.width,
                        captured.height,
                    )
                    display_landmarks = None
                else:
                    frame = replace(detected.frame, width=captured.width, height=captured.height)
                    display_landmarks = tuple(frame.landmarks)
                gesture_start = time.perf_counter_ns()
                batch = self.engine.process(frame)
                gesture_ms = (time.perf_counter_ns() - gesture_start) / 1_000_000
                hand_tracked = bool(batch.diagnostics.get("valid_hand", False))
                dispatch_start = time.perf_counter_ns()
                self._dispatch(batch)
                dispatch_ms = (time.perf_counter_ns() - dispatch_start) / 1_000_000
                total_ms = time.monotonic_ns() / 1_000_000 - captured.timestamp_ms
                if cv2 is not None:
                    image = captured.image
                    if self.config.camera.mirror:
                        image = cv2.flip(image, 1)
                        if display_landmarks is not None:
                            display_landmarks = tuple(
                                (1.0 - value if index % 3 == 0 else value)
                                for index, value in enumerate(display_landmarks)
                            )
                    lines = [
                        f"state: {batch.state.value}",
                        f"compute: {self.compute_plan.inference} | gesture: {self.compute_plan.gesture}",
                        f"engine: {getattr(self.engine, 'name', '?')} | backend: {self.backend.name}",
                        f"camera: {camera.actual_width}x{camera.actual_height} dropped: {camera.frames.dropped}",
                        f"index pinch: {batch.diagnostics.get('index_pinch', '-')}",
                        f"middle pinch: {batch.diagnostics.get('middle_pinch', '-')}",
                        f"preprocess: {preprocess_ms:.2f}ms inference: {landmarker.last_inference_ms or 0.0:.2f}ms gesture: {gesture_ms:.2f}ms input: {dispatch_ms:.2f}ms total: {total_ms:.2f}ms",
                        "warning: low confidence/no right hand" if not hand_tracked else "",
                        "SPACE arm/pause | Q/Esc emergency stop",
                    ]
                    cv2.imshow(
                        "mgesture",
                        draw_overlay(
                            image,
                            display_landmarks,
                            batch,
                            lines,
                            (
                                self.config.gesture.active_left,
                                self.config.gesture.active_top,
                                1.0 - self.config.gesture.active_right,
                                1.0 - self.config.gesture.active_bottom,
                            ),
                        ),
                    )
                    key = cv2.waitKey(1) & 0xFF
                    if key in (27, ord("q")):
                        self.stop_event.set()
                    elif key == ord(" "):
                        self.toggle_armed()
        finally:
            self._cleanup(camera, landmarker)
        return 0

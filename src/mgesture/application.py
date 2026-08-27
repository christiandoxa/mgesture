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
from .config import AppConfig, effective_handedness_mirror, effective_preview_mirror
from .engine import EngineConfig, LandmarkFrame, create_engine
from .input import GlobalShortcutListener, InputDispatcher, MouseBackend, create_backend
from .version import __version__
from .vision import Camera, HandLandmarker, available_model, select_camera_index
from .vision.overlay import draw_overlay
from .vision.scheduler import AdaptivePerformanceController, effective_performance

LOGGER = logging.getLogger(__name__)


def engine_config(config: AppConfig, backend: MouseBackend) -> EngineConfig:
    layout = backend.get_screen_layout()
    if not layout.monitors:
        raise RuntimeError(f"{backend.name} did not report any monitors")
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
        mirror=config.gesture.pointer_mirror,
        handedness_confidence=config.vision.handedness_confidence,
        hand_selection=config.vision.hand_selection,
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
                "scroll_exit_grace_ms",
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
                self.dispatcher.close()
            except Exception:
                LOGGER.exception("input cleanup failed after application setup error")
            raise
        performance = effective_performance(config.performance)
        self.performance = AdaptivePerformanceController(
            performance.target_fps, performance.max_fps, performance.idle_fps, performance.adaptive
        )
        self._hotkey_listener: GlobalShortcutListener | None = None
        self._signals_installed = False
        self._signal_handlers: dict[int, Any] = {}
        self._cleaned = False

    def _signal(self, signum: int, _frame: Any) -> None:
        LOGGER.info("received signal %s; stopping safely", signum)
        self.stop_event.set()

    def _install_signals(self) -> None:
        if self._signals_installed:
            return
        try:
            for signum in (signal.SIGINT, signal.SIGTERM):
                self._signal_handlers[signum] = signal.signal(signum, self._signal)
        except Exception:
            self._restore_signals()
            raise
        self._signals_installed = True

    def _restore_signals(self) -> None:
        for signum, handler in tuple(self._signal_handlers.items()):
            try:
                signal.signal(signum, handler)
            except Exception:
                LOGGER.exception("failed to restore signal handler %s", signum)
        self._signal_handlers.clear()
        self._signals_installed = False

    def _dispatch(self, batch: Any) -> None:
        self.dispatcher.dispatch(batch)

    def _reset_input(self, reason: str) -> None:
        try:
            self._dispatch(self.engine.reset(reason))
        finally:
            self.dispatcher.release_all()

    def toggle_armed(self) -> None:
        batch = self.engine.set_armed(not getattr(self.engine, "armed", False))
        self._dispatch(batch)

    def _start_hotkey(self) -> None:
        listener = GlobalShortcutListener(self.config.activation_shortcut)
        try:
            listener.start()
        except Exception as exc:
            LOGGER.warning(
                "global activation shortcut unavailable: %s; run `mgesture doctor`", exc
            )
            return
        self._hotkey_listener = listener

    def _process_toggle_requests(self) -> None:
        if self._hotkey_listener is not None:
            self._hotkey_listener.process(self.toggle_armed)

    def _cleanup(self, camera: Camera | None, landmarker: HandLandmarker | None) -> None:
        if self._cleaned:
            return
        self._cleaned = True
        listener, self._hotkey_listener = self._hotkey_listener, None
        if listener is not None:
            try:
                listener.stop()
            except Exception:
                LOGGER.exception("global shortcut close failed")
        try:
            self._dispatch(self.engine.reset("application shutdown"))
        except Exception:
            LOGGER.exception("gesture engine reset failed during shutdown")
        try:
            self.dispatcher.close()
        except Exception:
            LOGGER.exception("mouse input cleanup failed during shutdown")
        for resource, name in ((landmarker, "landmarker"), (camera, "camera")):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    LOGGER.exception("failed to close %s", name)
        if self.preview:
            try:
                import cv2 as cv2_module

                cv2_module.destroyAllWindows()
            except Exception:
                LOGGER.exception("preview close failed during shutdown")
        self._restore_signals()

    def run(self) -> int:
        camera: Camera | None = None
        landmarker: HandLandmarker | None = None
        try:
            self._install_signals()
            model = (
                available_model(Path(self.config.vision.model_path))
                if self.config.vision.model_path
                else available_model()
            )
            if model is None:
                raise RuntimeError("hand model is not installed; run `mgesture model install`")
            camera_index = select_camera_index(
                self.config.camera.index,
                self.config.camera.width,
                self.config.camera.height,
                self.config.camera.target_fps,
            )
            if camera_index is None:
                raise RuntimeError(
                    "no usable camera found; run `mgesture list-cameras` or `mgesture doctor`"
                )
            camera = Camera(
                camera_index,
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
                    effective_handedness_mirror(self.config.vision),
                    self.config.vision.hand_selection,
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
                    effective_handedness_mirror(self.config.vision),
                    self.config.vision.hand_selection,
                )
            cv2 = None
            if self.preview:
                try:
                    import cv2 as cv2_module

                    cv2 = cv2_module
                except ImportError as exc:
                    raise RuntimeError("preview requested but OpenCV is unavailable") from exc
            LOGGER.debug(
                "compute=%s inference=%s preprocessing=%s gesture=%s preview=%s",
                self.compute_request,
                self.compute_plan.inference,
                self.compute_plan.preprocessing,
                self.compute_plan.gesture,
                self.compute_plan.preview,
            )
            LOGGER.info(
                "mgesture %s | camera %s (%sx%s@%.1f) | engine %s | compute %s | status Paused | press %s to activate; Ctrl+C exits safely",
                __version__,
                camera.index,
                camera.actual_width,
                camera.actual_height,
                camera.actual_fps,
                getattr(self.engine, "name", "unknown"),
                self.compute_plan.inference.removeprefix("mediapipe_").upper(),
                self.config.activation_shortcut,
            )
            self._start_hotkey()
            hand_tracked = False
            last_camera_warning = 0.0
            handled_camera_failure = 0
            last_result_timestamp = -1
            while not self.stop_event.is_set():
                self._process_toggle_requests()
                if camera.failure_generation > handled_camera_failure:
                    handled_camera_failure = camera.failure_generation
                    message = camera.last_error or "camera failure"
                    LOGGER.error("%s; all held buttons released", message)
                    camera.frames.clear()
                    landmarker.discard_pending()
                    try:
                        self._reset_input("camera failure")
                    except Exception:
                        LOGGER.exception("camera failure cleanup failed")
                    hand_tracked = False
                captured = camera.read_latest(0.25)
                self._process_toggle_requests()
                if captured is None:
                    if camera.error and time.monotonic() - last_camera_warning >= 2.0:
                        LOGGER.warning("%s", camera.error)
                        last_camera_warning = time.monotonic()
                    continue
                now = time.monotonic()
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
                        self._reset_input("GPU inference failure")
                    self.compute_plan = select_compute_plan(
                        "cpu", self.hardware, getattr(self.engine, "name", "python")
                    )
                    landmarker = HandLandmarker(
                        str(model),
                        self.config.vision.detection_confidence,
                        self.config.vision.presence_confidence,
                        self.config.vision.tracking_confidence,
                        "cpu",
                        effective_handedness_mirror(self.config.vision),
                        self.config.vision.hand_selection,
                    )
                    continue
                preprocess_ms = (time.perf_counter_ns() - preprocess_start) / 1_000_000
                result = landmarker.poll_latest()
                if result is None:
                    continue
                if result.timestamp_ms <= last_result_timestamp:
                    continue
                last_result_timestamp = result.timestamp_ms
                if getattr(result, "hand_changed", False):
                    self._reset_input("hand switch")
                detected = result.hand
                if detected is None:
                    frame = LandmarkFrame(
                        result.timestamp_ms,
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
                total_ms = time.monotonic_ns() / 1_000_000 - result.timestamp_ms
                if cv2 is not None:
                    image = captured.image
                    # Preview/control mirroring is independent from MediaPipe input mirroring.
                    if effective_preview_mirror(self.config.camera):
                        image = cv2.flip(image, 1)
                        if display_landmarks is not None:
                            display_landmarks = tuple(
                                (1.0 - value if index % 3 == 0 else value)
                                for index, value in enumerate(display_landmarks)
                            )
                    scroll_progress = batch.diagnostics.get("scroll_entry_progress")
                    scroll_progress_text = (
                        f"{float(scroll_progress):.0%}"
                        if isinstance(scroll_progress, (int, float))
                        else "-"
                    )
                    scroll_fingers = batch.diagnostics.get("scroll_fingers_ready")
                    scroll_fingers_text = (
                        "ready"
                        if scroll_fingers is True
                        else "not ready"
                        if scroll_fingers is False
                        else "-"
                    )
                    lines = [
                        f"state: {batch.state.value}",
                        f"hand: {frame.handedness} | selection: {self.config.vision.hand_selection.value}",
                        f"compute: {self.compute_plan.inference} | gesture: {self.compute_plan.gesture}",
                        f"engine: {getattr(self.engine, 'name', '?')} | backend: {self.backend.name}",
                        f"camera: {camera.actual_width}x{camera.actual_height}@{camera.actual_fps:.1f} "
                        f"dropped: {camera.frames.dropped} reconnects: {camera.reconnects}",
                        f"inference queue: {landmarker.diagnostics()['pending_frames']} "
                        f"dropped: {landmarker.dropped_submissions + landmarker.dropped_results}",
                        f"index pinch: {batch.diagnostics.get('index_pinch', '-')}",
                        f"middle pinch: {batch.diagnostics.get('middle_pinch', '-')}",
                        f"scroll fingers: {scroll_fingers_text} "
                        f"entry: {scroll_progress_text} "
                        f"active: {'yes' if batch.state.value == 'SCROLL' else 'no'}",
                        f"preprocess: {preprocess_ms:.2f}ms inference: {landmarker.last_inference_ms or 0.0:.2f}ms gesture: {gesture_ms:.2f}ms input: {dispatch_ms:.2f}ms total: {total_ms:.2f}ms",
                        "warning: low confidence/no selected hand" if not hand_tracked else "",
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

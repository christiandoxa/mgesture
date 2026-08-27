from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CapturedFrame:
    timestamp_ms: int
    image: Any
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class CameraInfo:
    index: int
    opened: bool
    readable: bool
    backend: str = "unknown"
    width: int = 0
    height: int = 0
    fps: float = 0.0
    error: str | None = None
    requested_width: int = 0
    requested_height: int = 0
    requested_fps: int = 0

    @property
    def detail(self) -> str:
        status = "readable" if self.readable else "not readable"
        detail = (
            f"index={self.index}, opened={self.opened}, {status}, "
            f"requested={self.requested_width}x{self.requested_height}@{self.requested_fps}, "
            f"negotiated={self.width}x{self.height}@{self.fps:.1f}, backend={self.backend}"
        )
        return f"{detail}; {self.error}" if self.error else detail

    def as_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "opened": self.opened,
            "readable": self.readable,
            "backend": self.backend,
            "negotiated_width": self.width,
            "negotiated_height": self.height,
            "negotiated_fps": self.fps,
            "requested_width": self.requested_width,
            "requested_height": self.requested_height,
            "requested_fps": self.requested_fps,
            "error": self.error,
        }


class CameraError(RuntimeError):
    pass


class LatestFrameBuffer:
    """One-slot handoff: a slow consumer sees newest frame, never an old queue."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._frame: CapturedFrame | None = None
        self.dropped = 0

    def put(self, frame: CapturedFrame) -> None:
        with self._condition:
            if self._frame is not None:
                self.dropped += 1
            self._frame = frame
            self._condition.notify()

    def get(self, timeout: float = 0.2) -> CapturedFrame | None:
        deadline = time.monotonic() + max(0.0, timeout)
        with self._condition:
            while self._frame is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not self._condition.wait(remaining):
                    return None
            frame, self._frame = self._frame, None
            return frame

    def clear(self) -> None:
        with self._condition:
            self._frame = None


def _backend_name(capture: Any) -> str:
    getter = getattr(capture, "getBackendName", None)
    try:
        return str(getter()) if callable(getter) else "unknown"
    except Exception:
        return "unknown"


def _capture_properties(capture: Any, cv2: Any) -> tuple[int, int, float]:
    try:
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    except (AttributeError, TypeError, ValueError, OverflowError):
        return 0, 0, 0.0
    return width, height, fps


def probe_camera(
    index: int, width: int = 640, height: int = 480, target_fps: int = 30
) -> CameraInfo:
    try:
        import cv2
    except ImportError as exc:
        raise CameraError("OpenCV is not installed; run `pixi install`") from exc
    try:
        capture = cv2.VideoCapture(index)
    except Exception as exc:
        raise CameraError(f"camera {index} open failed: {exc}") from exc
    try:
        opened = bool(capture.isOpened())
        if not opened:
            return CameraInfo(
                index,
                False,
                False,
                _backend_name(capture),
                error="camera could not be opened",
                requested_width=width,
                requested_height=height,
                requested_fps=target_fps,
            )
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        capture.set(cv2.CAP_PROP_FPS, target_fps)
        actual_width, actual_height, actual_fps = _capture_properties(capture, cv2)
        ok, image = capture.read()
        readable = bool(ok and image is not None)
        return CameraInfo(
            index,
            True,
            readable,
            _backend_name(capture),
            actual_width,
            actual_height,
            actual_fps,
            None if readable else "camera opened but returned no frame",
            width,
            height,
            target_fps,
        )
    except Exception as exc:
        return CameraInfo(
            index,
            bool(locals().get("opened", False)),
            False,
            error=str(exc),
            requested_width=width,
            requested_height=height,
            requested_fps=target_fps,
        )
    finally:
        capture.release()


def probe_cameras(
    limit: int = 8, width: int = 640, height: int = 480, target_fps: int = 30
) -> tuple[CameraInfo, ...]:
    if limit < 0:
        raise ValueError("camera probe limit must be >= 0")
    return tuple(probe_camera(index, width, height, target_fps) for index in range(limit))


def select_camera_index(
    preferred: int, width: int = 640, height: int = 480, target_fps: int = 30, limit: int = 8
) -> int | None:
    """Prefer configured camera, then choose the first readable camera deterministically."""
    candidates = (preferred, *(index for index in range(limit) if index != preferred))
    for index in candidates:
        info = probe_camera(index, width, height, target_fps)
        if info.opened and info.readable:
            return index
    return None


class Camera:
    _READ_FAILURE_LIMIT = 3
    _RECONNECT_INITIAL_DELAY = 0.1
    _RECONNECT_MAX_DELAY = 2.0

    def __init__(self, index: int, width: int, height: int, target_fps: int) -> None:
        self.index = index
        self.requested_width = width
        self.requested_height = height
        self.requested_fps = target_fps
        self._capture: Any = None
        self._capture_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._cv2: Any = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.frames = LatestFrameBuffer()
        self.actual_width = 0
        self.actual_height = 0
        self.actual_fps = 0.0
        self.backend = "unknown"
        self.error: str | None = None
        self.last_error: str | None = None
        self.failure_generation = 0
        self.read_failures = 0
        self.reconnects = 0
        self.frames_read = 0
        self.observed_fps = 0.0
        self._fps_started = 0.0
        self._fps_frames = 0
        self._last_timestamp_ms = -1

    def open(self) -> Camera:
        try:
            import cv2
        except ImportError as exc:
            raise CameraError("OpenCV is not installed; run `pixi install`") from exc
        self._cv2 = cv2
        try:
            capture = self._new_capture()
        except CameraError:
            raise
        except Exception as exc:
            raise CameraError(f"camera {self.index} open failed: {exc}") from exc
        if capture is None:
            raise CameraError(
                f"camera {self.index} could not be opened; run `mgesture list-cameras` "
                "and check camera permissions"
            )
        self._record_capture_properties(capture)
        with self._capture_lock:
            self._capture = capture
        self._stop.clear()
        self._thread = threading.Thread(target=self._reader, name="mgesture-camera", daemon=True)
        self._thread.start()
        return self

    def _new_capture(self) -> Any | None:
        capture: Any = None
        try:
            capture = self._cv2.VideoCapture(self.index)
            if not capture.isOpened():
                capture.release()
                return None
            capture.set(self._cv2.CAP_PROP_FRAME_WIDTH, self.requested_width)
            capture.set(self._cv2.CAP_PROP_FRAME_HEIGHT, self.requested_height)
            capture.set(self._cv2.CAP_PROP_FPS, self.requested_fps)
            return capture
        except Exception as exc:
            if capture is not None:
                try:
                    capture.release()
                except Exception:
                    pass
            raise CameraError(f"camera {self.index} open failed: {exc}") from exc

    def _record_capture_properties(self, capture: Any | None = None) -> None:
        if capture is None:
            capture = self._capture
        if capture is None:
            return
        self.actual_width, self.actual_height, self.actual_fps = _capture_properties(
            capture, self._cv2
        )
        self.backend = _backend_name(capture)

    def _mark_failure(self, message: str) -> None:
        with self._state_lock:
            if self.error is None:
                self.failure_generation += 1
            self.error = message
            self.last_error = message

    def _clear_failure(self) -> None:
        with self._state_lock:
            self.error = None

    def _detach(self, capture: Any) -> None:
        self.frames.clear()
        with self._capture_lock:
            if self._capture is capture:
                self._capture = None
        try:
            capture.release()
        except Exception:
            pass

    def _reader(self) -> None:
        with self._capture_lock:
            capture = self._capture
        failures = 0
        reconnect_attempt = 0
        while not self._stop.is_set():
            if capture is None:
                delay = min(
                    self._RECONNECT_MAX_DELAY,
                    self._RECONNECT_INITIAL_DELAY * (2 ** max(0, reconnect_attempt - 1)),
                )
                if reconnect_attempt and self._stop.wait(delay):
                    break
                try:
                    replacement = self._new_capture()
                except CameraError as exc:
                    replacement = None
                    reason = str(exc)
                else:
                    reason = "camera remained unavailable"
                if replacement is not None:
                    try:
                        self._record_capture_properties(replacement)
                    except Exception as exc:
                        replacement.release()
                        replacement = None
                        reason = str(exc)
                if replacement is not None:
                    with self._capture_lock:
                        if self._stop.is_set():
                            replacement.release()
                            break
                        self._capture = replacement
                    capture = replacement
                    reconnect_attempt = 0
                    failures = 0
                    with self._state_lock:
                        self.reconnects += 1
                    self._clear_failure()
                    continue
                reconnect_attempt += 1
                next_delay = min(
                    self._RECONNECT_MAX_DELAY,
                    self._RECONNECT_INITIAL_DELAY * (2 ** max(0, reconnect_attempt - 1)),
                )
                self._mark_failure(
                    f"camera {self.index} reconnect failed (attempt {reconnect_attempt}); "
                    f"retrying in {next_delay:.1f}s: {reason}"
                )
                continue

            try:
                ok, image = capture.read()
                read_error = ""
            except Exception as exc:
                ok, image = False, None
                read_error = str(exc)
            if not ok or image is None:
                failures += 1
                with self._state_lock:
                    self.read_failures += 1
                if failures < self._READ_FAILURE_LIMIT:
                    detail = f"camera read failed ({failures}/{self._READ_FAILURE_LIMIT})"
                    if read_error:
                        detail += f": {read_error}"
                    self._mark_failure(f"camera {self.index} {detail}; retrying")
                    if self._stop.wait(min(0.05 * (2 ** (failures - 1)), 0.2)):
                        break
                    continue
                detail = f"camera {self.index} read failed; reconnecting"
                if read_error:
                    detail += f": {read_error}"
                detail += "; check permissions or run `mgesture list-cameras`"
                self._mark_failure(detail)
                self._detach(capture)
                capture = None
                failures = 0
                reconnect_attempt = 0
                continue

            failures = 0
            reconnect_attempt = 0
            self._clear_failure()
            if self._stop.is_set():
                break
            now = time.monotonic()
            with self._state_lock:
                self.frames_read += 1
                self._fps_frames += 1
                if self._fps_started == 0.0:
                    self._fps_started = now
                elif now - self._fps_started >= 1.0:
                    self.observed_fps = self._fps_frames / (now - self._fps_started)
                    self._fps_started = now
                    self._fps_frames = 0
            width, height = self.actual_width, self.actual_height
            if (width <= 0 or height <= 0) and hasattr(image, "shape"):
                height, width = int(image.shape[0]), int(image.shape[1])
            timestamp_ms = time.monotonic_ns() // 1_000_000
            with self._state_lock:
                timestamp_ms = max(timestamp_ms, self._last_timestamp_ms + 1)
                self._last_timestamp_ms = timestamp_ms
            self.frames.put(CapturedFrame(timestamp_ms, image, width, height))

    def read_latest(self, timeout: float = 0.2) -> CapturedFrame | None:
        return self.frames.get(timeout)

    def diagnostics(self) -> dict[str, object]:
        with self._state_lock:
            error = self.error
            last_error = self.last_error
            failure_generation = self.failure_generation
            read_failures = self.read_failures
            reconnects = self.reconnects
            frames_read = self.frames_read
            observed_fps = self.observed_fps
        return {
            "index": self.index,
            "backend": self.backend,
            "requested": {
                "width": self.requested_width,
                "height": self.requested_height,
                "fps": self.requested_fps,
            },
            "negotiated": {
                "width": self.actual_width,
                "height": self.actual_height,
                "fps": self.actual_fps,
            },
            "observed_fps": observed_fps,
            "frames_read": frames_read,
            "dropped_frames": self.frames.dropped,
            "read_failures": read_failures,
            "reconnects": reconnects,
            "failure_generation": failure_generation,
            "error": error,
            "last_error": last_error,
        }

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        with self._capture_lock:
            capture, self._capture = self._capture, None
        if capture is not None:
            try:
                capture.release()
            except Exception:
                pass

    def __enter__(self) -> Camera:
        return self.open()

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()

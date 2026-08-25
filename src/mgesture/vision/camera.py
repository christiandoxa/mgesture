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
        with self._condition:
            if self._frame is None:
                self._condition.wait(timeout)
            frame, self._frame = self._frame, None
            return frame


class Camera:
    def __init__(self, index: int, width: int, height: int, target_fps: int) -> None:
        self.index = index
        self.requested_width = width
        self.requested_height = height
        self.requested_fps = target_fps
        self._capture: Any = None
        self._cv2: Any = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.frames = LatestFrameBuffer()
        self.actual_width = 0
        self.actual_height = 0
        self.actual_fps = 0.0
        self.backend = "unknown"
        self.error: str | None = None

    def open(self) -> Camera:
        try:
            import cv2
        except ImportError as exc:
            raise CameraError("OpenCV is not installed; run `pixi install`") from exc
        self._cv2 = cv2
        self._capture = self._new_capture()
        if self._capture is None:
            raise CameraError(f"camera {self.index} could not be opened")
        self._record_capture_properties()
        self.backend = str(self._capture.getBackendName())
        self._stop.clear()
        self._thread = threading.Thread(target=self._reader, name="mgesture-camera", daemon=True)
        self._thread.start()
        return self

    def _new_capture(self) -> Any | None:
        capture = self._cv2.VideoCapture(self.index)
        if not capture.isOpened():
            capture.release()
            return None
        capture.set(self._cv2.CAP_PROP_FRAME_WIDTH, self.requested_width)
        capture.set(self._cv2.CAP_PROP_FRAME_HEIGHT, self.requested_height)
        capture.set(self._cv2.CAP_PROP_FPS, self.requested_fps)
        return capture

    def _record_capture_properties(self) -> None:
        self.actual_width = int(self._capture.get(self._cv2.CAP_PROP_FRAME_WIDTH))
        self.actual_height = int(self._capture.get(self._cv2.CAP_PROP_FRAME_HEIGHT))
        self.actual_fps = float(self._capture.get(self._cv2.CAP_PROP_FPS) or 0.0)
        self.backend = str(self._capture.getBackendName())

    def _reader(self) -> None:
        failures = 0
        while not self._stop.is_set():
            ok, image = self._capture.read()
            if not ok:
                failures += 1
                if failures < 5:
                    time.sleep(0.05)
                    continue
                self.error = "camera read failed; attempting reconnect"
                self._capture.release()
                replacement = self._new_capture()
                if replacement is not None:
                    self._capture = replacement
                    self._record_capture_properties()
                    self.error = None
                    failures = 0
                else:
                    time.sleep(0.5)
                continue
            failures = 0
            self.error = None
            self.frames.put(
                CapturedFrame(
                    time.monotonic_ns() // 1_000_000, image, self.actual_width, self.actual_height
                )
            )

    def read_latest(self, timeout: float = 0.2) -> CapturedFrame | None:
        return self.frames.get(timeout)

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def __enter__(self) -> Camera:
        return self.open()

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()

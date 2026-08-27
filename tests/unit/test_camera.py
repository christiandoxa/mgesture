from __future__ import annotations

import sys
import threading
from types import SimpleNamespace

from mgesture.vision.camera import Camera, CapturedFrame, LatestFrameBuffer, probe_camera


def test_latest_frame_buffer_keeps_only_newest_frame() -> None:
    buffer = LatestFrameBuffer()
    buffer.put(CapturedFrame(1, "old", 640, 480))
    buffer.put(CapturedFrame(2, "new", 640, 480))

    assert buffer.get(0).image == "new"
    assert buffer.dropped == 1
    assert buffer.get(0) is None


class _Capture:
    def __init__(self, reads: list[tuple[bool, object | None]]) -> None:
        self.reads = reads
        self.released = False

    def isOpened(self) -> bool:
        return True

    def set(self, _property: int, _value: int) -> bool:
        return True

    def get(self, property_id: int) -> float:
        return {1: 1280.0, 2: 720.0, 3: 30.0}[property_id]

    def getBackendName(self) -> str:
        return "fake"

    def read(self) -> tuple[bool, object | None]:
        return self.reads.pop(0) if self.reads else (False, None)

    def release(self) -> None:
        self.released = True


def test_camera_reconnects_after_bounded_read_failures() -> None:
    camera = Camera(0, 640, 480, 30)
    replacement = _Capture([(True, object())])
    replacement.read = lambda: (camera._stop.set() or True, object())
    camera._cv2 = SimpleNamespace(
        CAP_PROP_FRAME_WIDTH=1,
        CAP_PROP_FRAME_HEIGHT=2,
        CAP_PROP_FPS=3,
        VideoCapture=lambda _index: replacement,
    )
    camera._capture = _Capture([(False, None), (False, None), (False, None)])
    thread = threading.Thread(target=camera._reader)
    thread.start()
    thread.join(1.0)
    camera._stop.set()
    camera.close()

    assert not thread.is_alive()
    assert camera.reconnects == 1
    assert camera.failure_generation == 1
    assert camera.last_error == (
        "camera 0 read failed; reconnecting; check permissions or run `mgesture list-cameras`"
    )


def test_probe_reports_negotiated_camera_properties(monkeypatch) -> None:
    fake_cv2 = SimpleNamespace(
        CAP_PROP_FRAME_WIDTH=1,
        CAP_PROP_FRAME_HEIGHT=2,
        CAP_PROP_FPS=3,
        VideoCapture=lambda _index: _Capture([(True, object())]),
    )
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)

    info = probe_camera(4, 640, 480, 24)

    assert info.opened and info.readable
    assert info.width == 1280
    assert info.height == 720
    assert info.fps == 30.0
    assert "negotiated=1280x720@30.0" in info.detail

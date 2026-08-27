from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import mgesture.onboarding as onboarding
from mgesture.config import default_config
from mgesture.input import FakeMouseBackend


def test_tutorial_skip_uses_fake_input_only(monkeypatch, tmp_path: Path):
    model = tmp_path / "hand.task"
    model.write_bytes(b"model")
    created: list[FakeMouseBackend] = []

    class RecordingFake(FakeMouseBackend):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)

    class Camera:
        def __init__(self, *args):
            pass

        def __enter__(self):
            self.frames = iter(
                [SimpleNamespace(image=object(), timestamp_ms=1, width=640, height=480)]
            )
            return self

        def __exit__(self, *args):
            return None

        def read_latest(self, _timeout):
            return next(self.frames)

    class Landmarker:
        def __init__(self, *args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def submit(self, *_args):
            return True

        def poll_latest(self):
            return None

    fake_cv2 = SimpleNamespace(
        imshow=lambda *args: None, waitKey=lambda *_args: ord("k"), destroyAllWindows=lambda: None
    )
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)
    monkeypatch.setattr(onboarding, "available_model", lambda *_args: model)
    monkeypatch.setattr(onboarding, "select_camera_index", lambda *_args: 0)
    monkeypatch.setattr(onboarding, "Camera", Camera)
    monkeypatch.setattr(onboarding, "HandLandmarker", Landmarker)
    monkeypatch.setattr(onboarding, "FakeMouseBackend", RecordingFake)
    monkeypatch.setattr(onboarding, "draw_overlay", lambda image, *_args: image)
    monkeypatch.setattr(onboarding, "set_onboarding_completed", lambda *_args: None)

    assert onboarding.run_tutorial(default_config()) == 0
    assert len(created) == 1
    assert created[0].events == []

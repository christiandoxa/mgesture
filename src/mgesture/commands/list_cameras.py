from __future__ import annotations

from mgesture.vision.camera import CameraError, probe_cameras


def list_cameras(limit: int = 8, width: int = 640, height: int = 480, target_fps: int = 30) -> int:
    try:
        cameras = probe_cameras(limit, width, height, target_fps)
    except CameraError as exc:
        raise RuntimeError(str(exc)) from exc
    found = 0
    for camera in cameras:
        if camera.opened:
            print(camera.detail)
            found += 1
    if not found:
        print("No cameras opened.")
    return 0

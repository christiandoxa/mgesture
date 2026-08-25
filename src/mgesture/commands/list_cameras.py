from __future__ import annotations


def list_cameras(limit: int = 8) -> int:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("camera listing needs OpenCV; run `pixi install`") from exc
    found = 0
    for index in range(limit):
        capture = cv2.VideoCapture(index)
        if capture.isOpened():
            ok, _ = capture.read()
            print(
                f"{index}: opened={capture.isOpened()} read={ok} backend={capture.getBackendName()}"
            )
            found += 1
        capture.release()
    if not found:
        print("No cameras opened.")
    return 0

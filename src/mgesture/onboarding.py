from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from .application import engine_config
from .config import AppConfig, set_onboarding_completed
from .engine import ActionBatch, Button, LandmarkFrame, PythonGestureEngine
from .input import FakeMouseBackend, InputDispatcher, Monitor, ScreenLayout
from .vision import Camera, HandLandmarker, available_model, select_camera_index
from .vision.overlay import draw_overlay

_STEPS = (
    ("Selected hand", "Show your selected physical hand to the camera."),
    (
        "Move the pointer",
        "Move your selected hand's index finger through the left, center, and right areas.",
    ),
    ("Left click", "Pinch your thumb and index finger together, then release."),
    ("Hold and drag", "Keep the thumb-index pinch held while moving, then release."),
    ("Right click", "Pinch your thumb and middle finger together, then release."),
    (
        "Scroll",
        "Raise index and middle, relax ring and pinky, hold until Scroll mode is active, then move up and down.",
    ),
    ("Pause and resume", "Use the configured shortcut to pause, then press it again to resume."),
)


def _advance(step: int, progress: dict[str, Any]) -> int:
    progress.clear()
    return step + 1


def run_tutorial(config: AppConfig) -> int:
    """Run one safe tutorial using the production engine and a fake mouse."""
    try:
        import cv2
    except ImportError as exc:
        print("mgesture tutorial: preview needs OpenCV; run `pixi install`", flush=True)
        del exc
        return 1

    model = (
        available_model(Path(config.vision.model_path))
        if config.vision.model_path
        else available_model()
    )
    if model is None:
        print(
            "mgesture tutorial: hand model is unavailable; run `mgesture model install`",
            flush=True,
        )
        return 1
    camera_index = select_camera_index(
        config.camera.index,
        config.camera.width,
        config.camera.height,
        config.camera.target_fps,
    )
    if camera_index is None:
        print(
            "mgesture tutorial: no usable camera found; run `mgesture list-cameras` or `mgesture doctor`",
            flush=True,
        )
        return 1

    fake = FakeMouseBackend(
        ScreenLayout(
            (Monitor("tutorial", 0, 0, config.display.width, config.display.height, True),)
        )
    )
    dispatcher = InputDispatcher(fake)
    tutorial_config = replace(
        config,
        gesture=replace(config.gesture, activation_gesture=False),
    )
    engine = PythonGestureEngine(engine_config(tutorial_config, fake), armed=True)
    batch = ActionBatch((), engine.state, engine.name)
    progress: dict[str, Any] = {}
    step = 0
    last_result = -1
    calibrate_after = False
    completed = False
    last_success = ""
    selected_hand = config.vision.hand_selection.value
    selected_hand_label = selected_hand if selected_hand in ("left", "right") else "selected"

    print(
        "Welcome to mgesture. This short tutorial uses simulated input only; it cannot move or click your real mouse."
    )
    print("Press K to skip, Q or Escape to stop safely.")
    try:
        with (
            Camera(
                camera_index,
                config.camera.width,
                config.camera.height,
                config.camera.target_fps,
            ) as camera,
            HandLandmarker(
                str(model),
                config.vision.detection_confidence,
                config.vision.presence_confidence,
                config.vision.tracking_confidence,
                "cpu",
                config.vision.handedness_mirrored_input,
                config.vision.hand_selection,
            ) as landmarker,
        ):
            while True:
                captured = camera.read_latest(0.25)
                if captured is None:
                    continue
                landmarker.submit(captured.image, captured.timestamp_ms)
                result = landmarker.poll_latest()
                display_landmarks: tuple[float, ...] | None = None
                if result is not None and result.timestamp_ms > last_result:
                    last_result = result.timestamp_ms
                    if result.hand is None:
                        frame = LandmarkFrame(
                            result.timestamp_ms,
                            (0.0,) * 63,
                            "Unknown",
                            0.0,
                            captured.width,
                            captured.height,
                        )
                    else:
                        frame = replace(
                            result.hand.frame,
                            width=captured.width,
                            height=captured.height,
                        )
                        display_landmarks = tuple(frame.landmarks)
                    batch = engine.process(frame)
                    start = len(fake.events)
                    dispatcher.dispatch(batch)
                    events = fake.events[start:]

                    if step == 0:
                        if batch.diagnostics.get("valid_hand") is True:
                            progress["right_frames"] = progress.get("right_frames", 0) + 1
                        else:
                            progress["right_frames"] = 0
                        if progress.get("right_frames", 0) >= 5:
                            last_success = "✓ Selected hand detected"
                            step = _advance(step, progress)
                    elif step == 1:
                        for event in events:
                            if event.kind == "move_absolute" and event.x is not None:
                                progress.setdefault("pointer_bins", set()).add(
                                    min(2, max(0, int(event.x / max(1, config.display.width) * 3)))
                                )
                        if len(progress.get("pointer_bins", set())) >= 3:
                            last_success = "✓ Pointer movement detected"
                            step = _advance(step, progress)
                    elif step in (2, 4):
                        button = Button.LEFT if step == 2 else Button.RIGHT
                        for event in events:
                            if event.kind == "button_down" and event.button == button.value:
                                progress["down"] = True
                            if event.kind == "button_up" and event.button == button.value:
                                progress["up"] = True
                        if progress.get("down") and progress.get("up"):
                            last_success = (
                                "✓ Left click detected" if step == 2 else "✓ Right click detected"
                            )
                            step = _advance(step, progress)
                    elif step == 3:
                        for event in events:
                            if event.kind == "button_down" and event.button == Button.LEFT.value:
                                progress["down"] = True
                            elif event.kind == "button_up" and event.button == Button.LEFT.value:
                                progress["up"] = True
                            elif event.kind == "move_absolute" and progress.get("down"):
                                progress["moves"] = progress.get("moves", 0) + 1
                        if (
                            progress.get("down")
                            and progress.get("up")
                            and progress.get("moves", 0) >= 2
                        ):
                            last_success = "✓ Hold and drag detected"
                            step = _advance(step, progress)
                    elif step == 5:
                        for event in events:
                            if event.kind == "scroll" and event.dy is not None:
                                progress["scroll_up"] = (
                                    progress.get("scroll_up", False) or event.dy > 0
                                )
                                progress["scroll_down"] = (
                                    progress.get("scroll_down", False) or event.dy < 0
                                )
                        if progress.get("scroll_up") and progress.get("scroll_down"):
                            last_success = "✓ Scroll up and down detected"
                            step = _advance(step, progress)
                    elif step == 6:
                        if not engine.armed:
                            progress["paused"] = True
                        elif progress.get("paused"):
                            last_success = "✓ Pause and resume understood"
                            step = _advance(step, progress)

                if step >= len(_STEPS):
                    lines = [
                        "Move pointer: selected hand's index finger | Left click: thumb + index",
                        "Hold/drag: keep left pinch | Right click: thumb + middle",
                        "Scroll: index + middle up, ring + pinky relaxed | Pause/resume: shortcut or Space",
                        "Q/Escape or Ctrl+C exits safely. Press C to calibrate, or any other key to start.",
                        "K skips the tutorial at any time; all practice input is simulated.",
                    ]
                else:
                    title, instruction = _STEPS[step]
                    if step == 6:
                        instruction = (
                            f"Press {config.activation_shortcut} to pause, then press it again to resume. "
                            "Space also works in this preview."
                        )
                    lines = [
                        f"Step {step + 1} of {len(_STEPS)} — {title}",
                        instruction,
                        "Practice input is simulated | K skip | Q/Escape stop",
                    ]
                    if last_success:
                        lines.insert(2, last_success)
                    if step == 0 and batch.diagnostics.get("valid_hand") is not True:
                        lines.append(f"Waiting for your {selected_hand_label} hand...")
                    elif step == 0:
                        lines.append(f"{selected_hand_label.title()} hand detected")
                    elif step == 5:
                        fingers_ready = batch.diagnostics.get("scroll_fingers_ready") is True
                        raw_entry_progress = batch.diagnostics.get("scroll_entry_progress", 0.0)
                        entry_progress = (
                            float(raw_entry_progress)
                            if isinstance(raw_entry_progress, (int, float))
                            else 0.0
                        )
                        active = batch.state.value == "SCROLL"
                        lines.extend(
                            [
                                "Finger readiness: "
                                + (
                                    "ready"
                                    if fingers_ready
                                    else "index + middle up; ring + pinky relaxed"
                                ),
                                f"Entry progress: {entry_progress:.0%}",
                                "Scroll mode active"
                                if active
                                else "Hold pose until Scroll mode active",
                                f"Motion: up {'✓' if progress.get('scroll_up') else '—'} | down {'✓' if progress.get('scroll_down') else '—'}",
                            ]
                        )

                overlay = draw_overlay(
                    captured.image,
                    display_landmarks,
                    batch,
                    lines,
                    (
                        config.gesture.active_left,
                        config.gesture.active_top,
                        1.0 - config.gesture.active_right,
                        1.0 - config.gesture.active_bottom,
                    ),
                )
                if step in (1, 3, 5):
                    height, width = overlay.shape[:2]
                    if step in (1, 3):
                        x = int(fake.position[0] / max(1, config.display.width) * width)
                        y = int(fake.position[1] / max(1, config.display.height) * height)
                        cv2.circle(overlay, (x, y), 10, (0, 255, 255), 2)
                    if step == 1:
                        for fraction in (0.2, 0.5, 0.8):
                            cv2.circle(
                                overlay,
                                (int(width * fraction), int(height * 0.8)),
                                14,
                                (255, 180, 0),
                                2,
                            )
                    elif step == 3:
                        cv2.rectangle(
                            overlay,
                            (int(width * 0.15), int(height * 0.65)),
                            (int(width * 0.35), int(height * 0.85)),
                            (255, 180, 0),
                            2,
                        )
                        cv2.rectangle(
                            overlay,
                            (int(width * 0.65), int(height * 0.65)),
                            (int(width * 0.85), int(height * 0.85)),
                            (0, 255, 0),
                            2,
                        )
                    else:
                        cv2.rectangle(
                            overlay,
                            (int(width * 0.25), int(height * 0.2)),
                            (int(width * 0.75), int(height * 0.85)),
                            (255, 180, 0),
                            2,
                        )
                cv2.imshow("mgesture tutorial", overlay)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    return 1
                if key == ord("k"):
                    completed = True
                    break
                if step >= len(_STEPS) and key == ord("c"):
                    calibrate_after = True
                    completed = True
                    break
                if step >= len(_STEPS) and key != 255:
                    completed = True
                    break
                if step == 6 and key == ord(" "):
                    dispatcher.dispatch(engine.set_armed(not engine.armed))
    except KeyboardInterrupt:
        print("Tutorial cancelled safely.", flush=True)
        return 1
    except (OSError, RuntimeError) as exc:
        print(f"mgesture tutorial: {exc}", flush=True)
        return 1
    finally:
        try:
            dispatcher.close()
        except Exception:
            pass
        cv2.destroyAllWindows()

    if not completed:
        return 1
    set_onboarding_completed(True)
    print("Tutorial complete. Starting mgesture with safe defaults.", flush=True)
    if calibrate_after:
        from .commands.calibrate import calibrate

        print("Optional calibration selected; no real mouse input will be emitted.", flush=True)
        calibrate(config)
    return 0

# Troubleshooting

- `model unavailable`: run `mgesture model install`, or set a verified custom `vision.model_path`.
- `camera unavailable`: run `mgesture list-cameras`, check permissions, and close other camera users.
- X11 backend failure: verify `XDG_SESSION_TYPE=x11`, `DISPLAY`, and XTest/pynput access.
- Wayland backend failure: check `/dev/uinput` existence and the narrowly scoped udev helper; the normal app does not require root.
- macOS backend failure: grant Camera and Accessibility permissions to the terminal/app.
- `--engine mojo` failure: run `pixi run mojo-build`; use `--engine python` when the current platform/bindings are unavailable.
- `--compute gpu` failure: use `mgesture doctor --json` to see hardware, MediaPipe delegate, and driver status. `--compute auto` falls back once to CPU.

Never diagnose a stuck button by killing power first; press Escape/Q or Ctrl+C and confirm the OS button state. The runtime calls `release_all()` on all handled shutdown paths.

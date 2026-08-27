# Troubleshooting

- `model unavailable`: run `mgesture model install`, or set a verified custom `vision.model_path`.
- `camera unavailable` or `camera read failed`: run `mgesture list-cameras`, check negotiated mode and permissions, and close other camera users. Runtime retries with bounded backoff; held buttons are released on every detected outage.
- X11 backend failure: verify `DISPLAY`, `xrandr`, and XTest/pynput access; monitor discovery fails closed when the layout cannot be queried.
- Wayland backend failure: verify `XDG_SESSION_TYPE=wayland` or `WAYLAND_DISPLAY`, `/dev/uinput` existence, and the narrowly scoped udev helper; uinput provides relative movement only and the normal app does not require root.
- macOS backend failure: grant Camera and Accessibility permissions to the terminal/app.
- `--engine mojo` failure: run `pixi run mojo-build`; use `--engine python` when the current platform/bindings are unavailable.
- `--compute gpu` failure: use `mgesture doctor --json` to see hardware, MediaPipe delegate, and driver status. `--compute auto` falls back once to CPU.
- Wrong physical hand: replay `mgesture tutorial` to confirm the hand shown by the camera, or try `mgesture --mirror on` and `mgesture --mirror off` for a one-session inference-orientation override. Preview mirroring is independent.
- Scroll is not detected: raise index and middle, relax or fold ring and pinky, keep the thumb out of a deliberate pinch, hold until `Scroll mode active`, then move the whole palm rather than only the fingertips.
- Reset safely with `mgesture --reset --dry-run` to inspect the mutable paths. `mgesture --reset` preserves the installed executable and bundled release; `mgesture update` preserves user data while replacing the application transactionally.

For local developer fixtures, use the opt-in command `mgesture record-landmarks --developer --output ./recordings/hand.jsonl`. It writes timestamped landmark JSON lines only; it never writes camera images or sends data anywhere.

Never diagnose a stuck button by killing power first; press Escape/Q or Ctrl+C and confirm the OS button state. The runtime calls `release_all()` on all handled shutdown paths.

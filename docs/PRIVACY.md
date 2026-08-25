# Privacy

- Webcam processing is local to the host.
- Frames are not uploaded, transmitted, or saved by default.
- No telemetry, analytics, cloud dependency, or account is required.
- The MediaPipe model is downloaded only by the explicit `mgesture model install` command.
- Calibration and replay use no real mouse clicks; replay uses the fake backend.
- Future debug recording, if added, must remain opt-in, visibly warned, and local.

The optional model download is an explicit user action and records the source, checksum, and license beside the cached model. Stop the application with Escape, Q, or Ctrl+C; all held buttons are released during shutdown.

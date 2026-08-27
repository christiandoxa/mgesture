# Configuration

`mgesture config path` prints the OS-specific TOML path. `mgesture config show` prints defaults or the loaded file. `mgesture config write-example --path ./config.toml` writes a private example.

Important sections are `[camera]`, `[vision]`, `[display]`, `[gesture]`, `[input]`, `[compute]`, and `[performance]`. `vision.handedness_mirrored_input` documents whether the camera buffer is already mirrored; the default OpenCV path is unmirrored and normalizes MediaPipe's handedness label accordingly. `compute.mode` is independent from `input.engine`; both accept `auto` plus their explicit choices. `performance.profile` is `balanced`, `performance`, or `efficiency`.

Camera startup applies requested width, height, and FPS, then reports negotiated values in `list-cameras`, `doctor --json`, logs, and the preview. Camera index is selected with `[camera].index` or `run --camera`; read outages use a capped local reconnect backoff and release held buttons.

`calibrate --output PATH --samples N` collects robust open-hand and pinch observations, then updates existing pinch thresholds only after enough valid right-hand samples. Calibration never creates an input backend. No configuration migration is needed; omitted fields retain defaults.

The configuration validator rejects invalid thresholds, margins, confidence values, backends, engine/compute selectors, and FPS relationships before runtime.

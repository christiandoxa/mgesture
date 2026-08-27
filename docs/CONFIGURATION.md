# Configuration

`mgesture config path` prints the OS-specific TOML path. `mgesture config show` prints defaults or the loaded file. `mgesture config write-example --path ./config.toml` writes a private example.

Important sections are `[camera]`, `[vision]`, `[display]`, `[gesture]`, `[input]`, `[compute]`, and `[performance]`. `vision.hand_selection` accepts `right`, `left`, `either`, or `auto` and defaults to `right` for backward-compatible behavior. `either` locks the first eligible physical hand; `auto` prefers physical right and falls back to left. Both detect two hands in one MediaPipe call and keep one physical hand locked until a replacement is stable. `vision.handedness_mirrored_input` describes the image actually sent to MediaPipe: the default OpenCV buffer is unmirrored, so its MediaPipe label is normalized to physical left/right. `camera.mirror` only controls the user-facing preview and horizontal pointer mapping; it does not change the inference buffer or label normalization. `compute.mode` is independent from `input.engine`; both accept `auto` plus their explicit choices. `performance.profile` is `balanced`, `performance`, or `efficiency`.

Camera startup applies requested width, height, and FPS, then reports negotiated values in `list-cameras`, `doctor --json`, logs, and the preview. Camera index is selected with `[camera].index` or `run --camera`; read outages use a capped local reconnect backoff and release held buttons.

`calibrate --output PATH --samples N` collects robust open-hand and pinch observations from the selected physical hand, then updates existing pinch thresholds only after enough valid samples. Calibration never creates an input backend. No configuration migration is needed; omitted fields retain defaults.

Normal startup is `mgesture`; `mgesture run` remains an explicit alias. On first launch, a completed flag is stored in the platform user-data directory and the safe tutorial runs before real input. `mgesture tutorial` replays it without changing settings. `mgesture --reset` removes mgesture user configuration, state, cache, logs, and recordings under the platform directories after confirmation; it keeps installed application files and bundled assets.

The configuration validator rejects invalid thresholds, margins, confidence values, backends, engine/compute selectors, and FPS relationships before runtime.

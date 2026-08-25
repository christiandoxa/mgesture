# Configuration

`mgesture config path` prints the OS-specific TOML path. `mgesture config show` prints defaults or the loaded file. `mgesture config write-example --path ./config.toml` writes a private example.

Important sections are `[camera]`, `[vision]`, `[display]`, `[gesture]`, `[input]`, `[compute]`, and `[performance]`. `vision.handedness_mirrored_input` documents whether the camera buffer is already mirrored; the default OpenCV path is unmirrored and normalizes MediaPipe's handedness label accordingly. `compute.mode` is independent from `input.engine`; both accept `auto` plus their explicit choices. `performance.profile` is `balanced`, `performance`, or `efficiency`.

The configuration validator rejects invalid thresholds, margins, confidence values, backends, engine/compute selectors, and FPS relationships before runtime.

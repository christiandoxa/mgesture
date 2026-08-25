# mgesture

Local webcam hand gestures for safe desktop mouse control.

mgesture keeps camera frames on the machine, starts paused, and converts one right-hand landmark stream into typed mouse actions. The Python engine is the reference behavior. Stable Mojo is optional on supported Linux/macOS environments; native Windows uses Python. Compute selection is independent: `--compute auto|gpu|cpu` controls vision inference, while `--engine auto|mojo|python` controls gesture processing.

## Installation

### Linux and macOS

```sh
curl -fsSL https://github.com/christiandoxa/mgesture/releases/latest/download/install.sh | sh
```

### Windows

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://github.com/christiandoxa/mgesture/releases/latest/download/install.ps1 | iex"
```

Then run:

```sh
mgesture --version
mgesture doctor
mgesture calibrate
mgesture
```

Release installers verify the checksum-covered release manifest and staged archive before activation. They install a self-contained runtime; Python, Pixi, and Mojo are not required. The latest-release installer source is also auditable at `https://raw.githubusercontent.com/christiandoxa/mgesture/main/install.sh` and `https://raw.githubusercontent.com/christiandoxa/mgesture/main/install.ps1`; release URLs are recommended for stable installation.

Standalone target availability is reported in [docs/PLATFORM_SUPPORT.md](docs/PLATFORM_SUPPORT.md). Unsupported target dependencies fail explicitly instead of selecting a misleading archive.

## Status

The current version contains a runnable CLI, deterministic Python engine, fake-backend replay, explicit model management, bounded camera/MediaPipe pipeline, Linux X11/Wayland-uinput/Windows/macOS adapters, centralized compute planning, and stable-Mojo build scaffolding. Hardware and cross-platform claims below are intentionally conservative; run `mgesture doctor` on the target machine.

## Zorin OS quick start

```bash
curl -fsSL https://pixi.sh/install.sh | bash
export PATH="$HOME/.pixi/bin:$PATH"
cd /path/to/mgesture
pixi install
pixi run python -m mgesture model install
pixi run python -m mgesture doctor
pixi run python -m mgesture run --engine python --compute auto
```

The application opens paused. Use the preview Space key to arm/pause; `Q` or Escape is an emergency stop. Start with `--backend fake` only for development/replay. X11 requires a working `DISPLAY`. Wayland requires the narrowly scoped uinput setup described in `docs/PLATFORM_SUPPORT.md`.

## Commands

```bash
mgesture --help
mgesture doctor [--json]
mgesture doctor --runtime --json
mgesture list-cameras
mgesture model install
mgesture calibrate
mgesture replay --fixture tests/fixtures/basic.json
mgesture run --engine auto --compute auto --profile balanced
mgesture benchmark --engine compare --compute cpu
mgesture benchmark --compare-compute
mgesture self-test --headless --fake-input
mgesture update --check
mgesture update
mgesture config show
mgesture config path
```

`MGESTURE_ENGINE=auto|mojo|python` and `MGESTURE_COMPUTE=auto|gpu|cpu` are equivalent environment controls. `auto` may fall back; explicit `mojo` and `gpu` fail with an actionable error when unavailable.

## Gesture reference

- Index fingertip controls the pointer inside a configurable active camera region.
- Thumb-index pinch presses and holds the left button; release produces the corresponding up event, so drag-and-drop is natural.
- Thumb-middle pinch presses and holds the right button.
- Index and middle extended with ring and pinky folded enters vertical scroll after a stability delay; pointer movement is locked while scrolling.
- Low-confidence/left-hand input is ignored. Hand loss, pause, errors, signals, camera failure, and exit release every held button.

See [docs/GESTURES.md](docs/GESTURES.md) for thresholds, precedence, and replay cases.

## Compute architecture

Acceleration is reported by layer rather than as a blanket claim:

```text
camera capture       CPU / V4L2 or platform camera
preprocessing        CPU color conversion
hand inference       MediaPipe CPU or successfully initialized GPU delegate
gesture processing   Python CPU or persistent Mojo CPU
preview              CPU/OpenCV
mouse dispatch       platform backend
```

The 21x3 landmark workload stays on CPU unless an end-to-end benchmark proves a GPU path faster. `auto` probes hardware and MediaPipe capability, tries GPU inference when appropriate, and switches once to CPU on initialization failure after releasing input state. `gpu` never silently falls back.

## Development

```bash
pixi install
pixi run test
pixi run lint
pixi run format
pixi run typecheck
pixi run build
pixi run mojo-build
pixi run mojo-test
```

The model is downloaded only by `model install`, stored in the OS cache, and verified against a pinned SHA-256. It is not downloaded at launch.

`mgesture update` is explicit and stages the latest target through the same installer verification path. Unix uninstall is `install.sh --uninstall`; PowerShell uninstall is `install.ps1 -Uninstall`. Neither removes configuration or calibration by default.

## Privacy

Processing is local. Frames are not uploaded, saved, or sent to telemetry by default. Optional debug recording is not enabled by the runtime. See [docs/PRIVACY.md](docs/PRIVACY.md).

## Indonesian quick start

```bash
export PATH="$HOME/.pixi/bin:$PATH"
pixi install
pixi run python -m mgesture model install
pixi run python -m mgesture doctor
pixi run python -m mgesture run --engine python --compute auto
```

Aplikasi mulai dalam keadaan jeda untuk mencegah klik tidak sengaja. Tekan Space pada pratinjau untuk mengaktifkan, dan Q atau Escape untuk berhenti darurat. Kamera diproses secara lokal; frame tidak diunggah dan telemetri tidak digunakan.

## Known limitations

MediaPipe Python GPU delegate support is platform/package-specific and must initialize successfully; no GPU claim is made from hardware presence alone. Wayland uinput needs user permission and currently reports a primary 1920x1080 layout unless a platform-specific layout provider is added. Native Mojo is not claimed on Windows. Webcam and real-pointer behavior remain hardware/manual checks, not ordinary CI checks.

License: Apache-2.0 for this project. MediaPipe and its model retain their upstream licenses and terms.

# mgesture

Local webcam hand gestures for safe desktop mouse control.

## Installation

### Linux

```sh
curl -fsSL https://github.com/christiandoxa/mgesture/releases/latest/download/install.sh | sh
```

### macOS

```sh
curl -fsSL https://github.com/christiandoxa/mgesture/releases/latest/download/install.sh | sh
```

### Windows

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://github.com/christiandoxa/mgesture/releases/latest/download/install.ps1 | iex"
```

The standalone installers verify the release manifest and checksums before activating a
versioned, self-contained application. Python, Pixi, and a Mojo compiler are not required.

## Quick start

After installing, simply run:

```sh
mgesture
```

That’s it. mgesture automatically selects the available camera, compute backend, gesture
engine, and supported desktop input backend using safe defaults. It starts paused; press the
configured shortcut shown at startup (`ctrl+alt+m` by default) to activate it. Press the same
shortcut again to pause. Use `mgesture config show` to confirm the configured shortcut.

On the first launch, mgesture asks which hand you want to use and guides you through a short
interactive tutorial. Later launches go straight to normal operation with your saved settings.

## How to use mgesture

mgesture can use your physical right or left hand. Choose a hand during the first-run tutorial;
the same gesture meanings apply to either hand. The preview shows the selected hand and current
state.

| Mouse action | Hand gesture |
|---|---|
| Move cursor | Move the selected hand’s index finger |
| Left click | Pinch thumb and index finger, then release |
| Hold | Keep thumb and index finger pinched |
| Drag and drop | Keep the left pinch held while moving |
| Right click | Pinch thumb and middle finger, then release |
| Right hold | Keep thumb and middle finger pinched |
| Scroll | Raise index and middle, relax/fold ring and pinky, keep the thumb relaxed, hold briefly, then move the whole hand vertically |
| Pause / resume | Use the configured shortcut or the optional open-palm gesture |
| Exit safely | Press Q/Escape in the preview or Ctrl+C in the terminal |

Scroll has two phases: hold the index-plus-middle pose until **Scroll mode active** appears,
then move your whole hand. Small fingertip movements are intentionally ignored.

## First run

The first time you run `mgesture`, the safe tutorial teaches hand selection, camera
handedness, pointer movement, left click, hold and drag, right click, scrolling, pause/resume,
and emergency stop. It uses the real camera and production gesture engine with a fake input
backend, so practice cannot move or click the real mouse. If you stop before completing it, the
tutorial runs again next time. At the pause/resume step, press the configured shortcut once to
pause and again to resume; `Space` is the preview-only fallback. Press `K` to skip.

## Calibration

Calibration is optional but recommended when you want to tune pinch thresholds for your hand and
camera:

```sh
mgesture calibrate
```

Calibration collects multiple observations and uses observation-only input; it never emits real
mouse clicks.

## Replay the tutorial

Practice again without deleting calibration or settings:

```sh
mgesture tutorial
```

Use `mgesture tutorial --hand left` or `--hand right` for a one-session hand override. Use
`--mirror auto`, `--mirror on`, or `--mirror off` to retry the camera handedness interpretation.

## Update mgesture

Updates are explicit and target the latest stable release for the current native platform:

```sh
mgesture update
```

Only check for an update without downloading it:

```sh
mgesture update --check
```

The updater verifies the target manifest and SHA-256 checksum, stages and self-tests the new
release, and activates it transactionally. Configuration, calibration, hand selection, and
onboarding state are preserved. A failed update leaves the current installation unchanged.

## Reset mgesture

Reset clears mgesture user state—configuration, calibration, preferences, onboarding state,
recordings, cache, and logs—without uninstalling the application:

```sh
mgesture --reset
```

Reset asks for confirmation. Preview the exact reset plan without deleting anything:

```sh
mgesture --reset --dry-run
```

For deliberate non-interactive use:

```sh
mgesture --reset --yes
```

The installed executable, release directories, bundled Python/MediaPipe runtime, native Mojo
library, and bundled model are protected. After reset, run `mgesture` to see the first-run
tutorial again. Reset is not uninstall; uninstall removes the installed application.

| Command | Application files | User state |
|---|---|---|
| `mgesture --reset` | Preserved | Reset |
| `mgesture update` | Updated safely | Preserved |
| Uninstall | Removed | Preserved or purged according to uninstall options |

## Safety

mgesture starts paused, never clicks during onboarding or calibration, and releases held buttons
on pause, hand loss, camera failure, exceptions, signals, and normal exit. Keep the configured
pause shortcut available as an emergency stop. Camera frames stay local and are not saved or
uploaded by default.

## Linux

Linux X11 uses the native XTest/pynput path. Linux Wayland uses the supported relative-input
backend and may require `/dev/uinput` permission. See [docs/PLATFORM_SUPPORT.md](docs/PLATFORM_SUPPORT.md)
for technology-specific setup and diagnostics.

## macOS

Grant Camera and Accessibility permission to the terminal or application. Pointer coordinates use
logical display points, including negative coordinates for a monitor positioned left of primary.

## Windows

The standalone package is native for x86_64 and ARM64 Windows. It uses `SendInput`, enables
per-monitor DPI awareness, and maps the virtual desktop, including negative monitor coordinates.
WSL is not supported.

## Standalone platforms

| Platform | Architecture | Standalone | Vision | Mojo source | Python engine |
|---|---|---:|---|---:|---:|
| Linux | x86_64 | Yes | Yes (MediaPipe) | Yes | Yes |
| Linux | ARM64 | Yes | Yes (MediaPipe 1.0.1) | Yes | Yes |
| macOS | Intel x86_64 | Yes | Yes (MediaPipe 0.10.21) | Yes | Yes |
| macOS | Apple Silicon ARM64 | Yes | Yes (MediaPipe 0.10.35) | Yes | Yes |
| Windows | x86_64 | Yes | Yes (MediaPipe 0.10.35) | Yes | Yes |
| Windows | ARM64 | Yes | Yes (MediaPipe 0.10.35) | Yes | Yes |

All six standalone targets include the canonical Mojo source, a target-native Mojo engine, the
Python fallback, a verified model, checksums, a release manifest, an SBOM, and provenance
metadata. Camera and real-pointer behavior still require manual hardware validation.

## Troubleshooting

If startup cannot access a camera, input backend, compute option, or operating-system permission:

```sh
mgesture doctor
mgesture list-cameras
```

### Linux/X11 input problems

Run `mgesture doctor` and fix the failing capability:

- `X11 display`: `DISPLAY` is missing or the X server cannot be reached.
- `X11 XTest`: the XTest extension is unavailable.
- `xrandr`: the command is missing; install it and retry.
- `pynput capabilities`: a missing packaged `pynput` dynamic module means the standalone
  bundle is incomplete; reinstall the bundle. This is separate from `DISPLAY`, XTest, and
  `xrandr` setup.

### mgesture detects the wrong hand

Replay the tutorial and confirm the physical hand shown by the preview:

```sh
mgesture tutorial
```

For a one-session diagnostic override, try `mgesture --mirror on` or `mgesture --mirror off`.
Preview mirroring and physical-hand interpretation are independent.

### Scroll gesture is not detected

Raise only index and middle, relax or fold ring and pinky, do not make a deliberate thumb pinch,
wait for **Scroll mode active**, and move the whole hand rather than only the fingertips. If it
still needs tuning, run `mgesture calibrate`.

For developer-only, privacy-safe landmark recordings:

```sh
mgesture record-landmarks --developer --output ./recordings/hand.jsonl
```

Recordings contain landmarks rather than camera frames, but they can still reveal behavioral
information and should be treated as user data. Nothing is uploaded.

## Advanced usage

The explicit `run` form remains available for scripts and power users:

```sh
mgesture run --compute cpu
mgesture run --compute gpu
mgesture run --engine python
mgesture run --engine mojo
mgesture run --hand left
mgesture run --mirror off
mgesture list-cameras
mgesture doctor --json
mgesture benchmark --engine compare --compute cpu
```

Normally leave engine, compute, camera, backend, profile, and mirror selection at their safe
automatic defaults. Configuration can be inspected with `mgesture config show` and
`mgesture config path`.

## Development

```sh
pixi install
pixi run test
pixi run lint
pixi run format
pixi run typecheck
pixi run build
pixi run mojo-build
pixi run mojo-test
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/GESTURES.md](docs/GESTURES.md),
[docs/CONFIGURATION.md](docs/CONFIGURATION.md), [docs/PLATFORM_SUPPORT.md](docs/PLATFORM_SUPPORT.md),
[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md), and [docs/PRIVACY.md](docs/PRIVACY.md).

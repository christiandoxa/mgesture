# mgesture

Local webcam hand gestures for safe desktop mouse control.

## Installation

### Linux and macOS

```sh
curl -fsSL https://github.com/christiandoxa/mgesture/releases/latest/download/install.sh | sh
```

### Windows

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://github.com/christiandoxa/mgesture/releases/latest/download/install.ps1 | iex"
```

## Quick start

After installing, simply run:

```sh
mgesture
```

That’s it. mgesture automatically selects the available camera, compute backend, gesture engine, and desktop input backend using safe defaults. It starts paused; press the configured shortcut shown at startup to activate it.

On the first launch, mgesture opens a short safe tutorial. It teaches pointer movement, clicking, holding, dragging, scrolling, pausing, and safe exit using simulated input before normal mouse control is enabled. Later launches go straight to normal operation.

## How to use mgesture

Use your right hand. The preview shows the active camera region and current state.

| Mouse action | Hand gesture |
|---|---|
| Move cursor | Move your right index finger |
| Left click | Pinch thumb and index finger, then release |
| Hold | Keep thumb and index finger pinched |
| Drag and drop | Keep the left pinch held while moving |
| Right click | Pinch thumb and middle finger, then release |
| Right hold | Keep thumb and middle finger pinched |
| Scroll | Extend index and middle fingers, fold ring and pinky, then move vertically |
| Pause / resume | Use the configured shortcut or the optional open-palm gesture |
| Exit safely | Press Q/Escape in the preview or Ctrl+C in the terminal |

## First run

The first time you run `mgesture`, an interactive tutorial asks you to show your right hand and practice each gesture. It uses the real camera and canonical gesture engine, but a fake input backend: tutorial practice cannot move or click the real mouse. Press `K` to skip; skipping marks onboarding complete. If you stop before completion, the tutorial runs again next time.

Want to practice again?

```sh
mgesture tutorial
```

Replaying the tutorial does not remove calibration or settings.

## Calibration

Calibration is optional. Run it once if you want to tune sensitivity for your hand, camera position, pinch distance, pointer range, or scrolling:

```sh
mgesture calibrate
```

Calibration uses observation only and never emits real mouse clicks. It collects multiple samples and saves only after enough valid observations.

## Reset mgesture

To clear mgesture user configuration, calibration, preferences, tutorial state, recordings, and application-owned cached data under its platform directories:

```sh
mgesture --reset
```

Reset asks for confirmation and does not uninstall mgesture or remove bundled application files. For deliberate non-interactive use:

```sh
mgesture --reset --yes
```

After reset, `mgesture` shows the first-run tutorial again. Reset is different from uninstall: reset clears user state; uninstall removes the installed application.

## Safety

mgesture starts paused, never clicks during calibration or onboarding, and releases held buttons on pause, hand loss, camera failure, exceptions, signals, and normal exit. Keep the configured keyboard shortcut available as an emergency stop. Camera frames stay local and are not saved or uploaded by default.

## Linux

Linux X11 uses the native XTest/pynput path and discovers the X11 monitor layout through `xrandr`. Linux Wayland uses `/dev/uinput` for relative pointer events; grant the required device permission as described in [docs/PLATFORM_SUPPORT.md](docs/PLATFORM_SUPPORT.md). The application reports actionable permission and camera errors.

## macOS

Grant Camera and Accessibility permission to the terminal or application. Quartz coordinates use logical display points, including negative coordinates for a monitor positioned left of the primary display.

## Windows

The standalone package is native for x86_64 and ARM64 Windows. It uses `SendInput`, enables per-monitor DPI awareness, and maps the Windows virtual desktop, including negative monitor coordinates. WSL is not supported.

## Standalone platforms

| Platform | Architecture | Standalone | Vision | Mojo source | Python engine |
|---|---|---:|---|---:|---:|
| Linux | x86_64 | Yes | Yes (MediaPipe) | Yes | Yes |
| Linux | ARM64 | Yes | Yes (MediaPipe 1.0.1) | Yes | Yes |
| macOS | Intel x86_64 | Yes | Yes (MediaPipe 0.10.21) | Yes | Yes |
| macOS | Apple Silicon ARM64 | Yes | Yes (MediaPipe 0.10.35) | Yes | Yes |
| Windows | x86_64 | Yes | Yes (MediaPipe 0.10.35) | Yes | Yes |
| Windows | ARM64 | Yes | Yes (MediaPipe 0.10.35) | Yes | Yes |

All six standalone targets include the same canonical Mojo source, a native Mojo engine, and the Python fallback. Camera, Accessibility, and real-pointer behavior still need manual hardware validation.

## Troubleshooting

If startup cannot access a camera, input backend, compute option, or operating-system permission, run:

```sh
mgesture doctor
mgesture list-cameras
```

For local developer fixtures, use the explicit opt-in landmark recorder:

```sh
mgesture record-landmarks --developer --output ./recordings/hand.jsonl
```

It writes timestamped landmarks only, never camera images, and never sends data anywhere. Landmark recordings can still reveal behavioral information and should be treated as user data.

## Advanced usage

The explicit `run` form remains available for scripts and power users:

```sh
mgesture run --compute cpu
mgesture run --compute gpu
mgesture run --engine python
mgesture run --engine mojo
mgesture list-cameras
mgesture doctor --json
mgesture benchmark --engine compare --compute cpu
```

Normally, leave engine, compute, camera, backend, and profile selection at their safe `auto`/balanced defaults. Configuration is available with `mgesture config show`, `mgesture config path`, and `mgesture config write-example`.

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

The model is downloaded only by the explicit `mgesture model install` command and stored in the OS cache. Standalone releases bundle a verified model, native Mojo engine, Python fallback, checksums, manifest, SBOM, and provenance metadata for six native targets.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/GESTURES.md](docs/GESTURES.md), [docs/CONFIGURATION.md](docs/CONFIGURATION.md), [docs/PLATFORM_SUPPORT.md](docs/PLATFORM_SUPPORT.md), [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md), and [docs/PRIVACY.md](docs/PRIVACY.md) for engineering and platform details.

# Changelog

## [Unreleased]

## [0.3.1] - 2026-08-27

### Fixed

- Fixed `mgesture update --check` and `mgesture update` failing TLS verification in standalone bundles by using the bundled `certifi` trust store when available.

### Safety

- Kept release metadata HTTPS verification, manifest validation, checksum validation, staged self-tests, and transactional activation unchanged.

## [0.3.0] - 2026-08-27

### Added

- Added physical hand selection modes (`right`, `left`, `either`, and `auto`) with stable two-hand locking and the same mouse gesture semantics for both hands.
- Added explicit camera handedness interpretation controls (`--mirror auto|on|off`) and one-time tutorial confirmation so MediaPipe labels are normalized independently from preview mirroring and pointer mapping.
- Added `mgesture update` for explicit stable-release updates and `mgesture update --check` for a no-download check.
- Added `mgesture --reset --dry-run` to preview the exact mutable user-state reset plan.

### Changed

- Improved two-finger scrolling with palm-normalized finger reach/straightness, relaxed ring/pinky handling, thumb pinch-down arbitration, time-based entry, and active-state grace for brief landmark dropouts.
- Extended tutorial and debug diagnostics with selected-hand status, scroll finger readiness, entry progress, active state, displacement, remainder, and block reason.
- Bumped the native Mojo ABI to version 2 for the scroll exit-grace configuration while keeping the Python reference fallback and parity contract.

### Fixed

- Fixed physical left/right hand interpretation when the camera buffer and MediaPipe's mirrored-input convention differ.
- Fixed natural two-finger scroll poses being rejected by the old single distance-ratio classifier or being reset by brief landmark jitter.
- Fixed `mgesture --reset` recursively deleting standalone application files when the installer root shared the platform user-data directory.
- Fixed Unix release activation during updates so replacing the `current` pointer does not move the new pointer into the old release directory.

### Safety

- Reset now validates an explicit mutable-path allowlist, protects executables, release roots, runtimes, models, and metadata, and removes symlinks without following them.
- Updates verify the stable target manifest/checksum through the existing installer, stage and self-test before activation, and preserve user configuration and calibration on failure or success.

### Platform

- Kept preview mirroring, inference handedness interpretation, and pointer mirroring as independent cross-platform settings.
- Added extracted-package reset-preservation coverage to the standalone release smoke path.

### Build / CI

- Consolidated platform-independent quality checks into one CI owner while retaining meaningful six-target Python and six-target Mojo validation.
- Added target-, lockfile-, manifest-, and Windows ARM build-flag-aware Pixi environment caching, plus one verified model artifact per CI run.
- Built exact-SHA standalone candidates once in successful main CI and reused those validated bytes in the official release workflow.

### Documentation

- Documented left/right hand control, mirror troubleshooting, precise scroll posing, update/reset ownership, and generic Linux/macOS/Windows platform terminology.

## [0.2.0] - 2026-08-27

### Added

- Added zero-argument startup: `mgesture` is the normal application command while `mgesture run` remains available for scripts.
- Added a safe first-run interactive tutorial, replayable with `mgesture tutorial`; tutorial practice uses the production gesture engine with fake input.
- Added `mgesture --reset` and `--reset --yes` to clear platform user state without removing the installed application or bundled assets.
- Added opt-in developer landmark recording with timestamped JSONL output and no camera-frame recording.

### Changed

- Calibration now collects multiple valid observations and derives robust pinch thresholds without emitting mouse input.
- Camera selection, negotiated camera mode reporting, and platform input diagnostics now use automatic safe defaults.

### Fixed

- Hardened pinch arbitration, invalid-landmark handling, release hysteresis, scroll dead-zone behavior, and reacquisition state.
- Fixed stale asynchronous vision results and camera read failures from reaching gesture processing.
- Fixed desktop input cleanup after dispatch, backend, signal, and shutdown failures.

### Performance

- Bounded camera and MediaPipe handoff to newest-frame/newest-result processing, with capped reconnect backoff and adaptive idle scheduling.

### Platform

- Improved Linux X11 monitor discovery and Wayland relative-input diagnostics.
- Added macOS logical multi-display layout handling and Windows per-monitor DPI-aware virtual-desktop mapping.

### Safety

- Tutorial, calibration, replay, and automated tests use observation or fake input; held buttons are released on failure and exit paths.

### Documentation

- Reorganized README around the simple `mgesture` workflow and generic Linux/macOS/Windows platform terminology.
- Standalone bundle target-native binary enforcement from `c01e588` is retained in the release history.

# Changelog

## [Unreleased]

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

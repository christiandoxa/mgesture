# Architecture

Python hosts the portable application because camera capture, MediaPipe Tasks, OpenCV, CLI tooling, configuration, and desktop integration are mature there. The Python engine defines observable gesture semantics.

```text
Camera (bounded newest-frame buffer, reconnect/backoff)
  -> MediaPipe Hand Landmarker LIVE_STREAM (bounded pending/results)
  -> newest normalized LandmarkFrame
  -> Python or Mojo GestureEngine
  -> ActionBatch
  -> MouseBackend
```

The engine owns filtering, normalized palm-scale pinch distances, hysteresis, debounce, hand-loss cleanup, reacquisition, scroll accumulation, pause state, and action ordering. Camera and preview never dispatch mouse events. The input dispatcher translates typed actions and calls the shared idempotent `release_all()` safety contract.

`compute.py` detects hardware and produces an inference/gesture plan. MediaPipe GPU initialization is attempted first when auto selects a usable candidate; auto mode switches once to CPU if initialization fails, while explicit GPU fails clearly. The small 21x3 gesture workload remains CPU/Mojo unless total measurements prove otherwise. `vision/scheduler.py` owns blocking waits and a bounded adaptive rate, reducing work when paused or no hand is tracked. Camera diagnostics report requested and negotiated mode, backend, drops, read failures, reconnects, and observed FPS.

The Mojo boundary is intentionally small: one persistent engine, one frame call, contiguous landmark data, and compact action results. The canonical `.mojo` sources are architecture-independent, included in source distributions and standalone bundles, and recorded with one deterministic source hash. The production core exposes a versioned, fixed-layout C ABI; the Python binding is a thin development adapter, while standalone bundles load the prebuilt native library without a compiler. Source availability is therefore distinct from the build host/toolchain used to produce that library.

The current binding reuses a contiguous Python `array('f')` destination and performs one measured float32 conversion per Mojo frame; current stable bindings do not provide a verified zero-copy path for this object. This conversion cost is measured in the core benchmark and is kept to one call per frame. No unsafe zero-copy claim is made.

Standalone distribution uses a PyInstaller onedir bundle because MediaPipe/OpenCV contain native libraries. `scripts/release/build_bundle.py` stages the bundled model, runtime metadata, licenses, and installers; `install.sh`/`install.ps1` verify checksums and manifests, execute the safe self-test, then atomically activate a versioned release behind a user-local shim. `mgesture update` reuses the same release resolution by invoking the installed canonical installer rather than owning a second archive updater.

## Ownership

- `vision`: capture, inference, model cache, landmark normalization, overlay, local recording.
- `engine`: gesture state machine and typed actions.
- `input`: OS pointer calls and button safety.
- `compute.py`: hardware capability and compute policy.
- `config.py`: defaults, TOML parsing, validation.
- `diagnostics.py`: environment checks and reports.
- `application.py`: composition, scheduling, signal/exception cleanup.

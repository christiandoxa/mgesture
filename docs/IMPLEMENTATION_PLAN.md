# mgesture implementation plan

1. Bootstrap a Pixi-managed Python 3.11 package, typed configuration, CLI, diagnostics, safety contract, fake input backend, and CI.
2. Implement the deterministic Python gesture engine with normalized measurements, filtering, hysteresis, bounded replay, and safety tests.
3. Add explicit model installation, bounded camera capture, MediaPipe LIVE_STREAM landmarking, preview, calibration, and offline replay.
4. Add native input adapters for X11, Wayland uinput, Windows SendInput, and macOS Quartz behind one protocol.
5. Verify stable Mojo 1.0.0 bindings, add a persistent numeric engine, loader, strict selection, parity tests, and measured benchmarks.
6. Add centralized GPU/CPU capability planning, adaptive scheduling, per-layer diagnostics, fallback behavior, docs, CI, and final safety/reuse review.
7. Build standalone PyInstaller archives, transactional installers, update checks, exact-SHA release workflow, checksums, SBOM, provenance, malware scanning, and target-matrix validation.

The first manual validation target is this Zorin OS 18.1 x86_64 X11 machine. No other platform or hardware result is claimed until it is run.

Current verification covers the Linux source/runtime path locally and the six native release lanes in GitHub CI: Python tests, Mojo extension build/native test, Python/Mojo parity, GPU/CPU inference benchmark, standalone extraction, installer fixture install/rollback checksum failure, and safe fake-input runtime smoke. Camera and real-pointer claims remain manual hardware checks.

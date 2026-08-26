# mgesture Engineering Guidelines

## Project principles

- Correctness and safe mouse behavior come before convenience or optimization.
- Keep pointer latency low without wasting CPU or power.
- Use GPU acceleration only after successful initialization and measured benefit.
- Keep CPU-only execution fully functional and first-class.
- Keep platform behavior explicit, local, and privacy-preserving.
- Do not add telemetry, cloud processing, or webcam-frame uploads.
- Follow reuse-first engineering: search, understand, reuse, extend, refactor, then create.

## Repository architecture

The repository uses a `src/` layout:

- `src/mgesture/config.py` owns typed TOML configuration and defaults.
- `src/mgesture/vision/` owns camera capture, MediaPipe landmarks, model files, and overlay presentation.
- `src/mgesture/engine/` owns the Python gesture state machine, action models, loader, and Mojo boundary.
- `src/mgesture/input/` owns the shared mouse protocol, fake backend, and OS-specific dispatch.
- `src/mgesture/compute.py` owns hardware capability detection and compute planning.
- `src/mgesture/vision/scheduler.py` owns adaptive processing-rate policy.
- `src/mgesture/application.py` owns runtime composition, scheduling, dispatch, and cleanup orchestration.
- `src/mgesture/commands/` owns CLI command implementations.
- `src/mgesture/diagnostics.py` owns doctor checks and machine-readable reports.
- `src/mgesture/release.py` owns runtime release resolution/update checks and bundled metadata.
- `src/mgesture/self_test.py` owns the headless packaged fake-input smoke contract.
- `src/mgesture/input/dispatcher.py` owns shared typed-action dispatch and held-button tracking.
- `tests/` contains unit, replay, integration, and fixture tests.
- `mojo/` contains the optional stable-Mojo numeric extension and Mojo-native tests.
- `docs/` contains implementation, architecture, gesture, platform, privacy, troubleshooting, and benchmark documents.
- `scripts/` contains explicit setup/build helpers; scripts must not silently download models or require root.
- `release/targets.toml` is the canonical standalone target matrix.
- `scripts/release/` owns bundle construction, manifest/checksum/SBOM generation, verification, scanning, and release validation.

## Domain boundaries

Vision produces bounded, normalized landmark frames. It never injects mouse events.
The gesture engine alone interprets landmarks into typed actions and state transitions.
The input layer dispatches typed actions and owns release safety; platform files contain only system calls.
Hardware detection and compute policy remain centralized. Configuration is the source of defaults.
The CLI composes existing domain services. Diagnostics report actual status and never claim untested support.
Python defines gesture semantics. Mojo mirrors those semantics and is accepted only after compile and parity checks.

## Reuse-first rule

> Before creating a new implementation, search the repository for existing code that can be reused or extended. Do not duplicate behavior when a canonical implementation already exists.

Extend before duplicate. Parameterize before copy-paste. Move shared behavior to its correct domain.
Preserve one canonical implementation, one set of defaults, one validator, one state machine, and one cleanup contract.
Do not create random utility dumping grounds or duplicate platform detection, coordinate mapping, timing, conversion, or error handling.

Before adding meaningful reusable code, search with `rg` for its names and concepts, inspect callers, and record why reuse is unsuitable when the choice is non-obvious.

## New-code checklist

1. Does this behavior already exist?
2. Can it be reused directly?
3. Can an existing implementation accept a parameter instead?
4. Can a small refactor expose the existing behavior?
5. Which domain should own it?
6. Would it create a second source of truth?
7. Does the abstraction reduce complexity rather than add indirection?

## Utility/helper policy

Do not casually create `utils.py`, `helper.py`, `helpers.py`, `common.py`, or `misc.py`.
Reusable code belongs in a named domain module. A generic module is acceptable only when its concern is truly generic and cohesive.

## Architecture rules

- Keep camera, inference, gesture interpretation, dispatch, preview, configuration, and diagnostics separate.
- Keep OS-specific imports inside OS-specific modules.
- Camera callbacks cannot inject input directly.
- Preview code reads diagnostics; it does not recognize gestures.
- Input backends do not infer gestures.
- Hardware detection and compute planning are centralized.
- No unbounded realtime queues; drop stale frames.
- Models, GPU contexts, and gesture engines are persistent, never created per frame.
- Python/Mojo public behavior stays parity-tested.
- Prefer composition over inheritance and avoid speculative plugin frameworks.

## Code size and maintainability

Avoid god objects, giant functions, duplicate wrappers, dead code, speculative configuration, and unnecessary dependencies.
Use clear names. Comments explain non-obvious reasons, not obvious code.
Public interfaces need useful documentation.

## Dependency rules

Before adding a dependency, check the standard library, existing dependencies, Mojo standard library, license, maintenance, and target-platform support.
Do not add two packages for one job. Pixi is the reproducible development environment; `pyproject.toml` remains conventionally installable.

## Performance rules

- Measure before optimizing or claiming a speedup.
- Benchmark GPU inference against CPU end to end, including transfer and initialization realities.
- Keep tiny 21x3 gesture calculations on optimized CPU/Mojo unless GPU wins measurably.
- Reuse contiguous float32 buffers and avoid needless Python/Mojo crossings.
- Use blocking waits and adaptive scheduling; never busy-spin.
- Keep paused and hand-absent modes lightweight.
- Report each layer independently: camera, preprocessing, inference, gesture, preview, and input.
- CPU-only remains complete and supported.

## Safety and privacy rules

- Every error, pause, hand-loss, signal, camera failure, backend close, and normal exit releases all buttons.
- `release_all()` is idempotent and must not be silently bypassed.
- The app starts disarmed unless the user explicitly arms it.
- Calibration emits no real click by default.
- Automated tests use the fake backend and never move the real cursor.
- Camera frames are local and not saved or uploaded by default.
- No telemetry.

## Commands

Use Pixi from the repository root:

- `pixi install`
- `pixi run python -m mgesture --help`
- `pixi run doctor`
- `pixi run test`
- `pixi run lint`
- `pixi run format`
- `pixi run typecheck`
- `pixi run replay`
- `pixi run benchmark`
- `pixi run build`
- `pixi run mojo-build` on Linux or supported macOS environments
- `pixi run mojo-test` on Linux or supported macOS environments (`mojo run`, not the removed `mojo test` command)
- `pixi run package-local` after the verified model is installed
- `pixi run release-check`
- `pixi run smoke-standalone`

Model setup is explicit: `pixi run python -m mgesture model install`.
Hardware validation uses `pixi run python -m mgesture doctor --json`; real webcam/pointer tests are manual only.

## Mojo compatibility rules

- Pin stable Mojo `1.0.0` where the target Pixi platform provides it.
- Native Mojo support is Linux and supported macOS environments; native Windows uses Python.
- Follow current official syntax and Python binding limits; keep the binding small and below six PythonObject parameters.
- Compile every meaningful Mojo change with `mojo build` and run Mojo tests.
- Mojo owns meaningful persistent numeric state; it is not a cosmetic wrapper.
- Do not claim Mojo or GPU improvement without benchmark evidence.
- If bindings or a platform are unavailable, `--engine mojo` fails clearly; `auto` may use Python.

## Distribution and Releases

- Stable standalone releases target exactly these native platforms:
  `x86_64-unknown-linux-gnu`, `aarch64-unknown-linux-gnu`,
  `x86_64-apple-darwin`, `aarch64-apple-darwin`,
  `x86_64-pc-windows-msvc`, and `aarch64-pc-windows-msvc`.
- Never remove a release target solely to make CI pass, and never publish an
  artifact whose executable architecture differs from its target metadata.
- Platform-specific acceleration must not fork core gesture behavior. Reuse the
  canonical target matrix for workflows, installers, packaging, and manifests.
- Stable release publication requires every mandatory target to pass native
  package smoke tests; call a target supported only after its final bundle runs
  successfully on that native architecture.
- Official end-user distribution is through GitHub Releases, not a source checkout.
- Release users receive standalone bundles; they do not need Python, Pixi, or a Mojo compiler.
- README installation commands remain versionless and use `releases/latest/download`.
- Installers verify `SHA256SUMS`, `release-manifest.json`, `release-manifest.tsv`, staged version output, and the headless fake-input self-test before atomic activation.
- `release/targets.toml` is the single canonical target matrix; unsupported rows are explicit and not published.
- Release bundles include the CPU reference runtime and pinned model where the target is publishable. GPU drivers remain external system dependencies; CPU fallback is always present.
- Build and packaged smoke tests must pass before publication. Release artifacts are executed after packaging.
- The release workflow may publish only an exact full-SHA `main` commit whose normal CI run succeeded.
- GitHub Actions are pinned by immutable commit SHA where practical. Final assets require checksums, SBOM, provenance-attestation configuration, and ClamAV/EICAR scanning.
- No agent may push, tag, create a GitHub Release, mutate settings, or upload artifacts without explicit authorization.
- Platform claims distinguish source implementation, CI/package smoke tests, and manual hardware tests.
- Do not duplicate release behavior in multiple scripts. Target mapping, version semantics, manifest schema, checksum policy, and package metadata each have one canonical owner.
- Before modifying installation or release code, inspect `install.sh`, `install.ps1`, `release/targets.toml`, all `scripts/release/` files, and both workflows together.

## Testing requirements

Behavior changes require unit tests and replay fixtures where appropriate. Use fake input for all automation.
Run tests, Ruff lint/format checks, mypy, and relevant Mojo build/tests before handoff.
Parity tests compare action ordering, state transitions, numeric tolerances, and no-stuck-button invariants.

## Change discipline

At each major phase: read this file, inspect relevant files and usages, search for reusable behavior, implement the smallest needed change, run focused checks, then continue.
After editing, inspect the diff, search for duplicate constants/functions, remove dead code, and update public documentation.

## Definition of done

A change is done only when existing reusable code was considered, no unnecessary duplicate was introduced, tests/lint/type checks pass, relevant Mojo code compiles, docs reflect public behavior, safety paths release buttons, and every performance/platform claim is supported by an actual check.

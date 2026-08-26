# Platform support

| Platform | Architecture | Standalone | Vision backend | Mojo source | Python engine | Native package smoke |
|---|---|---:|---|---:|---:|---|
| Linux | x86_64 | Yes | Yes (MediaPipe) | Yes | Yes | CI/release runner |
| Linux | ARM64 | Yes | Yes (MediaPipe 1.0.1) | Yes | Yes | CI/release runner |
| macOS | Intel x86_64 | Yes | Yes (MediaPipe 0.10.21) | Yes | Yes | CI/release runner |
| macOS | Apple Silicon ARM64 | Yes | Yes (MediaPipe 0.10.35) | Yes | Yes | CI/release runner |
| Windows | x86_64 | Yes | Yes (MediaPipe 0.10.35) | Yes | Yes | CI/release runner |
| Windows | ARM64 | Yes | Yes (MediaPipe 0.10.35) | Yes | Yes | CI/release runner |

Stable releases publish exactly these six native targets. The table above describes source/application capability, not whether a compiler is present on the user's machine. The standalone runtime uses the Python reference engine with CPU fallback; its current native Mojo engine capability is separate:

| Platform | Architecture | MediaPipe runtime | Native Mojo engine | Runtime default |
|---|---|---:|---:|---|
| Linux | x86_64 | Yes | No (not bundled) | Python |
| Linux | ARM64 | Yes | No (not bundled) | Python |
| macOS | Intel x86_64 | Yes | No (toolchain unavailable) | Python |
| macOS | Apple Silicon ARM64 | Yes | No (not bundled) | Python |
| Windows | x86_64 | Yes | No (native compiler unavailable) | Python |
| Windows | ARM64 | Yes | No (native compiler unavailable) | Python |

The macOS Intel lane uses the stable MediaPipe 0.10.21 x86_64 wheel, the last selected stable release with a native Intel macOS wheel. Windows ARM uses a native OpenCV source build with DNN disabled because the selected OpenCV PyPI release has no Windows ARM64 wheel. Source Mojo compilation is covered by matching Linux x86_64/ARM64 and Apple Silicon CI lanes; the standalone native engine remains deliberately false until its runtime libraries can be redistributed and smoke-tested.

All six rows use the same vision, gesture, dispatch, and cleanup architecture. Camera discovery/capture, Accessibility permissions on macOS, `/dev/uinput` permissions on Linux Wayland, and real pointer behavior remain manual hardware checks; ordinary CI uses only fake input and no webcam.

Standalone distribution currently has six publishable matrix rows: `x86_64-unknown-linux-gnu`, `aarch64-unknown-linux-gnu`, `x86_64-apple-darwin`, `aarch64-apple-darwin`, `x86_64-pc-windows-msvc`, and `aarch64-pc-windows-msvc`. Each is packaged as a PyInstaller onedir archive with the pinned model and Python reference engine. Matching-host CI extracts each archive and passes `--version`, `self-test --headless --fake-input`, and runtime diagnostics without system Python or Mojo. Camera, Accessibility, and real-pointer behavior remain manual hardware checks; the Windows ARM build uses a pinned OpenCV source build with DNN disabled because the published OpenCV wheel has no Windows ARM64 binary.

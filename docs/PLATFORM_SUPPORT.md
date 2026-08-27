# Platform support

| Platform | Architecture | Standalone | Vision backend | Mojo source | Python engine | Native package smoke |
|---|---|---:|---|---:|---:|---|
| Linux | x86_64 | Yes | Yes (MediaPipe) | Yes | Yes | CI/release runner |
| Linux | ARM64 | Yes | Yes (MediaPipe 1.0.1) | Yes | Yes | CI/release runner |
| macOS | Intel x86_64 | Yes | Yes (MediaPipe 0.10.21) | Yes | Yes | CI/release runner |
| macOS | Apple Silicon ARM64 | Yes | Yes (MediaPipe 0.10.35) | Yes | Yes | CI/release runner |
| Windows | x86_64 | Yes | Yes (MediaPipe 0.10.35) | Yes | Yes | CI/release runner |
| Windows | ARM64 | Yes | Yes (MediaPipe 0.10.35) | Yes | Yes | CI/release runner |

Stable releases publish exactly these six native targets. The table above describes source/application capability. Every standalone runtime contains a compiler-free native Mojo engine and the Python reference engine with CPU fallback:

| Platform | Architecture | MediaPipe runtime | Native Mojo engine | Runtime default |
|---|---|---:|---:|---|
| Linux | x86_64 | Yes | Yes | Mojo |
| Linux | ARM64 | Yes | Yes | Mojo |
| macOS | Intel x86_64 | Yes | Yes | Mojo |
| macOS | Apple Silicon ARM64 | Yes | Yes | Mojo |
| Windows | x86_64 | Yes | Yes | Mojo |
| Windows | ARM64 | Yes | Yes | Mojo |

The macOS Intel lane uses the stable MediaPipe 0.10.21 x86_64 wheel, the last selected stable release with a native Intel macOS wheel. Windows ARM uses a native OpenCV source build with DNN disabled because the selected OpenCV PyPI release has no Windows ARM64 wheel. Mojo object generation and native library linking are covered by the six target CI lanes; the final release workflow repeats the extracted-package smoke test before publication.

The CI graph has one Python job and one Mojo job for each of the six targets. Each Mojo job validates target-native object/library architecture, ABI exports, native loading, deterministic processing, parity, and standalone smoke behavior on the matching runner.

All six rows use the same vision, gesture, dispatch, and cleanup architecture. X11, macOS Quartz, and Windows report native logical multi-monitor bounds. Wayland uses permissioned relative uinput events and cannot query a compositor-wide cursor position or layout through a common API; its configured display bounds are used for relative scaling. Camera discovery/capture, Accessibility permissions on macOS, `/dev/uinput` permissions on Linux Wayland, and real pointer behavior remain manual hardware checks; ordinary CI uses only fake input and no webcam.

Standalone distribution currently has six publishable matrix rows: `x86_64-unknown-linux-gnu`, `aarch64-unknown-linux-gnu`, `x86_64-apple-darwin`, `aarch64-apple-darwin`, `x86_64-pc-windows-msvc`, and `aarch64-pc-windows-msvc`. Each is packaged as a PyInstaller onedir archive with the pinned model, native Mojo ABI library, and Python reference engine. Matching-host CI extracts each archive and passes `--version`, forced `--engine mojo` self-test, `auto` diagnostics, replay, and architecture checks without system Python or Mojo. Camera, Accessibility, and real-pointer behavior remain manual hardware checks; the Windows ARM build uses a pinned OpenCV source build with DNN disabled because the published OpenCV wheel has no Windows ARM64 binary.

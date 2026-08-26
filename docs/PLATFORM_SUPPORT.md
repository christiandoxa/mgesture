# Platform support

| Platform | Camera | Pointer/buttons | Scrolling | Mojo | Python | Actually tested here | Limitations |
|---|---|---|---|---|---|---|---|
| Zorin OS 18.1 x86_64 X11 | OpenCV path implemented | pynput/X11 path implemented | implemented | installed stable 1.0.0, build pending | implemented | CLI/environment only so far | webcam, model, real pointer, and Mojo build still need hardware run |
| Linux Wayland | OpenCV path implemented | uinput path implemented | implemented | supported where native Mojo exists | implemented | not tested | `/dev/uinput` permissions; layout/portal integration limited |
| macOS Apple Silicon | OpenCV path implemented | Quartz path implemented | implemented | Pixi package available; not hardware tested | implemented | not tested | Camera and Accessibility permissions |
| macOS Intel | OpenCV dependency conditional; verify package support | Quartz path implemented | implemented | no Pixi Mojo candidate in current lock solve | implemented where MediaPipe wheel exists | not tested | dependency availability varies |
| Windows native | OpenCV path implemented | SendInput path implemented | implemented | explicitly Python-only | implemented | not tested | native Windows required; no WSL-only claim |

Status meanings: implemented means source path exists; unit tested means fake/replay tests cover it; CI tested and hardware tested are only claimed after those checks run. No frame or real-pointer hardware test is part of ordinary CI.

Standalone distribution currently has six publishable matrix rows: `x86_64-unknown-linux-gnu`, `aarch64-unknown-linux-gnu`, `x86_64-apple-darwin`, `aarch64-apple-darwin`, `x86_64-pc-windows-msvc`, and `aarch64-pc-windows-msvc`. Each is packaged as a PyInstaller onedir archive with the pinned model and Python reference engine. Matching-host CI extracts each archive and passes `--version`, `self-test --headless --fake-input`, and runtime diagnostics without system Python or Mojo. Camera, Accessibility, and real-pointer behavior remain manual hardware checks; the Windows ARM build uses a pinned OpenCV source build with DNN disabled because the published OpenCV wheel has no Windows ARM64 binary.

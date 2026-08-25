from __future__ import annotations

import functools
import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class HardwareCapabilities:
    os_name: str
    architecture: str
    cpu: str
    logical_cpus: int
    physical_cpus: int
    gpu_detected: bool
    gpu_vendor: str
    gpu_device: str
    driver: str
    gpu_memory_mb: int | None
    mesa_available: bool
    mojo_available: bool
    mojo_accelerator: str
    mediapipe_gpu_api: bool
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ComputePlan:
    requested: str
    inference: str
    preprocessing: str
    gesture: str
    preview: str
    gpu_candidate: bool
    reason: str


@functools.lru_cache(maxsize=1)
def detect_hardware() -> HardwareCapabilities:
    system = platform.system()
    vendor, device, driver, memory = _gpu_details(system)
    mojo = shutil.which("mojo") is not None
    media_gpu = _mediapipe_gpu_api()
    notes: list[str] = []
    if not vendor:
        notes.append("No GPU vendor was detected from portable OS/device metadata")
    if not media_gpu:
        notes.append("Installed MediaPipe Python API does not expose a GPU delegate")
    return HardwareCapabilities(
        os_name=system,
        architecture=platform.machine(),
        cpu=platform.processor() or platform.machine(),
        logical_cpus=_cpu_counts()[1],
        physical_cpus=_cpu_counts()[0],
        gpu_detected=bool(vendor),
        gpu_vendor=vendor or "unknown",
        gpu_device=device or "unknown",
        driver=driver or "unknown",
        gpu_memory_mb=memory,
        mesa_available=Path("/usr/lib/x86_64-linux-gnu/libGLX_mesa.so.0").exists()
        or Path("/usr/lib/aarch64-linux-gnu/libGLX_mesa.so.0").exists(),
        mojo_available=mojo,
        mojo_accelerator=_mojo_accelerator() if mojo else "unavailable",
        mediapipe_gpu_api=media_gpu,
        notes=tuple(notes),
    )


@functools.lru_cache(maxsize=1)
def _cpu_counts() -> tuple[int, int]:
    try:
        result = subprocess.run(
            ["lscpu", "-p=Core,Socket"], capture_output=True, text=True, timeout=1, check=False
        )
        pairs = {line for line in result.stdout.splitlines() if line and not line.startswith("#")}
        physical = len(pairs) or (os.cpu_count() or 1)
    except (OSError, ValueError, subprocess.SubprocessError):
        physical = os.cpu_count() or 1
    return physical, os.cpu_count() or physical


def capabilities_dict(capabilities: HardwareCapabilities) -> dict[str, object]:
    return {
        "os": capabilities.os_name,
        "architecture": capabilities.architecture,
        "cpu": capabilities.cpu,
        "logical_cpus": capabilities.logical_cpus,
        "physical_cpus": capabilities.physical_cpus,
        "gpu_detected": capabilities.gpu_detected,
        "gpu_vendor": capabilities.gpu_vendor,
        "gpu_device": capabilities.gpu_device,
        "driver": capabilities.driver,
        "gpu_memory_mb": capabilities.gpu_memory_mb,
        "mesa_available": capabilities.mesa_available,
        "mojo_available": capabilities.mojo_available,
        "mojo_accelerator": capabilities.mojo_accelerator,
        "mediapipe_gpu_api": capabilities.mediapipe_gpu_api,
        "notes": list(capabilities.notes),
    }


def _mediapipe_gpu_api() -> bool:
    try:
        from mediapipe.tasks.python import BaseOptions  # type: ignore[import-untyped]

        return hasattr(BaseOptions, "Delegate") and hasattr(BaseOptions.Delegate, "GPU")
    except Exception:
        return False


def _mojo_accelerator() -> str:
    probe = Path(__file__).resolve().parents[2] / "mojo" / "accelerator_probe.mojo"
    if not probe.exists():
        return "unknown"
    try:
        result = subprocess.run(
            ["mojo", "run", str(probe)], capture_output=True, text=True, timeout=10, check=False
        )
        values = dict(line.split(maxsplit=1) for line in result.stdout.splitlines() if " " in line)
        active = [name for name in ("nvidia", "amd", "apple") if values.get(name) == "True"]
        return ",".join(active) if values.get("accelerator") == "True" and active else "cpu-only"
    except (OSError, subprocess.SubprocessError, ValueError):
        return "unavailable"


def _gpu_details(system: str) -> tuple[str, str, str, int | None]:
    if system == "Linux":
        return _linux_gpu_details()
    if system == "Darwin":
        return _mac_gpu_details()
    if system == "Windows":
        return _windows_gpu_details()
    return "", "", "", None


def _linux_gpu_details() -> tuple[str, str, str, int | None]:
    vendor = device = driver = ""
    memory: int | None = None
    drm_root = Path("/sys/class/drm")
    for card in sorted(drm_root.glob("card[0-9]")):
        vendor_id = (
            (card / "device/vendor").read_text(encoding="utf-8", errors="ignore").strip().lower()
            if (card / "device/vendor").exists()
            else ""
        )
        device_name = (
            (card / "device/uevent").read_text(encoding="utf-8", errors="ignore")
            if (card / "device/uevent").exists()
            else ""
        )
        if vendor_id in ("0x10de", "0x10de\n"):
            vendor = "NVIDIA"
        elif vendor_id in ("0x1002", "0x1022"):
            vendor = "AMD"
        elif vendor_id in ("0x8086",):
            vendor = "Intel"
        if vendor:
            device = next(
                (
                    line.split("=", 1)[1]
                    for line in device_name.splitlines()
                    if line.startswith("PCI_ID=")
                ),
                card.name,
            )
            driver_path = card / "device/driver"
            driver = driver_path.resolve().name if driver_path.exists() else ""
            break
    nvidia_version = Path("/proc/driver/nvidia/version")
    if nvidia_version.exists():
        line = nvidia_version.read_text(encoding="utf-8", errors="ignore").splitlines()[0]
        match = re.search(r"Kernel Module\s+([0-9.]+)", line)
        driver = match.group(1) if match else driver
    if vendor == "NVIDIA" and shutil.which("nvidia-smi"):
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,driver_version,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            values = [value.strip() for value in result.stdout.split(",")]
            if result.returncode == 0 and len(values) == 3:
                device, driver = values[0], values[1]
                memory = int(float(values[2]))
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    return vendor, device, driver, memory


def _mac_gpu_details() -> tuple[str, str, str, int | None]:
    if platform.machine() in ("arm64", "aarch64"):
        return "Apple", "Apple Silicon GPU", "Metal", None
    try:
        result = subprocess.run(
            ["system_profiler", "SPDisplaysDataType"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        text = result.stdout
        if text.strip():
            return (
                "Apple",
                next(
                    (
                        line.split(":", 1)[1].strip()
                        for line in text.splitlines()
                        if "Chipset Model:" in line
                    ),
                    "Mac GPU",
                ),
                "Metal",
                None,
            )
    except (OSError, subprocess.SubprocessError):
        pass
    return "", "", "", None


def _windows_gpu_details() -> tuple[str, str, str, int | None]:
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_VideoController | Select-Object -First 1 -ExpandProperty Name",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        device = result.stdout.strip()
        lower = device.lower()
        vendor = (
            "NVIDIA"
            if "nvidia" in lower
            else "AMD"
            if "amd" in lower or "radeon" in lower
            else "Intel"
            if "intel" in lower
            else ""
        )
        return vendor, device, "native", None
    except (OSError, subprocess.SubprocessError):
        return "", "", "", None


def select_compute_plan(
    requested: str, capabilities: HardwareCapabilities, gesture_engine: str = "auto"
) -> ComputePlan:
    if requested not in ("auto", "gpu", "cpu"):
        raise ValueError("compute must be auto, gpu, or cpu")
    candidate = capabilities.gpu_detected and capabilities.mediapipe_gpu_api
    if requested == "gpu" and not candidate:
        raise RuntimeError(
            "GPU compute requested, but no usable MediaPipe GPU delegate is available; check drivers and package support"
        )
    use_gpu = requested == "gpu" or (requested == "auto" and candidate)
    gesture = (
        "mojo_cpu"
        if gesture_engine == "mojo" or (gesture_engine == "auto" and capabilities.mojo_available)
        else "python_cpu"
    )
    if use_gpu:
        return ComputePlan(
            requested,
            "mediapipe_gpu",
            "cpu",
            gesture,
            "cpu",
            True,
            "GPU candidate selected; Hand Landmarker initialization must still succeed",
        )
    return ComputePlan(
        requested,
        "mediapipe_cpu",
        "cpu",
        gesture,
        "cpu",
        False,
        "CPU selected explicitly or GPU candidate unavailable",
    )


class AdaptivePerformanceController:
    def __init__(self, target_fps: int, max_fps: int, idle_fps: int, adaptive: bool = True) -> None:
        self.target_fps = max(1, target_fps)
        self.max_fps = max(self.target_fps, max_fps)
        self.idle_fps = max(1, idle_fps)
        self.adaptive = adaptive
        self._next_at = 0.0

    def wait_interval(self, paused: bool, hand_tracked: bool) -> float:
        if not self.adaptive:
            return 1.0 / self.max_fps
        fps = self.idle_fps if paused or not hand_tracked else self.target_fps
        return 1.0 / max(1, fps)

    def should_process(self, now: float, paused: bool, hand_tracked: bool) -> bool:
        if now < self._next_at:
            return False
        self._next_at = now + self.wait_interval(paused, hand_tracked)
        return True

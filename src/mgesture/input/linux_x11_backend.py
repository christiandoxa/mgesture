from .pynput_backend import PynputMouseBackend


class LinuxX11Backend(PynputMouseBackend):
    name = "linux-x11-pynput"

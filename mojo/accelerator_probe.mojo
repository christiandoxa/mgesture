from std.sys import has_accelerator, has_amd_gpu_accelerator, has_apple_gpu_accelerator, has_nvidia_gpu_accelerator


def main():
    print("accelerator", has_accelerator())
    print("nvidia", has_nvidia_gpu_accelerator())
    print("amd", has_amd_gpu_accelerator())
    print("apple", has_apple_gpu_accelerator())

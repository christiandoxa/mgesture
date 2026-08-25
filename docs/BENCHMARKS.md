# Benchmarks

Core benchmark commands:

```bash
mgesture benchmark --engine python --compute cpu
mgesture benchmark --engine mojo --compute cpu
mgesture benchmark --compare-compute
```

The core section uses identical synthetic landmark frames. The inference section initializes MediaPipe in image mode when the verified model is installed and reports median/p95/p99 latency, FPS, process CPU time, and maximum resident memory. GPU results are reported only after delegate initialization succeeds. Missing hardware/model/delegate is an explicit unavailable result, not a zero or claimed speedup.

The end-to-end webcam target is approximately 30 processed FPS with bounded latency, not a universal guarantee. Record machine, OS, resolution, model, engine, compute mode, dropped frames, and CPU/GPU observations when adding measured results here.

## Zorin validation snapshot

Run on 2026-08-25 on Zorin OS 18.1 x86_64, Linux 7.0.0-30, Python 3.11.16, MediaPipe 0.10.35, Mojo 1.0.0, NVIDIA GeForce RTX 3060 12 GB, model SHA-256 `fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1`.

| Workload | Median | P95 | FPS | CPU process time | Result |
|---|---:|---:|---:|---:|---|
| Python gesture core, 3,000 synthetic frames | 0.0126 ms | 0.0173 ms | 76,421 | 0.051 s | reference |
| Mojo gesture core, same frames | 0.0093 ms | 0.0106 ms | 107,905 | 0.038 s | faster in this isolated run; not an end-to-end claim |
| MediaPipe CPU, 30 blank 640x480 frames | 12.94 ms | 13.85 ms | 76.2 | 0.584 s | available |
| MediaPipe GPU, 30 blank 640x480 frames | 2.40 ms | 4.70 ms | 339.3 | 0.279 s | delegate initialized successfully |
| MediaPipe auto, same fixture | 2.57 ms | 10.16 ms | 302.1 | 0.292 s | selected GPU |

The inference benchmark showed a lower median and lower measured process CPU time for the GPU delegate on this machine, so `compute=auto` selects MediaPipe GPU. Gesture work remains Mojo CPU because the 21x3 workload is tiny and the benchmark does not justify GPU transfer/launch overhead. These are synthetic/image-mode measurements, not a universal webcam or power claim; the application was also run for a short fake-input camera smoke with the real local camera, but no real pointer was moved.

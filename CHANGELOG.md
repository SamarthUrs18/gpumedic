# Changelog

## 0.1.0 — 14 October 2026

The first release: a health check for one GPU machine.

- **`gpumedic scan`** reads every GPU and reports what's wrong, what to check, and a verdict per
  GPU and for the node: HEALTHY, WARNING or DRAIN. Exit codes 0 / 1 / 2 (and 3 when gpumedic
  itself couldn't run) make it a scheduler health check with no glue.
- **Checks:** temperature against the GPU's own slowdown temperature; throttling (thermal, hardware
  power brake, power cap); ECC errors and row remapping; XID errors from the kernel log, matched to
  the GPU by PCI address; PCIe link width and generation; stragglers against the node's median
  clock; GPUs that have disappeared, or fewer than `--expect-gpus`.
- **Collectors:** NVIDIA via NVML (`pip install "gpumedic[nvidia]"`), macOS for development, six
  simulated failures (`--mock`), and replay of saved snapshots (`--replay`).
- **`gpumedic capture`** records raw `nvidia-smi`, DCGM and kernel-log output plus a snapshot, so
  checks can be run and developed on another machine. `scripts/runpod-check.sh` does the whole
  real-hardware side on a rented GPU.
- **`gpumedic watch`**, **`--json`**, and a library API: `diagnose(get_collector().collect())`.
- Snapshots carry a `schema_version`; one from a newer gpumedic is refused rather than misread.
- No required dependencies, Python 3.9 to 3.13, Apache-2.0.

**Run on real hardware:** a GeForce RTX 3090 (driver 580.126.20) in a RunPod container, idle and
under full load, with every reading matching `nvidia-smi`. Datacenter-only counters (ECC, row
remapping, NVLink) are tested against a fake NVML only, and XIDs haven't been read outside a
container yet.

# gpumedic

Scan a GPU node, find hardware problems, and say what to do about them.

```
$ gpumedic scan --mock overheating
gpumedic · mock-node-01 · mock:overheating · driver 550.54.15

GPU  MODEL                  TEMP  POWER     UTIL  SM CLOCK   MEMORY  VERDICT
0    NVIDIA H100 80GB HBM3  56°C  612/700W  97%   1980/1980  69/80G  HEALTHY
...
3    NVIDIA H100 80GB HBM3  91°C  621/700W  97%   1410/1980  69/80G  DRAIN

Findings
  CRIT  GPU 3   91°C is at or above the slowdown temperature (87°C); the GPU is cutting its clocks.
              → Check fans, airflow and inlet temperature for this node.
  ...
Node verdict: DRAIN (1 GPU(s) to drain, 0 with warnings)
```

## What it checks

| Check | Signal |
|---|---|
| Temperature | Close to or above the GPU's own slowdown temperature |
| Throttling | Thermal slowdown, hardware power brake, power cap |
| Memory errors | Corrected / uncorrectable ECC errors, pending or failed row remaps |
| XID errors | Driver-reported faults from the kernel log (fallen off bus, ECC, NVLink, GSP, ...) |
| PCIe | Link running narrower or slower than it should |
| Stragglers | A busy GPU running well below the node's median clock |
| Missing GPUs | XIDs for GPUs that vanished, or fewer GPUs than `--expect-gpus` |

Each GPU gets a verdict: **HEALTHY**, **WARNING** or **DRAIN**.

## Install

```bash
# Development (Mac or Linux, no GPU needed)
uv venv && uv pip install -e ".[dev]"

# On an NVIDIA machine
pip install -e ".[nvidia]"
```

## Usage

```bash
gpumedic scan                        # auto-detect: NVIDIA (NVML), else macOS
gpumedic scan --mock ecc             # simulate a failure scenario
gpumedic scenarios                   # list simulated scenarios
gpumedic scan --expect-gpus 8        # flag the node if a GPU is missing
gpumedic scan --json                 # machine-readable output
gpumedic watch --interval 5          # live view
gpumedic capture                     # record raw GPU output for replay
gpumedic scan --replay captures/<folder>
```

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Healthy |
| 1 | Warnings |
| 2 | At least one GPU should be drained |
| 3 | gpumedic couldn't run (no GPU, bad replay file, ...) |

That makes it usable as a Slurm node health check, a cron job or a CI gate.

## Developing without an NVIDIA GPU

1. Build and test on any machine with `--mock` scenarios and the `macos` collector.
2. On a rented GPU (e.g. a RunPod pod):
   ```bash
   git clone <repo> && cd gpumedic && pip install -e ".[nvidia]"
   gpumedic scan
   gpumedic capture
   ```
3. Copy the `captures/<host>-<time>/` folder back and run `gpumedic scan --replay` on it.
   Sanitized captures can become test fixtures.

**Container note:** RunPod pods are containers, so the kernel log (and therefore XID errors)
is usually not readable. gpumedic says so in a `note:` line instead of failing.

## Layout

```
src/gpumedic/
  models.py        NodeSnapshot, GpuSample, Finding, Verdict
  collectors/      nvml (NVIDIA), macos, mock, replay, kernel_log (XIDs)
  rules.py         snapshot → findings
  xid.py           XID meanings and actions
  report.py        text and JSON output
  capture.py       record raw output on a GPU node
  cli.py           command line
```

The pipeline is `collect() → NodeSnapshot → diagnose() → Diagnosis`, and it can be used as a library:

```python
from gpumedic.collectors import get_collector
from gpumedic.rules import diagnose

diag = diagnose(get_collector().collect())
print(diag.node_verdict)
```

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/brand/logo-dark.svg">
    <img alt="gpumedic" src="docs/brand/logo-light.svg" width="390">
  </picture>
</p>

<p align="center">
  <a href="https://pypi.org/project/gpumedic/"><img alt="PyPI" src="https://img.shields.io/pypi/v/gpumedic?cacheSeconds=3600"></a>
  <img alt="Python 3.9 to 3.13" src="https://img.shields.io/badge/python-3.9%20%7C%203.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue">
  <a href="LICENSE"><img alt="License: Apache-2.0" src="https://img.shields.io/badge/license-Apache--2.0-green"></a>
</p>

**A health check for GPU machines.** It reads what the NVIDIA driver knows about every GPU on a
node — temperatures, throttling, memory errors, driver error codes, PCIe links — and says in plain
English what's wrong, what to check, and whether each GPU should keep taking work.

One command, no configuration, nothing to run in the background. It never changes anything on
the machine.

```
$ gpumedic scan
gpumedic · gpu-node-07 · nvml · driver 550.54.15

GPU  MODEL                  TEMP  POWER     UTIL  SM CLOCK   MEMORY  VERDICT
0    NVIDIA H100 80GB HBM3  56°C  612/700W  97%   1980/1980  69/80G  HEALTHY
1    NVIDIA H100 80GB HBM3  57°C  615/700W  97%   1980/1980  69/80G  HEALTHY
2    NVIDIA H100 80GB HBM3  58°C  310/700W  97%   1050/1980  69/80G  DRAIN
...

Findings
  CRIT  GPU 2   Hardware power brake engaged; clocks are forced down by an external power signal.  [throttle.power_brake]
              → Suggested: Check the node's PSUs and power delivery, then drain the node.
  WARN  GPU 2   Running at 53% of the node's median clock; in multi-GPU jobs every other GPU waits for it.  [perf.straggler]
              → Suggested: Fix the cause above, or exclude this GPU from multi-GPU jobs.

Node verdict: DRAIN (1 GPU to drain)
```

## Quickstart

Requires Python 3.9–3.13.

```bash
pip install "gpumedic[nvidia]"
gpumedic scan
```

No NVIDIA GPU? Install it without the extra and look at a simulated failure instead:

```bash
pip install gpumedic
gpumedic scan --mock overheating
```

`gpumedic scenarios` lists the others: a GPU with memory errors, one that fell off the bus, a
hardware power brake, a degraded PCIe link.

## What it checks

| Check | What it looks at | Example |
|---|---|---|
| **Temperature** | Against the GPU's *own* slowdown temperature, not a fixed number | 91°C on a card that slows down at 87°C → CRIT |
| **Throttling** | Why the GPU is cutting its clocks | Hardware power brake → CRIT, too hot → WARN, power cap under load → INFO |
| **Memory errors** | ECC counters and row remapping | Uncorrectable errors → CRIT, a remap waiting for a reset → WARN |
| **XID errors** | Fault codes the driver writes to the kernel log, matched to the GPU by PCI address | XID 79 (fell off the bus) → CRIT, XID 13 (usually the application) → WARN |
| **PCIe** | Link width and generation against what the slot supports | x8 instead of x16 → WARN |
| **Stragglers** | Each busy GPU's clock against the node's median | One GPU at 53% while the rest run flat out → WARN |
| **Missing GPUs** | XIDs for GPUs that are no longer visible, and `--expect-gpus N` | 7 of 8 GPUs → CRIT |

Every finding has a stable code (`thermal.slowdown`, `xid.79`) for scripts to match on, a message
for people, and a suggested next step. **The suggestion is advice, not an action:** gpumedic only
reads. Deciding to drain, reset or replace a GPU stays with you, or with the scheduler script you
point at its exit code.

### What an XID is

When the NVIDIA driver hits a problem with a GPU it logs a line like
`NVRM: Xid (PCI:0000:9a:00): 79, ... GPU has fallen off the bus`. The number says what kind of
problem it was. Your program usually only sees `CUDA error: unspecified launch failure`; the XID
is often the only record of whether the GPU or the code was at fault. gpumedic reads them, says
which GPU each belongs to, and explains the common ones.

## Verdicts and exit codes

Each GPU gets the verdict of its worst finding, and the node gets the worst of all of them.

| Verdict | Means | Exit code |
|---|---|---|
| **HEALTHY** | Nothing at WARN or above | 0 |
| **WARNING** | Worth a look; keep running | 1 |
| **DRAIN** | At least one GPU shouldn't take new work | 2 |
| — | gpumedic itself couldn't run (no GPU, unreadable snapshot) | 3 |

That makes it a node health check with no glue. In Slurm, for example:

```bash
#!/bin/bash
# HealthCheckProgram=/etc/slurm/gpumedic-health.sh in slurm.conf
gpumedic scan --expect-gpus 8 > /var/log/gpumedic.log
if [ $? -eq 2 ]; then
    scontrol update nodename="$(hostname -s)" state=drain reason="gpumedic: see /var/log/gpumedic.log"
fi
```

Draining in Slurm stops new jobs landing on the node; running jobs finish.

## What it can and can't see

gpumedic reports what it couldn't check rather than guessing, in a `note:` line under the findings.

| Where | What's missing | Why |
|---|---|---|
| **Containers** (RunPod pods, most Kubernetes pods) | XID errors | The kernel log usually isn't readable from inside a container |
| **Consumer GPUs** (GeForce) | ECC and row-remap checks | The cards don't have ECC memory; those columns show `-` |
| **macOS** | Temperature, power, clocks | macOS doesn't expose them without `sudo`. The Mac collector is for development |

Every metric is optional: a check whose data is missing is skipped, never failed.

## Working without a GPU

Most of gpumedic can be developed and tested on a laptop. Two pieces make that work:

- **`--mock SCENARIO`** builds a simulated 8× H100 node with one thing broken.
- **`gpumedic capture`** on a real GPU machine records the raw `nvidia-smi`, DCGM and kernel-log
  output plus a snapshot. Copy the folder back and `gpumedic scan --replay <folder>` runs the
  checks on it anywhere.

[`scripts/runpod-check.sh`](scripts/runpod-check.sh) does the whole real-hardware side in one go
on a rented GPU: install, scan, capture, and pack the results into one `.tar.gz` to copy back.

## The `gpumedic` CLI

| | |
|---|---|
| `gpumedic scan` | Checks this node once and prints a report. `--json`, `--expect-gpus N`, `--collector` |
| `gpumedic scan --mock SCENARIO` | Runs the checks on a simulated failure |
| `gpumedic scan --replay PATH` | Runs the checks on a saved snapshot or capture folder |
| `gpumedic watch` | Re-scans every few seconds. `--interval` |
| `gpumedic capture` | Records raw GPU output for replay on another machine. `--out` |
| `gpumedic scenarios` | Lists the simulated failures |
| `gpumedic --version` | The installed version |

`NO_COLOR` turns colors off; output that isn't a terminal is never colored.

## Using it as a library

The CLI is three calls, and they're the public API:

```python
from gpumedic.collectors import get_collector
from gpumedic.rules import diagnose

diag = diagnose(get_collector().collect())
print(diag.node_verdict)                  # Verdict.DRAIN
for finding in diag.findings:
    print(finding.severity.name, finding.gpu_index, finding.code, finding.message)
```

`get_collector()` picks NVML on an NVIDIA machine and the Mac collector on macOS; pass
`scenario=` or `replay=` for the others. Snapshots serialise to JSON (`snapshot.to_dict()`) with a
`schema_version`, so one machine can collect and another diagnose. A snapshot from a newer
gpumedic than the reader is refused with a message to upgrade, rather than misread.

## Status

**0.1 — early.** Run on real hardware so far: a GeForce RTX 3090 (driver 580, in a RunPod container),
idle and under full load, with every reading matching `nvidia-smi`. Snapshots from that run are
test fixtures. Datacenter cards (ECC, row remapping, NVLink) are covered only by a fake NVML in the
tests until someone runs it on an A100 or H100, and XID reading hasn't been tried outside a
container yet.

Next: a DCGM collector (diagnostics, NVLink), AMD GPUs, a threshold config file, and Kubernetes
and Prometheus integrations.

## Development

```bash
uv venv && uv pip install -e ".[dev]"     # or: pip install -e ".[dev]"
pytest
```

The pipeline is `collect() → NodeSnapshot → diagnose() → Diagnosis → report`:

```
src/gpumedic/
  collectors/   nvml (NVIDIA), macos, mock, replay, and kernel_log for XIDs
  models.py     NodeSnapshot, GpuSample, Finding, Verdict: the shapes everything shares
  rules.py      one small function per check
  xid.py        what each XID means, how serious it is, what to check
  report.py     the text table and JSON
  capture.py    records raw output on a GPU node
  cli.py        the command line
```

A new check is a function in `rules.py` that returns findings, plus a mock scenario and a test. A
new data source is a class with a `collect()` method; the rules and report don't change.

## License

[Apache-2.0](LICENSE). Use it at work, embed it in a commercial product, ship it closed — keep the
copyright notice and the [`NOTICE`](NOTICE) file in what you distribute, and don't use the
project's name to imply it endorses you.

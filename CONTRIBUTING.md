# Contributing

Thanks for looking. This file is for people changing the code. If you want to *use* gpumedic, the
[README](README.md) is the right place.

## Before you start

**The licence is [Apache-2.0](LICENSE).** Anyone can run gpumedic at work, embed it in a commercial
product and rebrand it, which is what most of the people who'll rely on it need to do.

**Your first pull request will ask you to sign a [CLA](CLA.md).** A bot posts the link; you reply
with one line and it's done, once, for every contribution you ever make. It asks for a licence,
not ownership — you keep the copyright in everything you write. It exists because a licence
change can't be applied retroactively to code that arrived without one, and a project that may
one day offer different terms has to ask on day one or never.

**Don't paste code from other tools.** dcgm-exporter, NVIDIA's samples, vendor scripts and the
rest are fine to read and learn from; their code carries licences this project hasn't accepted.
Hardware facts (what an XID means, which counter matters) are fine to use — cite where they came
from, in your own words.

## Setup

```bash
uv venv && uv pip install -e ".[dev]"     # or: pip install -e ".[dev]"
pytest
ruff check .
```

CI runs both on Python 3.9, 3.10, 3.11, 3.12 and 3.13. Nothing in the suite needs a GPU.

## How the code is laid out

```
src/gpumedic/
├── collectors/     where data comes from: nvml, macos, mock, replay; kernel_log reads XIDs
├── models.py       NodeSnapshot, GpuSample, Finding, Verdict — the contract between the rest
├── rules.py        snapshot → findings, one small function per check
├── xid.py          what each XID means, how serious it is, what to check
├── report.py       the text table and JSON
├── capture.py      records raw output on a GPU node
└── cli.py          the command line
tests/
├── fixtures/       snapshots recorded on real GPUs
└── test_*.py
```

The pipeline is `collect() → NodeSnapshot → diagnose() → Diagnosis → report`. Collectors only fill
in a snapshot; rules only read one. Keep it that way.

## Rules a review will hold you to

**gpumedic only reads.** It never resets a GPU, drains a node, kills a process or writes anywhere
except where `capture` is told to. A finding's `suggestion` is advice for a person. Acting on it is
the job of whoever reads the exit code — a Slurm health check, a script, an operator.

**Every metric is optional.** Consumer cards have no ECC, containers hide the kernel log, macOS
hides temperatures. A collector stores `None` for anything it can't read, and a rule skips `None`.
A query that isn't supported must never crash a scan.

**No false alarms on healthy hardware.** An idle card drops its PCIe link to Gen1 and its clocks to
a few hundred MHz; a busy one sits at its power cap. Neither is a problem. A rule that fires on a
healthy card is a bug, and the real-hardware fixtures are there to catch it. Add the case that
proves your rule stays quiet, not only the one that proves it fires.

**Use the hardware's own limits.** The GPU reports its slowdown temperature; use that before any
fixed threshold. A default in `Thresholds` is a fallback, not the rule.

**Findings say what to do.** A message says what's wrong in plain English, a suggestion says what
to check next, and a stable `code` (`thermal.slowdown`, `xid.79`) is what scripts match on. Don't
rename a code once it's released.

**The snapshot format is a contract.** Adding an optional field is free. Renaming or removing one,
or changing a unit, means bumping `SCHEMA_VERSION` in `models.py` and teaching `from_dict` to read
the old one.

**No required dependencies, nothing phoned home.** gpumedic installs on an old cluster node with
nothing but Python, and runs on air-gapped machines. Vendor libraries go in an optional extra
(`[nvidia]`). It never sends anything anywhere.

## Adding things

**A check:** a function in `rules.py` that takes a `GpuSample` and `Thresholds` and returns a list
of findings, added to `GPU_RULES`. Add a mock scenario in `collectors/mock.py` that triggers it,
and tests for both the scenario and a healthy card.

**An XID:** one line in `XID_CATALOG` in `xid.py`, with what it means and what to check. Say where
the meaning came from in the pull request.

**A data source** (AMD, DCGM, another OS): a class in `collectors/` with a `collect()` that returns
a `NodeSnapshot`, registered in `get_collector`. The rules and the report shouldn't need to change;
if they do, say why. Test it against a fake of the vendor library, the way `tests/test_nvml.py`
fakes pynvml.

## Real hardware

The most valuable contribution is a GPU we haven't seen. On any NVIDIA machine:

```bash
bash scripts/runpod-check.sh
```

It installs gpumedic in its own venv, scans, and records a capture. Before you share one, **remove
the hostname and GPU UUIDs** (and anything else that identifies your machines) from `snapshot.json`.
A sanitized snapshot goes in `tests/fixtures/`, with a test in `tests/test_real_hardware.py` that
names the card and driver.

## Pull requests

Keep a pull request to one change. Say what broke or what was missing, not only what you did —
the reason a change exists is the part that's hard to recover later. If a rule was wrong on real
hardware, say which card and driver, and include the snapshot.

## Security

Don't open a public issue for a security problem. See [SECURITY.md](SECURITY.md).

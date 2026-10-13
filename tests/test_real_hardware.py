"""Snapshots recorded on real GPUs, replayed through the rules.

rtx3090-*.json: a GeForce RTX 3090 on a RunPod pod (driver 580.126.20),
recorded with `gpumedic capture` / `scan --json`, hostname and UUID removed.
"""

from pathlib import Path

import pytest

from gpumedic.collectors.replay import ReplayCollector
from gpumedic.models import Verdict
from gpumedic.rules import diagnose

FIXTURES = Path(__file__).parent / "fixtures"


def replay(name):
    return diagnose(ReplayCollector(str(FIXTURES / name)).collect())


def test_rtx3090_under_full_load_is_healthy_at_its_power_cap():
    diag = replay("rtx3090-load.json")
    gpu = diag.snapshot.gpus[0]
    assert gpu.utilization_pct == 100 and gpu.throttle_reasons == ["sw_power_cap"]
    assert diag.node_verdict is Verdict.HEALTHY
    assert [f.code for f in diag.findings] == ["throttle.power_cap"]


def test_rtx3090_idle_has_no_false_alarms():
    # Idle cards drop the PCIe link to Gen1 and clocks to ~210 MHz to save power.
    diag = replay("rtx3090-idle.json")
    gpu = diag.snapshot.gpus[0]
    assert (gpu.pcie_gen, gpu.pcie_gen_max) == (1, 4)
    assert diag.findings == []


@pytest.mark.parametrize("name", ["rtx3090-load.json", "rtx3090-idle.json"])
def test_consumer_card_has_no_ecc_data(name):
    gpu = replay(name).snapshot.gpus[0]
    assert gpu.ecc_corrected is None and gpu.remap_pending is None
    assert gpu.slowdown_temp_c == 95  # read from the card, not the default

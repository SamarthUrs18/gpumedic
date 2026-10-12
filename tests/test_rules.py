import pytest

from gpumedic.collectors.mock import MockCollector
from gpumedic.models import Verdict
from gpumedic.rules import diagnose


def run(scenario, **kwargs):
    return diagnose(MockCollector(scenario).collect(), **kwargs)


def codes(diag, gpu_index):
    return {f.code for f in diag.findings if f.gpu_index == gpu_index}


def test_healthy_node_has_no_findings():
    diag = run("healthy")
    assert diag.findings == []
    assert diag.node_verdict is Verdict.HEALTHY


def test_overheating_gpu_is_drained_and_flagged_as_straggler():
    diag = run("overheating")
    assert diag.gpu_verdict(3) is Verdict.DRAIN
    assert {"thermal.slowdown", "throttle.thermal", "perf.straggler"} <= codes(diag, 3)
    assert all(diag.gpu_verdict(i) is Verdict.HEALTHY for i in (0, 1, 2, 4, 5, 6, 7))


def test_ecc_errors_drain_the_gpu():
    diag = run("ecc")
    assert diag.gpu_verdict(5) is Verdict.DRAIN
    assert {"ecc.uncorrected", "ecc.corrected_high", "remap.pending", "xid.94"} <= codes(diag, 5)


def test_fallen_off_bus_is_a_node_level_drain():
    diag = run("fallen-off-bus")
    assert len(diag.snapshot.gpus) == 7
    assert diag.node_verdict is Verdict.DRAIN
    assert "xid.79" in codes(diag, None)


def test_expected_gpu_count():
    diag = run("fallen-off-bus", expected_gpus=8)
    assert "node.missing_gpus" in codes(diag, None)
    assert "node.missing_gpus" not in codes(run("healthy", expected_gpus=8), None)


def test_power_brake_drains_gpu():
    diag = run("power-brake")
    assert diag.gpu_verdict(2) is Verdict.DRAIN
    assert {"throttle.power_brake", "perf.straggler"} <= codes(diag, 2)


def test_degraded_pcie_is_a_warning():
    diag = run("pcie-degraded")
    assert diag.gpu_verdict(6) is Verdict.WARNING
    assert codes(diag, 6) == {"pcie.width"}


@pytest.mark.parametrize("scenario", ["overheating", "ecc", "power-brake", "pcie-degraded"])
def test_findings_are_sorted_most_severe_first(scenario):
    severities = [f.severity for f in run(scenario).findings]
    assert severities == sorted(severities, reverse=True)


def test_metrics_missing_from_collector_are_skipped():
    node = MockCollector("healthy").collect()
    for g in node.gpus:
        g.temperature_c = g.ecc_corrected = g.ecc_uncorrected = g.pcie_width = None
    assert diagnose(node).findings == []

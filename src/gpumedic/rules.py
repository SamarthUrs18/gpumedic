"""Turn a NodeSnapshot into findings.

Each rule looks at one kind of problem and skips metrics the collector
couldn't read (None).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Optional

from . import xid
from .models import Diagnosis, Finding, GpuSample, NodeSnapshot, Severity


@dataclass
class Thresholds:
    temp_warn_c: float = 83.0  # used when the GPU doesn't report its slowdown temperature
    temp_crit_c: float = 90.0
    temp_warn_margin_c: float = 5.0  # warn this close to the reported slowdown temperature
    ecc_corrected_warn: int = 100
    busy_util_pct: float = 50.0
    straggler_clock_ratio: float = 0.85  # below this fraction of the node median clock


def _temperature(g: GpuSample, t: Thresholds) -> list[Finding]:
    if g.temperature_c is None:
        return []
    temp = g.temperature_c
    if g.slowdown_temp_c is not None:
        crit_at, warn_at = g.slowdown_temp_c, g.slowdown_temp_c - t.temp_warn_margin_c
    else:
        crit_at, warn_at = t.temp_crit_c, t.temp_warn_c
    suggestion = "Check fans, airflow and inlet temperature for this node."
    if temp >= crit_at:
        return [Finding(Severity.CRIT, "thermal.slowdown",
                        f"{temp:.0f}°C is at or above the slowdown temperature ({crit_at:.0f}°C); the GPU is cutting its clocks.",
                        suggestion, g.index)]
    if temp >= warn_at:
        return [Finding(Severity.WARN, "thermal.hot",
                        f"{temp:.0f}°C is close to the slowdown temperature ({crit_at:.0f}°C).",
                        suggestion, g.index)]
    return []


def _throttling(g: GpuSample, t: Thresholds) -> list[Finding]:
    reasons = set(g.throttle_reasons)
    findings = []
    if "hw_power_brake" in reasons:
        findings.append(Finding(Severity.CRIT, "throttle.power_brake",
                                "Hardware power brake engaged; clocks are forced down by an external power signal.",
                                "Check the node's PSUs and power delivery, then drain the node.", g.index))
    elif "hw_slowdown" in reasons:
        findings.append(Finding(Severity.WARN, "throttle.hw_slowdown",
                                "Hardware slowdown active (thermal or power protection).",
                                "Check cooling and power delivery.", g.index))
    if "hw_thermal" in reasons or "sw_thermal" in reasons:
        findings.append(Finding(Severity.WARN, "throttle.thermal",
                                "Clocks reduced because the GPU is too hot.",
                                "Check fans, airflow and inlet temperature for this node.", g.index))
    busy = g.utilization_pct is not None and g.utilization_pct >= t.busy_util_pct
    if "sw_power_cap" in reasons and busy:
        findings.append(Finding(Severity.INFO, "throttle.power_cap",
                                "Running at the power limit (normal under heavy load).", "", g.index))
    return findings


def _memory_errors(g: GpuSample, t: Thresholds) -> list[Finding]:
    findings = []
    if g.ecc_uncorrected:
        findings.append(Finding(Severity.CRIT, "ecc.uncorrected",
                                f"{g.ecc_uncorrected} uncorrectable memory error(s) since the last reset.",
                                "Drain the node and reset the GPU. RMA if errors return.", g.index))
    if g.ecc_corrected is not None and g.ecc_corrected >= t.ecc_corrected_warn:
        findings.append(Finding(Severity.WARN, "ecc.corrected_high",
                                f"{g.ecc_corrected} corrected memory errors since the last reset.",
                                "Watch the trend; schedule a GPU reset.", g.index))
    if g.remap_failed:
        findings.append(Finding(Severity.CRIT, "remap.failed",
                                "Memory row remapping failed; the GPU has run out of spare rows.",
                                "Drain the node and open an RMA for this GPU.", g.index))
    elif g.remap_pending:
        findings.append(Finding(Severity.WARN, "remap.pending",
                                "A memory row remap is waiting for a GPU reset.",
                                "Reset the GPU (or reboot the node) when idle.", g.index))
    return findings


def _xids(g: GpuSample, t: Thresholds) -> list[Finding]:
    findings = []
    for event in g.xid_events:
        info = xid.lookup(event.xid)
        findings.append(Finding(info.severity, f"xid.{event.xid}",
                                f"XID {event.xid}: {info.meaning}.", info.suggestion, g.index))
    return findings


def _pcie(g: GpuSample, t: Thresholds) -> list[Finding]:
    findings = []
    if g.pcie_width and g.pcie_width_max and g.pcie_width < g.pcie_width_max:
        findings.append(Finding(Severity.WARN, "pcie.width",
                                f"PCIe link running at x{g.pcie_width} instead of x{g.pcie_width_max}; host bandwidth is reduced.",
                                "Check GPU seating, risers and cables.", g.index))
    # Links drop to a lower generation at idle to save power, so only flag busy GPUs.
    busy = g.utilization_pct is not None and g.utilization_pct >= t.busy_util_pct
    if busy and g.pcie_gen and g.pcie_gen_max and g.pcie_gen < g.pcie_gen_max:
        findings.append(Finding(Severity.WARN, "pcie.gen",
                                f"PCIe link at Gen{g.pcie_gen} instead of Gen{g.pcie_gen_max} while busy.",
                                "Check GPU seating, risers and BIOS PCIe settings.", g.index))
    return findings


GPU_RULES = (_temperature, _throttling, _memory_errors, _xids, _pcie)


def _stragglers(node: NodeSnapshot, t: Thresholds) -> list[Finding]:
    busy = [
        g for g in node.gpus
        if g.sm_clock_mhz and g.utilization_pct is not None and g.utilization_pct >= t.busy_util_pct
    ]
    if len(busy) < 2:
        return []
    median = statistics.median(g.sm_clock_mhz for g in busy)
    return [
        Finding(Severity.WARN, "perf.straggler",
                f"Running at {g.sm_clock_mhz / median:.0%} of the node's median clock; "
                "in multi-GPU jobs every other GPU waits for it.",
                "Fix the cause above, or exclude this GPU from multi-GPU jobs.", g.index)
        for g in busy
        if g.sm_clock_mhz < median * t.straggler_clock_ratio
    ]


def _missing_gpus(node: NodeSnapshot, expected: Optional[int]) -> list[Finding]:
    findings = []
    for event in node.unmatched_xids:
        info = xid.lookup(event.xid)
        findings.append(Finding(info.severity, f"xid.{event.xid}",
                                f"XID {event.xid} on PCI {event.pci_bus_id}, which is no longer visible: {info.meaning}.",
                                info.suggestion))
    if expected is not None and len(node.gpus) < expected:
        findings.append(Finding(Severity.CRIT, "node.missing_gpus",
                                f"Only {len(node.gpus)} of {expected} expected GPUs are visible.",
                                "Drain the node and check the missing GPU(s) are seated and powered."))
    return findings


def diagnose(
    node: NodeSnapshot, thresholds: Optional[Thresholds] = None, expected_gpus: Optional[int] = None
) -> Diagnosis:
    t = thresholds or Thresholds()
    findings: list[Finding] = []
    for g in node.gpus:
        for rule in GPU_RULES:
            findings.extend(rule(g, t))
    findings.extend(_stragglers(node, t))
    findings.extend(_missing_gpus(node, expected_gpus))
    findings.sort(key=lambda f: (-f.severity, -1 if f.gpu_index is None else f.gpu_index))
    return Diagnosis(node, findings)

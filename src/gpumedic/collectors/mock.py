"""Simulated 8x H100 node with common failure scenarios, for development without GPUs."""

from __future__ import annotations

import time
from typing import Callable

from ..models import GpuSample, NodeSnapshot, XidEvent
from .base import Collector, CollectorUnavailable

BUS_IDS = ["18:00", "2a:00", "3a:00", "5d:00", "9a:00", "ab:00", "ba:00", "db:00"]


def _healthy_node() -> NodeSnapshot:
    gpus = [
        GpuSample(
            index=i,
            name="NVIDIA H100 80GB HBM3",
            uuid=f"GPU-mock-{i:04d}",
            pci_bus_id=bus,
            temperature_c=56.0 + i % 4,
            slowdown_temp_c=87.0,
            power_w=612.0 + i * 3,
            power_limit_w=700.0,
            utilization_pct=97.0,
            memory_used_mb=71_000.0,
            memory_total_mb=81_559.0,
            sm_clock_mhz=1980.0,
            max_sm_clock_mhz=1980.0,
            ecc_corrected=0,
            ecc_uncorrected=0,
            remap_pending=False,
            remap_failed=False,
            pcie_gen=5,
            pcie_gen_max=5,
            pcie_width=16,
            pcie_width_max=16,
        )
        for i, bus in enumerate(BUS_IDS)
    ]
    return NodeSnapshot(
        hostname="mock-node-01",
        collector="mock",
        timestamp=time.time(),
        driver_version="550.54.15",
        gpus=gpus,
    )


def _overheating(node: NodeSnapshot) -> None:
    g = node.gpus[3]
    g.temperature_c = 91.0
    g.throttle_reasons = ["sw_thermal", "hw_thermal"]
    g.sm_clock_mhz = 1410.0


def _ecc(node: NodeSnapshot) -> None:
    g = node.gpus[5]
    g.ecc_corrected = 340
    g.ecc_uncorrected = 2
    g.remap_pending = True
    g.xid_events.append(XidEvent(94, g.pci_bus_id, "Contained ECC error"))


def _fallen_off_bus(node: NodeSnapshot) -> None:
    lost = node.gpus.pop(4)
    for i, g in enumerate(node.gpus):  # NVML re-indexes the GPUs it can still see
        g.index = i
    node.unmatched_xids.append(XidEvent(79, lost.pci_bus_id, "GPU has fallen off the bus."))


def _power_brake(node: NodeSnapshot) -> None:
    g = node.gpus[2]
    g.throttle_reasons = ["hw_slowdown", "hw_power_brake"]
    g.sm_clock_mhz = 1050.0
    g.power_w = 310.0


def _pcie_degraded(node: NodeSnapshot) -> None:
    node.gpus[6].pcie_width = 8


SCENARIOS: dict[str, tuple[str, Callable[[NodeSnapshot], None]]] = {
    "healthy": ("All 8 GPUs healthy under full load", lambda node: None),
    "overheating": ("GPU 3 above its slowdown temperature and throttling", _overheating),
    "ecc": ("GPU 5 with uncorrectable memory errors and a pending row remap", _ecc),
    "fallen-off-bus": ("One GPU disappeared after XID 79", _fallen_off_bus),
    "power-brake": ("GPU 2 clocks forced down by a hardware power brake", _power_brake),
    "pcie-degraded": ("GPU 6 PCIe link running at x8 instead of x16", _pcie_degraded),
}


class MockCollector(Collector):
    def __init__(self, scenario: str = "healthy"):
        if scenario not in SCENARIOS:
            raise CollectorUnavailable(
                f"Unknown mock scenario {scenario!r}. Choose from: {', '.join(SCENARIOS)}"
            )
        self.scenario = scenario
        self.name = f"mock:{scenario}"

    def collect(self) -> NodeSnapshot:
        node = _healthy_node()
        SCENARIOS[self.scenario][1](node)
        node.collector = self.name
        return node

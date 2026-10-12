"""Data shapes shared by collectors, rules and reports.

Every metric is optional. Collectors fill in what the hardware and their
permissions allow, and rules skip anything that is None.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum, IntEnum
from typing import Any, Optional

# Version of the NodeSnapshot JSON format. Bump it when a change would break
# older readers (renaming or removing a field, changing a unit); adding an
# optional field doesn't need a bump.
SCHEMA_VERSION = 1


class UnsupportedSchema(ValueError):
    """A snapshot was written by a newer gpumedic than this one."""


class Severity(IntEnum):
    OK = 0
    INFO = 1
    WARN = 2
    CRIT = 3


class Verdict(str, Enum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    DRAIN = "DRAIN"

    @classmethod
    def from_severity(cls, severity: Severity) -> "Verdict":
        if severity >= Severity.CRIT:
            return cls.DRAIN
        if severity >= Severity.WARN:
            return cls.WARNING
        return cls.HEALTHY


# Normalized clock throttle reason names (see collectors/nvml.py for the bitmask mapping).
THROTTLE_REASONS = (
    "gpu_idle",
    "app_clocks",
    "sw_power_cap",
    "hw_slowdown",
    "sync_boost",
    "sw_thermal",
    "hw_thermal",
    "hw_power_brake",
    "display_clocks",
)


@dataclass
class XidEvent:
    xid: int
    pci_bus_id: str  # normalized "bus:device", e.g. "3b:00"
    message: str = ""


@dataclass
class GpuSample:
    index: int
    name: str
    uuid: str = ""
    pci_bus_id: str = ""  # normalized "bus:device"
    temperature_c: Optional[float] = None
    slowdown_temp_c: Optional[float] = None
    power_w: Optional[float] = None
    power_limit_w: Optional[float] = None
    utilization_pct: Optional[float] = None
    memory_used_mb: Optional[float] = None
    memory_total_mb: Optional[float] = None
    sm_clock_mhz: Optional[float] = None
    max_sm_clock_mhz: Optional[float] = None
    throttle_reasons: list[str] = field(default_factory=list)
    ecc_corrected: Optional[int] = None
    ecc_uncorrected: Optional[int] = None
    remap_pending: Optional[bool] = None
    remap_failed: Optional[bool] = None
    pcie_gen: Optional[int] = None
    pcie_gen_max: Optional[int] = None
    pcie_width: Optional[int] = None
    pcie_width_max: Optional[int] = None
    xid_events: list[XidEvent] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GpuSample":
        data = dict(data)
        data["xid_events"] = [XidEvent(**x) for x in data.get("xid_events", [])]
        return cls(**data)


@dataclass
class NodeSnapshot:
    hostname: str
    collector: str
    timestamp: float
    driver_version: str = ""
    gpus: list[GpuSample] = field(default_factory=list)
    # XIDs whose PCI id matches no visible GPU, e.g. a GPU that fell off the bus.
    unmatched_xids: list[XidEvent] = field(default_factory=list)
    # Things the collector could not see, e.g. "kernel log not readable".
    notes: list[str] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NodeSnapshot":
        # Snapshots from before versioning have no field and are version 1.
        version = data.get("schema_version", 1)
        if version > SCHEMA_VERSION:
            raise UnsupportedSchema(
                f"Snapshot uses schema version {version}, but this gpumedic reads up to "
                f"{SCHEMA_VERSION}. Upgrade gpumedic to read it."
            )
        return cls(
            hostname=data["hostname"],
            collector=data["collector"],
            timestamp=data["timestamp"],
            driver_version=data.get("driver_version", ""),
            gpus=[GpuSample.from_dict(g) for g in data.get("gpus", [])],
            unmatched_xids=[XidEvent(**x) for x in data.get("unmatched_xids", [])],
            notes=list(data.get("notes", [])),
        )


@dataclass
class Finding:
    severity: Severity
    code: str  # stable id, e.g. "thermal.slowdown"
    message: str
    action: str = ""
    gpu_index: Optional[int] = None  # None means node-level


@dataclass
class Diagnosis:
    snapshot: NodeSnapshot
    findings: list[Finding]

    def gpu_verdict(self, index: int) -> Verdict:
        worst = max(
            (f.severity for f in self.findings if f.gpu_index == index),
            default=Severity.OK,
        )
        return Verdict.from_severity(worst)

    @property
    def node_verdict(self) -> Verdict:
        worst = max((f.severity for f in self.findings), default=Severity.OK)
        return Verdict.from_severity(worst)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_verdict": self.node_verdict.value,
            "gpu_verdicts": {
                str(g.index): self.gpu_verdict(g.index).value for g in self.snapshot.gpus
            },
            "findings": [
                {**asdict(f), "severity": f.severity.name} for f in self.findings
            ],
            "snapshot": self.snapshot.to_dict(),
        }

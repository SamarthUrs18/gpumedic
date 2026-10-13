"""What common NVIDIA XID errors mean and what to do about them.

Severities and suggestions are starting points summarized from NVIDIA's XID
documentation (docs.nvidia.com/deploy/xid-errors); verify against it and
tune per fleet.
"""

from __future__ import annotations

from typing import NamedTuple

from .models import Severity


class XidInfo(NamedTuple):
    severity: Severity
    meaning: str
    suggestion: str


_APP_FAULT = "Check the job's logs. If it repeats across different jobs on this GPU, run DCGM diagnostics."
_RESET = "Drain the node and reset the GPU. If it happens again, open an RMA."

XID_CATALOG: dict[int, XidInfo] = {
    13: XidInfo(Severity.WARN, "Graphics engine exception, usually an application bug", _APP_FAULT),
    31: XidInfo(Severity.WARN, "GPU memory page fault, usually an application bug", _APP_FAULT),
    43: XidInfo(Severity.WARN, "GPU stopped processing, often after an application fault", _APP_FAULT),
    45: XidInfo(Severity.INFO, "Preemptive cleanup after an earlier error", "Look at the XID logged just before it."),
    48: XidInfo(Severity.CRIT, "Double-bit (uncorrectable) ECC memory error", _RESET),
    61: XidInfo(Severity.WARN, "Internal micro-controller warning", "Update driver/firmware and watch for repeats."),
    62: XidInfo(Severity.CRIT, "Internal micro-controller halted", _RESET),
    63: XidInfo(Severity.INFO, "ECC page retirement or row remap recorded", "Reset the GPU when idle to apply it."),
    64: XidInfo(Severity.CRIT, "ECC page retirement or row remap failed", "Drain the node; an RMA is likely."),
    74: XidInfo(Severity.CRIT, "NVLink error", "Drain the node and check NVLink/NVSwitch health with DCGM."),
    79: XidInfo(Severity.CRIT, "GPU has fallen off the bus", "Drain the node, reseat or power-cycle it. RMA if it repeats."),
    92: XidInfo(Severity.WARN, "High single-bit ECC error rate", "Schedule a GPU reset and watch for escalation."),
    94: XidInfo(Severity.WARN, "Contained ECC error; the affected application was stopped", "Restart the job and reset the GPU when idle."),
    95: XidInfo(Severity.CRIT, "Uncontained ECC error", _RESET),
    119: XidInfo(Severity.CRIT, "GSP firmware RPC timeout", "Drain the node and reset the GPU; update the driver if it repeats."),
    120: XidInfo(Severity.CRIT, "GSP firmware error", "Drain the node and reset the GPU; update the driver if it repeats."),
}


def lookup(xid: int) -> XidInfo:
    return XID_CATALOG.get(
        xid,
        XidInfo(
            Severity.WARN,
            f"XID {xid} (not in gpumedic's catalog yet)",
            "Look it up in NVIDIA's XID documentation.",
        ),
    )

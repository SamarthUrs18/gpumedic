"""Read NVIDIA XID errors from the kernel log.

The NVIDIA driver logs hardware and driver faults as lines like:

    NVRM: Xid (PCI:0000:3b:00): 79, pid=1234, GPU has fallen off the bus.

The kernel log is often unreadable inside containers (e.g. RunPod pods),
so callers get a note back instead of an error when it can't be read.
"""

from __future__ import annotations

import re
import subprocess
from typing import Iterable, Optional

from ..models import GpuSample, XidEvent

XID_RE = re.compile(
    r"NVRM: Xid \(PCI:(?:[0-9a-fA-F]+:)?([0-9a-fA-F]+):([0-9a-fA-F]+)(?:\.[0-9a-fA-F])?\): (\d+),?\s*(.*)"
)

_LOG_COMMANDS = (
    ["dmesg"],
    ["journalctl", "-k", "--no-pager", "-q"],
)


def normalize_pci_bus_id(bus_id: str) -> str:
    """Reduce any PCI id form to "bus:device", lowercase.

    "00000000:3B:00.0" (NVML) and "0000:3b:00" (kernel log) both become "3b:00".
    """
    parts = bus_id.strip().lower().split(":")
    if len(parts) < 2:
        return bus_id.strip().lower()
    return f"{parts[-2]}:{parts[-1].split('.')[0]}"


def parse_xids(lines: Iterable[str]) -> list[XidEvent]:
    events = []
    for line in lines:
        m = XID_RE.search(line)
        if m:
            bus, dev, xid, rest = m.groups()
            events.append(
                XidEvent(
                    xid=int(xid),
                    pci_bus_id=f"{bus.lower()}:{dev.lower()}",
                    message=rest.strip(),
                )
            )
    return events


def read_kernel_xids() -> tuple[list[XidEvent], Optional[str]]:
    """Return XIDs since boot, plus a note if the kernel log couldn't be read."""
    for cmd in _LOG_COMMANDS:
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if out.returncode == 0 and out.stdout:
            return parse_xids(out.stdout.splitlines()), None
    return [], "Kernel log not readable (common in containers); XID errors were not checked."


def attach_xids(gpus: list[GpuSample], events: list[XidEvent]) -> list[XidEvent]:
    """Attach each XID to the GPU at its PCI address. Returns XIDs that match no GPU."""
    by_bus = {g.pci_bus_id: g for g in gpus if g.pci_bus_id}
    unmatched = []
    for event in events:
        gpu = by_bus.get(event.pci_bus_id)
        if gpu is None:
            unmatched.append(event)
        else:
            gpu.xid_events.append(event)
    return unmatched

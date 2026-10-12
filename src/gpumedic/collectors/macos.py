"""Apple Silicon Macs, for a live development loop without an NVIDIA GPU.

macOS exposes little GPU telemetry without sudo, so this reports unified
memory usage and OS-level thermal throttling only.
"""

from __future__ import annotations

import re
import socket
import subprocess
import sys
import time
from typing import Optional

from ..models import GpuSample, NodeSnapshot
from .base import Collector, CollectorUnavailable


def _run(*cmd: str) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def parse_vm_stat_used_mb(output: str) -> Optional[float]:
    page = re.search(r"page size of (\d+) bytes", output)
    if not page:
        return None

    def pages(label: str) -> int:
        m = re.search(rf"{label}:\s+(\d+)", output)
        return int(m.group(1)) if m else 0

    used = pages("Pages active") + pages("Pages wired down") + pages("Pages occupied by compressor")
    return used * int(page.group(1)) / 1024**2


def parse_cpu_speed_limit(output: str) -> Optional[int]:
    m = re.search(r"CPU_Speed_Limit\s*=\s*(\d+)", output)
    return int(m.group(1)) if m else None


class MacCollector(Collector):
    name = "macos"

    @staticmethod
    def available() -> bool:
        return sys.platform == "darwin"

    def collect(self) -> NodeSnapshot:
        if not self.available():
            raise CollectorUnavailable("The macos collector only runs on macOS.")

        chip = _run("sysctl", "-n", "machdep.cpu.brand_string").strip() or "Apple Silicon"
        memsize = _run("sysctl", "-n", "hw.memsize").strip()
        speed_limit = parse_cpu_speed_limit(_run("pmset", "-g", "therm"))

        gpu = GpuSample(
            index=0,
            name=f"{chip} (integrated GPU)",
            memory_total_mb=int(memsize) / 1024**2 if memsize.isdigit() else None,
            memory_used_mb=parse_vm_stat_used_mb(_run("vm_stat")),
            throttle_reasons=["sw_thermal"] if speed_limit is not None and speed_limit < 100 else [],
        )
        return NodeSnapshot(
            hostname=socket.gethostname(),
            collector=self.name,
            timestamp=time.time(),
            gpus=[gpu],
            notes=["macOS exposes limited GPU metrics without sudo; temperature, power and clocks are unavailable."],
        )

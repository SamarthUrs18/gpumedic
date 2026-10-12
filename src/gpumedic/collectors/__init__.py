from __future__ import annotations

import sys
from typing import Optional

from .base import Collector, CollectorUnavailable
from .macos import MacCollector
from .mock import SCENARIOS, MockCollector
from .nvml import NvmlCollector
from .replay import ReplayCollector

__all__ = ["Collector", "CollectorUnavailable", "SCENARIOS", "get_collector"]


def get_collector(
    kind: str = "auto", scenario: Optional[str] = None, replay: Optional[str] = None
) -> Collector:
    if replay:
        return ReplayCollector(replay)
    if scenario or kind == "mock":
        return MockCollector(scenario or "healthy")
    if kind == "nvml":
        return NvmlCollector()
    if kind == "macos":
        return MacCollector()
    if kind != "auto":
        raise CollectorUnavailable(f"Unknown collector {kind!r}")

    if NvmlCollector.available():
        return NvmlCollector()
    if sys.platform == "darwin":
        return MacCollector()
    raise CollectorUnavailable(
        "No NVIDIA GPU found (or NVML not installed). "
        "Install with: pip install 'gpumedic[nvidia]', or try --mock healthy"
    )

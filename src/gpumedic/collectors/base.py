from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import NodeSnapshot


class CollectorUnavailable(RuntimeError):
    """Raised when a collector cannot run on this machine."""


class Collector(ABC):
    name: str = "base"

    @abstractmethod
    def collect(self) -> NodeSnapshot:
        """Take one snapshot of every GPU on this node."""

"""Replay a snapshot saved by `gpumedic capture` (or `scan --json`)."""

from __future__ import annotations

import json
from pathlib import Path

from ..models import NodeSnapshot, UnsupportedSchema
from .base import Collector, CollectorUnavailable


class ReplayCollector(Collector):
    def __init__(self, path: str):
        p = Path(path)
        if p.is_dir():
            p = p / "snapshot.json"
        if not p.is_file():
            raise CollectorUnavailable(f"No snapshot found at {p}")
        self.path = p
        self.name = f"replay:{p}"

    def collect(self) -> NodeSnapshot:
        data = json.loads(self.path.read_text())
        # Accept both a bare snapshot and the full `scan --json` output.
        try:
            snapshot = NodeSnapshot.from_dict(data.get("snapshot", data))
        except UnsupportedSchema as e:
            raise CollectorUnavailable(str(e)) from e
        snapshot.collector = self.name
        return snapshot

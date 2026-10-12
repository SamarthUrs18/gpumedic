"""Record raw hardware output on a real GPU node so it can be replayed elsewhere.

Run `gpumedic capture` on a RunPod pod (or any GPU node), copy the folder
back, then `gpumedic scan --replay <folder>` on the Mac.
"""

from __future__ import annotations

import json
import socket
import subprocess
import time
from pathlib import Path
from typing import Optional

from .collectors import CollectorUnavailable, get_collector

_QUERY_FIELDS = ",".join([
    "index", "name", "pci.bus_id", "temperature.gpu", "power.draw", "power.limit",
    "utilization.gpu", "clocks.sm", "clocks.max.sm", "clocks_throttle_reasons.active",
    "ecc.errors.corrected.volatile.total", "ecc.errors.uncorrected.volatile.total",
    "pcie.link.gen.current", "pcie.link.gen.max", "pcie.link.width.current", "pcie.link.width.max",
])

COMMANDS: dict[str, list[str]] = {
    "nvidia-smi-q.xml": ["nvidia-smi", "-q", "-x"],
    "nvidia-smi-query.csv": ["nvidia-smi", f"--query-gpu={_QUERY_FIELDS}", "--format=csv"],
    "nvidia-smi-topo.txt": ["nvidia-smi", "topo", "-m"],
    "dcgmi-discovery.txt": ["dcgmi", "discovery", "-l"],
    "dcgmi-diag-r1.txt": ["dcgmi", "diag", "-r", "1"],
    "dmesg.txt": ["dmesg"],
}


def _run(cmd: list[str], timeout: int = 300) -> dict:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {"returncode": out.returncode, "stdout": out.stdout, "stderr": out.stderr[-2000:]}
    except FileNotFoundError:
        return {"returncode": None, "stdout": "", "stderr": f"{cmd[0]} not installed"}
    except subprocess.TimeoutExpired:
        return {"returncode": None, "stdout": "", "stderr": f"timed out after {timeout}s"}


def capture(out_root: str = "captures", collector_kind: str = "auto") -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = Path(out_root) / f"{socket.gethostname()}-{stamp}"
    out.mkdir(parents=True, exist_ok=False)

    manifest: dict[str, Optional[dict]] = {}
    for filename, cmd in COMMANDS.items():
        result = _run(cmd)
        if result["stdout"]:
            (out / filename).write_text(result["stdout"])
        manifest[filename] = {"command": cmd, "returncode": result["returncode"], "stderr": result["stderr"]}

    try:
        snapshot = get_collector(collector_kind).collect()
        (out / "snapshot.json").write_text(json.dumps(snapshot.to_dict(), indent=2))
        manifest["snapshot.json"] = {"collector": snapshot.collector, "returncode": 0, "stderr": ""}
    except CollectorUnavailable as e:
        manifest["snapshot.json"] = {"collector": collector_kind, "returncode": None, "stderr": str(e)}

    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return out

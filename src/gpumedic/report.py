from __future__ import annotations

import json
from typing import Optional

from .models import Diagnosis, Severity, Verdict

_COLORS = {
    Verdict.HEALTHY: "\033[32m",
    Verdict.WARNING: "\033[33m",
    Verdict.DRAIN: "\033[31m",
    Severity.INFO: "\033[36m",
    Severity.WARN: "\033[33m",
    Severity.CRIT: "\033[31m",
}
_BOLD, _DIM, _RESET = "\033[1m", "\033[2m", "\033[0m"


def _fmt(value: Optional[float], unit: str = "", fmt: str = "{:.0f}") -> str:
    return "-" if value is None else fmt.format(value) + unit


def _pair(value: Optional[float], limit: Optional[float], unit: str) -> str:
    if value is None:
        return "-"
    return f"{value:.0f}/{limit:.0f}{unit}" if limit is not None else f"{value:.0f}{unit}"


def render_text(diag: Diagnosis, color: bool = False) -> str:
    def c(key, text: str) -> str:
        return f"{_COLORS[key]}{text}{_RESET}" if color else text

    def style(code: str, text: str) -> str:
        return f"{code}{text}{_RESET}" if color else text

    node = diag.snapshot
    header = f"gpumedic · {node.hostname} · {node.collector}"
    if node.driver_version:
        header += f" · driver {node.driver_version}"
    lines = [style(_BOLD, header), ""]

    rows = [("GPU", "MODEL", "TEMP", "POWER", "UTIL", "SM CLOCK", "MEMORY", "VERDICT")]
    for g in node.gpus:
        mem = _pair(g.memory_used_mb / 1024 if g.memory_used_mb is not None else None,
                    g.memory_total_mb / 1024 if g.memory_total_mb is not None else None, "G")
        rows.append((
            str(g.index),
            g.name[:28],
            _fmt(g.temperature_c, "°C"),
            _pair(g.power_w, g.power_limit_w, "W"),
            _fmt(g.utilization_pct, "%"),
            _pair(g.sm_clock_mhz, g.max_sm_clock_mhz, ""),
            mem,
            diag.gpu_verdict(g.index).value,
        ))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for n, row in enumerate(rows):
        cells = [cell.ljust(widths[i]) for i, cell in enumerate(row)]
        if n == 0:
            lines.append(style(_DIM, "  ".join(cells).rstrip()))
        else:
            cells[-1] = c(Verdict(row[-1]), cells[-1])
            lines.append("  ".join(cells).rstrip())
    if not node.gpus:
        lines.append("(no GPUs visible)")

    lines += ["", style(_BOLD, "Findings")]
    if not diag.findings:
        lines.append("  None. Everything looks healthy.")
    shown_actions = set()
    for f in diag.findings:
        where = f"GPU {f.gpu_index}" if f.gpu_index is not None else "node"
        lines.append(f"  {c(f.severity, f.severity.name.ljust(4))}  {where.ljust(6)}  {f.message}  {style(_DIM, f'[{f.code}]')}")
        if f.action and (f.gpu_index, f.action) not in shown_actions:
            shown_actions.add((f.gpu_index, f.action))
            lines.append(f"              → {f.action}")

    for note in node.notes:
        lines.append(style(_DIM, f"  note: {note}"))

    verdict = diag.node_verdict
    drain = sum(1 for g in node.gpus if diag.gpu_verdict(g.index) is Verdict.DRAIN)
    warn = sum(1 for g in node.gpus if diag.gpu_verdict(g.index) is Verdict.WARNING)
    node_issues = sum(1 for f in diag.findings if f.gpu_index is None and f.severity >= Severity.WARN)
    parts = []
    if drain:
        parts.append(f"{_plural(drain, 'GPU')} to drain")
    if warn:
        parts.append(f"{_plural(warn, 'GPU')} with warnings")
    if node_issues:
        parts.append(f"{_plural(node_issues, 'node-level issue')}")
    summary = f" ({', '.join(parts)})" if parts else ""
    lines += ["", f"Node verdict: {c(verdict, style(_BOLD, verdict.value))}{summary}"]
    return "\n".join(lines)


def _plural(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def render_json(diag: Diagnosis) -> str:
    return json.dumps(diag.to_dict(), indent=2)

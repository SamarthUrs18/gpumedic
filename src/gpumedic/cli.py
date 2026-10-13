"""gpumedic command line.

Exit codes (so Slurm health checks and scripts can use them):
  0 healthy, 1 warnings, 2 at least one GPU should be drained, 3 gpumedic itself failed.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Optional

from . import __version__
from .capture import capture
from .collectors import SCENARIOS, CollectorUnavailable, get_collector
from .models import Verdict
from .report import render_json, render_text
from .rules import diagnose

EXIT_CODES = {Verdict.HEALTHY: 0, Verdict.WARNING: 1, Verdict.DRAIN: 2}
EXIT_ERROR = 3


def _add_source_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--collector", default="auto", choices=["auto", "nvml", "macos", "mock"],
                   help="where to read GPU data from (default: auto-detect)")
    p.add_argument("--mock", metavar="SCENARIO", choices=list(SCENARIOS),
                   help="simulate a failure scenario (see `gpumedic scenarios`)")
    p.add_argument("--replay", metavar="PATH", help="replay a saved snapshot.json or capture folder")
    p.add_argument("--expect-gpus", type=int, metavar="N", help="flag the node if fewer than N GPUs are visible")
    p.add_argument("--json", action="store_true", help="print machine-readable JSON")


def _use_color() -> bool:
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


def _scan_once(args) -> int:
    snapshot = get_collector(args.collector, args.mock, args.replay).collect()
    diag = diagnose(snapshot, expected_gpus=args.expect_gpus)
    print(render_json(diag) if args.json else render_text(diag, color=_use_color()))
    return EXIT_CODES[diag.node_verdict]


def cmd_scan(args) -> int:
    return _scan_once(args)


def cmd_watch(args) -> int:
    try:
        while True:
            if not args.json:
                print("\033[2J\033[H", end="")
            _scan_once(args)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print()  # end the ^C line so the shell prompt starts on its own line
        return 0


def cmd_capture(args) -> int:
    out = capture(args.out, args.collector)
    print(f"Saved capture to {out}")
    print(f"Copy it to your dev machine and run: gpumedic scan --replay {out}")
    return 0


def cmd_scenarios(args) -> int:
    width = max(len(name) for name in SCENARIOS)
    for name, (description, _) in SCENARIOS.items():
        print(f"{name.ljust(width)}  {description}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gpumedic", description="Find GPU node problems and say what to do about them.")
    parser.add_argument("--version", action="version", version=f"gpumedic {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="check this node once and print a health report")
    _add_source_args(scan)
    scan.set_defaults(func=cmd_scan)

    watch = sub.add_parser("watch", help="re-scan every few seconds")
    _add_source_args(watch)
    watch.add_argument("--interval", type=float, default=5.0, help="seconds between scans (default: 5)")
    watch.set_defaults(func=cmd_watch)

    cap = sub.add_parser("capture", help="record raw GPU output for replay on another machine")
    cap.add_argument("--out", default="captures", help="parent folder for the capture (default: captures/)")
    cap.add_argument("--collector", default="auto", choices=["auto", "nvml", "macos"])
    cap.set_defaults(func=cmd_capture)

    scen = sub.add_parser("scenarios", help="list mock failure scenarios")
    scen.set_defaults(func=cmd_scenarios)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except CollectorUnavailable as e:
        print(f"gpumedic: {e}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())

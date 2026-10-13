#!/usr/bin/env bash
# Check gpumedic on a real NVIDIA machine (e.g. a RunPod pod) in one go.
#
#   cd /workspace/gpumedic && bash scripts/runpod-check.sh
#
# Installs gpumedic, runs a scan, records a capture, and packs everything
# into one .tar.gz to copy back to your dev machine.
set -uo pipefail

cd "$(dirname "$0")/.."

echo "== Installing gpumedic with NVIDIA support"
pip install -q -e ".[nvidia]" || exit 1

echo
echo "== nvidia-smi"
nvidia-smi || echo "(nvidia-smi failed)"

echo
echo "== gpumedic scan"
gpumedic scan
echo "exit code: $? (0 healthy, 1 warnings, 2 drain, 3 gpumedic failed)"

echo
echo "== gpumedic capture"
out=$(gpumedic capture | sed -n 's/^Saved capture to //p')
if [ -z "$out" ]; then
    echo "Capture failed"
    exit 1
fi
gpumedic scan --json > "$out/scan.json"

archive="$out.tar.gz"
tar czf "$archive" -C "$(dirname "$out")" "$(basename "$out")"
echo
echo "== Done: $archive"
echo "Copy it to your Mac, e.g.:"
echo "  scp -P <PORT> root@<POD_IP>:$(pwd)/$archive ."
echo "Then: tar xzf $(basename "$archive") && gpumedic scan --replay $(basename "$out")"

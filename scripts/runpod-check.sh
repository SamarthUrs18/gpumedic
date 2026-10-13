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
# A venv of its own: images like RunPod's refuse pip into the system Python (PEP 668).
python3 -m venv .venv || exit 1
.venv/bin/pip install -q -e ".[nvidia]" || exit 1
gpumedic() { .venv/bin/gpumedic "$@"; }

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

# RunPod puts the pod's public address in PID 1's environment; an SSH session may not inherit it.
runpod_var() { printenv "$1" 2>/dev/null || tr '\0' '\n' < /proc/1/environ 2>/dev/null | sed -n "s/^$1=//p"; }
ip=$(runpod_var RUNPOD_PUBLIC_IP)
port=$(runpod_var RUNPOD_TCP_PORT_22)
echo "To copy it back, leave this machine (exit) and run on YOUR computer:"
echo "  scp -P ${port:-<PORT>} -i ~/.ssh/id_rsa root@${ip:-<POD_IP>}:$(pwd)/$archive ."
echo "Then: tar xzf $(basename "$archive") && gpumedic scan --replay $(basename "$out")"

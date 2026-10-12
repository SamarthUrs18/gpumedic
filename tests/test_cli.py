import json

import pytest

from gpumedic.cli import main


@pytest.mark.parametrize(
    "scenario, code",
    [("healthy", 0), ("pcie-degraded", 1), ("overheating", 2), ("fallen-off-bus", 2)],
)
def test_scan_exit_codes(scenario, code, capsys):
    assert main(["scan", "--mock", scenario]) == code
    assert "Node verdict" in capsys.readouterr().out


def test_scan_json_can_be_replayed(tmp_path, capsys):
    assert main(["scan", "--mock", "ecc", "--json"]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["node_verdict"] == "DRAIN"
    assert output["gpu_verdicts"]["5"] == "DRAIN"

    saved = tmp_path / "scan.json"
    saved.write_text(json.dumps(output))
    assert main(["scan", "--replay", str(saved)]) == 2


def test_missing_replay_file_is_a_tool_error(capsys):
    assert main(["scan", "--replay", "/nonexistent/snapshot.json"]) == 3
    assert "No snapshot found" in capsys.readouterr().err


def test_scenarios_lists_all(capsys):
    assert main(["scenarios"]) == 0
    assert "fallen-off-bus" in capsys.readouterr().out

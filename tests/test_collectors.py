import json

import pytest

from gpumedic.collectors.base import CollectorUnavailable
from gpumedic.collectors.kernel_log import attach_xids, normalize_pci_bus_id, parse_xids
from gpumedic.collectors.macos import parse_cpu_speed_limit, parse_vm_stat_used_mb
from gpumedic.collectors.mock import MockCollector
from gpumedic.collectors.nvml import decode_throttle_reasons
from gpumedic.collectors.replay import ReplayCollector
from gpumedic.models import SCHEMA_VERSION, GpuSample, NodeSnapshot, UnsupportedSchema

DMESG = """\
[ 1234.5] NVRM: Xid (PCI:0000:3b:00): 79, pid=4242, name=python, GPU has fallen off the bus.
[ 1300.0] some unrelated line
[ 1400.1] NVRM: Xid (PCI:0000:9A:00): 48, pid='<unknown>', name=<unknown>, An uncorrectable double bit error
"""


def test_normalize_pci_bus_id():
    assert normalize_pci_bus_id("00000000:3B:00.0") == "3b:00"
    assert normalize_pci_bus_id("0000:3b:00") == "3b:00"


def test_parse_xids():
    events = parse_xids(DMESG.splitlines())
    assert [(e.xid, e.pci_bus_id) for e in events] == [(79, "3b:00"), (48, "9a:00")]
    assert "fallen off the bus" in events[0].message


def test_attach_xids_returns_unmatched():
    gpus = [GpuSample(index=0, name="x", pci_bus_id="9a:00")]
    unmatched = attach_xids(gpus, parse_xids(DMESG.splitlines()))
    assert [e.xid for e in gpus[0].xid_events] == [48]
    assert [e.xid for e in unmatched] == [79]


def test_decode_throttle_reasons():
    assert decode_throttle_reasons(0x4 | 0x40) == ["sw_power_cap", "hw_thermal"]
    assert decode_throttle_reasons(0) == []


def test_macos_parsers():
    vm_stat = (
        "Mach Virtual Memory Statistics: (page size of 16384 bytes)\n"
        "Pages active:                  100000.\n"
        "Pages wired down:              50000.\n"
        "Pages occupied by compressor:  10000.\n"
    )
    assert parse_vm_stat_used_mb(vm_stat) == 160000 * 16384 / 1024**2
    assert parse_cpu_speed_limit("CPU_Scheduler_Limit = 100\nCPU_Speed_Limit = 70") == 70
    assert parse_cpu_speed_limit("Note: No thermal warning level has been recorded") is None


def test_snapshot_round_trips_through_replay(tmp_path):
    original = MockCollector("ecc").collect()
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(original.to_dict()))

    replayed = ReplayCollector(str(tmp_path)).collect()
    assert replayed.collector.startswith("replay:")
    replayed.collector = original.collector
    assert replayed == original
    assert NodeSnapshot.from_dict(original.to_dict()) == original


def test_snapshot_records_schema_version():
    assert MockCollector("healthy").collect().to_dict()["schema_version"] == SCHEMA_VERSION


def test_snapshot_from_before_versioning_is_accepted():
    data = MockCollector("healthy").collect().to_dict()
    del data["schema_version"]
    assert NodeSnapshot.from_dict(data).gpus


def test_newer_schema_is_refused(tmp_path):
    data = MockCollector("healthy").collect().to_dict()
    data["schema_version"] = SCHEMA_VERSION + 1
    with pytest.raises(UnsupportedSchema):
        NodeSnapshot.from_dict(data)

    (tmp_path / "snapshot.json").write_text(json.dumps(data))
    with pytest.raises(CollectorUnavailable, match="Upgrade gpumedic"):
        ReplayCollector(str(tmp_path)).collect()

"""Run the NVML collector against a fake pynvml, so it is exercised without a GPU.

GPU 0 is a datacenter card that supports everything. GPU 1 is a consumer
card that raises NVMLError for ECC and row remapping, as real ones do.
"""

import types
from types import SimpleNamespace

import pytest

from gpumedic.collectors import nvml as nvml_collector
from gpumedic.collectors.nvml import NvmlCollector
from gpumedic.models import XidEvent


class NVMLError(Exception):
    pass


def unsupported(*args):
    raise NVMLError("Not Supported")


GPUS = [
    {
        "name": b"NVIDIA H100 80GB HBM3",  # older bindings return bytes
        "uuid": "GPU-0000",
        "bus": "00000000:3B:00.0",
        "temp": 64, "slowdown": 87,
        "power_mw": 612_000, "limit_mw": 700_000,
        "util": 97, "used": 70 * 1024**3, "total": 80 * 1024**3,
        "clock": 1980, "max_clock": 1980,
        "reasons": 0x4,  # sw_power_cap
        "ecc": {0: 3, 1: 0}, "remap": (0, 0, True, False),
        "pcie": (5, 5, 16, 16),
    },
    {
        "name": "NVIDIA GeForce RTX 4090",
        "uuid": "GPU-0001",
        "bus": "00000000:9A:00.0",
        "temp": 71, "slowdown": 90,
        "power_mw": 300_000, "limit_mw": 450_000,
        "util": 20, "used": 2 * 1024**3, "total": 24 * 1024**3,
        "clock": 2520, "max_clock": 3105,
        "reasons": 0x1 | 0x40,  # gpu_idle, hw_thermal
        "ecc": None, "remap": None,
        "pcie": (4, 4, 8, 16),
    },
]


def make_fake_pynvml(renamed_reasons_fn: bool) -> types.ModuleType:
    nv = types.ModuleType("pynvml")
    nv.NVMLError = NVMLError
    nv.NVML_TEMPERATURE_GPU = 0
    nv.NVML_TEMPERATURE_THRESHOLD_SLOWDOWN = 1
    nv.NVML_CLOCK_SM = 1
    nv.NVML_MEMORY_ERROR_TYPE_CORRECTED = 0
    nv.NVML_MEMORY_ERROR_TYPE_UNCORRECTED = 1
    nv.NVML_VOLATILE_ECC = 0

    nv.nvmlInit = lambda: None
    nv.nvmlShutdown = lambda: None
    nv.nvmlSystemGetDriverVersion = lambda: b"550.54.15"
    nv.nvmlDeviceGetCount = lambda: len(GPUS)
    nv.nvmlDeviceGetHandleByIndex = lambda i: GPUS[i]
    nv.nvmlDeviceGetName = lambda h: h["name"]
    nv.nvmlDeviceGetUUID = lambda h: h["uuid"]
    nv.nvmlDeviceGetPciInfo = lambda h: SimpleNamespace(busId=h["bus"].encode())
    nv.nvmlDeviceGetTemperature = lambda h, sensor: h["temp"]
    nv.nvmlDeviceGetTemperatureThreshold = lambda h, kind: h["slowdown"]
    nv.nvmlDeviceGetPowerUsage = lambda h: h["power_mw"]
    nv.nvmlDeviceGetEnforcedPowerLimit = lambda h: h["limit_mw"]
    nv.nvmlDeviceGetUtilizationRates = lambda h: SimpleNamespace(gpu=h["util"], memory=0)
    nv.nvmlDeviceGetMemoryInfo = lambda h: SimpleNamespace(used=h["used"], total=h["total"])
    nv.nvmlDeviceGetClockInfo = lambda h, clock: h["clock"]
    nv.nvmlDeviceGetMaxClockInfo = lambda h, clock: h["max_clock"]
    nv.nvmlDeviceGetCurrPcieLinkGeneration = lambda h: h["pcie"][0]
    nv.nvmlDeviceGetMaxPcieLinkGeneration = lambda h: h["pcie"][1]
    nv.nvmlDeviceGetCurrPcieLinkWidth = lambda h: h["pcie"][2]
    nv.nvmlDeviceGetMaxPcieLinkWidth = lambda h: h["pcie"][3]

    def ecc(h, error_type, counter):
        return unsupported() if h["ecc"] is None else h["ecc"][error_type]

    def remap(h):
        return unsupported() if h["remap"] is None else h["remap"]

    nv.nvmlDeviceGetTotalEccErrors = ecc
    nv.nvmlDeviceGetRemappedRows = remap

    reasons = lambda h: h["reasons"]  # noqa: E731
    if renamed_reasons_fn:
        nv.nvmlDeviceGetCurrentClocksEventReasons = reasons
    nv.nvmlDeviceGetCurrentClocksThrottleReasons = reasons
    return nv


@pytest.fixture(params=[True, False], ids=["new-nvml", "old-nvml"])
def fake_nvml(request, monkeypatch):
    nv = make_fake_pynvml(renamed_reasons_fn=request.param)
    monkeypatch.setitem(__import__("sys").modules, "pynvml", nv)
    xids = [XidEvent(79, "5d:00", "GPU has fallen off the bus."), XidEvent(13, "9a:00", "")]
    monkeypatch.setattr(nvml_collector, "read_kernel_xids", lambda: (xids, None))
    return nv


def test_nvml_snapshot_fields(fake_nvml):
    assert NvmlCollector.available()
    node = NvmlCollector().collect()
    assert node.driver_version == "550.54.15"
    h100 = node.gpus[0]

    assert h100.name == "NVIDIA H100 80GB HBM3"
    assert h100.pci_bus_id == "3b:00"
    assert (h100.temperature_c, h100.slowdown_temp_c) == (64, 87)
    assert (h100.power_w, h100.power_limit_w) == (612.0, 700.0)
    assert (h100.memory_used_mb, h100.memory_total_mb) == (70 * 1024, 80 * 1024)
    assert h100.throttle_reasons == ["sw_power_cap"]
    assert (h100.ecc_corrected, h100.ecc_uncorrected) == (3, 0)
    assert (h100.remap_pending, h100.remap_failed) == (True, False)


def test_unsupported_queries_become_none(fake_nvml):
    rtx = NvmlCollector().collect().gpus[1]
    assert rtx.ecc_corrected is None and rtx.ecc_uncorrected is None
    assert rtx.remap_pending is None and rtx.remap_failed is None
    assert rtx.throttle_reasons == ["gpu_idle", "hw_thermal"]
    assert (rtx.pcie_width, rtx.pcie_width_max) == (8, 16)


def test_xids_are_attached_by_pci_address(fake_nvml):
    node = NvmlCollector().collect()
    assert [e.xid for e in node.gpus[1].xid_events] == [13]
    assert [e.xid for e in node.unmatched_xids] == [79]

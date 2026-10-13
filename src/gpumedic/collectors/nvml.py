"""Real NVIDIA GPUs via NVML (pip install 'gpumedic[nvidia]')."""

from __future__ import annotations

import socket
import time
from typing import Any, Callable, Optional

from ..models import GpuSample, NodeSnapshot
from .base import Collector, CollectorUnavailable
from .kernel_log import attach_xids, normalize_pci_bus_id, read_kernel_xids

# NVML clock throttle ("clocks event") reason bits.
_THROTTLE_BITS = {
    0x1: "gpu_idle",
    0x2: "app_clocks",
    0x4: "sw_power_cap",
    0x8: "hw_slowdown",
    0x10: "sync_boost",
    0x20: "sw_thermal",
    0x40: "hw_thermal",
    0x80: "hw_power_brake",
    0x100: "display_clocks",
}


def decode_throttle_reasons(mask: int) -> list[str]:
    return [name for bit, name in _THROTTLE_BITS.items() if mask & bit]


def _text(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


def _import_nvml():
    try:
        import pynvml  # provided by the nvidia-ml-py package
    except ImportError as e:
        raise CollectorUnavailable(
            "NVML bindings not installed. Run: pip install 'gpumedic[nvidia]'"
        ) from e
    return pynvml


class NvmlCollector(Collector):
    name = "nvml"

    @staticmethod
    def available() -> bool:
        try:
            nv = _import_nvml()
            nv.nvmlInit()
            nv.nvmlShutdown()
            return True
        except Exception:
            return False

    def collect(self) -> NodeSnapshot:
        nv = _import_nvml()
        try:
            nv.nvmlInit()
        except nv.NVMLError as e:
            raise CollectorUnavailable(f"NVML failed to initialize: {e}") from e
        try:
            driver = _text(nv.nvmlSystemGetDriverVersion())
            gpus = [self._sample(nv, i) for i in range(nv.nvmlDeviceGetCount())]
        finally:
            nv.nvmlShutdown()

        xids, note = read_kernel_xids()
        return NodeSnapshot(
            hostname=socket.gethostname(),
            collector=self.name,
            timestamp=time.time(),
            driver_version=driver,
            gpus=gpus,
            unmatched_xids=attach_xids(gpus, xids),
            notes=[note] if note else [],
        )

    @staticmethod
    def _sample(nv, index: int) -> GpuSample:
        def q(fn: Callable, *args) -> Optional[Any]:
            # Many queries are unsupported on some GPUs (e.g. ECC on consumer cards).
            try:
                return fn(*args)
            except nv.NVMLError:
                return None

        h = nv.nvmlDeviceGetHandleByIndex(index)
        mem = q(nv.nvmlDeviceGetMemoryInfo, h)
        util = q(nv.nvmlDeviceGetUtilizationRates, h)
        pci = q(nv.nvmlDeviceGetPciInfo, h)
        power_mw = q(nv.nvmlDeviceGetPowerUsage, h)
        limit_mw = q(nv.nvmlDeviceGetEnforcedPowerLimit, h)
        # Renamed from "throttle reasons" to "clocks event reasons" in newer NVML.
        reasons_fn = getattr(nv, "nvmlDeviceGetCurrentClocksEventReasons", None) or nv.nvmlDeviceGetCurrentClocksThrottleReasons
        reasons = q(reasons_fn, h)
        remap = q(nv.nvmlDeviceGetRemappedRows, h)  # (corrected, uncorrected, pending, failed)

        return GpuSample(
            index=index,
            name=_text(nv.nvmlDeviceGetName(h)),
            uuid=_text(q(nv.nvmlDeviceGetUUID, h) or ""),
            pci_bus_id=normalize_pci_bus_id(_text(pci.busId)) if pci else "",
            temperature_c=q(nv.nvmlDeviceGetTemperature, h, nv.NVML_TEMPERATURE_GPU),
            slowdown_temp_c=q(
                nv.nvmlDeviceGetTemperatureThreshold, h, nv.NVML_TEMPERATURE_THRESHOLD_SLOWDOWN
            ),
            power_w=power_mw / 1000 if power_mw is not None else None,
            power_limit_w=limit_mw / 1000 if limit_mw is not None else None,
            utilization_pct=util.gpu if util else None,
            memory_used_mb=mem.used / 1024**2 if mem else None,
            memory_total_mb=mem.total / 1024**2 if mem else None,
            sm_clock_mhz=q(nv.nvmlDeviceGetClockInfo, h, nv.NVML_CLOCK_SM),
            max_sm_clock_mhz=q(nv.nvmlDeviceGetMaxClockInfo, h, nv.NVML_CLOCK_SM),
            throttle_reasons=decode_throttle_reasons(reasons) if reasons is not None else [],
            ecc_corrected=q(
                nv.nvmlDeviceGetTotalEccErrors,
                h,
                nv.NVML_MEMORY_ERROR_TYPE_CORRECTED,
                nv.NVML_VOLATILE_ECC,
            ),
            ecc_uncorrected=q(
                nv.nvmlDeviceGetTotalEccErrors,
                h,
                nv.NVML_MEMORY_ERROR_TYPE_UNCORRECTED,
                nv.NVML_VOLATILE_ECC,
            ),
            remap_pending=bool(remap[2]) if remap else None,
            remap_failed=bool(remap[3]) if remap else None,
            pcie_gen=q(nv.nvmlDeviceGetCurrPcieLinkGeneration, h),
            pcie_gen_max=q(nv.nvmlDeviceGetMaxPcieLinkGeneration, h),
            pcie_width=q(nv.nvmlDeviceGetCurrPcieLinkWidth, h),
            pcie_width_max=q(nv.nvmlDeviceGetMaxPcieLinkWidth, h),
        )

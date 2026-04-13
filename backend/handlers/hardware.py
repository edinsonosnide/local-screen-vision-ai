"""CPU / GPU hardware monitoring."""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def get_hardware_info() -> Dict[str, Any]:
    import psutil

    vm = psutil.virtual_memory()
    info: Dict[str, Any] = {
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "ram_used_gb": round(vm.used / (1024**3), 2),
        "ram_total_gb": round(vm.total / (1024**3), 2),
        "ram_percent": vm.percent,
        "gpu": None,
        "using_gpu": False,
    }

    try:
        import pynvml  # type: ignore

        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        raw_name = pynvml.nvmlDeviceGetName(handle)
        name = raw_name if isinstance(raw_name, str) else raw_name.decode()
        info["gpu"] = {
            "name": name,
            "utilization": util.gpu,
            "mem_used_gb": round(mem.used / (1024**3), 2),
            "mem_total_gb": round(mem.total / (1024**3), 2),
        }
        info["using_gpu"] = True
    except Exception:
        pass

    return info

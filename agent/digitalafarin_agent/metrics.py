import time

import psutil


def collect_metrics() -> dict:
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    boot_time = psutil.boot_time()
    return {
        "cpu_percent": round(psutil.cpu_percent(interval=0.15), 2),
        "memory_percent": round(memory.percent, 2),
        "memory_used_bytes": memory.used,
        "memory_total_bytes": memory.total,
        "disk_percent": round(disk.percent, 2),
        "disk_used_bytes": disk.used,
        "disk_total_bytes": disk.total,
        "uptime_seconds": max(0, int(time.time() - boot_time)),
        "boot_time": int(boot_time),
    }

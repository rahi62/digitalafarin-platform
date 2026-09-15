import time

import httpx


class HealthCheckError(RuntimeError):
    pass


def _request(url: str, timeout: int) -> int:
    return httpx.get(url, timeout=timeout, follow_redirects=False).status_code


def check_http_health(spec: dict, *, request=_request, sleep=time.sleep) -> dict:
    allowed = {"url", "expected_status", "attempts", "timeout_seconds", "interval_seconds"}
    if set(spec) - allowed:
        raise HealthCheckError("invalid health check")
    url = spec.get("url")
    if not isinstance(url, str) or not url.startswith("http://127.0.0.1:"):
        raise HealthCheckError("health check must target loopback")
    expected = spec.get("expected_status", 200)
    attempts = spec.get("attempts", 6)
    timeout = spec.get("timeout_seconds", 10)
    interval = spec.get("interval_seconds", 5)
    if not 1 <= attempts <= 20 or not 1 <= timeout <= 30 or not 0 <= interval <= 30:
        raise HealthCheckError("invalid health check bounds")
    for attempt in range(1, attempts + 1):
        try:
            status = request(url, timeout)
        except Exception:
            status = None
        if status == expected:
            return {"attempts": attempt, "status": status}
        if attempt < attempts:
            sleep(interval)
    raise HealthCheckError("health check failed")

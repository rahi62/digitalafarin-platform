import time

import httpx


class HealthCheckError(RuntimeError):
    pass


def _request(url: str, timeout: int) -> int:
    return httpx.get(url, timeout=timeout, follow_redirects=False).status_code


def _validated(spec: dict) -> tuple[str, int, int, int, int]:
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
    if not isinstance(expected, int) or not 100 <= expected <= 599:
        raise HealthCheckError("invalid expected status")
    if not 1 <= attempts <= 20 or not 1 <= timeout <= 30 or not 0 <= interval <= 30:
        raise HealthCheckError("invalid health check bounds")
    return url, expected, attempts, timeout, interval


def check_http_health(spec: dict, *, request=_request, sleep=time.sleep) -> dict:
    url, expected, attempts, timeout, interval = _validated(spec)
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


def check_http_health_stable(
    spec: dict,
    *,
    required_successes: int = 2,
    request=_request,
    sleep=time.sleep,
) -> dict:
    url, expected, attempts, timeout, interval = _validated(spec)
    if required_successes != 2:
        raise HealthCheckError("invalid consecutive health requirement")
    streak = 0
    for attempt in range(1, attempts + 1):
        try:
            status = request(url, timeout)
        except Exception:
            status = None
        if status == expected:
            streak += 1
            if streak == required_successes:
                return {
                    "attempts": attempt,
                    "status": status,
                    "consecutive_successes": streak,
                }
        else:
            streak = 0
        if attempt < attempts:
            sleep(1 if streak == 1 else interval)
    raise HealthCheckError("health check failed")

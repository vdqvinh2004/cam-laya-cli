"""Local-only rules timing; no models, no provider usage of any kind."""

import platform
import statistics
import subprocess
import sys
import time

from .engine import decide

PROBE = {"preset": "test_decision", "state": {"last_test_result": "failed"}}


def distribution(samples):
    ordered = sorted(samples)
    return {"samples_ms": samples, "median_ms": round(statistics.median(samples), 3),
            "p95_ms": round(ordered[max(0, int(len(samples) * .95 + .999) - 1)], 3)}


def run(samples=100):
    if type(samples) is not int or not 1 <= samples <= 1000:
        raise ValueError("samples must be between one and 1000")
    timings = []
    for _ in range(samples):
        started = time.perf_counter()
        result = decide(PROBE)
        timings.append(round((time.perf_counter() - started) * 1000, 3))
        if result["status"] != "ok":
            raise ValueError("rules benchmark returned a non-ok result")
    processes = []
    for _ in range(samples):
        started = time.perf_counter()
        child = subprocess.run([sys.executable, "-m", "cam_laya_cli", "preset", "test_decision"],
                               input=b'{"last_test_result":"failed"}',
                               capture_output=True, timeout=70)
        processes.append(round((time.perf_counter() - started) * 1000, 3))
        if child.returncode:
            raise ValueError("fresh CLI benchmark failed")
    return {"status": "ok", "platform": platform.platform(), "python": platform.python_version(),
            "samples": samples, "mode": "rules-only", "probe": PROBE,
            "direct": distribution(timings), "fresh_cli": distribution(processes),
            "provider_tokens": None, "billed_usd": None}

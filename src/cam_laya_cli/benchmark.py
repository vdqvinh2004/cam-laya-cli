"""Local-only measurements; provider tokens and billed charges remain unknown."""

import json
import platform
import resource
import statistics
import subprocess
import sys
import time

from .engine import Engine, validate
from .worker import Client, encode, request


def distribution(samples):
    ordered = sorted(samples)
    return {"samples_ms": samples, "median_ms": round(statistics.median(samples), 3),
            "p95_ms": round(ordered[max(0, int(len(samples) * .95 + .999) - 1)], 3)}


def run(value, samples=100):
    if type(samples) is not int or not 1 <= samples <= 1000:
        raise ValueError("samples must be between one and 1000")
    validate(value)
    message = {"op": "decide", "request": value}
    prior = None
    try:
        prior = request({"op": "status"}, start=False, timeout=1)
    except Exception:
        pass
    started = time.perf_counter()
    first = request(message)
    first_ms = (time.perf_counter() - started) * 1000
    if first["status"] not in {"ok", "abstained"}:
        return {"status": "unavailable", "first_response": first, "first_call_ms": first_ms}
    ipc, processes, inference, queue, overhead = [], [], [], [], []
    with Client() as client:
        for _ in range(samples):
            started = time.perf_counter()
            result = client.call(message)
            ipc.append(round((time.perf_counter() - started) * 1000, 3))
            if result["status"] not in {"ok", "abstained"}:
                raise ValueError("warm benchmark returned an unavailable result")
            inference.append(result.get("inference_ms", 0))
            queue.append(result["timing"]["queue_ms"])
    for _ in range(samples):
        started = time.perf_counter()
        child = subprocess.run([sys.executable, "-m", "cam_laya_cli", "decide", "--input", "-"],
                               input=encode(value), capture_output=True, timeout=70)
        elapsed = round((time.perf_counter() - started) * 1000, 3)
        processes.append(elapsed)
        if child.returncode:
            raise ValueError("fresh CLI benchmark failed")
        result = json.loads(child.stdout)
        overhead.append(round(elapsed - result["timing"]["total_ms"], 3))
    engine = Engine()
    direct_first = time.perf_counter()
    direct = engine.decide(value)
    direct_first_ms = (time.perf_counter() - direct_first) * 1000
    timings = []
    for _ in range(samples):
        started = time.perf_counter()
        engine.decide(value)
        timings.append(round((time.perf_counter() - started) * 1000, 3))
    encode_times = []
    for _ in range(samples):
        started = time.perf_counter()
        encode(result)
        encode_times.append(round((time.perf_counter() - started) * 1000, 3))
    worker = request({"op": "status"}, start=False, timeout=1)
    memory = subprocess.run(["ps", "-o", "rss=", "-p", str(worker["pid"])],
                            capture_output=True, text=True, timeout=2)
    return {"status": "ok", "platform": platform.platform(), "python": platform.python_version(),
            "samples": samples, "source": first["source"], "checkpoint": first.get("model"),
            "worker_was_running": bool(prior), "worker_was_warm": bool(prior and prior.get("model_loaded")),
            "first_call_ms": round(first_ms, 3), "first_response": first,
            "ipc": distribution(ipc), "fresh_cli": distribution(processes),
            "inference": distribution(inference), "queue": distribution(queue),
            "direct_engine": distribution(timings), "direct_first_ms": round(direct_first_ms, 3),
            "direct_status": direct["status"], "output_formatting": distribution(encode_times),
            "response_bytes": len(encode(result)),
            "fresh_cli_non_engine": distribution(overhead),
            "worker_pid": worker["pid"], "worker_model_loads": worker["model_loads"],
            "worker_rss_kib": int(memory.stdout.strip()) if memory.returncode == 0 and memory.stdout.strip() else None,
            "max_rss": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "max_rss_units": "bytes" if sys.platform == "darwin" else "KiB",
            "memory_scope": "benchmark process including independent direct engine; not worker RSS",
            "provider_tokens": None, "billed_usd": None,
            "claims": {"whole_task_gain": False, "billed_saving": False}}

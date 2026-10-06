"""One inference implementation for CLI and benchmark-only MCP."""

import importlib.util
import math
import platform
import threading
import time
from collections import Counter

from .config import MODELS, checkpoint
from .presets import OPTIONS, SAFE_COMMANDS, deterministic_choice, hard_risk


class Unavailable(Exception):
    """Operational failure safe to expose without request contents."""


def finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("JSON numbers must be finite")
    if isinstance(value, dict):
        for item in value.values():
            finite(item)
    elif isinstance(value, list):
        for item in value:
            finite(item)


def validate(request):
    if not isinstance(request, dict):
        raise ValueError("request must be an object")
    if request.keys() - {"id", "state", "questions", "preset", "model", "min_confidence"}:
        raise ValueError("unknown request field")
    state = request.get("state")
    if not isinstance(state, (str, dict, list)):
        raise ValueError("state must be text, an object, or a conversation list")
    finite(request)
    if "id" in request and (type(request["id"]) not in (str, int) or len(str(request["id"])) > 128):
        raise ValueError("id must be a string or integer of at most 128 characters")
    if not isinstance(request.get("model", "auto"), str) or request.get("model", "auto") not in {"auto", *MODELS}:
        raise ValueError("model must be auto, english, multilingual, or typed-decisions")
    threshold = request.get("min_confidence")
    if threshold is not None and (type(threshold) not in (int, float) or not 0 <= threshold <= 1):
        raise ValueError("min_confidence must be between zero and one")
    if ("preset" in request) == ("questions" in request):
        raise ValueError("provide exactly one of preset or questions")
    if "preset" in request:
        if not isinstance(request["preset"], str) or request["preset"] not in OPTIONS or not isinstance(state, dict):
            raise ValueError("preset must name a supported policy and state must be an object")
        if "action" in state and not isinstance(state["action"], str):
            raise ValueError("action must be text")
        return
    questions = request["questions"]
    if not isinstance(questions, dict) or not 1 <= len(questions) <= 64:
        raise ValueError("questions must contain between one and 64 definitions")
    for key, question in questions.items():
        if not isinstance(key, str) or not key.strip() or not isinstance(question, dict):
            raise ValueError("each question needs a nonempty string id and an object definition")
        kind = question.get("type")
        if not isinstance(kind, str) or kind not in {"choice", "score", "noul"}:
            raise ValueError("question type must be choice, score, or noul")
        if not isinstance(question.get("instructions"), str) or not question["instructions"].strip():
            raise ValueError("question instructions must be nonempty text")
        criteria = question.get("criteria")
        if kind in {"choice", "score"}:
            if not isinstance(criteria, (dict, list)) or not 2 <= len(criteria) <= 64:
                raise ValueError("choice and score need between two and 64 criteria")
            if kind == "score" and not isinstance(criteria, list):
                raise ValueError("score criteria must be an ordered list")
            labels = list(criteria)
            if any(not isinstance(label, str) or not label.strip() for label in labels):
                raise ValueError("criteria must have nonempty text labels")
            if len(set(labels)) != len(labels):
                raise ValueError("criteria labels must be unique")
            if isinstance(criteria, dict) and any(not isinstance(v, str) for v in criteria.values()):
                raise ValueError("choice definitions must be text")
        elif criteria is not None and (
            not isinstance(criteria, dict) or set(criteria) != {"false", "true"}
            or any(not isinstance(v, str) for v in criteria.values())
        ):
            raise ValueError("noul criteria must define false and true")


class Runtime:
    def __init__(self):
        self.router = None
        self.loaded = None
        self.loading = False
        self.error = None
        self.load_count = 0
        self.load_ms = None

    def load(self, name):
        if platform.system() != "Darwin" or platform.machine() != "arm64":
            self.error = "unsupported_platform"
            raise Unavailable("unsupported_platform")
        if importlib.util.find_spec("laya_mlx") is None:
            self.error = "mlx_extra_missing"
            raise Unavailable("mlx_extra_missing")
        if self.loaded == name:
            return self.router.load(name)
        self.loading = True
        start = time.perf_counter()
        try:
            import laya_mlx

            if self.router is None:
                self.router = laya_mlx.Router(max_loaded=1)
            try:
                path = checkpoint(name)
            except Exception as exc:
                raise Unavailable("checkpoint_not_cached") from exc
            self.router.models[name] = str(path)
            agent = self.router.load(name)
            self.loaded = name
            self.load_count += 1
            self.error = None
            return agent
        except Unavailable as exc:
            self.error = str(exc)
            raise
        except Exception as exc:
            self.error = "model_load_failed"
            raise Unavailable(self.error) from exc
        finally:
            self.load_ms = round((time.perf_counter() - start) * 1000, 3)
            self.loading = False

    def route(self, state, questions, model):
        if platform.system() != "Darwin" or platform.machine() != "arm64":
            raise Unavailable("unsupported_platform")
        if model != "auto":
            return model
        try:
            from laya_mlx import Router

            router = self.router or Router()
            return router.route(state, questions).model
        except (ImportError, OSError) as exc:
            raise Unavailable("mlx_extra_missing") from exc

    def uncalibrated(self, agent, kind, count):
        from laya_mlx.common import QTYPES, temp_bucket

        bucket = temp_bucket(QTYPES[kind], count)
        original = agent.temperature_by_options_raw.get(bucket)
        if original is None:
            original = agent.temperature_raw[QTYPES[kind]]
            applied = agent.temperature[QTYPES[kind]]
        else:
            applied = agent.temperature_by_options.get(bucket)
        return original != applied


class Engine:
    def __init__(self, runtime=None):
        self.runtime = runtime or Runtime()
        # ponytail: one inference lock bounds MLX memory; add concurrency if queue timings justify it.
        self.inference_lock = threading.RLock()
        self.metrics_lock = threading.Lock()
        self.counts = Counter()
        self.last_error = None

    def stats(self):
        with self.metrics_lock:
            return dict(self.counts)

    def status(self):
        return {"status": "ok", "model_loaded": self.runtime.loaded,
                "loading": self.runtime.loading, "model_loads": self.runtime.load_count,
                "load_ms": self.runtime.load_ms, "last_error": self.last_error or self.runtime.error}

    def warm(self, name="english"):
        with self.inference_lock:
            self.runtime.load(name)
        return self.status()

    def decide(self, request):
        validate(request)
        start = time.perf_counter()
        with self.inference_lock:
            queue_ms = (time.perf_counter() - start) * 1000
            result = self._decide(request)
        result["timing"] = {"queue_ms": round(queue_ms, 3),
                            "total_ms": round((time.perf_counter() - start) * 1000, 3)}
        with self.metrics_lock:
            self.counts["requests"] += 1
            self.counts[result["source"]] += 1
            self.counts[result["status"]] += 1
            self.counts["inference_calls"] += int(result.get("inference_ms") is not None)
        return result

    def _decide(self, request):
        state = request["state"]
        result = {"schema_version": 1, "status": "ok", "source": "rule", "model": None}
        if "id" in request:
            result["id"] = request["id"]
        policy = request.get("preset")
        if policy:
            result["preset"] = policy
            if policy == "risk_check":
                action = state.get("action", "")
                reason = hard_risk(action)
                if reason:
                    risk = "destructive" if reason in {
                        "destructive_command", "database_destruction", "infrastructure_change"} else "high"
                    result.update(risk=risk, requires_human=True, confidence=1.0, reason_code=reason)
                    return result
                if action in SAFE_COMMANDS:
                    result.update(risk="safe", requires_human=False, confidence=1.0,
                                  reason_code="deterministic_safe")
                    return result
            elif choice := deterministic_choice(policy, state):
                result.update(decision=choice, confidence=1.0, reason_code="deterministic_rule")
                return result
            questions = {"decision": {"type": "choice", "instructions":
                         f"Choose the best {policy.replace('_', ' ')} for this coding-agent state.",
                         "criteria": OPTIONS[policy]}}
        else:
            questions = request["questions"]
        result["source"] = "model"
        try:
            name = self.runtime.route(state, questions, request.get("model", "auto"))
            agent = self.runtime.load(name)
            result["model"] = {"name": name, "id": MODELS[name][0], "revision": MODELS[name][1]}
            start = time.perf_counter()
            raw = agent.predict(state, questions)
            result["inference_ms"] = round((time.perf_counter() - start) * 1000, 3)
            finite(raw)
            if set(raw["answers"]) != set(questions):
                raise ValueError("model answer ids do not match question ids")
            result["usage"] = raw["usage"]
            result["calibration"] = "unvalidated_for_workload"
            result["confidence_semantics"] = {
                "confidence": "entropy-based for choice/score; maximum probability for noul",
                "answer_confidence": "maximum option probability; not measured accuracy",
            }
            answers = {}
            for key, answer in raw["answers"].items():
                reason = None
                kind = questions[key]["type"]
                value = answer[{"choice": "choice", "score": "score", "noul": "noul"}[kind]]
                confidence = answer["answer_confidence"]
                if not 0 <= confidence <= 1 or not 0 <= answer["confidence"] <= 1:
                    raise ValueError("invalid model probabilities")
                if kind == "choice" and value not in questions[key]["criteria"]:
                    raise ValueError("invalid model label")
                if kind in {"score", "noul"} and (
                    type(value) not in (int, float) or not 0 <= value <= (
                        1 if kind == "noul" else len(questions[key]["criteria"]) - 1)
                ):
                    raise ValueError("invalid numeric model answer")
                if key in raw["usage"].get("truncated_questions", []):
                    reason = "truncated_state"
                elif key in raw["usage"].get("options", {}):
                    reason = "collapsed_options"
                else:
                    count = 2 if kind == "noul" else len(questions[key]["criteria"])
                    if self.runtime.uncalibrated(agent, kind, count):
                        reason = "uncalibrated_temperature"
                threshold = request.get("min_confidence")
                if not reason and threshold is not None and confidence < threshold:
                    reason = "low_confidence"
                answers[key] = {"type": kind, "value": None if reason else value,
                                "status": "abstained" if reason else "ok", "reason_code": reason,
                                "confidence": answer["confidence"], "answer_confidence": confidence,
                                "abstention": "abstained" if reason else
                                    "passed" if threshold is not None else "unevaluated"}
                if reason:
                    result["status"] = "abstained"
            result["answers"] = answers
            result["details"] = raw["answers"]
            if policy:
                value = answers["decision"]["value"]
                result["experimental"] = True
                if policy == "risk_check":
                    # Model output is advisory; uncertainty never authorizes a risky action.
                    result.update(risk=value or "unknown", requires_human=True)
                else:
                    result["decision"] = value or "defer_to_agent"
            self.last_error = None
        except Unavailable as exc:
            result.update(status="unavailable", reason_code=str(exc))
            self.last_error = str(exc)
        except Exception:
            result.update(status="unavailable", reason_code="inference_failed")
            self.last_error = "inference_failed"
        if result["status"] == "unavailable" and policy:
            if policy == "risk_check":
                result.update(risk="unknown", requires_human=True)
            else:
                result["decision"] = "defer_to_agent"
        return result

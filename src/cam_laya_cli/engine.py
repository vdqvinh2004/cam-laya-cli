"""Rules-only decisions: deterministic presets, no models, no inference."""

from .presets import OPTIONS, SAFE_COMMANDS, deterministic_choice, hard_risk


def validate(request):
    if not isinstance(request, dict):
        raise ValueError("request must be an object")
    if request.keys() - {"id", "state", "preset"}:
        raise ValueError("unknown request field")
    state = request.get("state")
    if not isinstance(state, dict):
        raise ValueError("state must be an object")
    if "id" in request and (type(request["id"]) not in (str, int) or len(str(request["id"])) > 128):
        raise ValueError("id must be a string or integer of at most 128 characters")
    if "preset" not in request or request["preset"] not in OPTIONS:
        raise ValueError("preset must name a supported policy")
    if "action" in state and not isinstance(state["action"], str):
        raise ValueError("action must be text")


def decide(request):
    validate(request)
    state = request["state"]
    policy = request["preset"]
    result = {"schema_version": 1, "status": "ok", "source": "rule", "preset": policy}
    if "id" in request:
        result["id"] = request["id"]
    if policy == "risk_check":
        reason = hard_risk(state.get("action", ""))
        if reason:
            risk = "destructive" if reason in {
                "destructive_command", "database_destruction", "infrastructure_change"} else "high"
            result.update(risk=risk, requires_human=True, confidence=1.0, reason_code=reason)
            return result
        if state.get("action", "") in SAFE_COMMANDS:
            result.update(risk="safe", requires_human=False, confidence=1.0,
                          reason_code="deterministic_safe")
            return result
        result.update(status="abstained", risk="unknown", requires_human=True,
                      reason_code="no_deterministic_rule")
        return result
    choice = deterministic_choice(policy, state)
    if choice is not None:
        result.update(decision=choice, confidence=1.0, reason_code="deterministic_rule")
        return result
    result.update(status="abstained", decision="defer_to_agent",
                  reason_code="no_deterministic_rule")
    return result

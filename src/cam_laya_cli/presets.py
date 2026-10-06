"""Rules adapted from cam-laya-mcp e73ff6e, Apache-2.0; see NOTICE."""

import re
import shlex

OPTIONS = {
    "route_task": ["coding", "debugging", "refactoring", "testing", "documentation", "research", "architecture", "dependency_management", "security", "devops", "configuration", "code_review"],
    "next_action": ["inspect", "search", "edit", "implement", "test", "debug", "review", "commit", "ask_user", "stop"],
    "test_decision": ["no_test_needed", "targeted_test", "unit_tests", "integration_tests", "e2e_tests", "full_suite", "debug_failure", "ask_user"],
    "review_decision": ["continue", "self_review", "run_tests", "request_human_review", "stop"],
    "risk_check": ["safe", "low", "medium", "high", "destructive"],
}

SAFE_COMMANDS = frozenset({"git status", "git diff", "git log", "npm test", "pytest", "cargo test"})

HARD_TEXT_RULES = (
    (r"\b(?:drop\s+(?:database|table)|truncate\s+table)\b", "database_destruction"),
    (r"(?:^|[/\s'\"])(?:\.env(?:\.(?!example|sample)[^/\s'\"]+)?|id_rsa|id_ed25519|credentials|secrets?\.json)(?:\s|$|[/\"'])", "secrets_access"),
    (r"\b(?:OPENAI_API_KEY|ANTHROPIC_API_KEY|AWS_SECRET_ACCESS_KEY|GITHUB_TOKEN)\b", "credential_manipulation"),
    (r"(?i)ignore previous instructions.{0,80}(?:credentials|secrets|tokens|passwords)", "prompt_injection"),
    (r"\b(?:deploy|release)\b[^\n]*\b(?:prod|production)\b", "production_change"),
)

def _command_risk(words: list[str]) -> str | None:
    if not words:
        return None
    while words and re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*=.*", words[0]):
        words = words[1:]
    if not words:
        return None
    name = words[0].rsplit("/", 1)[-1]
    args = words[1:]
    if name in {"sudo", "su"}:
        return "privileged_change"
    if name in {"env", "command", "nohup", "time"}:
        offset = 0
        while offset < len(args) and (args[offset].startswith("-") or re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*=.*", args[offset])):
            if name == "env" and args[offset] in {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"}:
                offset += 1
            offset += 1
        return _command_risk(args[offset:])
    if name == "rm":
        flags = []
        for arg in args:
            if arg == "--":
                break
            if arg.startswith("-"):
                flags.append(arg)
        short_flags = "".join(flag[1:] for flag in flags if not flag.startswith("--"))
        recursive = "--recursive" in flags or "r" in short_flags or "R" in short_flags
        force = "--force" in flags or "f" in short_flags
        if recursive and force:
            return "destructive_command"
    if name == "git":
        for operation in ("push", "clean", "reset", "restore", "checkout", "stash"):
            if operation in args:
                flags = args[args.index(operation) + 1:]
                if operation == "push" and any(flag in {"-f", "--force", "--force-with-lease"} or flag.startswith("--force=") or flag.startswith("--force-with-lease=") for flag in flags):
                    return "force_push"
                if operation == "clean" and any(flag == "--force" or flag.startswith("-") and not flag.startswith("--") and "f" in flag for flag in flags):
                    return "destructive_command"
                if operation == "reset" and "--hard" in flags:
                    return "destructive_command"
                if operation == "restore" and ("--staged" not in flags or "--worktree" in flags) and any(not flag.startswith("-") for flag in flags):
                    return "destructive_command"
                if operation == "checkout" and "--" in flags and flags.index("--") < len(flags) - 1:
                    return "destructive_command"
                if operation == "stash" and any(flag in {"drop", "clear"} for flag in flags):
                    return "destructive_command"
    if name == "find" and "-delete" in args:
        return "destructive_command"
    if name == "terraform" and ("destroy" in args or ("apply" in args and "-auto-approve" in args)):
        return "infrastructure_change"
    if (name == "kubectl" and "delete" in args) or (name == "helm" and "uninstall" in args):
        return "infrastructure_change"
    if name == "chmod" and "777" in args:
        return "privileged_change"
    return None

def hard_risk(action: str, _depth: int = 0) -> str | None:
    if _depth > 8:
        return "unparseable_command"
    for pattern, reason in HARD_TEXT_RULES:
        if re.search(pattern, action, re.IGNORECASE):
            return reason
    for substitution in re.findall(r"\$\(([^()]*)\)|`([^`]*)`", action):
        if reason := hard_risk(substitution[0] or substitution[1], _depth + 1):
            return reason
    # ponytail: static shell scan covers common syntax; use a shell parser if full grammar matters.
    try:
        lexer = shlex.shlex(action, posix=True, punctuation_chars="|;&()\n")
        lexer.whitespace_split = True
        lexer.whitespace = " \t\r"
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return "unparseable_command"
    commands: list[list[str]] = [[]]
    operators: list[str] = []
    separators = {"|", "||", "&", "&&", ";", "(", ")", "\n"}
    for token in tokens:
        if token in separators:
            operators.append(token)
            commands.append([])
        else:
            commands[-1].append(token)
    for index, words in enumerate(commands):
        reason = _command_risk(words)
        if reason:
            return reason
        if words and words[0].rsplit("/", 1)[-1] in {"sh", "bash", "zsh"}:
            flag = next((i for i, word in enumerate(words[1:], 1) if word in {"-c", "-lc", "-ec"}), None)
            if flag is not None and flag + 1 < len(words):
                if reason := hard_risk(words[flag + 1], _depth + 1):
                    return reason
        if index and operators[index - 1] == "|" and commands[index - 1] and words and words[0].rsplit("/", 1)[-1] in {"sh", "bash", "zsh"}:
            return "remote_script_execution" if commands[index - 1][0].rsplit("/", 1)[-1] in {"curl", "wget"} else "shell_pipe_execution"
    return None

def deterministic_choice(policy: str, state: dict) -> str | None:
    if not isinstance(state, dict):
        return None
    changed = state.get("changed_files")
    changed = changed if type(changed) is int and changed >= 0 else None
    test_result = state.get("last_test_result")
    if policy == "test_decision":
        if test_result == "failed":
            return "debug_failure"
        if state.get("task_type") == "documentation":
            return "no_test_needed"
        if state.get("tests_available") is False:
            return "ask_user"
        if state.get("tests_available") is True and changed is not None:
            return "full_suite" if changed > 10 else "targeted_test"
    elif policy == "review_decision":
        if state.get("risk") == "high":
            return "request_human_review"
        if test_result == "not_run":
            return "run_tests"
        if test_result == "passed" and changed is not None:
            return "continue" if changed == 0 else "self_review"
    elif policy == "next_action":
        if test_result == "failed":
            return "debug"
        if state.get("last_action") == "edit":
            return "test"
        if test_result == "passed":
            return "review"
        if state.get("current_phase"):
            return "inspect"
    return None

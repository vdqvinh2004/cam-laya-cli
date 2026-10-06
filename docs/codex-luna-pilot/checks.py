"""Independent pilot acceptance checks; run outside the agent workspace."""
import contextlib
import io
import json
import math
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def check(task):
    from cam_laya_cli import cli, config, engine, integrations, worker

    if task == "warm_timeout":
        for timeout in (0.25, 12, 300):
            with patch.object(sys, "argv", ["cam-laya-cli", "warm", "--timeout", str(timeout)]), \
                    patch.object(cli, "request", return_value={"status": "ok"}) as call, \
                    contextlib.redirect_stdout(io.StringIO()):
                with contextlib.suppress(SystemExit):
                    cli.main()
                assert call.call_args.kwargs["timeout"] == timeout
        for timeout in ("0", "-1", "301", "nan", "inf"):
            output = io.StringIO()
            with patch.object(sys, "argv", ["cam-laya-cli", "warm", "--timeout", timeout]), \
                    patch.object(cli, "request") as call, contextlib.redirect_stdout(output):
                try:
                    cli.main()
                except SystemExit as exc:
                    assert exc.code == 2
                else:
                    raise AssertionError("invalid timeout accepted")
                assert not call.called
                assert json.loads(output.getvalue())["reason_code"] == "invalid_timeout"
    elif task == "client_timeout":
        for value in (0, -1, 301, math.nan, math.inf, True, False, "2", None):
            try:
                worker.Client(timeout=value)
            except ValueError:
                pass
            else:
                raise AssertionError(f"invalid Client timeout accepted: {value!r}")
        for value in (0.01, 1, 300):
            assert worker.Client(timeout=value).timeout == value
    elif task == "choice_descriptions":
        for text in ("", " ", "\t\n"):
            request = {"state": "a", "questions": {"q": {"type": "choice",
                       "instructions": "Choose", "criteria": {"a": text, "b": "Other"}}}}
            try:
                engine.validate(request)
            except ValueError:
                pass
            else:
                raise AssertionError("empty choice description accepted")
        for criteria in ({"a": "Alpha", "b": "Beta"}, ["a", "b"]):
            engine.validate({"state": "a", "questions": {"q": {"type": "choice",
                            "instructions": "Choose", "criteria": criteria}}})
    elif task == "integration_modified":
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "skill.md").write_text("original")
            record = {"client": "codex", "root": str(root),
                      "assets": {"skill.md": integrations.digest("original")}}
            with patch.object(integrations, "manifest", return_value={"test": record}):
                assert integrations.integration_status()[0]["state"] == "configured_unverified"
                (root / "skill.md").write_text("changed")
                assert integrations.integration_status()[0]["state"] == "modified"
                (root / "skill.md").unlink()
                assert integrations.integration_status()[0]["state"] == "incomplete"
                (root / "skill.md").mkdir()
                assert integrations.integration_status()[0]["state"] == "incomplete"
    elif task == "strict_saved_json":
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "saved.json"
            assert config.read_json(path, {}) == {}
            for text in ('{"a":1,"a":2}', '{"n":{"a":1,"a":2}}',
                         '{"x":NaN}', '{"x":Infinity}', '{"x":1e400}'):
                path.write_text(text)
                try:
                    config.read_json(path)
                except ValueError:
                    pass
                else:
                    raise AssertionError(f"invalid saved JSON accepted: {text}")
            path.write_text('{"nested":{"x":1},"items":[true,null]}')
            assert config.read_json(path) == {"nested": {"x": 1}, "items": [True, None]}
    elif task == "batch_error_ids":
        records = [{"id": "alpha", "state": "x", "questions": {}},
                   {"id": 0, "state": "x", "questions": {}},
                   {"id": True, "state": "x", "questions": {}},
                   {"id": "x" * 129, "state": "x", "questions": {}}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.jsonl"
            path.write_text("\n".join(map(json.dumps, records)) + "\n{broken\n")
            output = io.StringIO()
            args = SimpleNamespace(input=str(path), model=None, min_confidence=None,
                                   details=False, timeout=2, command="batch")
            with contextlib.redirect_stdout(output), patch.object(cli, "Client") as client:
                assert cli.batch(args) == 2
                assert not client.called
            values = [json.loads(line) for line in output.getvalue().splitlines()]
            assert values[0]["id"] == "alpha" and values[1]["id"] == 0
            assert all("id" not in item for item in values[2:])
            assert [item["record"] for item in values] == [1, 2, 3, 4, 5]
            valid = {"id": "transport", "preset": "test_decision",
                     "state": {"last_test_result": "failed"}}
            path.write_text(json.dumps(valid) + "\n")
            output = io.StringIO()
            with contextlib.redirect_stdout(output), \
                    patch.object(cli, "Client", side_effect=config.Unavailable("worker_timeout")):
                assert cli.batch(args) == 3
            assert json.loads(output.getvalue())["id"] == "transport"
    else:
        raise ValueError(task)


if __name__ == "__main__":
    check(sys.argv[1])
    print("acceptance passed")

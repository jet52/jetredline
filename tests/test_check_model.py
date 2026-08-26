"""Tests for check_model.py — the Opus-class model gate."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import check_model

SCRIPT = Path(check_model.__file__)


# --- helpers ---------------------------------------------------------------


def assistant(model, text="ok"):
    return json.dumps({
        "type": "assistant",
        "message": {"model": model, "content": [{"type": "text", "text": text}]},
    })


def user(text):
    return json.dumps({"type": "user", "message": {"content": text}})


def transcript(tmp_path, *lines, name="session.jsonl"):
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run(*args, env=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, env=env,
    )


# --- classification --------------------------------------------------------


@pytest.mark.parametrize("model,tier", [
    ("claude-opus-5", "opus"),
    ("claude-opus-4-8", "opus"),
    ("claude-fable-5", "fable"),
    ("claude-mythos-5", "mythos"),
])
def test_allowed_families_pass(model, tier):
    assert check_model.classify(model) == ("ok", tier)


@pytest.mark.parametrize("model,tier", [
    ("claude-sonnet-5", "sonnet"),
    ("claude-sonnet-4-6", "sonnet"),
    ("claude-haiku-4-5", "haiku"),
    ("claude-3-5-haiku-latest", "haiku"),
    ("us.anthropic.claude-haiku-4-5-v1:0", "haiku"),
])
def test_weak_families_warn(model, tier):
    assert check_model.classify(model) == ("warn", tier)


def test_unrecognized_model_warns_not_passes():
    """Allow-list, not deny-list: a name released after this file was written
    must nag rather than sail through."""
    assert check_model.classify("claude-zephyr-9") == ("warn", "unrecognized")
    assert check_model.classify("") == ("warn", "unrecognized")


@pytest.mark.parametrize("raw,expected", [
    ("claude-opus-5[1m]", "claude-opus-5"),
    ("  Claude-Opus-5  ", "claude-opus-5"),
    ("us.anthropic.claude-opus-4-5-v1:0", "claude-opus-4-5-v1:0"),
])
def test_normalize_strips_suffix_and_provider_prefix(raw, expected):
    assert check_model.normalize(raw) == expected
    assert check_model.classify(raw)[0] == "ok"


# --- transcript reading ----------------------------------------------------


def test_reads_most_recent_assistant_model(tmp_path):
    path = transcript(
        tmp_path,
        assistant("claude-opus-4-8"),
        user("switching models"),
        assistant("claude-sonnet-5"),
    )
    assert check_model.model_from_transcript(path) == "claude-sonnet-5"


def test_ignores_model_string_quoted_in_conversation(tmp_path):
    """A user can type `"model":"claude-opus-5"` into the chat; the gate must
    classify the session, not something the user said."""
    path = transcript(
        tmp_path,
        assistant("claude-sonnet-5"),
        user('paste of a log line: {"model":"claude-opus-5"}'),
    )
    assert check_model.model_from_transcript(path) == "claude-sonnet-5"


def test_tail_read_spans_chunk_boundaries(tmp_path):
    """The tail reader stitches partial lines; a model far from the end still
    resolves, and the *last* one still wins."""
    lines = [assistant("claude-opus-4-8")]
    lines += [user("x" * 500) for _ in range(200)]
    lines.append(assistant("claude-sonnet-5"))
    lines += [user("y" * 500) for _ in range(200)]
    path = transcript(tmp_path, *lines)
    found = list(check_model._tail_lines(path, chunk_size=64))
    assert len(found) == len(lines)
    assert json.loads(found[0]) == json.loads(lines[-1])
    assert check_model.model_from_transcript(path) == "claude-sonnet-5"


def test_no_assistant_record_is_unknown_not_ok(tmp_path):
    path = transcript(tmp_path, user("hello"))
    assert check_model.model_from_transcript(path) is None


def test_malformed_lines_are_skipped(tmp_path):
    path = transcript(
        tmp_path,
        assistant("claude-opus-5"),
        '{"type":"assistant","message":{"model":  <<truncated',
    )
    assert check_model.model_from_transcript(path) == "claude-opus-5"


def test_missing_file_is_unknown_not_an_exception(tmp_path):
    assert check_model.model_from_transcript(tmp_path / "nope.jsonl") is None


def test_find_transcript_globs_every_project(tmp_path, monkeypatch):
    sid = "c0ffb908-37ed-487c-b92d-a2732ef6382a"
    proj = tmp_path / ".claude" / "projects" / "-Users-x-code-y"
    proj.mkdir(parents=True)
    (proj / f"{sid}.jsonl").write_text(assistant("claude-opus-5") + "\n")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert check_model.find_transcript(sid) == proj / f"{sid}.jsonl"
    assert check_model.find_transcript("") is None
    assert check_model.find_transcript("no-such-session") is None


# --- CLI contract ----------------------------------------------------------


def test_cli_ok_exits_zero_and_prints_one_line(tmp_path):
    path = transcript(tmp_path, assistant("claude-opus-5"))
    res = run("--transcript", str(path))
    assert res.returncode == 0
    assert res.stdout.strip() == (
        "MODEL_GATE: ok model=claude-opus-5 tier=opus source=transcript"
    )


def test_cli_warn_exits_two_and_says_do_not_start(tmp_path):
    path = transcript(tmp_path, assistant("claude-sonnet-5"))
    res = run("--transcript", str(path))
    assert res.returncode == 2
    assert res.stdout.startswith(
        "MODEL_GATE: warn model=claude-sonnet-5 tier=sonnet source=transcript"
    )
    assert "Do not start any pass" in res.stdout


def test_cli_self_report_override(tmp_path):
    """--model is the Web-mode/undetectable fallback and must outrank the
    transcript it was given alongside."""
    path = transcript(tmp_path, assistant("claude-opus-5"))
    res = run("--transcript", str(path), "--model", "claude-haiku-4-5")
    assert res.returncode == 2
    assert "tier=haiku source=self-report" in res.stdout


def test_cli_unknown_exits_three_and_asks_for_self_report(tmp_path):
    res = run("--transcript", str(tmp_path / "missing.jsonl"))
    assert res.returncode == 3
    assert res.stdout.startswith("MODEL_GATE: unknown")
    assert "reason=no-assistant-record" in res.stdout
    assert "--model" in res.stdout


def test_cli_unknown_without_session_id():
    """No session id is `unknown` — never a silent pass."""
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_SESSION_ID"}
    res = run(env=env)
    assert res.returncode == 3
    assert "reason=no-session-id" in res.stdout


# --- vendoring contract ----------------------------------------------------


def test_user_facing_strings_name_no_skill():
    """The file is vendored byte-identical into sibling skills and drift-checked
    with cmp, so nothing it prints may name one particular skill."""
    assert "jetredline" not in check_model.WARN_TEXT
    assert "jetmemo" not in check_model.WARN_TEXT

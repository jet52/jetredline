#!/usr/bin/env python3
"""Report which Claude model this session is running on, and gate on it.

Shared across jet52 projects: jetredline (canonical), jetmemo. Vendored
copies must stay byte-identical — each consumer's `make drift-check` cmp's this
file, which is what lets jetredline's test suite cover every copy. Keep every
string in here skill-agnostic.

Why: these skills' reliability was measured on Opus-class models. Sonnet- and
Haiku-class models miss citation, quotation, and record-fact errors on this
workload at a materially higher rate, and the failure is silent — the report
still looks complete. The calling skill therefore requires an explicit human
decision before running on a model outside the allow-list.

Detection is deterministic where it can be: the runtime model is read from the
live session transcript (the `model` field of the most recent assistant
record), not from the model's own self-report, because a model naming its own
release is exactly the unreliable channel a gate must not depend on. Where the
transcript is unavailable (Web mode, a sandbox without ~/.claude, a session
whose first assistant record has not been flushed yet), the script reports
`unknown` and the caller falls back to self-report via --model.

Policy is an ALLOW-list, not a deny-list: only opus / fable / mythos proceed
silently. Any other family — including a model released after this file was
written — warns. That nags on a new top-tier release; the alternative silently
admits a future budget tier, which is the more expensive mistake here.

Output is one line on stdout:

    MODEL_GATE: ok      model=claude-opus-5   tier=opus         source=transcript
    MODEL_GATE: warn    model=claude-sonnet-5 tier=sonnet       source=transcript
    MODEL_GATE: warn    model=claude-x-9      tier=unrecognized source=self-report
    MODEL_GATE: unknown model=? tier=? source=none reason=no-transcript

Exit status: 0 = ok, 2 = warn, 3 = unknown. A nonzero exit is the gate firing,
not a broken script.

Usage:
    python3 check_model.py
    python3 check_model.py --model claude-opus-5      # self-report fallback
    python3 check_model.py --transcript /path/to.jsonl
"""

import argparse
import json
import os
import re
import sys
from glob import glob
from pathlib import Path

# Families these skills are validated on. Add a new top-tier family here when
# one ships; everything absent from this tuple warns.
ALLOWED_FAMILIES = ("opus", "fable", "mythos")

# Known lower-capability families, named only so the warning can say which one.
# Their absence from ALLOWED_FAMILIES is what actually triggers the gate.
WEAK_FAMILIES = ("sonnet", "haiku")

WARN_TEXT = (
    "This skill strongly recommends an Opus-class model — its reliability "
    "testing is based on one. Do not start any pass until the user has "
    "chosen whether to continue on this model; running here is supported, "
    "just less reliable. See Step 0.0 in the skill's SKILL.md."
)

# Strips a context-window suffix (claude-opus-5[1m]) and a provider prefix
# (us.anthropic.claude-opus-4-5-v1:0) before family matching.
_SUFFIX_RE = re.compile(r"\[[^\]]*\]\s*$")


def find_transcript(session_id: str):
    """Path to the session transcript, or None.

    Session IDs are UUIDs and unique across projects, so globbing every project
    directory beats reconstructing Claude Code's cwd-to-slug encoding. (Same
    mechanism as provenance.py; duplicated rather than imported so this script
    stands alone.)
    """
    if not session_id:
        return None
    matches = glob(
        os.path.expanduser(f"~/.claude/projects/*/{session_id}.jsonl")
    )
    return Path(matches[0]) if matches else None


def _tail_lines(path, chunk_size=131072, max_bytes=8 * 1024 * 1024):
    """Yield the file's lines from last to first, reading only what's needed.

    Transcripts run to hundreds of thousands of lines and the answer is almost
    always in the final few, so a forward scan would read megabytes to reach a
    field that sits at the end. Reads stop at max_bytes.
    """
    with open(path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        pos = fh.tell()
        read = 0
        tail = b""
        while pos > 0 and read < max_bytes:
            step = min(chunk_size, pos)
            pos -= step
            fh.seek(pos)
            buf = fh.read(step) + tail
            read += step
            parts = buf.split(b"\n")
            # The first element may be a partial line unless we reached the
            # start of the file; hold it back to be completed by the next read.
            tail = b"" if pos == 0 else parts.pop(0)
            for line in reversed(parts):
                if line.strip():
                    yield line.decode("utf-8", "replace")
        if tail.strip():
            yield tail.decode("utf-8", "replace")


def model_from_transcript(path):
    """The most recent assistant record's model id, or None.

    Records are parsed as JSON rather than regex-scanned: a transcript can
    quote the string `"model":"..."` inside ordinary conversation text, and a
    gate must not classify the session from something the user typed.
    """
    try:
        for line in _tail_lines(path):
            if '"model"' not in line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get("type") != "assistant":
                continue
            model = (record.get("message") or {}).get("model")
            if isinstance(model, str) and model.strip():
                return model.strip()
    except OSError:
        return None
    return None


def normalize(model_id: str) -> str:
    """Lowercase the id and strip context-window suffix and provider prefix."""
    ident = _SUFFIX_RE.sub("", (model_id or "").strip()).lower()
    # us.anthropic.claude-opus-4-5-v1:0 -> claude-opus-4-5-v1:0
    if "claude" in ident:
        ident = ident[ident.index("claude"):]
    return ident


def classify(model_id: str):
    """Return (status, tier) for a model id. Status is 'ok' or 'warn'."""
    ident = normalize(model_id)
    for family in ALLOWED_FAMILIES:
        if family in ident:
            return "ok", family
    for family in WEAK_FAMILIES:
        if family in ident:
            return "warn", family
    return "warn", "unrecognized"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default=None,
                    help="Model id to classify instead of reading the "
                         "transcript (the self-report fallback).")
    ap.add_argument("--transcript", default=None,
                    help="Transcript to read (defaults to this session's).")
    ap.add_argument("--session-id", default=os.environ.get("CLAUDE_CODE_SESSION_ID"),
                    help="Session whose transcript to read (defaults to "
                         "$CLAUDE_CODE_SESSION_ID).")
    args = ap.parse_args()

    if args.model:
        model, source, reason = args.model.strip(), "self-report", None
    else:
        path = Path(args.transcript) if args.transcript else find_transcript(args.session_id)
        if path is None:
            model, source = None, "none"
            reason = "no-session-id" if not args.session_id else "no-transcript"
        else:
            model = model_from_transcript(path)
            source = "transcript" if model else "none"
            reason = None if model else "no-assistant-record"

    if not model:
        print(f"MODEL_GATE: unknown model=? tier=? source=none reason={reason}")
        print("Model could not be detected. State which model you are from "
              "your own system prompt and re-run with --model <id>; if that "
              "still does not resolve, treat this as a warn.")
        return 3

    status, tier = classify(model)
    print(f"MODEL_GATE: {status} model={model} tier={tier} source={source}")
    if status == "warn":
        print(WARN_TEXT)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

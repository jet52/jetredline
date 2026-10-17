#!/usr/bin/env python3
"""Run the `Search:` patterns in an author's voice file against a draft.

A voice file (`my-writing-voice.md`) may attach a regex to a rule with a
line of the form

    Search: `PATTERN`

under that rule's bullet. This script collects every such pattern, runs it
over the draft text, and reports each match with the nearest preceding `¶`
marker. Pass 2 treats each hit as a candidate to judge, not a verdict, so a
rule's flag does not depend on a reader noticing the phrase.

Patterns are matched case-insensitively with `.` spanning newlines. The rule
label is the bold text (`**...**`) of the bullet the pattern belongs to, or
the bullet's first words when there is none.

Usage:
    voice_search.py VOICE_FILE DRAFT              # one line per hit
    voice_search.py --json VOICE_FILE DRAFT       # machine-readable

Exit status: 0 if at least one hit, 1 if none (including a voice file with no
patterns), 2 on a read error or an invalid pattern.
"""

import argparse
import json
import re
import sys
from pathlib import Path

SEARCH_RE = re.compile(r"^\s*Search:\s*`(?P<pat>[^`]+)`\s*$")
BULLET_RE = re.compile(r"^- (?P<text>.*)")
BOLD_RE = re.compile(r"\*\*(?P<label>.+?)\*\*")
# A paragraph marker opens a line ("[¶12]" or "¶12"); a "¶ 4" pincite inside
# a citation must not count.
PARA_RE = re.compile(r"^[ \t>*]*\[?¶\s*(\d+)\]?", re.M)


def load_patterns(voice_text: str):
    """Return [(label, compiled_regex)] for each Search: line."""
    patterns = []
    label = None
    for line in voice_text.splitlines():
        b = BULLET_RE.match(line)
        if b:
            m = BOLD_RE.search(b["text"])
            label = (m["label"] if m else " ".join(b["text"].split()[:6])).strip()
            continue
        s = SEARCH_RE.match(line)
        if s:
            patterns.append((label or "voice rule", re.compile(s["pat"], re.I | re.S)))
    return patterns


def para_at(text: str, pos: int):
    """The last ¶ marker at or before pos, as a string, or None."""
    last = None
    for m in PARA_RE.finditer(text, 0, pos + 1):
        last = m.group(1)
    return last


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("voice_file")
    ap.add_argument("draft")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--context", type=int, default=80,
                    help="characters of context on each side (default 80)")
    args = ap.parse_args(argv)

    try:
        voice = Path(args.voice_file).read_text(encoding="utf-8")
        draft = Path(args.draft).read_text(encoding="utf-8")
    except OSError as e:
        print(f"voice_search: {e}", file=sys.stderr)
        return 2
    try:
        patterns = load_patterns(voice)
    except re.error as e:
        print(f"voice_search: invalid Search pattern: {e}", file=sys.stderr)
        return 2

    hits = []
    for label, rx in patterns:
        for m in rx.finditer(draft):
            a = max(0, m.start() - args.context)
            z = min(len(draft), m.end() + args.context)
            hits.append({
                "rule": label,
                "para": para_at(draft, m.start()),
                "match": " ".join(m.group(0).split()),
                "context": " ".join(draft[a:z].split()),
            })

    if args.json:
        json.dump(hits, sys.stdout, indent=1, ensure_ascii=False)
        print()
    else:
        for h in hits:
            where = f"¶{h['para']}" if h["para"] else "¶?"
            print(f"{where}: [{h['rule']}] {h['match']}")
    return 0 if hits else 1


if __name__ == "__main__":
    sys.exit(main())

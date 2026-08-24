#!/usr/bin/env python3
"""Round-trip for cite-review marks: browser -> case folder -> next run.

The review page cannot write to disk.  The File System Access API needs a
secure context and ``file://`` is not one, so a page opened from a folder can
save only through the browser's own download path — in any browser, with or
without admin rights.  The round trip therefore runs through the *case
folder*, which the reviewer and the skill can both see:

    1. the page exports  cite-review-state__<case-id>__<stamp>.json
    2. the reviewer saves it into the case folder (Chrome and Edge's
       "Ask where to save each file" makes that one click)
    3. the next run finds the newest matching file and restores the marks

Restoring is the part that has to be careful.  Marks are keyed by character
offset, which is stable only while the draft is.  jetredline exists to edit
drafts, so offsets move — and a mark restored to the wrong offset would show a
citation as verified that nobody verified.  So nothing is restored by offset.
Each exported entry carries what identifies it to a *reader* — kind, citation
text, paragraph, and which occurrence within that paragraph — and restoring
re-derives the offset from those.  Matching runs in two tiers:

    1. same paragraph and occurrence: an exact identity match;
    2. the paragraph moved, but the citation is unique on *both* sides, so
       exactly one entry can be meant.  This recovers a draft whose
       paragraphs were renumbered, which would otherwise drop every mark.

Anything still unmatched is reported as dropped.  Tier 2 never chooses
between candidates — where a citation appears more than once on either side
the mark is dropped instead, because a mark restored onto the wrong citation
would show a cite as verified that nobody verified.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA = "jetredline/cite-review-state"
SCHEMA_VERSION = 1

#: Exported files are named so the next run can find them without being told.
FILENAME_GLOB = "cite-review-state__*.json"
_FILENAME_RE = re.compile(
    r"^cite-review-state__(?P<case>.+?)__(?P<stamp>\d{8}-\d{6})\.json$")

_STATUSES = frozenset({"verified", "flagged", "skipped"})


def safe_case_id(case_id: str) -> str:
    """Filename-safe form of a case id. Mirrors the page's own sanitizer."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", (case_id or "review")).strip("-") or "review"


def content_key(kind: str, label: str, para_num, occurrence) -> str:
    """Identity of a review entry, as a reader would recognize it.

    Deliberately *not* the character offset: offsets move when the draft is
    edited, and a mark restored onto the wrong citation is worse than a mark
    lost.  Paragraph plus occurrence-within-paragraph survives edits elsewhere
    in the document and fails loudly when the citation itself moves.
    """
    norm = " ".join((label or "").split())
    return "\x1f".join([
        "fact" if kind == "fact" else "cite",
        norm,
        "" if para_num is None else str(para_num),
        str(occurrence or 0),
    ])


def _label_key(kind: str, label: str | None) -> str:
    """Label-only identity, for the unique-on-both-sides fallback."""
    return ("fact" if kind == "fact" else "cite") + "\x1f" + \
        " ".join((label or "").split())


def state_key(kind: str, position, index: int) -> str:
    """The page's localStorage key for an entry.

    Must match ``stateKey()`` in the page JS exactly, or a restored mark
    lands nowhere.
    """
    pre = "f" if kind == "fact" else ""
    return f"{pre}p{position}" if position is not None else f"{pre}i{index}"


# ---------------------------------------------------------------------------
# Reading an exported file
# ---------------------------------------------------------------------------

class StateFileError(ValueError):
    """An export file that cannot be trusted to describe this review."""


def load(path: Path) -> dict:
    """Read and validate an exported state file."""
    try:
        payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    except OSError as e:
        raise StateFileError(f"cannot read {path}: {e}") from e
    except json.JSONDecodeError as e:
        raise StateFileError(f"{path} is not valid JSON: {e}") from e

    if not isinstance(payload, dict):
        raise StateFileError(f"{path}: expected an object at the top level")
    if payload.get("schema") != SCHEMA:
        raise StateFileError(
            f"{path}: not a cite-review state file "
            f"(schema={payload.get('schema')!r})")
    version = payload.get("schema_version")
    if version != SCHEMA_VERSION:
        raise StateFileError(
            f"{path}: schema version {version!r}, expected {SCHEMA_VERSION}")
    if not isinstance(payload.get("entries"), list):
        raise StateFileError(f"{path}: 'entries' missing or not a list")
    return payload


def find_latest(directory: Path, case_id: str | None = None) -> Path | None:
    """Newest export in ``directory``, optionally restricted to one case.

    Matching is on the case id embedded in the filename, so one shared folder
    can hold reviews for several matters without them resuming into each
    other.
    """
    directory = Path(directory).expanduser()
    if not directory.is_dir():
        return None
    wanted = safe_case_id(case_id) if case_id else None
    hits = []
    for p in directory.glob(FILENAME_GLOB):
        m = _FILENAME_RE.match(p.name)
        if not m:
            continue
        if wanted and m.group("case") != wanted:
            continue
        hits.append((m.group("stamp"), p))
    if not hits:
        return None
    # Sort on the embedded stamp, not mtime: copying a file into a shared
    # folder rewrites mtime and would make an older review look newer.
    hits.sort(key=lambda t: t[0])
    return hits[-1][1]


# ---------------------------------------------------------------------------
# Restoring onto a freshly built page
# ---------------------------------------------------------------------------

@dataclass
class Restore:
    """Result of mapping an exported review onto the current draft."""
    state: dict = field(default_factory=dict)
    restored: int = 0
    dropped: list[str] = field(default_factory=list)
    rematched: list[str] = field(default_factory=list)
    draft_changed: bool = False
    source: Path | None = None
    marks_in_file: int = 0

    def summary(self) -> str:
        bits = [f"restored {self.restored} of {self.marks_in_file} mark(s)"]
        if self.rematched:
            bits.append(f"{len(self.rematched)} re-matched after renumbering")
        if self.dropped:
            bits.append(f"{len(self.dropped)} no longer in the draft")
        if self.draft_changed:
            bits.append("draft has changed since the review")
        return "; ".join(bits)


def build_restore(payload: dict, data: list[dict],
                  draft_sha: str | None = None,
                  source: Path | None = None) -> Restore:
    """Map an exported review onto ``data`` (the page's DATA entries).

    ``data`` entries must carry kind, the display label, para_num, occurrence
    and position — i.e. the page's own records, so the derived keys match what
    the JS will look up.
    """
    result = Restore(source=source)
    result.draft_changed = bool(
        draft_sha and payload.get("draft_sha256")
        and payload["draft_sha256"] != draft_sha)

    # Where each content key now lives in the rebuilt page.
    index: dict[str, tuple[str, int]] = {}
    # Fallback index by label alone, used only where the label is unique on
    # both sides — see the two-tier match below.
    by_label: dict[str, list[tuple[str, int]]] = {}
    for i, d in enumerate(data):
        kind = d.get("kind") or "cite"
        label = d.get("claim") if kind == "fact" else d.get("cite_text")
        key = content_key(kind, label, d.get("para_num"), d.get("occurrence"))
        skey = state_key(kind, d.get("position"), i)
        # First occurrence wins: duplicates would be ambiguous, and guessing
        # between them is exactly what this design refuses to do.
        index.setdefault(key, (skey, i))
        by_label.setdefault(_label_key(kind, label), []).append((skey, i))

    # How often each label appears in the exported review, so tier 2 can
    # require uniqueness on both sides.
    export_label_counts: dict[str, int] = {}
    for entry in payload.get("entries", []):
        kind = entry.get("kind") or "cite"
        label = entry.get("claim") if kind == "fact" else entry.get("cite_text")
        k = _label_key(kind, label)
        export_label_counts[k] = export_label_counts.get(k, 0) + 1

    for entry in payload.get("entries", []):
        status = entry.get("status")
        notes = entry.get("notes") or ""
        if status not in _STATUSES and not notes:
            continue  # nothing to carry over
        result.marks_in_file += 1
        kind = entry.get("kind") or "cite"
        label = entry.get("claim") if kind == "fact" else entry.get("cite_text")
        key = content_key(kind, label, entry.get("para_num"),
                          entry.get("occurrence"))
        # Tier 1: same paragraph, same occurrence — an exact identity match.
        hit = index.get(key)
        if hit is None:
            # Tier 2: the paragraph moved (an edit renumbered the draft), but
            # the citation itself is unique on BOTH sides, so there is exactly
            # one entry it can be. No guessing is involved, which is why this
            # is allowed where a nearest-match would not be.
            lk = _label_key(kind, label)
            cands = by_label.get(lk, [])
            if len(cands) == 1 and export_label_counts.get(lk) == 1:
                hit = cands[0]
                result.rematched.append(
                    f"{' '.join((label or '').split())[:60]}")
        if hit is None:
            result.dropped.append(
                f"{'fact' if kind == 'fact' else 'cite'}: "
                f"{' '.join((label or '').split())[:60]}"
                + (f" (¶ {entry['para_num']})" if entry.get("para_num") else ""))
            continue
        result.state[hit[0]] = {"status": status if status in _STATUSES else None,
                                "notes": notes}
        result.restored += 1
    return result


def counts(payload: dict) -> dict:
    """Status tally over a payload's entries."""
    out = {"total": 0, "verified": 0, "flagged": 0, "skipped": 0, "unreviewed": 0}
    for e in payload.get("entries", []):
        out["total"] += 1
        st = e.get("status")
        out[st if st in _STATUSES else "unreviewed"] += 1
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Inspect exported cite-review state files.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", help="Case folder to search for the newest export")
    ap.add_argument("--file", help="A specific export file to inspect")
    ap.add_argument("--case-id", help="Restrict --dir search to one case id")
    args = ap.parse_args()

    if not args.dir and not args.file:
        ap.error("one of --dir or --file is required")

    path = Path(args.file).expanduser() if args.file else find_latest(
        Path(args.dir), args.case_id)
    if path is None:
        print(f"No {FILENAME_GLOB} found in {args.dir}", file=sys.stderr)
        sys.exit(2)

    try:
        payload = load(path)
    except StateFileError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)

    c = counts(payload)
    print(f"{path}")
    print(f"  case:     {payload.get('case_id')}")
    print(f"  title:    {payload.get('title')}")
    print(f"  exported: {payload.get('exported')}")
    print(f"  entries:  {c['total']}")
    print(f"    verified   {c['verified']}")
    print(f"    flagged    {c['flagged']}")
    print(f"    skipped    {c['skipped']}")
    print(f"    unreviewed {c['unreviewed']}")
    flagged = [e for e in payload["entries"] if e.get("status") == "flagged"]
    if flagged:
        print("  flagged:")
        for e in flagged:
            label = e.get("claim") if e.get("kind") == "fact" else e.get("cite_text")
            note = f" — {e['notes']}" if e.get("notes") else ""
            print(f"    ¶ {e.get('para_num')}  {label}{note}")


if __name__ == "__main__":
    main()

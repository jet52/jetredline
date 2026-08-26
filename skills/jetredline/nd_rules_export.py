#!/usr/bin/env python3
"""Regenerate the appellate-rules reference from the ndlaw corpus.

`references/nd-appellate-rules.md` is what the Pass 1 subagent reads to
analyze jurisdiction and timeliness. Hand-maintained, it drifted: by
August 2026 it labeled criminal post-judgment tolling "Rule 4(d)" (that is
post-conviction relief; criminal tolling is Rule 4(b)(3)), carried two
sections both headed "(d)", put cross-appeals at 4(b) (they are 4(a)(2)) and
premature notice at 4(c) (4(b)(2)), omitted subdivisions (c), (d), and (f)
entirely, and stated Rule 4(a) without its 60-day period. A jurisdictional
analysis citing the wrong subdivision is the kind of error that reaches a
published opinion, so the rule text is now generated rather than written.

The generated block is verbatim corpus text, delimited by HTML comment
markers. Anything outside those markers -- the preamble and the derived
quick-reference notes -- is preserved across regeneration, so human
commentary survives but can never be the source of a rule's words.

Two backends, same selection order as ndlaw_export.py:

  sqlite  -- a local ndlaw rules.db (--db, NDLAW_RULES_DB env, or the
             default development path), read-only.
  mcp     -- a deployed ndlaw instance over Streamable HTTP with Basic
             Auth (--url/NDLAW_URL, --auth/NDLAW_AUTH), via
             lookup_authority. Reuses ndlaw_export's JSON-RPC client.

Usage:
    nd_rules_export.py                  # rewrite the reference in place
    nd_rules_export.py --check          # fail if it has drifted
    nd_rules_export.py --out -          # print the block to stdout

Exit codes: 0 = written, unchanged, or no backend reachable (a machine
without the corpus is not a failure); 1 = --check found drift.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

DEFAULT_DB = "~/code/ndlaw-mcp/rules.db"
DEFAULT_OUT = Path(__file__).resolve().parent / "references" / "nd-appellate-rules.md"

BEGIN = "<!-- BEGIN GENERATED: ndlaw rules export — do not hand-edit below this line -->"
END = "<!-- END GENERATED -->"

# The rules this reference covers, in reading order. Timing of appeal is the
# subject; adding a rule here is all it takes to include it.
RULES = [
    ("ndrappp 2", "N.D.R.App.P. 2"),
    ("ndrappp 2.1", "N.D.R.App.P. 2.1"),
    ("ndrappp 2.2", "N.D.R.App.P. 2.2"),
    ("ndrappp 3", "N.D.R.App.P. 3"),
    ("ndrappp 4", "N.D.R.App.P. 4"),
    ("ndrappp 26", "N.D.R.App.P. 26"),
]


class SqliteRulesBackend:
    """Read-only view of the ndlaw rules corpus.

    `current_version_id` is the version in force; a rule with no current
    version (repealed, or mid-pipeline) simply yields None rather than an
    older text that would silently misstate the law.
    """

    def __init__(self, db_path: str):
        import sqlite3
        self.conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        self.conn.row_factory = sqlite3.Row

    def lookup(self, cite_key: str) -> dict | None:
        row = self.conn.execute(
            """SELECT p.citation, p.heading, p.status, v.effective_start,
                      v.source_url, v.text_content
               FROM provisions p
               JOIN provision_versions v ON v.id = p.current_version_id
               WHERE p.corpus = 'rule' AND p.cite_key = ?""",
            (cite_key,),
        ).fetchone()
        if row is None:
            return None
        return {
            "citation": row["citation"],
            "heading": row["heading"],
            "status": row["status"],
            "effective_start": row["effective_start"],
            "source_url": row["source_url"],
            "text": row["text_content"],
        }

    def close(self):
        self.conn.close()


class McpRulesBackend:
    """lookup_authority over the same Streamable HTTP client ndlaw_export uses."""

    def __init__(self, url: str, auth: str | None, timeout: float = 30.0):
        from ndlaw_export import McpBackend
        self._inner = McpBackend(url, auth, timeout)

    def lookup(self, cite_key: str) -> dict | None:
        # cite_key is the normalized form ("ndrappp 4"); lookup_authority
        # takes the citation as written.
        citation = cite_key.replace("ndrappp ", "N.D.R.App.P. ")
        rec = self._inner._call_tool("lookup_authority", {"citation": citation})
        if not rec or not rec.get("found"):
            return None
        return {
            "citation": rec.get("citation") or citation,
            "heading": rec.get("heading"),
            "status": rec.get("status"),
            "effective_start": rec.get("effective_start"),
            "source_url": rec.get("source_url"),
            "text": rec.get("text"),
        }

    def close(self):
        self._inner.close()


def pick_backend(args):
    db = args.db or os.environ.get("NDLAW_RULES_DB") or DEFAULT_DB
    if Path(db).expanduser().is_file():
        return SqliteRulesBackend(str(Path(db).expanduser())), f"sqlite:{db}"
    url = args.url or os.environ.get("NDLAW_URL")
    if url:
        return McpRulesBackend(url, args.auth or os.environ.get("NDLAW_AUTH")), f"mcp:{url}"
    return None, None


def _title(record: dict) -> str:
    """`APPEAL—WHEN TAKEN` -> `Appeal—When Taken`, with corpus noise trimmed.

    Headings arrive upper-cased and a few carry a leading dash from the
    scrape ("- MENTAL HEALTH APPEALS"). Title-casing here is cosmetic and
    touches only the heading line; the rule's own text is never rewritten.
    """
    heading = (record.get("heading") or "").strip().lstrip("-").strip()
    if not heading:
        return record["citation"]
    small = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "of",
             "on", "or", "the", "to", "under", "with"}
    words = []
    for i, word in enumerate(heading.split()):
        lowered = word.lower()
        words.append(lowered if i and lowered in small else word.title())
    return " ".join(words)


def render(records: list[dict], generated_on: str) -> str:
    """The generated block, markers included."""
    out = [BEGIN, ""]
    out.append(
        f"*Rule text below is verbatim from the ndlaw corpus, regenerated "
        f"{generated_on} by `nd_rules_export.py`. Each rule carries the "
        f"effective date of the version in force and the court's own URL. "
        f"Nested `>` levels encode subdivision depth. Do not edit this block "
        f"by hand — rerun the script.*"
    )
    out.append("")
    for rec in records:
        out.append(f"## {rec['citation']} — {_title(rec)}")
        out.append("")
        bits = []
        if rec.get("effective_start"):
            bits.append(f"Effective {rec['effective_start']}")
        if rec.get("status") and rec["status"] != "active":
            bits.append(f"**Status: {rec['status']}**")
        if rec.get("source_url"):
            bits.append(f"[ndcourts.gov]({rec['source_url']})")
        if bits:
            out.append("*" + ". ".join(bits) + ".*")
            out.append("")
        out.append((rec.get("text") or "").strip())
        out.append("")
    out.append(END)
    return "\n".join(out).rstrip() + "\n"


def splice(existing: str, block: str) -> str:
    """Replace the generated block, preserving everything around it."""
    if BEGIN in existing and END in existing:
        head = existing.split(BEGIN)[0]
        tail = existing.split(END, 1)[1]
        return head + block.rstrip("\n") + tail
    if BEGIN in existing or END in existing:
        # One marker without the other means the file was edited into a shape
        # this cannot splice. Appending would bury the rules below the notes
        # and leave a stray marker behind, so refuse instead.
        raise ValueError(
            "nd-appellate-rules.md has one generated-block marker but not "
            "both; restore the pair or delete both to regenerate from scratch"
        )
    # First run on a hand-written file: keep it all, append the block.
    return existing.rstrip("\n") + "\n\n" + block


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(DEFAULT_OUT),
                    help="Reference file to rewrite ('-' for stdout).")
    ap.add_argument("--check", action="store_true",
                    help="Exit 1 if the file differs from the corpus; write nothing.")
    ap.add_argument("--db", default=None,
                    help=f"ndlaw rules.db (or NDLAW_RULES_DB env; default {DEFAULT_DB})")
    ap.add_argument("--url", default=None, help="ndlaw MCP endpoint (or NDLAW_URL env)")
    ap.add_argument("--auth", default=None, help="Basic Auth header (or NDLAW_AUTH env)")
    ap.add_argument("--date", default=date.today().isoformat(),
                    help="Generation date stamped into the block (default: today).")
    args = ap.parse_args()

    backend, label = pick_backend(args)
    if backend is None:
        # Not a failure: an install-only machine has no corpus, exactly as
        # drift-check tolerates an absent canonical repo.
        print("nd_rules_export: no ndlaw backend (set NDLAW_RULES_DB or "
              "NDLAW_URL); leaving the reference unchanged.", file=sys.stderr)
        return 0

    records, missing = [], []
    try:
        for cite_key, citation in RULES:
            rec = backend.lookup(cite_key)
            if rec is None:
                missing.append(citation)
            else:
                records.append(rec)
    finally:
        backend.close()

    if missing:
        print(f"nd_rules_export: not in the corpus: {', '.join(missing)}",
              file=sys.stderr)
    if not records:
        print("nd_rules_export: no rules retrieved; leaving the reference "
              "unchanged.", file=sys.stderr)
        return 0

    block = render(records, args.date)

    if args.out == "-":
        sys.stdout.write(block)
        return 0

    out = Path(args.out)
    existing = out.read_text(encoding="utf-8") if out.exists() else ""
    updated = splice(existing, block)

    if args.check:
        # The date line changes daily and would make every check fail, so
        # compare everything except it.
        if _without_date(updated) == _without_date(existing):
            print(f"nd-appellate-rules: in sync with the ndlaw corpus ({label}).")
            return 0
        print("DRIFT: references/nd-appellate-rules.md differs from the ndlaw "
              "corpus — run 'make vendor-ndrules'", file=sys.stderr)
        return 1

    if updated == existing:
        print(f"nd-appellate-rules: unchanged ({len(records)} rules, {label}).")
        return 0
    out.write_text(updated, encoding="utf-8")
    print(f"nd-appellate-rules: wrote {len(records)} rules from {label}.")
    return 0


def _without_date(text: str) -> str:
    """Strip the regenerated-on stamp so --check compares substance."""
    import re
    return re.sub(r"regenerated \d{4}-\d{2}-\d{2} by", "regenerated by", text)


if __name__ == "__main__":
    sys.exit(main())

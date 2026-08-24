#!/usr/bin/env python3
"""Parallel-citation consistency check for cite review.

A draft citing "Whalen v. United States, 445 U.S. 684, 100 S. Ct. 1371" is
wrong: Whalen is 100 S. Ct. 1432, and 100 S. Ct. 1371 is Payton v. New York,
decided the day before.  Both are real citations; only the pairing is false.
This module resolves every member of a parallel-cite group against a source
authoritative for that member's reporter and reports whether they all name
the same case.

The verdict decides whether cite_review may collapse the group to its lead
reporter.  A group that checks out collapses to one review row; a group that
does not is left intact and flagged — silently dropping the wrong half of a
bad pairing is exactly how such an error escapes review today.

Ground truth is jurisdiction-specific, and the distinction is load-bearing:

    ND neutral cites, N.W./N.W.2d/N.W.3d   -> the ndlaw corpus
    U.S., S. Ct., L. Ed., F.2d/F.3d, ...   -> the CourtListener search API

CourtListener is **not** authoritative for North Dakota: it returns
"2020 ND 30" carrying no N.W.2d parallel and does not know "938 N.W.2d 897"
at all.  Reading that silence as a negative would manufacture mismatches on
the commonest cite class in this tool.  So a negative counts only from a
source that claims the reporter in question; every other absence is silence,
and silence yields "unverified" — never "wrong".

Offline, or with no backend reachable, every group is "unverified": the
collapse still happens (as it always has) but is badged, so nobody reads a
short queue as a checked one.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

SKILL_DIR = Path(__file__).parent

# --- Verdict statuses -------------------------------------------------------
CONSISTENT = "consistent"    # every asserted parallel confirmed same case
MISMATCH = "mismatch"        # a parallel positively resolves to another case
NOT_FOUND = "not_found"      # an authoritative source has no such citation
UNVERIFIED = "unverified"    # nothing authoritative could speak to it

#: Statuses that must NOT be collapsed to a single review row.
BLOCKING = frozenset({MISMATCH, NOT_FOUND})

# --- Reporter classes -------------------------------------------------------
# Matched against jetcite's normalized forms, tolerating the spaced and
# unspaced abbreviations that appear in real drafts ("S. Ct." / "S.Ct.").

_ND_PATTERNS = (
    re.compile(r"^[12]\d{3}\s+ND\s+\d{1,3}$", re.I),                  # 2020 ND 30
    re.compile(r"^\d+\s+N\.\s?W\.(?:\s?[23]d)?\s+\d+$", re.I),        # 938 N.W.2d 897
    re.compile(r"^\d+\s+N\.\s?D\.\s+\d+$", re.I),                     # 1 N.D. 1
)

_FED_PATTERNS = (
    re.compile(r"^\d+\s+U\.\s?S\.\s+\d+$", re.I),                     # 445 U.S. 684
    re.compile(r"^\d+\s+S\.\s?Ct\.\s+\d+$", re.I),                    # 100 S. Ct. 1432
    re.compile(r"^\d+\s+L\.\s?Ed\.(?:\s?2d)?\s+\d+$", re.I),          # 63 L. Ed. 2d 715
    re.compile(r"^\d+\s+F\.(?:\s?[234]d|\s?4th)?\s+\d+$", re.I),      # 410 F.3d 438
    re.compile(r"^\d+\s+F\.\s?Supp\.(?:\s?[23]d)?\s+\d+$", re.I),     # 900 F. Supp. 2d 1
)

def fold(cite: str | None) -> str:
    """Comparison key: case- and punctuation-insensitive.

    "100 S. Ct. 1432", "100 S.Ct. 1432" and "100 s ct 1432" all fold to
    "100sct1432", so a draft's spacing never reads as a mismatch.
    """
    return re.sub(r"[^a-z0-9]+", "", (cite or "").lower())


def _norm(cite: str | None) -> str:
    return " ".join((cite or "").split())


def _matches(cite: str, patterns) -> bool:
    c = _norm(cite)
    return any(p.match(c) for p in patterns)


# Reporter class, used to tell a corpus *gap* from a corpus *conflict*.
# If the corpus records a N.W.3d cite for this case and the draft's differs,
# that is a conflict. If it records none at all, the corpus simply has not
# assigned one yet — common for recent ND cases, where the reporter
# assignment lags the opinion — and silence must not read as a finding.
_CLASS_PATTERNS = (
    ("nd-neutral", re.compile(r"^[12]\d{3}\s+ND\s+\d{1,3}$", re.I)),
    ("nw",         re.compile(r"^\d+\s+N\.\s?W\.(?:\s?[23]d)?\s+\d+$", re.I)),
    ("nd-report",  re.compile(r"^\d+\s+N\.\s?D\.\s+\d+$", re.I)),
    ("us",         re.compile(r"^\d+\s+U\.\s?S\.\s+\d+$", re.I)),
    ("sct",        re.compile(r"^\d+\s+S\.\s?Ct\.\s+\d+$", re.I)),
    ("led",        re.compile(r"^\d+\s+L\.\s?Ed\.(?:\s?2d)?\s+\d+$", re.I)),
    ("fsupp",      re.compile(r"^\d+\s+F\.\s?Supp\.(?:\s?[23]d)?\s+\d+$", re.I)),
    ("f",          re.compile(r"^\d+\s+F\.(?:\s?[234]d|\s?4th)?\s+\d+$", re.I)),
)


def reporter_class(cite: str | None) -> str | None:
    """Which reporter series a citation belongs to, or None if unrecognized."""
    c = _norm(cite)
    for name, pat in _CLASS_PATTERNS:
        if pat.match(c):
            return name
    return None


# Database identifiers are not reporters; a draft never cites them as a
# parallel and a source returning one must not be treated as a case cite.
_DB_CITE_RE = re.compile(r"\b(?:LEXIS|WL)\b", re.I)


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------

def build_groups(citations: list[dict]) -> list[list[str]]:
    """Recover full parallel groups from jetcite's pairwise links.

    jetcite records only ``parallel_cite`` (singular — ``parallel_cites[0]``,
    see ``legacy.py``), so a three-member group arrives as a chain:
    445 U.S. 684 -> 100 S. Ct. 1371 <- 63 L. Ed. 2d 639.  Union-find over
    those links recovers the set.

    Repeats and pin cites are skipped: they resolve through their parent, and
    a parallel group is an authority-level fact.
    """
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    order: list[str] = []
    for c in citations:
        if c.get("is_repeat") or c.get("cite_type") == "pin_cite":
            continue
        n = _norm(c.get("normalized"))
        if not n:
            continue
        if n not in parent:
            order.append(n)
        find(n)
        pc = _norm(c.get("parallel_cite"))
        if pc:
            if pc not in parent:
                order.append(pc)
            union(n, pc)

    groups: dict[str, list[str]] = {}
    for n in order:
        groups.setdefault(find(n), []).append(n)
    return [g for g in groups.values() if len(g) > 1]


# ---------------------------------------------------------------------------
# Resolvers
# ---------------------------------------------------------------------------

class Resolver:
    """Resolves a citation to a case identity, for reporters it claims.

    ``claims()`` is the authority boundary: only a resolver that claims a
    reporter may turn a failed lookup into a negative finding.
    """

    name = "resolver"

    def claims(self, cite: str) -> bool:          # pragma: no cover - iface
        raise NotImplementedError

    def lookup(self, cite: str) -> dict | None:   # pragma: no cover - iface
        raise NotImplementedError


class NdResolver(Resolver):
    """The ndlaw corpus — authoritative for ND opinions and N.W. reporters."""

    name = "the ND corpus"

    def __init__(self, backend):
        self._backend = backend

    @classmethod
    def from_env(cls, db: str | None = None, url: str | None = None,
                 auth: str | None = None) -> "NdResolver | None":
        """Build from an ndlaw_export backend, or None if none is reachable."""
        try:
            sys.path.insert(0, str(SKILL_DIR))
            from ndlaw_export import _pick_backend
        except Exception:
            return None
        finally:
            if sys.path and sys.path[0] == str(SKILL_DIR):
                sys.path.pop(0)
        shim = argparse.Namespace(db=db, url=url, auth=auth)
        try:
            backend, _label = _pick_backend(shim)
        except Exception:
            return None
        return cls(backend) if backend is not None else None

    def claims(self, cite: str) -> bool:
        return _matches(cite, _ND_PATTERNS)

    def lookup(self, cite: str) -> dict | None:
        try:
            rec = self._backend.lookup_meta(cite)
        except Exception:
            return None
        if not rec:
            return None
        return {"case_name": rec.get("case_name"),
                "citations": rec.get("citations") or [cite]}

    def close(self) -> None:
        try:
            self._backend.close()
        except Exception:
            pass


class CourtListenerResolver(Resolver):
    """CourtListener's search API — federal reporters only.

    Deliberately *not* claiming ND: its ND coverage carries no N.W. parallels,
    so its silence there is a gap, not a finding.  Uses only the anonymous
    search endpoint (no token; full text is never requested).
    """

    name = "CourtListener"
    BASE = "https://www.courtlistener.com/api/rest/v4/search/"

    def __init__(self, timeout: float = 20.0):
        self.timeout = timeout

    def claims(self, cite: str) -> bool:
        return _matches(cite, _FED_PATTERNS)

    def lookup(self, cite: str) -> dict | None:
        qs = urllib.parse.urlencode({"q": f'citation:("{_norm(cite)}")',
                                     "type": "o"})
        req = urllib.request.Request(
            f"{self.BASE}?{qs}",
            headers={"User-Agent": "jetredline-parallel-check/1.0",
                     "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.load(resp)
        except Exception:
            return None
        if not data.get("count"):
            return None
        top = data["results"][0]
        cites = [c for c in (top.get("citation") or [])
                 if not _DB_CITE_RE.search(c)]
        return {"case_name": top.get("caseName"),
                "citations": cites or [_norm(cite)]}


# ---------------------------------------------------------------------------
# Checking
# ---------------------------------------------------------------------------

@dataclass
class Verdict:
    status: str
    members: list[str]
    detail: str = ""
    case_name: str | None = None
    source: str | None = None
    confirmed: list[str] = field(default_factory=list)

    @property
    def blocks_collapse(self) -> bool:
        return self.status in BLOCKING

    def to_dict(self) -> dict:
        return {"status": self.status, "members": list(self.members),
                "detail": self.detail, "case_name": self.case_name,
                "source": self.source, "confirmed": list(self.confirmed)}


def _resolver_for(cite: str, resolvers: list[Resolver]) -> Resolver | None:
    for r in resolvers:
        if r.claims(cite):
            return r
    return None


def check_group(members: list[str], resolvers: list[Resolver],
                cache: dict | None = None) -> Verdict:
    """Resolve a parallel group and judge whether its members agree.

    Anchors on the first member any resolver can actually resolve, then tests
    each remaining member against that case's authoritative citation set.
    """
    cache = {} if cache is None else cache

    def resolve(cite: str):
        key = fold(cite)
        if key not in cache:
            r = _resolver_for(cite, resolvers)
            cache[key] = (r, r.lookup(cite) if r else None)
        return cache[key]

    anchor = anchor_rec = anchor_res = None
    for m in members:
        res, rec = resolve(m)
        if rec:
            anchor, anchor_rec, anchor_res = m, rec, res
            break

    if anchor_rec is None:
        # Nothing resolvable. If a claiming resolver actively said "no such
        # citation" for every member it claims, that is a finding; otherwise
        # it is silence.
        claimed = [(m, _resolver_for(m, resolvers)) for m in members]
        denied = [(m, r) for m, r in claimed if r is not None]
        if denied:
            names = ", ".join(m for m, _ in denied)
            src = denied[0][1].name
            return Verdict(NOT_FOUND, members, source=src,
                           detail=f"not located in {src}: {names}")
        return Verdict(UNVERIFIED, members,
                       detail="no source available for these reporters")

    anchor_cites = list(anchor_rec.get("citations") or [])
    known = {fold(c) for c in anchor_cites}
    known.add(fold(anchor))
    src_name = anchor_res.name if anchor_res else "the source"
    confirmed, unconfirmed, bad, gaps = [anchor], [], [], []

    for m in members:
        if m == anchor:
            continue
        if fold(m) in known:
            confirmed.append(m)
            continue

        res, rec = resolve(m)
        if rec:
            other = {fold(c) for c in rec.get("citations") or []}
            if other & known:
                confirmed.append(m)
            else:
                # Positively a different case: the strongest finding there is.
                bad.append((m, f"{m} is {rec.get('case_name') or 'a different case'}"))
            continue

        # m did not resolve. Whether that is a finding depends on whether the
        # source has anything to say about m's reporter series for this case.
        cls = reporter_class(m)
        rival = next((c for c in anchor_cites
                      if cls and reporter_class(c) == cls and fold(c) != fold(m)),
                     None)
        if rival:
            # The source records a cite of this very series, and it differs.
            bad.append((m, f"{m} — {src_name} records {rival}"))
        elif res is not None:
            # A claiming source that records no cite of this series for the
            # case: a gap in the corpus, not evidence against the draft.
            # (Recent ND opinions routinely have no N.W.3d assignment yet.)
            gaps.append(f"{m} — no {cls or 'parallel'} cite recorded for this "
                        f"case in {res.name}")
        else:
            unconfirmed.append(m)

    if bad:
        lead = f"{anchor} is {anchor_rec.get('case_name') or 'one case'}"
        return Verdict(MISMATCH, members, case_name=anchor_rec.get("case_name"),
                       source=src_name, confirmed=confirmed,
                       detail=lead + ", but " + "; ".join(d for _, d in bad))
    if gaps or unconfirmed:
        parts = list(gaps) + [f"no source for {m}" for m in unconfirmed]
        return Verdict(UNVERIFIED, members, case_name=anchor_rec.get("case_name"),
                       source=src_name, confirmed=confirmed,
                       detail="; ".join(parts))
    return Verdict(CONSISTENT, members, case_name=anchor_rec.get("case_name"),
                   source=src_name, confirmed=confirmed,
                   detail=f"{len(members)} parallel cites, consistent")


def check_citations(citations: list[dict], resolvers: list[Resolver] | None = None,
                    verbose: bool = False) -> dict[str, Verdict]:
    """Check every parallel group; returns folded-citation -> Verdict.

    Every member of a group maps to the same Verdict object, so a caller can
    look up any citation form and get its group's finding.
    """
    resolvers = resolvers or []
    out: dict[str, Verdict] = {}
    cache: dict = {}
    for members in build_groups(citations):
        v = check_group(members, resolvers, cache)
        if verbose:
            print(f"  [{v.status}] {' = '.join(members)}"
                  + (f" — {v.detail}" if v.detail else ""), file=sys.stderr)
        for m in members:
            out[fold(m)] = v
    return out


def default_resolvers(local_only: bool = False, nd_db: str | None = None,
                      nd_url: str | None = None,
                      nd_auth: str | None = None) -> list[Resolver]:
    """ND first (authoritative where it speaks), then CourtListener.

    A local ndlaw sqlite corpus needs no network, so it survives
    ``--local-only``; CourtListener does not.
    """
    resolvers: list[Resolver] = []
    nd = NdResolver.from_env(db=nd_db, url=nd_url, auth=nd_auth)
    if nd is not None:
        resolvers.append(nd)
    if not local_only:
        resolvers.append(CourtListenerResolver())
    return resolvers


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cite-json", required=True,
                    help="cite_check.py JSON to check")
    ap.add_argument("--local-only", action="store_true",
                    help="Skip network resolvers (local ndlaw corpus only)")
    ap.add_argument("--json", action="store_true", help="Emit verdicts as JSON")
    args = ap.parse_args()

    entries = json.loads(Path(args.cite_json).expanduser().read_text(encoding="utf-8"))
    resolvers = default_resolvers(local_only=args.local_only)
    if not resolvers:
        print("No resolver available; every group will be unverified.",
              file=sys.stderr)
    verdicts = check_citations(entries, resolvers, verbose=not args.json)

    if args.json:
        seen, out = set(), []
        for v in verdicts.values():
            if id(v) in seen:
                continue
            seen.add(id(v))
            out.append(v.to_dict())
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return

    blocking = {id(v): v for v in verdicts.values() if v.blocks_collapse}
    print(f"\n{len(blocking)} group(s) need review.", file=sys.stderr)
    sys.exit(1 if blocking else 0)


if __name__ == "__main__":
    main()

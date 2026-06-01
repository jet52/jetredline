"""Canonical registry of outbound domains jetcite contacts.

Single source of truth for jetcite's network egress. Parsing and URL
generation are offline; the hosts below are reached only when resolving,
fetching, or verifying citations against official sources.

If you add a source module that fetches from a NEW host, add it here too.
``tests/test_egress.py`` fails otherwise — and that test also requires the
new entry to appear in ``jetcite/NETWORK.md`` (the allowlist instructions
that ship with every vendored copy) and in ``README.md``, so the setup
instructions can never silently fall out of date with the code.
"""

from __future__ import annotations

#: Allowlist entries, keyed by the pattern a user adds to a sandbox egress
#: allowlist (Claude Cowork "Additional allowed domains" /
#: ``sandbox.network.allowedDomains`` in Claude Code). Values describe what
#: each entry enables. A ``*.`` prefix is a subdomain wildcard.
EGRESS_ALLOWLIST: dict[str, str] = {
    "*.ndcourts.gov": "ND opinion PDF resolution, ND rules, ND case records",
    "www.courtlistener.com": "Case-law fallback URLs and source verification",
    "supreme.justia.com": "U.S. Reports opinion pages",
    "www.law.cornell.edu": "Federal rule pages (FRCP, FRE, etc.)",
    "www.govinfo.gov": "U.S. Code section links",
    "www.ecfr.gov": "C.F.R. section links",
    "ndlegis.gov": "NDCC, NDAC",
    "ndconst.org": "ND Constitution",
    "constitutioncenter.org": "U.S. Constitution",
}

#: Hosts that appear in source text but are never fetched (e.g. the project
#: URL baked into the User-Agent string). Excluded from the egress audit.
NON_FETCH_HOSTS: frozenset[str] = frozenset({"github.com"})


def covers(host: str) -> bool:
    """Return True if ``host`` is permitted by some ``EGRESS_ALLOWLIST`` entry."""
    for entry in EGRESS_ALLOWLIST:
        if entry.startswith("*."):
            base = entry[2:]
            if host == base or host.endswith("." + base):
                return True
        elif host == entry:
            return True
    return False

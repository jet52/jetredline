# jetcite — network egress requirements

> This file is the canonical list of domains jetcite contacts. It lives
> **inside the package** (`jetcite/NETWORK.md`), so it travels automatically
> with any `cp -r .../jetcite` vendoring step. Packages that vendor jetcite
> should point their own README at this file rather than copying the list (so
> it can't drift).

Citation **parsing** and URL **generation** are fully offline. A few features
make outbound HTTP requests, and sandboxed Claude environments (Claude Cowork,
Claude Code sandbox) route all egress through a filtering proxy with a domain
allowlist. If a target host is not allowlisted, the request is rejected at the
proxy (HTTP 403 on CONNECT) and jetcite degrades silently to a less specific
result — most visibly, an ND opinion keeps its *search* URL instead of
resolving to the direct opinion **PDF URL**.

## Domains to allowlist

| Allowlist entry | Host(s) contacted | Enables |
|-----------------|-------------------|---------|
| `*.ndcourts.gov` | `www.ndcourts.gov`, `record.ndcourts.gov` | ND opinion PDF resolution (default scan), ND rules, ND case records |
| `www.courtlistener.com` | `www.courtlistener.com` | Case-law fallback URLs and source verification |
| `supreme.justia.com` | `supreme.justia.com` | U.S. Reports opinion pages |
| `www.law.cornell.edu` | `www.law.cornell.edu` | Federal rule pages (FRCP, FRE, etc.) |
| `www.govinfo.gov` | `www.govinfo.gov` | U.S. Code section links |
| `www.ecfr.gov` | `www.ecfr.gov` | C.F.R. section links |
| `ndlegis.gov` | `ndlegis.gov` | NDCC, NDAC |
| `ndconst.org` | `ndconst.org` | ND Constitution |
| `constitutioncenter.org` | `constitutioncenter.org` | U.S. Constitution |

**Minimum:** add `*.ndcourts.gov`. It is the only host needed for the default
ND opinion PDF resolution — the feature most users notice missing. Add the rest
for full functionality (federal sources, case-law fallback, and verification).

## Where to set it

- **Claude Cowork:** sandbox settings → **Allow network egress** → **Domain
  allowlist** → **Additional allowed domains** → add each entry above.
- **Local Claude Code:** add the same hosts under
  `sandbox.network.allowedDomains` in `.claude/settings.json` (or
  `~/.claude/settings.json`).

## Two things that commonly trip people up

1. **A bare domain does not match its subdomains.** jetcite requests
   `www.ndcourts.gov`, so an allowlist entry of `ndcourts.gov` alone still 403s.
   Use the wildcard `*.ndcourts.gov` (or list the exact host).
2. **The allowlist is read when the session starts.** Editing it does not
   reconfigure an already-running sandbox — start a **new** session afterward.

## Verify

In a fresh session, resolve a known ND citation and confirm you get a direct
opinion URL (`…/opinions/<id>`) rather than a search URL (`…/opinions?cit1=…`):

```bash
python3 path/to/jetcite_tool.py lookup "2008 ND 144"
# → https://www.ndcourts.gov/supreme-court/opinions/114404
```

jetcite works with no `httpx` installed — it falls back to the standard-library
`urllib`, which uses the same proxy — so a 403 here is always an allowlist
issue, never a missing dependency.

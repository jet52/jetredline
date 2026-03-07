# TODO: Refs Caching Tests

## Goal
Validate that the jetcite `cache.py` module correctly resolves, fetches, and caches citations under `~/refs/`, especially for citation types that don't yet have local files. Verify behavior in both Claude Code and Cowork Desktop.

## Current state of ~/refs/
- `opin/markdown/{year}/` — ND opinions, 1997-2026 (well-populated)
- `ndcc/title-{t}/` — ND Century Code (well-populated)
- `cnst/` — ND Constitution
- `ndac/` — ND Administrative Code
- `rule/` — ND court rules
- `sess/` — session laws
- **`federal/` does not exist yet** — no federal opinions, USC, or CFR cached

## Directory structure defined in jetcite cache.py
These paths are returned by `_citation_path()` but most federal directories are empty/missing:

| Citation type | Cache path | Exists? |
|---|---|---|
| ND case (neutral) | `opin/markdown/{year}/{year}ND{number}.md` | Yes |
| Federal reporter case | `federal/opinions/{reporter}/{volume}/{page}.md` | No |
| USC statute | `federal/usc/{title}/{section}.md` | No |
| CFR regulation | `federal/cfr/{title}/{section}.md` | No |
| NDCC | `ndcc/title-{t}/chapter-{t}-{ch}.md` | Yes |
| ND Constitution | `cnst/art-{nn}/sec-{s}.md` | Yes |
| NDAC | `ndac/title-{p1}/article-{p1}-{p2}/chapter-{p1}-{p2}-{p3}.md` | Yes |
| ND court rule | `rule/{rule_set}/rule-{parts}.md` | Yes |

## Test cases to build

### 1. Old NW2d cases (pre-neutral citation era)
Pre-1997 ND cases only have NW2d cites (e.g., `Arneson v. Arneson, 355 N.W.2d 16 (N.D. 1984)`). These are state cases but `_citation_path()` routes them through the federal reporter path: `federal/opinions/NW2d/355/16.md`. This is arguably wrong — NW2d is a regional reporter, not a federal one. Questions:
- Should NW2d/NW cases get their own top-level directory (e.g., `state/opinions/NW2d/`)?
- Or keep the current `federal/opinions/` as a catch-all for all reporter-based cases?
- Does `fetch_and_cache()` actually succeed for these? Google Scholar and CourtListener URLs may not resolve cleanly to markdown.
- Test with a handful of well-known old ND cases and verify round-trip: scan -> fetch -> cache -> re-scan shows `local_exists: true`.

### 2. Federal citations
- **U.S. Supreme Court**: e.g., `Brown v. Board of Education, 347 U.S. 483 (1954)` — maps to `federal/opinions/US/347/483.md`
- **Federal reporter**: e.g., `Smith v. Jones, 500 F.3d 200 (8th Cir. 2007)` — maps to `federal/opinions/F3d/500/200.md`
- **USC**: e.g., `42 U.S.C. § 1983` — maps to `federal/usc/42/1983.md`
- **CFR**: e.g., `29 C.F.R. § 1630.2` — maps to `federal/cfr/29/1630.2.md`
- Test that `fetch_and_cache()` creates the directory tree and writes content + `.meta.json` sidecar.
- Verify fetched content is usable (not raw HTML or a PDF binary blob).

### 3. Cache sidecar metadata
- Verify `.meta.json` is created with `citation`, `source_url`, `fetched`, `content_type`.
- Test `is_stale()` for statutes (90-day threshold) and court rules (180-day threshold).
- Confirm cases and constitution entries are marked permanent (never stale).

### 4. nd_cite_check.py integration
- Run `nd_cite_check.py` on a test opinion containing a mix of ND neutral cites, old NW2d cites, federal cites, and statutes.
- Verify JSON output shows correct `local_path`, `local_exists`, `url`, and `cite_type` for each.
- After running `fetch_and_cache()` for missing ones, re-run and confirm `local_exists` flips to `true`.

### 5. Environment testing
- **Claude Code**: primary dev environment, should work as-is.
- **Cowork Desktop**: verify `~/refs/` path resolves correctly, `fetch_and_cache()` has network access, and the venv Python can import jetcite. Check if sandbox restrictions affect file writes to `~/refs/`.

## Open questions
- The `federal/opinions/` directory name is misleading for NW2d state cases. Consider renaming to `reporter/` or splitting into `federal/` and `state/`.
- Should `fetch_and_cache()` be called automatically during `nd_cite_check.py` runs, or only on demand?
- Content quality: fetched HTML from legal sites often needs cleanup. Should there be a post-fetch markdown conversion step?

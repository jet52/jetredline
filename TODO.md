# TODO: Refs Cache Directory Restructure & Tests

## Goal
Restructure `_citation_path()` in jetcite `cache.py` to use a three-tier directory layout under `~/refs/`, then validate with tests.

## Current state of ~/refs/
- `opin/markdown/{year}/` — ND opinions, 1997-2026 (well-populated)
- `ndcc/title-{t}/` — ND Century Code (well-populated)
- `cnst/` — ND Constitution
- `ndac/` — ND Administrative Code
- `rule/` — ND court rules
- `sess/` — session laws
- **`federal/` does not exist yet**
- **`reporter/` does not exist yet**

---

## New directory structure

Three-tier layout for case citations. All reporter directory names are normalized by stripping periods and spaces from the Bluebook reporter abbreviation.

### Normalization rule

`reporter_dir = reporter_name.replace(".", "").replace(" ", "").replace("'", "").replace("\u2019", "")`

Examples: `N.W.2d` → `NW2d`, `F. Supp. 3d` → `FSupp3d`, `S. Ct.` → `SCt`, `F. App'x` → `FAppx`

One exception: `U.S.` maps to `scotus` (not `US`), because `US` is ambiguous and these are Supreme Court cases.

### Tier 1: `opin/` — North Dakota cases only

| Citation | Path |
|---|---|
| ND neutral (1997+) | `opin/markdown/{year}/{year}ND{number}.md` |
| N.W.2d (pre-1997 ND) | `opin/NW2d/{volume}/{page}.md` |
| N.W. (pre-1889 ND) | `opin/NW/{volume}/{page}.md` |
| N.D. (1890-1953) | `opin/ND/{volume}/{page}.md` |

**Note:** NW and NW2d are regional reporters covering multiple states. We store them under `opin/` because they are the historical reporters for ND cases before neutral citations. NW3d (started 2024) goes under `reporter/` since ND cases from that era always have neutral citations as the primary cite.

**Future consideration:** May eventually move ND to `reporter/ND/` for structural consistency across all reporter-based citations.

### Tier 2: `federal/` — federal cases, statutes, regulations

Cases:

| Reporter | Directory |
|---|---|
| U.S. (U.S. Reports) | `federal/scotus/{volume}/{page}.md` |
| S. Ct. | `federal/SCt/{volume}/{page}.md` |
| L. Ed. | `federal/LEd/{volume}/{page}.md` |
| L. Ed. 2d | `federal/LEd2d/{volume}/{page}.md` |
| F. | `federal/F/{volume}/{page}.md` |
| F.2d | `federal/F2d/{volume}/{page}.md` |
| F.3d | `federal/F3d/{volume}/{page}.md` |
| F.4th | `federal/F4th/{volume}/{page}.md` |
| F. Supp. | `federal/FSupp/{volume}/{page}.md` |
| F. Supp. 2d | `federal/FSupp2d/{volume}/{page}.md` |
| F. Supp. 3d | `federal/FSupp3d/{volume}/{page}.md` |
| B.R. | `federal/BR/{volume}/{page}.md` |
| F.R.D. | `federal/FRD/{volume}/{page}.md` |
| Fed. Cl. | `federal/FedCl/{volume}/{page}.md` |
| M.J. | `federal/MJ/{volume}/{page}.md` |
| Vet. App. | `federal/VetApp/{volume}/{page}.md` |
| T.C. | `federal/TC/{volume}/{page}.md` |
| F. App'x | `federal/FAppx/{volume}/{page}.md` |

Statutes and regulations (unchanged):

| Type | Path |
|---|---|
| USC | `federal/usc/{title}/{section}.md` |
| CFR | `federal/cfr/{title}/{section}.md` |

### Tier 3: `reporter/` — all other state and regional reporters

| Reporter | Directory |
|---|---|
| N.W.3d | `reporter/NW3d/{volume}/{page}.md` |
| A. / A.2d / A.3d | `reporter/A/{volume}/...`, `reporter/A2d/...`, `reporter/A3d/...` |
| N.E. / N.E.2d / N.E.3d | `reporter/NE/...`, `reporter/NE2d/...`, `reporter/NE3d/...` |
| S.E. / S.E.2d | `reporter/SE/...`, `reporter/SE2d/...` |
| So. / So.2d / So.3d | `reporter/So/...`, `reporter/So2d/...`, `reporter/So3d/...` |
| S.W. / S.W.2d / S.W.3d | `reporter/SW/...`, `reporter/SW2d/...`, `reporter/SW3d/...` |
| P. / P.2d / P.3d | `reporter/P/...`, `reporter/P2d/...`, `reporter/P3d/...` |
| Cal. / Cal.2d / Cal.3d / Cal.4th / Cal.5th | `reporter/Cal/...`, `reporter/Cal2d/...`, etc. |
| Cal. Rptr. / Cal. Rptr. 2d / Cal. Rptr. 3d | `reporter/CalRptr/...`, `reporter/CalRptr2d/...`, etc. |
| N.Y. / N.Y.2d / N.Y.3d | `reporter/NY/...`, `reporter/NY2d/...`, etc. |
| N.Y.S. / N.Y.S.2d / N.Y.S.3d | `reporter/NYS/...`, `reporter/NYS2d/...`, etc. |
| Ohio St. / Ohio St.2d / Ohio St.3d | `reporter/OhioSt/...`, etc. |
| Ill. / Ill.2d | `reporter/Ill/...`, `reporter/Ill2d/...` |
| Ill. Dec. | `reporter/IllDec/{volume}/{page}.md` |
| Wash. / Wash.2d | `reporter/Wash/...`, `reporter/Wash2d/...` |
| Wash. App. / Wash. App. 2d | `reporter/WashApp/...`, `reporter/WashApp2d/...` |
| Other state reporters (Conn., Ga., etc.) | `reporter/{normalized}/{volume}/{page}.md` |

### Unchanged paths (non-case citations)

| Type | Path |
|---|---|
| NDCC | `ndcc/title-{t}/chapter-{t}-{ch}.md` |
| ND Constitution | `cnst/art-{nn}/sec-{s}.md` |
| NDAC | `ndac/title-{p1}/article-{p1}-{p2}/chapter-{p1}-{p2}-{p3}.md` |
| ND court rule | `rule/{rule_set}/rule-{parts}.md` |
| Session laws | `sess/` (manual, not cache-managed) |

---

## Implementation plan

### Step 1: Update `_citation_path()` in jetcite `cache.py`

Replace the current CASE routing logic with:

```python
# Reporter directory name: strip periods and spaces
def _reporter_dir(reporter: str) -> str:
    if reporter == "U.S.":
        return "scotus"
    return reporter.replace(".", "").replace(" ", "")

# ND reporters that go under opin/ (historical ND case reporters)
_ND_REPORTERS = {"N.W.", "N.W.2d", "N.D."}
```

Case routing:
1. ND neutral citation → `opin/markdown/{year}/...` (unchanged)
2. Reporter in `_ND_REPORTERS` → `opin/{dir}/{volume}/{page}.md`
3. Federal jurisdiction cases → `federal/{dir}/{volume}/{page}.md`
4. Everything else → `reporter/{dir}/{volume}/{page}.md`

Determining federal vs state: cases from `FederalCaseMatcher` all have `jurisdiction="us"`. But so do regional reporter cases from `RegionalReporterMatcher`. We can't rely on jurisdiction alone.

**Approach:** Define a set of federal reporters explicitly:
```python
_FEDERAL_REPORTERS = {
    "U.S.", "S. Ct.", "L. Ed.", "L. Ed. 2d",
    "F.", "F.2d", "F.3d", "F.4th",
    "F. Supp.", "F. Supp. 2d", "F. Supp. 3d",
    "B.R.", "F.R.D.", "Fed. Cl.", "M.J.",
    "Vet. App.", "T.C.", "F. App'x",
}
```

Routing: ND neutral → opin/markdown, ND reporter → opin/, federal reporter → federal/, all others → reporter/.

### Step 2: Update `nd_cite_check.py` `_legacy_cite_type()`

The `_legacy_cite_type()` function in nd_cite_check.py derives a cite_type string from the jetcite Citation. It currently routes reporter cases to `"federal_reporter"`. Update to distinguish:
- `"nd_reporter"` for NW/NW2d/ND reporter cases
- `"federal_reporter"` for federal reporter cases
- `"state_reporter"` for everything else in reporter/

### Step 3: Create directories on first write

Already handled — `cache_content()` calls `full.parent.mkdir(parents=True, exist_ok=True)`. No change needed.

### Step 4: Tests

#### 4a. Unit tests for `_citation_path()`
Build Citation objects for each category and verify the returned path:
- ND neutral → `opin/markdown/...`
- `355 N.W.2d 16` → `opin/NW2d/355/16.md`
- `50 N.D. 123` → `opin/ND/50/123.md`
- `347 U.S. 483` → `federal/scotus/347/483.md`
- `500 F.3d 200` → `federal/F3d/500/200.md`
- `42 U.S.C. § 1983` → `federal/usc/42/1983.md`
- `29 C.F.R. § 1630.2` → `federal/cfr/29/1630.2.md`
- `140 S. Ct. 1731` → `federal/SCt/140/1731.md`
- `800 P.2d 500` → `reporter/P2d/800/500.md`
- `10 N.W.3d 500` → `reporter/NW3d/10/500.md`

#### 4b. Cache sidecar metadata
- Verify `.meta.json` is created with `citation`, `source_url`, `fetched`, `content_type`.
- Test `is_stale()` for statutes (90-day threshold) and court rules (180-day threshold).
- Confirm cases and constitution entries are marked permanent (never stale).

#### 4c. Round-trip integration test
- Run `nd_cite_check.py` on text containing a mix of citation types.
- Verify JSON output has correct `local_path`, `local_exists`, `cite_type` for each.

#### 4d. Environment testing
- **Claude Code**: primary dev environment.
- **Cowork Desktop**: verify `~/refs/` path resolves, `fetch_and_cache()` has network access, venv can import jetcite. Check sandbox restrictions on file writes to `~/refs/`.

---

## Open questions
- Should `fetch_and_cache()` be called automatically during `nd_cite_check.py` runs, or only on demand?
- Content quality: fetched HTML from legal sites often needs cleanup. Should there be a post-fetch markdown conversion step?

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

---

# TODO: Cowork Compatibility & Skill Improvements

## Context
These issues were identified during a Cowork session (2026-03-17) redlining a draft dissent in *Ferderer v. NDDHHS*, No. 20250335. The skill ran to completion but required multiple workarounds. The goal is full functionality in both Claude Code and Cowork without manual intervention.

## Environment differences: Claude Code vs. Cowork

| Constraint | Claude Code | Cowork |
|---|---|---|
| Skill directory | `~/.claude/skills/jetredline/` (read-write) | `/mnt/.skills/skills/jetredline/` (read-only) |
| Docx plugin path | `~/.claude/plugins/cache/anthropic-agent-skills/document-skills/69c0b1a06741/skills/docx/` | `/mnt/.skills/skills/docx/` |
| Docx plugin layout | `ooxml/scripts/{unpack,pack}.py`, `scripts/document.py`, `scripts/utilities.py`, `ooxml.md` | `scripts/office/{unpack,pack}.py`, `scripts/comment.py`, no `document.py`, no `utilities.py`, no `ooxml.md` |
| Document API | `scripts.document.Document` — full tracked-change + comment API using minidom | **Not available.** Comments via standalone `scripts/comment.py` (writes comment XML files + rels); no tracked-change helper |
| Comment workflow | `doc.add_comment()` handles everything: range markers in document.xml, comment XML files, rels, people.xml | `comment.py` handles comment XML files + rels only; caller must insert `commentRangeStart`/`commentRangeEnd`/`commentReference` into document.xml manually |
| LibreOffice | Installed at `/Applications/LibreOffice.app/Contents/MacOS/soffice` | Installed at `/usr/bin/soffice` (v25.2); `soffice.py` provides `LD_PRELOAD` shim for `AF_UNIX` sandbox restrictions |
| Python venv | `~/.claude/skills/jetredline/.venv/` (writable) | Read-only skill dir; venv must go to `/tmp/` |
| Network | Direct | SOCKS proxy (requires `httpx[socks]`); `socksio` not pre-installed |
| Temp files | Writable anywhere | `/mnt/` has restricted write permissions; use `/tmp/` or `/sessions/` |
| `~/refs/` | Exists on host filesystem | Not mounted by default |
| Home directory | Real `~` with `.claude/`, `code/`, etc. | Sandboxed; `~` is `/root` with minimal contents |
| `defusedxml` | In venv | Pre-installed (used by docx plugin) |

---

## Issue 1: `apply_edits.py` depends on missing `scripts.document` module

**Symptom:** `ModuleNotFoundError: No module named 'scripts.document'` when running `apply_edits.py`.

**Root cause:** The script imports `from scripts.document import Document`, which exists in the Claude Code docx plugin layout but not in the Cowork layout. Cowork's docx plugin is a completely different codebase — it has `scripts/comment.py` as a standalone comment injection script, but no `Document` class and no `utilities.py` (the `XMLEditor` base class).

**Workaround used:** Wrote a custom `apply_edits_v2.py` script that directly manipulates document.xml with string operations.

### Revised plan: Make `apply_edits.py` environment-agnostic

After exploring the Cowork docx plugin layout, a full reimplementation is unnecessary. The strategy is:

**1. Inline the trivial DOM manipulation.** Replace `editor.insert_before()` / `editor.insert_after()` with direct minidom calls. The Document API's `_parse_fragment()` method is ~15 lines (parse XML string with namespace declarations from the root element, import nodes into the document). `insertBefore` is a standard minidom method. This eliminates the `from scripts.document import Document` import for all tracked-change operations.

**2. Inline the RSID + people.xml setup.** `Document.__init__` generates a random RSID hex string and writes it to `settings.xml`, and creates `people.xml` from a template. This is ~30 lines of straightforward XML manipulation. Without it, Word may show a "repair" dialog on first open (cosmetic, not data loss).

**3. Abstract comment injection over two backends:**
- **If `scripts.document.Document` is importable** (Claude Code) → use `doc.add_comment()` as before
- **Otherwise** (Cowork) → shell out to Cowork's `scripts/comment.py` for the comment metadata XML (it handles all 4 comment XML files + rels + content types), then insert `commentRangeStart`/`commentRangeEnd`/`commentReference` markers into `document.xml` directly

This is the cleanest split because both environments already agree on who inserts the document.xml markers — apply_edits.py does it in Claude Code (via the runs it builds), and would do it directly in Cowork. The only difference is who writes `comments.xml` et al.

**4. Pass pack/unpack/comment paths via CLI args or env vars.** SKILL.md Step 0 discovers the paths; apply_edits.py receives them. No hardcoded paths in the Python script.

### What the Document API actually provides (for reference)

Methods used by apply_edits.py and what replaces them:

| Document API method | What it does | Replacement |
|---|---|---|
| `Document(path, author=)` | RSID setup, people.xml, settings.xml | Inline ~30 lines |
| `doc["word/document.xml"]` | Returns `DocxXMLEditor` (wraps minidom) | Direct `defusedxml.minidom.parse()` |
| `editor.dom` | The minidom DOM tree | Direct from parse |
| `editor.insert_before(elem, xml)` | Parse fragment + `insertBefore` | Inline `_parse_fragment()` (~15 lines) + `parentNode.insertBefore()` |
| `editor.insert_after(elem, xml)` | Parse fragment + insert after | Same + `nextSibling` logic |
| `doc.add_comment(start, end, text)` | Writes to 4 XML files + rels + document.xml markers | Claude Code: keep as-is; Cowork: shell out to `comment.py` + inline markers |
| `doc.save(validate=False)` | Serializes DOM back to file | `dom.toxml()` + write |

- [ ] Inline `_parse_fragment()`, `insert_before()`, `insert_after()` as standalone functions
- [ ] Inline RSID generation and people.xml template setup
- [ ] Add comment backend abstraction (Document API vs. Cowork `comment.py`)
- [ ] Accept pack/unpack/comment paths via `--pack-script`, `--comment-script` args
- [ ] Remove hardcoded `DOCX_PLUGIN_PATH` and `PYTHONPATH` dependency
- [ ] Test in both Claude Code and Cowork

---

## Issue 2: Docx plugin path resolution in SKILL.md

**Symptom:** Hardcoded paths to `ooxml/scripts/pack.py`, `ooxml/scripts/unpack.py`, and `ooxml.md` don't exist in Cowork.

**Root cause:** The two environments have completely different docx plugin layouts:

| Component | Claude Code | Cowork |
|---|---|---|
| Unpack | `ooxml/scripts/unpack.py` | `scripts/office/unpack.py` |
| Pack | `ooxml/scripts/pack.py` | `scripts/office/pack.py` |
| Comments | `scripts/document.py` (Document API) | `scripts/comment.py` (standalone) |
| XML reference | `ooxml.md` (separate file) | Embedded in `SKILL.md` |
| Validate | `ooxml/scripts/validation/` | `scripts/office/validate.py` |
| LibreOffice env | Manual PATH setup | `scripts/office/soffice.py` → `get_soffice_env()` / `run_soffice()` |
| Accept changes | N/A | `scripts/accept_changes.py` (headless LibreOffice macro) |

**Suggested fix:** Add a docx-plugin path discovery block to SKILL.md Step 0 that probes for both layouts and sets variables consumed by apply_edits.py:

```bash
# Detect docx plugin location
if [ -d "/mnt/.skills/skills/docx" ]; then
    DOCX_SKILL="/mnt/.skills/skills/docx"
elif [ -d "$HOME/.claude/plugins/cache/anthropic-agent-skills/document-skills" ]; then
    DOCX_SKILL=$(find "$HOME/.claude/plugins/cache/anthropic-agent-skills/document-skills" -maxdepth 2 -name "docx" -type d | head -1)
fi

# Detect layout variant
if [ -f "$DOCX_SKILL/scripts/office/unpack.py" ]; then
    UNPACK_SCRIPT="$DOCX_SKILL/scripts/office/unpack.py"
    PACK_SCRIPT="$DOCX_SKILL/scripts/office/pack.py"
    COMMENT_SCRIPT="$DOCX_SKILL/scripts/comment.py"
elif [ -f "$DOCX_SKILL/ooxml/scripts/unpack.py" ]; then
    UNPACK_SCRIPT="$DOCX_SKILL/ooxml/scripts/unpack.py"
    PACK_SCRIPT="$DOCX_SKILL/ooxml/scripts/pack.py"
    COMMENT_SCRIPT=""  # Uses Document API instead
fi
```

Also update the "read the docx skill" instruction: "Read `SKILL.md` from the docx skill directory. If `ooxml.md` exists as a separate file, read it too; otherwise the OOXML XML reference is embedded in `SKILL.md`."

- [ ] Add docx plugin path discovery block to SKILL.md Step 0
- [ ] Update SKILL.md to handle both plugin layouts for unpack/pack/comment paths
- [ ] Update "read the docx skill" instructions to check for `ooxml.md` existence
- [ ] Pass discovered paths to apply_edits.py via CLI args

---

## Issue 3: Python venv creation fails on read-only filesystem

**Symptom:** `uv venv ~/.claude/skills/jetredline/.venv` fails with `Read-only file system (os error 30)`.

**Root cause:** In Cowork, the skill directory is mounted read-only. The venv path is inside that directory.

**Workaround used:** Attempted system-wide pip install; `textstat` was missing. Readability metrics were skipped.

**Suggested fix:** Add a Cowork fallback to the venv setup:

```bash
VENV_DIR=~/.claude/skills/jetredline/.venv
if ! mkdir -p "$VENV_DIR" 2>/dev/null; then
    # Read-only skill dir (Cowork) — use session-local venv
    VENV_DIR=/tmp/jetredline-venv
    if [ ! -d "$VENV_DIR" ]; then
        python3 -m venv "$VENV_DIR"
        "$VENV_DIR/bin/pip" install defusedxml pikepdf textstat -q
    fi
fi
VENV_PYTHON="$VENV_DIR/bin/python"
```

Alternative: `pip install defusedxml pikepdf textstat --break-system-packages -q` as a one-liner fallback when the venv can't be created.

- [ ] Add read-only filesystem detection to venv setup in SKILL.md
- [ ] Add fallback venv path (`/tmp/jetredline-venv` or session dir)
- [ ] Alternatively, add `--break-system-packages` pip fallback for Cowork

---

## Issue 4: `jetcite_tool.py` missing `httpx[socks]` dependency

**Symptom:** First failure: `ModuleNotFoundError: No module named 'httpx'`. After installing httpx, second failure: `ImportError: Using SOCKS proxy, but the 'socksio' package is not installed`.

**Root cause:** Cowork routes network traffic through a SOCKS proxy. The `httpx` package needs the `[socks]` extra to handle this. The jetcite skill's dependencies don't include `httpx[socks]`.

**Workaround used:** `pip install "httpx[socks]" --break-system-packages`.

**Suggested fix:**
1. Add `httpx[socks]` to the skill's requirements (or `requirements.txt`)
2. Make the ndcourts URL resolution gracefully degrade when network fails — the citation scan (regex + URL generation) doesn't need network; only the ndcourts redirect resolution does
3. Add `socksio` to the dependency list explicitly

- [ ] Add `httpx[socks]` (or `httpx` + `socksio`) to jetcite dependencies
- [ ] Make `resolve_nd_opinion_url()` in `ndcourts.py` catch network errors and fall back to search URL pattern
- [ ] Add `requirements.txt` to jetcite skill if not present

---

## Issue 5: XML entity mismatches cause edit failures in `apply_edits.py`

**Symptom:** 3 of 13 tracked-change edits failed on first pass. Edit JSON contained Python Unicode strings (`'`, `¶`, `\xa0`) but the XML contained entity-encoded equivalents (`&#x2019;`, literal `¶` + `\xa0`, nested `&#x201C;...&#x2018;...&#x2019;...&#x201D;`).

**Specific failures:**
1. Smart apostrophe in possessive: `§ 75-02-13-02(5)'s` — XML has `&#x2019;s`
2. Paragraph symbol + non-breaking space: `¶ 35` — XML has `¶\xa0` (U+00B6 + U+00A0)
3. Nested smart quotes: `"not a 'form.'"` — XML has `&#x201C;not a &#x2018;form.&#x2019;&#x201D;`

**Root cause clarification:** This is *not* an XML parsing issue. minidom correctly decodes entities when parsing. The problem occurs when the edit JSON `old` text and the extracted `w:t` text are both Unicode but use different Unicode characters for the "same" glyph — e.g., regular space (U+0020) vs. non-breaking space (U+00A0), or when Claude generates the edit JSON from reading raw XML and carries through entity notation.

**Suggested fix:** Normalize both sides to NFC Unicode before searching, but operate on the original text for the actual XML manipulation. Key: normalize only for *match finding*, not for the content that gets written.

```python
import unicodedata

def _normalize_for_search(text):
    """Normalize text for fuzzy matching — NFC + NBSP→space."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\xa0", " ")  # NBSP → space
    return text
```

Apply to both `old_text` from the edit JSON and `full_text` from concatenated runs in `find_paragraph_containing()` and the run-matching loop. Once the match position is found in normalized space, map back to the un-normalized run offsets (same approach as `nd_cite_check.py`).

**Risk:** Over-normalizing could cause false-positive matches. NBSP→space is the main concern — if a document intentionally uses NBSP for formatting (e.g., between `¶` and a number), collapsing it could match the wrong location. Mitigation: only normalize for searching; preserve original characters in the output.

- [ ] Add Unicode normalization layer to text search in `apply_edits.py`
- [ ] Normalize both edit JSON text and extracted run text before matching
- [ ] Build offset mapping between normalized and original text for correct run splitting
- [ ] Handle NBSP variants (`\xa0`, `\u202f`) with care — normalize for search only
- [ ] Consider sharing normalization code between `apply_edits.py` and `nd_cite_check.py`

---

## Issue 6: Temp directory permissions in Cowork

**Symptom:** `PermissionError: [Errno 13] Permission denied: '.../unpacked/word/comments.xml'` when writing to the unpacked directory.

**Root cause:** Temp directory was created inside `/mnt/...` (the mounted workspace), which has restricted write permissions in Cowork's sandbox. The unpack script could create files there, but subsequent modification of those files was blocked.

**Workaround used:** Re-unpacked to `/sessions/` (the VM's own writable filesystem).

**Suggested fix:** In SKILL.md Step 0, detect Cowork and create temp dir under `/tmp/` rather than `$(pwd)`:

```bash
# Use /tmp for temp files if cwd is under a restricted mount
if [[ "$(pwd)" == /mnt/* ]]; then
    TMPBASE="/tmp"
else
    TMPBASE="$(pwd)"
fi
```

This is independent of the apply_edits.py refactor — it's a SKILL.md instruction change only.

- [ ] Update SKILL.md Step 0 temp-dir logic to use `/tmp/` when cwd is under `/mnt/`

---

## Issue 7: `ooxml.md` not found at expected path

**Symptom:** Read tool returned "File does not exist" for `ooxml.md` in the docx skill directory.

**Root cause:** The Cowork docx plugin embeds the XML reference in `SKILL.md` rather than providing a separate `ooxml.md` file.

**Workaround used:** Read further into `SKILL.md` and found the XML Reference section there.

**Suggested fix:** Update jetredline SKILL.md instruction from "Read `SKILL.md` and `ooxml.md`" to "Read `SKILL.md` from the docx skill directory. If `ooxml.md` exists as a separate file, read it too."

- [ ] Update SKILL.md Step 1 to conditionally read `ooxml.md`

---

## Issue 8: Citation hyperlinks not applied to .docx output

**Symptom:** User requested every citation be a clickable hyperlink. The `jetcite` scan produced URLs for all citations, but no mechanism exists in the edit pipeline to convert citation text into OOXML hyperlinks.

**Root cause:** `apply_edits.py`'s JSON schema supports `"type": "replace"` and `"type": "comment"` but not hyperlinks. OOXML hyperlinks require: (a) adding a `<Relationship>` entry to `word/_rels/document.xml.rels`, and (b) wrapping the citation text in `<w:hyperlink r:id="rIdN">` in `document.xml`.

**Suggested fix:** Add a `"type": "hyperlink"` edit type to the JSON schema:

```json
{
    "type": "hyperlink",
    "para": 5,
    "anchor": "454 N.W.2d 732",
    "url": "https://www.courtlistener.com/c/N.W.%202d/454/732/",
    "display": "454 N.W.2d 732"
}
```

The script would:
1. Find the anchor text in the paragraph
2. Generate a unique relationship ID
3. Add a `<Relationship>` entry to `document.xml.rels`
4. Wrap the matched text in `<w:hyperlink r:id="rIdN"><w:r><w:rPr><w:rStyle w:val="Hyperlink"/></w:rPr><w:t>display text</w:t></w:r></w:hyperlink>`

This integrates naturally with the `jetcite` scan output — the main-context workflow would run `jetcite scan`, collect the URLs, and generate hyperlink entries in the edits JSON alongside tracked changes and comments.

- [ ] Add `"type": "hyperlink"` to `apply_edits.py` JSON schema
- [ ] Implement relationship-ID generation and `document.xml.rels` updates
- [ ] Implement `<w:hyperlink>` wrapping in `document.xml`
- [ ] Integrate with `jetcite` scan output in the main workflow
- [ ] Test hyperlink rendering in Word, LibreOffice, and Google Docs

---

## Issue 9: Readability metrics skipped

**Symptom:** `readability_metrics.py` was not run because `textstat` wasn't available and the venv couldn't be created (Issue 3).

**Root cause:** Cascading failure from Issue 3.

**Suggested fix:** Resolving Issue 3 resolves this. Additionally, `readability_metrics.py` could catch `ImportError` for `textstat` and fall back to basic sentence-length and passive-voice metrics using only the standard library (regex-based).

- [ ] Add `textstat` ImportError fallback in `readability_metrics.py`
- [ ] Implement basic sentence-length and passive-voice regex metrics as fallback

---

## Issue 10: Citation review HTML (`cite_review.py`) skipped

**Symptom:** The interactive citation review HTML was not generated.

**Root cause:** Session focused on getting the core redline done; the `cite_review.py` step was deprioritized. Also depends on the opinion being available as markdown, which requires an additional conversion step for the dissent.

**Suggested fix:** Lower priority, but the workflow should attempt it after the main outputs are produced. Add to SKILL.md Step 11: "If cite_review.py fails or is skipped, note this in the analysis document."

- [ ] Ensure `cite_review.py` is attempted after main outputs
- [ ] Add graceful degradation note to SKILL.md if it fails

---

## Issue 11: `nd_cite_check.py` imports symbols not yet in installed `jetcite`

**Symptom:** `cite_review.py` crashes with `ImportError: cannot import name '_ND_REPORTERS' from 'jetcite.cache'`. This also blocks any tool that imports `nd_cite_check` at the module level.

**Root cause:** `nd_cite_check.py` line 50 does `from jetcite.cache import _ND_REPORTERS, _FEDERAL_REPORTERS`. These symbols are defined in the TODO plan (Step 1 of the refs cache restructure above) but have not been added to the installed `jetcite` package. The code was updated to use the planned API before the package was updated.

**Cascade:** `cite_review.py` imports `from nd_cite_check import scan_opinion` at line 85, triggering the same `ImportError`. This means the citation review HTML cannot be generated in any environment.

**Discovered:** 2026-03-19, *Marschner v. Marschner* session. The Pass 3B citation subagent worked around this by calling `nd_cite_check.py` as a subprocess (which catches the error differently), but `cite_review.py` failed outright.

**Fix options (pick one):**

1. **Add the symbols to `jetcite.cache` now.** Implement the `_ND_REPORTERS` and `_FEDERAL_REPORTERS` sets as defined in Step 1 above and release an updated `jetcite` package. This is the correct long-term fix but requires the full refs cache restructure to be useful.

2. **Guard the import in `nd_cite_check.py`.** Make the import conditional so the module loads even when the symbols don't exist:
   ```python
   try:
       from jetcite.cache import _ND_REPORTERS, _FEDERAL_REPORTERS
   except ImportError:
       _ND_REPORTERS = {"N.W.", "N.W.2d", "N.D."}
       _FEDERAL_REPORTERS = {
           "U.S.", "S. Ct.", "L. Ed.", "L. Ed. 2d",
           "F.", "F.2d", "F.3d", "F.4th",
           "F. Supp.", "F. Supp. 2d", "F. Supp. 3d",
           "B.R.", "F.R.D.", "Fed. Cl.", "M.J.",
           "Vet. App.", "T.C.", "F. App'x",
       }
   ```
   Quick fix. Duplicates the constants but unblocks both `nd_cite_check.py` and `cite_review.py` immediately.

3. **Define the constants locally in `nd_cite_check.py`.** Move them out of `jetcite.cache` entirely until the cache restructure is complete. Remove the import line.

**Recommendation:** Option 2 (guarded import) as an immediate fix, then Option 1 when the cache restructure lands.

- [ ] Fix `nd_cite_check.py` import of `_ND_REPORTERS` / `_FEDERAL_REPORTERS` (guard or define locally)
- [ ] Verify `cite_review.py` loads successfully after the fix
- [ ] Add the constants to `jetcite.cache` when the refs cache restructure is implemented

---

## Issue 12: Unpack/pack pipeline produces .docx files Word cannot open

**Symptom:** Word for Mac refuses to open .docx files produced by the `apply_edits.py` → `ooxml_fixup.py` → `pack.py` pipeline. The error is either a hard failure ("Word experienced an error trying to open the file") or a repair dialog that itself fails. LibreOffice, python-docx, and the skill's own `ooxml_validate.py` all report the files as valid.

**Discovered:** 2026-03-19, *Marschner v. Marschner* session (Claude Code on macOS). The apply_edits.py pipeline reported all 19 edits applied, fixup found 0 issues, validation passed. Word refused to open the file.

**Root cause (confirmed by bisection):**

The unpack/pack round-trip re-serializes all XML files through Python's minidom, which changes the encoding and formatting in ways Word rejects:

1. **Encoding change.** The original .docx XML files declare `encoding="UTF-8"` and contain raw UTF-8 bytes for characters like smart quotes (U+2019 → 3-byte sequence `0xe2 0x80 0x99`). The unpack script reads these, and the pack script (or `apply_edits.py` via `dom.toxml(encoding="ascii")`) re-serializes as `encoding="ascii"` with entity-encoded non-ASCII characters (`&#8217;`). While technically valid XML, Word for Mac rejects the encoding change.

2. **Standalone declaration dropped.** The original has `standalone="yes"` in the XML declaration; minidom's `toxml()` omits it.

3. **Whitespace reformatting.** The unpack script pretty-prints the XML (adding indentation and newlines). The original document.xml is 40,004 bytes; the unpacked/repacked version is ~60,000 bytes with identical content. While OOXML is supposed to be whitespace-insensitive between elements, Word may be sensitive to whitespace changes in certain contexts.

4. **ZIP metadata.** Python's `zipfile` module creates entries with `create_system=3` (Unix) and `external_attr=0x81a40000` (Unix file permissions). The original has `create_system=0` (MS-DOS) and `external_attr=0`. This alone doesn't cause the hard failure (confirmed: repacking the original byte-identical XML with Unix ZIP attrs still opens), but it may contribute to the repair dialog.

**Bisection results:**

| Test | Result |
|------|--------|
| Byte-for-byte copy of original .docx | Opens |
| Original XML round-tripped through minidom with `encoding="UTF-8"` + `standalone="yes"` | Opens |
| Original XML round-tripped through minidom with `encoding="ascii"` | Fails |
| apply_edits.py output (through unpack pipeline, ASCII encoding) | Fails |
| Direct minidom edits on original XML, serialized as UTF-8, ZIP entries copied from original | Opens with all tracked changes and comments |

**Workaround used (Marschner session):**

Wrote a standalone `build_redline.py` script that:
1. Extracts `document.xml` directly from the original .docx ZIP (no unpack reformatting)
2. Parses with minidom and applies tracked changes + comment markers via DOM manipulation
3. Serializes back with `dom.toxml(encoding="UTF-8")` and restores `standalone="yes"`
4. Builds comments.xml, people.xml, Content_Types.xml, and document.xml.rels from scratch
5. Constructs the output ZIP by copying all original entries byte-for-byte and replacing/adding only the modified files, preserving the original ZIP entry metadata (`create_system=0`, `external_attr=0`)

This bypasses the entire unpack/apply_edits/ooxml_fixup/pack pipeline.

**Proper fix — two options:**

### Option A: Fix the serialization in apply_edits.py (recommended)

Modify `apply_edits.py` to work directly on the original ZIP rather than requiring an unpacked directory:

```python
# Instead of:
#   apply_edits.py --input <unpacked_dir> --edits edits.json --output out.docx --pack-script pack.py
# Change to:
#   apply_edits.py --input original.docx --edits edits.json --output out.docx

# Internally:
# 1. Extract document.xml from the ZIP (raw bytes, no reformatting)
# 2. Parse with minidom
# 3. Apply edits via DOM manipulation
# 4. Serialize with dom.toxml(encoding="UTF-8"), restore standalone="yes"
# 5. Build comment XML files from scratch (no dependency on docx plugin)
# 6. Copy all original ZIP entries, replacing/adding only changed files
# 7. Preserve original ZIP entry metadata (create_system, external_attr, etc.)
```

This eliminates the dependency on unpack.py, pack.py, ooxml_fixup.py, and the docx plugin entirely. The script becomes fully self-contained.

**Key serialization rules:**
- Always use `dom.toxml(encoding="UTF-8")` — never `encoding="ascii"`
- Restore `standalone="yes"` in the XML declaration after serialization
- When building the output ZIP, copy `ZipInfo` objects from the original for replaced files (preserves `create_system`, `create_version`, `extract_version`, `flag_bits`, `external_attr`)
- For new files (comments.xml, people.xml), use `create_system=0`, `create_version=45`, `extract_version=20`, `external_attr=0` to match Windows-originated entries

### Option B: Fix the unpack/pack pipeline

Make the pipeline preserve original encoding:
1. `unpack.py`: Store the original XML declaration and encoding for each file
2. `apply_edits.py`: Serialize using the stored encoding
3. `pack.py`: Preserve original ZIP entry metadata

This is more work and still requires the docx plugin dependency. Option A is simpler and more robust.

### Changes to SKILL.md

Under either option, update the Step 9 workflow to skip the unpack step:

```bash
# Old workflow (broken):
# 1. Unpack: unpack.py original.docx unpacked/
# 2. Edit:   apply_edits.py --input unpacked/ --edits edits.json
# 3. Fixup:  ooxml_fixup.py unpacked/
# 4. Pack:   pack.py unpacked/ output.docx

# New workflow:
# 1. Edit:   apply_edits.py --input original.docx --edits edits.json --output output.docx
```

- [ ] Rewrite `apply_edits.py` to accept .docx input directly (no unpack required)
- [ ] Serialize all XML as UTF-8 with `standalone="yes"`
- [ ] Copy ZIP entries from original, preserving metadata
- [ ] Build comment infrastructure (comments.xml, people.xml, Content_Types, rels) internally
- [ ] Remove dependency on unpack.py, pack.py, ooxml_fixup.py, and docx plugin
- [ ] Update SKILL.md Step 9 workflow
- [ ] Test with Word for Mac, Word for Windows, and LibreOffice

---

## Summary: Priority order for implementation

### Phase 1 — Fix .docx output (Issues 1, 2, 5, 6, 12)

Make `apply_edits.py` produce valid .docx files in all environments.

**1a. Rewrite apply_edits.py to work directly on .docx input** (Issue 12): This is the top priority — the current pipeline produces files Word cannot open. The rewrite eliminates the unpack/pack pipeline entirely, operates directly on the original ZIP, serializes as UTF-8, and preserves original ZIP metadata. This also resolves Issue 1 (no dependency on `scripts.document`) and Issue 2 (no dependency on docx plugin paths). See Issue 12 for the full design.

**1b. Unicode normalization for text matching** (Issue 5): Normalize both edit JSON and extracted run text to NFC before searching. Low-risk, high-impact — directly fixes 3/13 edit failures from the Ferderer session.

**1c. SKILL.md environment detection** (Issues 2, 6, 7): Path discovery block in Step 0 that detects docx plugin layout for unpack (still needed for reading existing .docx content), chooses temp directory, handles venv fallback. The pack-side paths are no longer needed after 1a.

### Phase 2 — Dependency and feature improvements

2. **Medium — Hyperlink support** (Issue 8): Add `"type": "hyperlink"` to edit schema. New feature; integrates with jetcite.
3. **Medium — jetcite dependency fix** (Issue 4): Add `httpx[socks]` and graceful network fallback.
4. **Low — Readability fallback** (Issue 9): Standard-library fallback for `textstat`.
5. **Low — cite_review.py robustness** (Issue 10): Graceful degradation.

### Immediate — Unblock citation pipeline (Issue 11)

**0. Fix `nd_cite_check.py` import** (Issue 11): Guard the `from jetcite.cache import _ND_REPORTERS, _FEDERAL_REPORTERS` import with a try/except fallback defining the constants locally. This is a one-line fix that unblocks both `nd_cite_check.py` and `cite_review.py`. Do this before anything else — it's broken right now in the deployed skill.

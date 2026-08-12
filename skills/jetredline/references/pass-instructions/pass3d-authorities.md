# Pass 3D: Supplied Authorities — Subagent Instructions

You are a jetredline subagent. The caller's prompt supplies: the draft opinion markdown path, the case directory holding the supplied PDFs, a TMPDIR path, the skill root (written as `<SKILL_ROOT>` below), and the venv python path (written as `<VENV_PYTHON>` below; if omitted, use `python3`).

A *supplied authority* is a source the draft relies on that the citation parser cannot recognize — a convention journal, an official report of debates, a treatise, a periodical in an obsolete abbreviation, an archival document, a historical constitution, an out-of-jurisdiction slip opinion — for which a PDF copy sits in the case directory. Pass 3 never sees these; your job is to connect each reference in the draft to its PDF, extract and verify the cited pages, and report what could not be connected.

Return **only** the results table, tallies, and findings specified in Step 7. Also Write `<TMPDIR>/authorities.json` (Step 6) — the citation-review page renders it — and place page extracts in `<case-dir>/authorities/`.

## Shell command hygiene

Permission allowlists match a command's **first token**; keep every Bash call matchable:

- **Never `cd`.** Pass absolute paths instead.
- **Never prefix a command with variable assignments** (`TMPDIR=… cmd`). Put the value in the argument directly.
- **Invoke the venv python by the literal absolute path the caller gave you.**
- **Prefer the shipped helpers to throwaway scripts** — `authorities.py`, `pdfsource.py`, `pdf_page_grep.py` cover this pass; a one-off `.py` in a temp dir yields an unmatchable command every time.
- **Write absolute paths in full and quote any containing spaces.** `~` and `$HOME` are not expanded when matching.

## Step 1: Inventory the supplied PDFs

```bash
<VENV_PYTHON> "<SKILL_ROOT>/authorities.py" inventory <case_dir> --manifest <manifest.json path, if one exists> --json
```

This walks the case directory and identifies candidate authority PDFs from metadata and opening pages, skipping what other passes own (manifest briefs, record items, packets over 200 MB, and `authorities/` — this pass's own extracts). **Filenames lie and metadata sometimes does too** — treat the reported titles as evidence, not identity; Step 4's page check is what actually disambiguates.

## Step 2: Collect candidate spans from the draft

First generate the cite JSON so spans jetcite already claimed are excluded (no `--cache` — this run only needs span positions, not fetched sources):

```bash
<VENV_PYTHON> "<SKILL_ROOT>/cite_check.py" --file <draft.md> > <TMPDIR>/cites.json
<VENV_PYTHON> "<SKILL_ROOT>/authorities.py" candidates <draft.md> --cites <TMPDIR>/cites.json --json
```

The output is a **pre-filter, not a recognizer**: short spans that look like authority references and that jetcite did not claim. It deliberately over-collects (recall over precision) — you discard false positives cheaply, but a reference it never surfaced is unrecoverable, so also stay alert while reading context in Step 3 for references the patterns missed (e.g. a work introduced by prose alone: "the Journal records that…").

## Step 3: Build structured reference records (your judgment step)

Read the draft paragraph around each candidate span and decide: is this a reference to an external work?

**Discard:** case citations jetcite already handles, ordinary prose or headings that pattern-matched, references to the record or the parties' briefs (Passes 4 and 6 own those), and duplicates of the same span.

**Keep one record per citing occurrence** — a work cited on two pages for two propositions yields two records sharing a title (the review page groups them under one header). For each, emit:

```json
{ "title": "<the work's title, as completely as the draft and context allow>",
  "short": "<sidebar label, e.g. 'Official Report 1522'>",
  "kind": "journal|treatise|periodical|constitution|statute|archival|slip-op|other",
  "author": "<author(s), if stated>",
  "volume": "<volume, if stated>",
  "year": "<publication year, if stated>",
  "printed_page": 1522,
  "para": "<draft ¶ ref>",
  "draft_quote": "<10–20 word span copied VERBATIM from the draft>",
  "proposition": "<what the draft cites this work for>" }
```

- `printed_page` is the page number *as cited in the draft* (the printed folio, not a PDF page). Integer; omit when the draft cites no page. It is what Step 4 uses to disambiguate between volumes of a set — include it whenever the draft gives one.
- `draft_quote` must appear in the draft **exactly** — it anchors and highlights the entry in the draft pane (same mechanism as Pass 4). Never paraphrase, never normalize quotes or dashes.
- `title` drives the match score: include the words the *reference* uses, not a corrected library-catalogue form.

Write the array to `<TMPDIR>/authority-refs.json`.

## Step 4: Match references to files

```bash
<VENV_PYTHON> "<SKILL_ROOT>/authorities.py" match --refs <TMPDIR>/authority-refs.json --dir <case_dir> --manifest <manifest.json path, if one exists> --json
```

This scores each reference against the inventory and validates the winner against the measured printed↔PDF page offset. On image-only scans the offset measurement OCRs ~10 sampled pages and can take a minute or two per file — that is normal; do not kill it.

Reading the output:
- `matched[]` entries carry `file`, `score`, and when a cited page was checked: `pdf_page` (the printed page's location in that file), `offset`, `offset_confidence`, `page_verified`.
- `page_verified: false` with a `pdf_page` means the offset measurement was too weak to be evidence either way — the title match stands, but say "page unverified" in your table.
- `rejected_candidates[]` records files a *confident* offset excluded ("cannot hold printed page N") — useful in Notes when a filename suggested the wrong volume.
- `unmatched_references[]` and `unmatched_files[]` feed Step 7's findings.

## Step 5: Extract and verify the cited pages

For each matched reference with a cited page, pull the cited range into `<case_dir>/authorities/` (create the directory if needed):

```bash
<VENV_PYTHON> "<SKILL_ROOT>/pdfsource.py" extract <matched file> --pages 1521-1523 --printed --offset <offset from Step 4> --ocr --max-bytes 800000 -o <case_dir>/authorities/<slug>_p1521-1523.pdf --json
```

- Extract the cited page **plus one page each side** when a quoted passage could span a page break; the cited page alone otherwise. Use printed page numbers with `--printed` and pass the `--offset` Step 4 measured (this skips a second slow measurement). If Step 4 produced no offset, run without `--offset` and let extract measure — or, if that fails, skip extraction and point the ledger source at the original file instead.
- `--ocr` routes through the text-quality triage (a dense-but-corrupt layer is force-OCR'd, not skipped); `--max-bytes` compacts while verifying the text layer survives.
- **Verify the passage is actually in the extract** — an extraction that ran without error is not evidence the right page arrived:

```bash
<VENV_PYTHON> "<SKILL_ROOT>/pdf_page_grep.py" "<distinctive phrase>" <case_dir>/authorities/<slug>_p1521-1523.pdf
```

  On OCR'd scans an exact phrase often fails from character damage (`3↔8`, `l↔1`, `rn↔m`, mangled ligatures). Fall back to **proximity of rarer anchors**: search two or three distinctive proper nouns or unusual words that sit near the passage, and accept the page where they co-occur. Record the verbatim passage as OCR rendered it for the `quote` field — the review page fuzzy-matches it to highlight.
- Assess **substantive support**: does the passage support the proposition the draft cites it for? Report Supports / Partially / Does not support, as in Pass 3B.

## Step 6: Write the ledger

Write `<TMPDIR>/authorities.json` — a JSON array, one object per record from Step 3, extended with results:

```json
{ "title": "…", "short": "…", "kind": "…", "author": "…", "volume": "…",
  "year": "…", "para": "…", "draft_quote": "…", "proposition": "…",
  "result": "Verified | Discrepancy | Unverified",
  "note": "<condensed finding, e.g. 'passage on printed 1522; supports'>",
  "via": "supplied",
  "sources": [ { "raw": "<the reference as written in the draft>",
                 "file": "authorities/<slug>_p1521-1523.pdf",
                 "page": 2,
                 "quote": "<short verbatim passage from the source>" } ] }
```

- `sources[].file` is **relative to the case directory** and points at the Step 5 extract (or the original PDF when extraction failed or no page was cited).
- `sources[].page` is the page **within that file** — for an extract of printed 1521–1523 with the passage on 1522, `page` is 2.
- `sources[].quote` is what locates and highlights the evidence inside the embedded viewer; include it whenever you found the passage.
- Unmatched references still get entries — `result: "Unverified"`, an empty `sources` array, and a `note` saying no copy was found. They must appear in the review page, not vanish.

## Step 7: Return results

**Results table**, one row per reference:

| ¶ | Authority | Kind | Cited page | Matched file | Page check | Quote check | Supports? | Notes |
|---|-----------|------|------------|--------------|------------|-------------|-----------|-------|
| [¶] | [short title] | journal / treatise / … | [printed page or —] | [filename or **none found**] | Verified / Unverified / N/A | Verified / Discrepancy / Not found / No quote | Supports / Partially / Does not support / — | [offset, rejected candidates, OCR caveats] |

**Summary line:** [N] references identified ([D] candidate spans discarded as false positives). [M] matched to supplied PDFs, [P] page-verified, [Q] passages verified. [U] references with no supplied copy. [F] supplied PDFs nothing referenced.

**Findings:**
- **Authorities relied on but not located** — one line per unmatched reference: "The draft relies on *[title]* ([¶ ref]) and no copy is in the case directory." This is exactly what chambers wants flagged; never bury it.
- **Supplied but unreferenced PDFs** — before reporting one, Grep the draft for two or three distinctive tokens from its title: an unused file can mean Step 2 missed a reference. If a reference turns up, loop it back through Steps 3–6; otherwise list the file as informational.

## Error handling

- If `authorities.py inventory` finds no candidate PDFs **and** Step 2/3 yield no references, return "No supplied authorities detected" with empty tallies — do not manufacture entries.
- If the offset cannot be measured for a file (`locate` undetermined), match still ran on title evidence — report its matches with "page unverified" and extract by printed range only if a `--printed` extraction succeeds; otherwise reference the original file.
- If `ocrmypdf` or poppler tools are missing, extraction may degrade or fail — fall back to pointing `sources[].file` at the original PDF with the measured `pdf_page`, and say so in Notes.
- Always return partial results. A table with Unverified rows and a written `authorities.json` beats silence; every reference must appear in both.

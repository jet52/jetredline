# Supplied Authorities — design plan

Generalizing ad-hoc work done during a 2026-08 run into a first-class jetredline
capability. The draft in that run relied on a number of historical and secondary
sources supplied as PDFs in the project directory — none of which the citation
pipeline can see.

(Deliberately written without matter-identifying detail; this file is tracked and
pushed. Working notes live in the gitignored `TODO.md`.)

---

## A. The gap

jetredline has two verification lanes and no third:

| Lane | Discovery | Pass | Rendered as |
|---|---|---|---|
| **Citations** | jetcite regex over reporter/code forms | 3A/3B | sidebar entries |
| **Facts** | model extraction of record assertions | 4 | fact panel |

Everything else a draft may lean on is invisible to both: legislative and constitutional
records, treatises, periodicals in obsolete abbreviations, archival documents,
historical primary sources, out-of-jurisdiction slip opinions, unpublished orders,
and legislative history.

When a draft's reasoning rests on that material, "everything else" *is* the argument.
In the originating run those sources carried roughly 40% of the load-bearing claims and
received 0% coverage from the citation pipeline. They were verified only because a
bespoke subagent was hand-written for the purpose — which is not a repeatable process.

`sources.json` already has a `pdf` field, but it is **keyed by citation string**, so it
structurally cannot reach an authority jetcite never extracted. That is the design bug,
not a missing feature.

---

## B. Concept: *supplied authorities*

A third entry class. An authority qualifies when:

1. jetcite produces no citation object for it, **or** produces one with no online/`~/refs`
   source; **and**
2. a copy exists in the working directory, or is retrievable.

**Put them in the same sidebar as citations, as a typed entry — not a separate section.**

The reviewer's task is identical ("does this source say what the draft says it says?"),
the verify/flag/skip state model is identical, and the keybindings are identical. A
separate section is the easiest thing in the world to never open. Instead:

- distinct badge (`supplied`) and `Via` tier (`local-pdf`, `ocr`, `archive.org`);
- a **filter chip row** (`All · Citations · Authorities · Facts`) to isolate them on demand;
- the existing `authpdf` viewer plumbing renders them — it already works.

---

## C. New module: `pdfsource.py`

The reusable engine. Every step below was done by hand this session with one-off shell
commands; that is the leverage. Library functions plus a CLI subcommand each.

| Subcommand | Job |
|---|---|
| `probe` | page count, size, damage, text-layer **presence and quality**, which toolchain can address the file |
| `repair` | normalize a damaged/oversized PDF via the poppler fallback path |
| `locate` | discover the printed-page ↔ PDF-page offset by OCR-probing running heads (binary search); return offset, confidence, and probe evidence |
| `find` | OCR-tolerant passage search |
| `extract` | pull a printed-page range into a small standalone PDF, preserving or creating a text layer |
| `ocr` | the corrected ladder, with a quality gate |
| `compact` | downscale/recompress to a size budget, verifying the text layer survives |

Two pieces matter most.

### C1. Text-layer quality gate

The current detector is **density-only** (`< ~50 chars/page`). It cannot see a text layer
that is dense and *wrong* — a scanned nineteenth-century source in the originating run
extracted a clause reading "shall **Le suberdmate** to the gelleral plall" and cleared every
density threshold by two orders of magnitude. That silently degraded a verification
until it was caught by eye.

Replace with a scorer over extracted tokens: dictionary hit-rate, non-alpha noise ratio,
mean token length, presence of expected legal stopwords. Emit three states, not two:

- `text-ok`
- `no-text-layer` → `ocrmypdf --skip-text` is correct
- `text-layer-corrupt` → **`--force-ocr` is required**

### C2. OCR-tolerant search

Keyword search failed outright on a scanned volume retrieved from the Internet Archive:
the section heading being searched for had been OCR'd into an unrecognizable string
(a five-word heading came back as an unreadable jumble), so every literal query
missed. What worked was proximity search on two rarer proper nouns that happened to OCR
cleanly nearby.

`find` should therefore: normalize aggressively (case, ligatures, common OCR confusions
`3↔8`, `l↔1`, `rn↔m`), then fuzzy/n-gram match, then fall back to proximity-of-anchors,
returning a confidence score with each hit.

---

## D. New pass: **3D — Authority Resolution**

Runs after 3A/3B. Delegated to a subagent — it reads PDFs, which must stay out of main
context. Two-sided discovery, then a match.

### Side 1 — references in the draft

Deterministic pre-filter first, to cut model tokens and raise recall:

- italic runs recovered from the `.docx` (already extracted — 144 spans in this draft);
- `supra` / `hereinafter` / `id.` chains;
- Title-Case spans followed by `(YYYY)`;
- small caps; footnote-only text;
- **any span jetcite did not claim**.

Then a model pass converts candidate spans into structured records:

```json
{ "kind": "journal|treatise|periodical|constitution|archival|slip-op|other",
  "title": "...", "author": "...", "volume": "2",
  "printed_pages": [814], "year": 1902, "draft_paras": [17] }
```

This is genuinely non-mechanical recognition — hence a model task — but the pre-filter
means the model sees candidate spans rather than the whole draft, and the output is
schema-constrained.

### Side 2 — PDFs on disk

Inventory every PDF in the working directory recursively, excluding files already
classified as briefs or record items. For each: `probe`, then identify from PDF metadata
(`Title`/`Subject`/`Keywords`, which on scanned historical material frequently names the
work outright) plus OCR of pages 1–3 and the running heads.

### Match

Fuzzy bipartite match scored on title / author / year / volume, **with the requested
printed-page range checked against the file's `locate` offset**. A file that cannot
contain the cited printed page is not a match.

That check earns its keep. In the originating run, three files of a multi-volume scanned
set were named `-1`, `-2`, `-3` and their names were simply wrong about which volume each
held: measured printed-page offsets were 628, 1145, and 633, so the cited page was not in
the file its name implied — and one cited page was in none of them. Matching on title
alone would have confidently embedded the wrong volume.

Emit `authorities.json` with three buckets:

- `matched` — reference + file + page range + extraction plan
- `unmatched-reference` — **a finding in its own right**: "the draft relies on X and no
  copy is in the working directory" is exactly what chambers wants flagged
- `unmatched-file` — a PDF nobody cites; usually noise, occasionally a missed authority

Optional, behind a flag (network step): attempt retrieval of unmatched references via
Internet Archive full-text search, HathiTrust, or Google Books.

---

## E. `cite_review.py` changes

- Accept `--authorities-json`.
- New sidebar entry type, `supplied` badge, filter chips.
- New source mode `suppliedpdf` (reuses `authpdf` plumbing).
- **Asset pool with dedupe** — one extraction per `(file, page-range)`, content-hashed and
  shared across entries. Two authorities citing the same volume must not embed it twice.
- **Sidecar budget** — `--asset-budget` (default ~25 MB). Over budget: progressively
  downscale, then fall back to `--link-pdfs` for the largest assets, and **report what it
  did**. Never silently truncate.
- Page-range extraction stays the default. Embedding a 126 MB *Official Report* is never
  correct; base64 inflates it another third.

---

## F. Bugs found this run — worth fixing regardless of the rest

1. **`ocrmypdf --skip-text` is a silent no-op on a corrupt text layer.** SKILL.md's OCR
   ladder recommends it. Court e-filing scans and Google/Acrobat "Paper Capture" scans
   routinely carry dense-but-garbage layers. **Highest severity — it yields unverified
   text that looks verified.**
2. **`_resolve_fact_source` record-item regex** is `^R\.?\s*(\d+)$`, but Pass 4 ledgers
   emit bare `"785"`. Accept bare digits when `raw` begins with `R`, or normalize on load.
   Cost 27 unresolved references in this run.
3. **`--case-manifest` is not auto-discovered** when `manifest.json` sits in a `briefs/`
   subdirectory — which is where jetmemo's downloader puts it. Search one level down.
4. **`splitmarks --check-text`** shares bug 1's blind spot (density only). Route it
   through the C1 scorer.
5. **PDFs over 2 GB / damaged**: pypdf and qpdf both fail on 32-bit xref offset overflow;
   poppler reads them fine. The packet-splitting path needs a poppler fallback
   (`pdfseparate` + `pdfunite`) and should report the degradation rather than dying.

---

## G. Documentation changes

- `SKILL.md`: new Pass 3D section; corrected OCR ladder with the quality gate;
  `pdfsource.py` added to the resource table.
- New `references/pass-instructions/pass3d-authorities.md`.
- Pass 4 instructions: emit `R`-prefixed `item` values.
- Analysis-document template: new **Supplied Authorities** table, plus an
  "authorities relied on but not located" checklist.

---

## H. Phasing

| Phase | Content | Value |
|---|---|---|
| **1** ✅ | Bugs F1–F5 + the C1 quality scorer | **Shipped in 4.17.0.** Removes a silent-corruption risk from every existing run. |
| **2** | `pdfsource.py` (probe/ocr/locate/extract/compact) | Usable standalone immediately; ends the one-off shell commands. |
| **3** | Pass 3D discovery + matching → `authorities.json`; cite_review rendering, filter chips, asset pool | The feature proper. |
| **4** | Retrieval of unmatched references; analysis-doc section | Optional polish. |

Phase 1 is worth doing on its own even if nothing else ships.

---

---

## Phase 1 — shipped in 4.17.0

| Item | Where |
|---|---|
| C1 quality scorer | new `skills/jetredline/textquality.py` (library + CLI), 15 tests |
| F1 OCR ladder | `SKILL.md` — three-state detection, `--force-ocr` for corrupt layers, re-score after OCR |
| F2 record-item resolution | `cite_review.py` `_resolve_fact_source` — accepts bare digits corroborated by `raw`; `pass4-factcheck.md` now specifies the `R` prefix |
| F3 manifest discovery | `cite_review.py` `_candidate_manifests` — searches one level down, conventional names first |
| F4 splitmarks gate | upstream `splitmarks` 2.2.0, optional `textquality` import, re-vendored |
| F5 poppler fallback | `SKILL.md` — `pdfseparate`/`pdfunite` path plus Ghostscript compression, with the naming rule for `--record-dir` |

**Calibration.** Thresholds were measured, not guessed. Corruption scores across
the reference corpus:

| Sample | corruption |
|---|---|
| 19th-c. document, Acrobat "Paper Capture" layer | **0.414** |
| same file after `--force-ocr` | 0.016 |
| 19th-c. book scan (clean) | 0.020 |
| appellate brief (born-digital) | 0.021 |
| appellate brief (OCR-recovered) | 0.025 |
| law review PDF | 0.025 |
| 1890s periodical scan | 0.008 |

Cutoff 0.10 — roughly 4x headroom on both sides. Stopword rate was tried and
**rejected**: the born-digital brief scored 0.298 against the corrupt scan's
0.380, i.e. backwards, because short function words survive the OCR damage that
destroys everything else.

**Regression.** Rebuilding the originating review with its original unmodified
Pass 4 ledger and no manual flags: manifest auto-discovered from `briefs/`, and
unresolved fact sources fell from **37 to 2** (the two being a case citation and
a statute, correctly text-only). The corrupt scan is now flagged despite yielding
5,390 characters per page — a density check calls that healthy.

---

## I. Risks and limits

- **False positives in model extraction** — a quoted phrase mistaken for a title. Bounded
  by the schema and by requiring corroboration from a file on disk before an entry is
  rendered as an authority.
- **Unmatched references must be reported as "not located," never "does not exist."**
- **`locate` confidence must be surfaced.** An OCR-probed page offset is an inference; a
  wrong offset silently points the reviewer at the wrong page, which is worse than no
  viewer at all. Below a confidence threshold, degrade to whole-file embedding with a
  page hint, and say so.
- **Network retrieval is optional and must never block a run.**

# Supplied Authorities — handoff

**State as of 2026-08-12.** Written so a fresh session can finish the feature
without rediscovering what has already been learned the hard way.

Design rationale lives in `supplied-authorities-design.md`; this file is the
current state, the remaining work, and the traps. Written without
matter-identifying detail — it is tracked and pushed. Working notes for the
originating matter are in the gitignored `TODO.md`.

---

## 1. What the feature is

A draft may rely on sources the citation parser cannot recognize: convention
journals, official reports of debates, treatises, periodicals in obsolete
abbreviations, archival documents, historical constitutions, out-of-jurisdiction
slip opinions. Copies of those sit in the project directory as PDFs.

jetredline had two verification lanes — citations (jetcite → Pass 3) and facts
(Pass 4) — and no third, so this material was invisible to every pass. In the
originating run it carried roughly 40% of the load-bearing claims and was
verified only because a bespoke subagent was hand-written for it.

`sources.json` has a `pdf` field, but it is **keyed by citation string**, so it
structurally cannot reach an authority jetcite never extracted. That is the
design bug the feature exists to fix.

---

## 2. What is done

Seven commits, `9c62e18..4125cd4`. **334 tests pass** (`make test`).

### Shipped in 4.17.0 — `textquality.py` (15 tests)

Three-state text-layer triage: `text-ok` / `no-text-layer` /
`text-layer-corrupt`, each mapped to the `ocrmypdf` flag it needs.

The prior check was density-only (`<50 chars/page`), which cannot see a layer
that is dense and *wrong*. A scanned source extracted 5,390 chars/page of
confident nonsense and cleared every threshold; because a layer existed,
`--skip-text` skipped all of it and reported success.

Scoring is on impossible letter sequences — internal case flips, vowelless
tokens, 4+ consonant runs — calibrated against a measured corpus (corrupt 0.414
vs 0.008–0.025 clean; cutoff 0.10). **Stopword rate was tried and rejected**: a
born-digital brief scored 0.298 against the corrupt scan's 0.380, i.e.
backwards, because short function words survive the damage that destroys
everything else. Intercapped surnames (McCue, LaMoure) are guarded.

Also in that commit: the `_resolve_fact_source` record-item regex (ledgers store
`item:"785"` with the `R` only in `raw` — cost 27 of 27 resolutions in one run),
`manifest.json` auto-discovery one level down, and the poppler fallback for
>2 GB damaged packets.

### `pdfsource.py` (22 tests)

`probe` / `locate` / `extract` / `compact`, library + CLI.

- **`locate`** measures the printed↔PDF page offset by sampling *adjacent
  pairs* and finding a number whose successor appears on the next page.
- **`extract`** converts printed ranges through the measured offset, falls back
  from qpdf to `pdfseparate`/`pdfunite`, OCRs with the flag `textquality`
  selects, and compacts to a byte budget.
- **`compact`** verifies the text layer survived Ghostscript; a compacted file
  that lost its text cannot anchor a quote, so the original is kept instead.

Verified end to end: printed 1522 → measured offset → PDF page 377 → extract →
OCR → 527 KB, with the expected passage present.

### `cite_review.py` — the rendering lane (104 tests in that file)

`--authorities-json` loads a supplied-authorities ledger and renders entries as
`kind: "authority"` **in the citations sidebar**, not the facts lane. Badge
`supplied`, source mode `suppliedpdf` (embedded PDF leads, since for these the
page *is* the source of truth), plus an authority-detail pane carrying the
proposition cited for.

Lane filter chips (`All · Citations · Authorities · Facts`) hide rows rather
than rebuilding the list — renumbering would invalidate every note keyed to an
index. Group headers hide when nothing under them survives.

`sources[]` deliberately reuses the Pass 4 facts shape
(`raw`/`file`/`item`/`page`/`quote`), so resolution, viewer generation, and
page/quote anchoring run through one code path.

Proven on a real review: ten authorities moved out of the facts lane, two
references to one work correctly collapsing to a single group header.

### `authorities.py` (14 tests)

Pass 3D's deterministic half: `inventory` / `candidates` / `match`.

- **`inventory`** walks the project dir, skips what other passes own (manifest
  briefs, record items, >200 MB packets, and `authorities/` — this pipeline's
  own extracts), identifies the rest from PDF metadata then opening pages.
- **`candidates`** is a *pre-filter, not a recognizer*: it hands a model a short
  list of spans rather than the whole draft. Recall over precision — the model
  discards a false positive cheaply and can never recover a span this never
  surfaces.
- **`match`** scores references against files and weighs the cited printed page
  against `locate`.

Verified on a real directory: 4/4 references matched, including a title that
matches three volumes of one set equally where only the page check disambiguates.

### Also landed

- `jetcite` 2.10.2 — antecedent extraction no longer truncates a case name at a
  comma (`Williamson v. Lee Optical of Okla., Inc.` was rendering as `Inc.`).
  Vendored in.
- Resizable citation sidebar (drag; double-click resets; persisted). Fixed a
  latent bug in the existing draft/source splitter: neither handle suppressed
  pointer events on iframes, so a drag froze when the cursor crossed a PDF.

---

## 3. What is left

> **Update 2026-08-12 (4.18.0):** §3.1–3.3 landed — `pass3d-authorities.md`
> (the subagent runs `cite_check.py` itself, so Pass 3D launches in parallel
> with 3B), SKILL.md wiring (Part D, workflow step 5a, `--authorities-json`
> in Step 11b, the Supplied Authorities analysis section, scope map 3A–D),
> and provenance labels for the usage table.
>
> **End-to-end run (§6 item 2) also done, same day.** A subagent given only
> the delegation prompt produced 19 ledger entries against the originating
> directory versus 10 in the hand-built ledger — all 10 covered, plus the
> missing-treatise finding, three unparseable old case cites, and a negative
> claim ("the source contains no discussion of X") correctly reported as
> unverifiable from an excerpt. It survived the mislabeled-volume trap and
> went further: the volume the draft cites at printed 264 is in *no* supplied
> file (two scans measured as the same middle volume), which the hand pass
> had not noticed. The model overrode three matcher false positives, and the
> pre-filter's misses (two case cites in a parenthetical) were recovered by
> the read-the-context instruction. Ledger loads through `_load_authorities`;
> page renders with all lanes. One nuance: subagents transcribe the draft's
> nonbreaking spaces as plain spaces in `draft_quote` — harmless, because the
> page's `foldQ` normalizes U+00A0 when matching anchors. Cost: ~158k tokens,
> 48 min (dominated by offset OCR on two large scans).
>
> Remaining: the §3.4 optionals.

### 3.1 The model step — the only real gap

`candidates_from_draft()` emits spans. Something must turn them into structured
records and hand them to `match()`. This is the one piece that needs a model
rather than deterministic code, which is why it was left for last.

Write `references/pass-instructions/pass3d-authorities.md`, following the shape
of `pass3b-citations.md`. The subagent should:

1. Run `authorities.py candidates <draft.md> --cites <cites.json> --json`.
2. Convert each span into a record:
   ```json
   { "title": "...", "short": "...", "kind": "journal|treatise|periodical|
     constitution|statute|archival|slip-op|other", "author": "...",
     "volume": "3", "year": "1881", "printed_page": 1522,
     "para": "13", "draft_quote": "<verbatim anchor in the draft>",
     "proposition": "what the draft cites it for" }
   ```
   `draft_quote` must be verbatim — it is how the entry anchors and highlights
   in the draft pane (same mechanism Pass 4 uses).
3. Discard false positives. The pre-filter deliberately over-collects; case
   citations jetcite already claimed will still slip through occasionally.
4. Run `authorities.py match --refs <refs.json> --dir <case-dir> --json`.
5. For each match, `pdfsource.py extract --printed --ocr --max-bytes` the cited
   page range into `authorities/`, and emit the final `authorities.json` with
   `sources[].file` pointing at the extract.
6. Report `unmatched_references` as a finding — "the draft relies on X and no
   copy is in the project directory" is exactly what chambers wants flagged.

### 3.2 Wire it into SKILL.md

Pass 3D does not yet exist in the workflow. Add it after Pass 3A/3B, delegated
(it reads PDFs — keep them out of main context), and add `--authorities-json`
to the Step 11b `cite_review.py` invocation.

### 3.3 Analysis-document section

A **Supplied Authorities** table, and an "authorities relied on but not
located" checklist.

### 3.4 Smaller, optional

- **`pdfsource find`** — OCR-tolerant passage search. Deferred because it is not
  needed to *place* a page, only to confirm a quote once there. Needed:
  normalize aggressively (case, ligatures, `3↔8`, `l↔1`, `rn↔m`), fuzzy/n-gram
  match, then proximity-of-anchors. Keyword search failed outright on one
  archive scan whose OCR mangled a five-word heading beyond recognition; what
  worked was proximity on two rarer proper nouns nearby.
- **Asset pool with dedupe** in `cite_review.py` — one extraction per
  `(file, page-range)`, content-hashed, shared across entries, with a
  `--asset-budget` that degrades to `--link-pdfs` and *reports* what it did.
- **Retrieval** of unmatched references (Internet Archive / HathiTrust /
  Google Books), behind a flag; must never block a run.

---

## 4. Traps — do not rediscover these

**The offset sign is not constrained.** An early version filtered negative
offsets on the theory that front matter makes printed ≥ PDF page. It is the
reverse: unnumbered front matter puts printed page 90 on PDF page 98, an offset
of **−8**. That filter silently discarded four *unanimous* votes. A file holding
only the back half of a set runs **+1145**. Both occur in one directory.

**Filenames lie, and metadata sometimes does too.** Three files of one scanned
set, named `-1`/`-2`/`-3`, measured offsets of 630, 1145 and 633 — the names
were wrong about which volume each held, and one cited page was in none of the
file its name implied. This is why `LocateResult.contains()` exists.

**Page-containment must not be a hard veto.** A 23-page offprint beginning at
printed 922 measured **+16** from a stray footnote sequence (22 on one page, 23
on the next); a hard veto used that to reject the article from its own file. A
veto now requires `VETO_CONFIDENCE`; a weak measurement is *no evidence*, so it
neither promotes nor demotes.

**Single-page voting is too weak on scans.** Most sampled pages of a poorly-OCR'd
volume yield only footnote markers and the year from the running head, so the
one page that surfaces a real folio can never reach a majority — two of three
volumes came back undetermined. Adjacent pairs fixed it: a folio increments with
the PDF page and nothing else does, and a year is constant so it fails the +1
test outright.

**`ocrmypdf --skip-text` is a silent no-op on a corrupt layer.** It exits 0,
writes a file, and changes nothing. Always route the flag through
`textquality`, and *re-score after OCR* — a pass that ran without error is not
evidence that it worked.

**pypdf and qpdf both refuse >2 GB damaged PDFs** (32-bit xref offset overflow);
poppler reads them fine. Every extraction path falls back to poppler.

**Jaccard dilutes filename matches.** A filename carrying author, volume, page
and year tokens the reference never mentions drove a real match to 0.17. Use
coverage-of-the-reference.

**Character similarity without a shared token is noise.** "Journal of the
Constitutional Convention" vs "Federal Taxation" scores ~0.3 on SequenceMatcher
from common letters alone — enough to clear a match threshold.

---

## 5. How to verify

```bash
cd <repo> && make test          # 334 passing

# Against a real project directory:
PY=skills/jetredline/.venv/bin/python
$PY skills/jetredline/textquality.py <dir>/*.pdf
$PY skills/jetredline/pdfsource.py locate <scan>.pdf --printed 1522
$PY skills/jetredline/authorities.py inventory <dir> --manifest <dir>/briefs/manifest.json
$PY skills/jetredline/authorities.py candidates <draft>.md --cites <cites>.json
$PY skills/jetredline/authorities.py match --refs <refs>.json --dir <dir>
```

`locate` on an image-only scan runs OCR on ~10 pages and takes a minute or two;
on a file with a text layer it is fast.

---

## 6. Suggested order for the next session

1. `pass3d-authorities.md` + wire Pass 3D into SKILL.md (§3.1, §3.2) — this is
   what makes the feature automatic rather than hand-fed.
2. Run it end to end on a real case and compare against the hand-built ledger.
3. Analysis-document section (§3.3).
4. `pdfsource find`, asset pool, retrieval (§3.4) as appetite allows.

Version is 4.17.0; bump on the next release-worthy change and keep
`VERSION` / `plugin.json` / `SKILL.md` in sync (`make version-check`).

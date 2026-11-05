# Step 11: Citation Review Page — ndlaw export + `cite_review.py`

SKILL.md Step 11 carries the two commands and the rules that bite on every run. This file holds the full procedure: backend selection, the scribe-subagent fallback, what each flag does and when to omit it, the sidecar/bundle mechanics, review-state resumption, local-PDF authorities, and what the finished page contains. `$SKILL_DIR` and `$VENV_PYTHON` are the literal paths captured in SKILL.md's Environment Setup.

## 11a. Refresh ND authority text + direct URLs from ndlaw (zero token cost)

Run the export script first — it pulls each cited ND opinion's authoritative text and the court's direct opinion URL (`https://www.ndcourts.gov/supreme-court/opinions/<id>`) from the ndlaw corpus into `~/refs`, plus a metadata map for the review page. It auto-selects a backend: a local `opinions.db` (`NDLAW_DB` env or the default dev path), else a deployed ndlaw instance named by `NDLAW_URL` + `NDLAW_AUTH` env (or `--url`/`--auth`), else **the public server at `https://ndlaw.org/mcp`**, which needs no credentials. The public default is what makes this step work in Cowork and on any machine without a local corpus; do not go looking for a URL or auth header in MCP config. The script speaks to the server directly, so no opinion text passes through model context.

```bash
$VENV_PYTHON "$SKILL_DIR/ndlaw_export.py" \
  --opinion <opinion_md_path> \
  --refs-dir ~/refs \
  --meta-out <TMPDIR>/sources.json
```

Exit 2 means no backend was reachable — almost always an egress allowlist that omits `ndlaw.org` (stderr classifies the failure and names the fix, and the Step 0 preflight should already have warned). **Fall back to a scribe subagent riding the in-context MCP connection** — if ndlaw tools are available:

1. From the cite JSON, list the corpus-eligible authorities that still lack refs text: case entries (not `pin_cite`, not `is_repeat`) whose `normalized` is an ND neutral cite (`YYYY ND N`) or N.W.-family reporter cite, with `local_exists` false.
2. Launch **one** subagent (Agent tool, `model: haiku`, subagent_type `general-purpose`) with that list and these instructions: for each citation, call `lookup_opinion(<cite>)` and record `case_name`, `url`, `url_source`, `date_filed`, and `citations`; then page through `get_opinion_text(<cite>, offset=..., limit=50000)` until `has_more` is false and **Write the concatenated text verbatim** (do not summarize, reformat, or strip the frontmatter block) to the refs path: `~/refs/opin/ND/<year>/<year>ND<n>.md` for `YYYY ND N`; `~/refs/opin/NW2d/<vol>/<page>.md` for `V N.W.2d P` (analogously `NW3d`, `NW`). Write `<TMPDIR>/sources.json` **incrementally**: after each `lookup_opinion` call and *before* paging that opinion's text, re-read the file, add entries mapping **every** citation form from `citations` to `{"case_name", "url", "url_source", "date_filed", "via": "ndlaw"}`, and write it back — paging text is the context-expensive step, and metadata held only in memory has been lost to context exhaustion on long lists. Finish by counting the refs files actually on disk (not from memory) and return only that tally ("N exported, M not in corpus") — never opinion text.
3. The token cost stays inside the subagent's isolated context (and within the subscription); main context must never page opinion text through its own tool results just to embed it.

If MCP tools are also unavailable, skip `--sources-meta` below and fall through (never stall on this step) — or, at most, build a minimal `sources.json` from one cheap `lookup_opinion` call per unique ND case (URL + case name only) if a stray connection allows it.

**Fall through, but never silently.** When neither the corpus nor the MCP connection was reachable, the citation text the review rests on is whatever `~/refs` already held — copies of unrecorded age, which the corpus has since corrected in ways they cannot know about (`opinions.db` carries Westlaw merges and quality-scan fixes that never reach a refs file). Record it: say so in the Step 12 summary, and render the **⚠ Authority Text Not Refreshed** section of the analysis document. A run that could not check its authorities against the corpus must not read as one that did.

## 11b. Generate the page

Write a `via.json` mapping each citation (as written, or its normalized form) to the tier from the Pass 3B **Via** column — e.g. `{"2024 ND 156": "ndlaw", "445 U.S. 684": "CourtListener", "N.D.C.C. § 14-05-24": "local"}`:

```bash
$VENV_PYTHON "$SKILL_DIR/cite_review.py" \
  --opinion <opinion_md_path> \
  --docx <original_draft.docx> \
  --refs-dir ~/refs \
  --title "<case caption>" \
  --via-json <TMPDIR>/via.json \
  --sources-meta <TMPDIR>/sources.json \
  --passages-json <TMPDIR>/passages.json \
  --facts-json <TMPDIR>/facts.json \
  --authorities-json <TMPDIR>/authorities.json \
  --case-dir <working_dir> \
  --record-dir <record_item_dir> \
  --resume-state auto \
  --output <output_dir>/cite-review.html
```

**Flags.**
- `--docx`: pass whenever the draft arrived as a .docx (the same original file Step 3 extracted from) — it recovers italics (case names, *Id.*, signals, added emphasis) and block-quote indentation for the draft pane; omit it for pasted-text or markdown drafts, and rendering degrades gracefully to plain.
- Omit `--via-json` if Pass 3B did not run or produced no table; omit `--sources-meta` if step 11a exported nothing; omit `--passages-json` if Pass 3B wrote no passages ledger; omit `--facts-json` if Pass 4 did not run or wrote no facts ledger; omit `--authorities-json` if Pass 3D did not run or detected no supplied authorities — when present, its entries render in the citations sidebar with a `supplied` badge and lane filter chips (`All · Citations · Authorities · Facts`).
- `--case-dir` is the working directory holding the case PDFs (pass it because the opinion markdown lives in TMPDIR); a `manifest.json` there is picked up automatically for docket-number and brief-name resolution.
- **`--record-dir` is mandatory whenever Step 0 split a record** (Pass 4 then cites record items as `R<N>`, and those refs resolve only against that directory of `R<N> - <Type> <Title>.pdf` files) — record cites like "R243" then resolve to embedded PDF viewers opened at the cited page with the evidence quote highlighted. This is a dependency between Step 0's split output and Step 11b's inputs: keep the split directory until the page is generated. The script enforces it — a facts ledger with record-item refs and no `--record-dir` is an error (exit 1), as is a run where fewer than one in five fact refs resolve; between 20% and 80% it warns with the resolution rate. The only way to get a text-only Facts lane is to ask for it with `--no-fact-sources` (unresolved refs then show the ledger's quote, labeled as not re-verified). Brief names in the ledger (`Brief - Appellee`, `Brief of Appellants X & Y`) resolve against the case-dir filenames and the manifest.
- **`--resume-state auto` picks up a previous review.** It looks in `--case-dir` (else the opinion's directory) for the newest `cite-review-state__<case-id>__<stamp>.json` — the file a reviewer saved there with the page's **Save review** button — and restores their verify/flag/skip marks and notes into the new page, so a re-run continues a review instead of restarting it. Safe to pass always: with no such file it prints one line and builds a fresh page, and a malformed or foreign file warns and is skipped rather than failing the run. Marks are matched by citation text, paragraph, and occurrence — never by character offset, which moves whenever the draft is edited — so anything the draft no longer contains is reported as dropped on stderr rather than reattached to the wrong citation. Report the restore line to the user: it says how many marks came back, how many were re-matched after renumbering, and whether the draft changed since the review.
- `--link-pdfs` swaps the embedded viewers for zero-copy native iframes if sidecar size is a concern; `--asset-budget <bytes>` is the middle path — identical files already share one viewer, files embed smallest-first under the cap, and only the overflow degrades to links (reported on stderr, never silent).

**The output is two objects, not one.** Unless `--link-pdfs` is used, embedded viewers live in a sibling directory `<stem>_pdfs/` (one PDF.js file per unique source, roughly 1.33× the source bytes), and the HTML's links are relative to it — the page is useless without the sidecar. The completion line reports the sidecar's path, file count, and size. In Cowork or any remote session, where a single file is what gets delivered, add `--bundle <output_dir>/<stem>.zip` and deliver the zip (unzip, open the HTML). If the bundle would exceed the delivery cap, shrink the record extracts first (the `gs` recipe in `references/pdf-ingestion.md` — page counts must survive) and/or set `--asset-budget`; do not drop `--record-dir`.

**Local-PDF authorities.** If a cited authority has no online or refs source but a PDF copy sits in the working directory (an obscure treatise, an out-of-state slip opinion, a session-law scan), add to the step 11a `sources.json` entry for that citation: `"pdf": "<path relative to the working dir>"`, plus optional `"page": N` and `"quote": "<verbatim passage>"`. The review page then offers a "Local PDF" source mode with the same embedded viewer, opened at the page/quote.

## What the page contains

The result is an HTML file — plus, whenever record, brief, or local-PDF sources are embedded, the `<stem>_pdfs/` sidecar directory that must travel with it (`--bundle` zips both; `--link-pdfs` embeds nothing) — with:
- A sidebar listing **every citation occurrence** — first full cites, repeat full cites, short forms, and *id.* references each as a separate reviewable entry — with verification status and its **Via** provenance badge (the tier that verified it); supplied authorities (Pass 3D) appear alongside citations with a `supplied` badge, and lane filter chips (`All · Citations · Authorities · Facts`) narrow the list
- A split main pane: draft paragraph (with the exact occurrence highlighted) on top; on the bottom, the cited authority — embedded source text scrolled to the pinpoint ¶, the Pass 3B verification passage when no full text is available, or a web fallback — with a link bar carrying the court's direct opinion URL, and a 3-way source control (`ndlaw.org` → official source → local reference)
- Keyboard navigation (`j`/`k` to move, `v`/`f`/`s` to verify/flag/skip, `Space`/`Enter` to verify and advance, `a` to toggle auto-advance, `h`/`l` to switch source view, `n` for notes, `?` for help)
- LocalStorage persistence so review state survives browser restarts, a **Save review** button that writes the state file `--resume-state auto` reads back, and an "Export JSON" button

Tell the user the citation review file is available and can be opened in any browser, and name the sidecar (or the bundle) alongside it. Name it `<original-filename>-CITE-REVIEW.html`.

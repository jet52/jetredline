# PDF Ingestion — splitting, text-layer triage, OCR recovery (Step 0)

PDF source materials are used only by the Pass 4 fact-checking and Pass 6 brief-matching subagents. In Step 0, identify and prepare the files but **do not read their contents** into main context. `$SKILL_DIR` and `$VENV_PYTHON` are the literal paths captured in SKILL.md's Environment Setup.

## Splitting large packets

For PDF files **> 10 MB**, use `splitmarks` to split the PDF at its top-level bookmarks into individual documents:
```bash
# Preview what bookmarks exist
$VENV_PYTHON "$SKILL_DIR/splitmarks.py" packet.pdf --dry-run -vv

# Split into individual files in an output directory, flagging image-scanned output
$VENV_PYTHON "$SKILL_DIR/splitmarks.py" packet.pdf -o split_output -v --check-text
```

`--check-text` runs `pdftotext` over each output file and prints a `WARNING: <file> … appears image-scanned` line to stderr for anything under ~50 chars/page, naming the file and suggesting `ocrmypdf`. **Read those warnings — they tell you which files need the OCR ladder below before any subagent touches them.** The flag needs `pdftotext` on `PATH`; without poppler it degrades to "can't check," so its silence is not proof of a text layer.

**Recursive split:** After the initial split, check the resulting files. If any single file is still **> 10 MB** (typically a record bundle containing many individual record items), split it again into a subdirectory:
```bash
$VENV_PYTHON "$SKILL_DIR/splitmarks.py" split_output/Record-Bundle.pdf -o split_output/record_items -v --check-text
```
This produces individual record-item files (e.g., `R1-Application.pdf`, `R58-Amended-Petition.pdf`) that can be targeted efficiently during fact-checking.

**If `splitmarks` (or any pypdf/qpdf step) refuses the file, fall back to poppler.** Record packets above 2 GB routinely carry a cross-reference offset that overflows a signed 32-bit integer. pypdf raises `ValueError: negative seek value`, and `qpdf` fails its reconstruction with `root of pages tree has no /Kids array` — but poppler reads the same file without complaint. Extract the page range you need and reassemble:

```bash
pdfseparate -f <first> -l <last> "<packet>.pdf" "<TMPDIR>/pg-%d.pdf"
pdfunite $(ls -v "<TMPDIR>"/pg-*.pdf) "<outdir>/R<N> - <Title>.pdf"
```

Scanned record pages are large; compress the result before it is embedded anywhere, and confirm the text layer survived:

```bash
gs -sDEVICE=pdfwrite -dCompatibilityLevel=1.5 -dPDFSETTINGS=/ebook \
   -dNOPAUSE -dQUIET -dBATCH -dDetectDuplicateImages=true \
   -sOutputFile=<small>.pdf <big>.pdf
pdftotext -f 1 -l 1 <small>.pdf -    # text still there?
```

An 85-page findings order went from 70 MB to 3.3 MB this way with its text layer intact. Note the naming: `R<N> - <Title>.pdf` is what `cite_review.py --record-dir` globs for, and page *N* of the extract should equal page *N* of the record item so pin cites land.

## Image-scanned / image-only PDFs (detection + OCR recovery)

Court e-filing systems (e.g., C-Track) routinely produce raster-scanned briefs with no text layer at all. **Detect and recover such files — do not skip them.** A brief the court never read is not a footnote; treat an unreadable input as a coverage failure (Step 11), not a stall.

`splitmarks --check-text` flags split *outputs* proactively (above). It does **not** cover PDFs that were never split — anything ≤ 10 MB that went straight to a subagent — so run the detection signals below on those, and use them as a backstop whenever `--check-text` was unavailable or silent.

**Detection — run `textquality.py`, which decides all three cases at once:**

```bash
$VENV_PYTHON "$SKILL_DIR/textquality.py" <file>.pdf [<file>.pdf ...]
```

It classifies each file as **`text-ok`**, **`no-text-layer`**, or **`text-layer-corrupt`**, and prints the exact `ocrmypdf` command to run. Exit status is 1 if any file is corrupt. `--json` for machine use, `--quiet` to list only files needing work.

> **Why a third state matters.** A missing text layer and a *corrupt* one need different flags, and telling them apart by character count is impossible. A scanned nineteenth-century source extracted at **5,390 characters per page** — a hundred times any density threshold — and every one of those pages read like `"the assessmellt thereof shall Le suberdmate to the gelleral plall"` Dense, confident, and wrong. Because a layer existed, `--skip-text` skipped all of it and reported success; the verification that relied on it looked clean. Density alone cannot see this. `textquality.py` scores letter-sequence plausibility instead (internal case flips, vowelless tokens, impossible consonant runs), which separated corrupt from clean by more than tenfold across a measured corpus of briefs, book scans, and law-review PDFs.

Fallback signals if `textquality.py` cannot run (both tools optional — degrade, don't error):
- `pdffonts <file>.pdf` reports **zero embedded fonts** (near-certain image-only).
- After `pdftotext`, output stripped of form-feeds/whitespace has **< ~50 characters per page**. This catches image-only files **but never catches a corrupt layer** — do not treat a pass here as proof the text is usable. If `pdftotext` is absent entirely, go straight to the Read-as-images rung; if that is also unavailable, mark the file `not-ingested`.

**OCR recovery ladder (CLI mode — escalate in order, stop at first success):**
1. Probe tooling once and branch on what exists: `command -v pdffonts pdftotext ocrmypdf pdftoppm tesseract`. `pdffonts`/`pdftotext`/`pdftoppm` ship together in poppler (present or absent as a set); `ocrmypdf` and `tesseract` are separate. A missing tool just disables its rung — never a hard failure.
2. **Preferred — ocrmypdf**, with the flag `textquality.py` selected:
   - `no-text-layer` → `ocrmypdf --skip-text --quiet <file>.pdf <file>.ocr.pdf`
   - `text-layer-corrupt` → `ocrmypdf --force-ocr --quiet <file>.pdf <file>.ocr.pdf`

   Then `pdftotext <file>.ocr.pdf <file>.txt`. **Persist `<file>.ocr.pdf`** next to the original so re-runs need no re-OCR.

   **Never use `--skip-text` on a corrupt layer.** It skips every page that already carries text, so it exits 0, writes an output file, and changes nothing. That failure is silent and it produces unverified text wearing a verified label. `--force-ocr` rasterizes and re-recognizes unconditionally, which is what a corrupt layer requires.
3. **Fallback — pdftoppm + tesseract:** if `ocrmypdf` is unavailable, `pdftoppm -r 300 -png <file>.pdf <TMPDIR>/page` then `tesseract` each page, concatenating output to `<file>.txt`. Note the limit of this rung: the `.txt` feeds the subagents, but nothing downstream rewrites the PDF, so the Step 11b review page still embeds the original file with its corrupt text layer — quote highlighting will miss on those items even though the fact-check itself used the recovered text. Say so in the analysis document's coverage section when it happens.
4. **Last resort — Read-as-images:** if no OCR binary is present, read the PDF directly with the Read tool (renders pages as images).
5. **None available** (e.g., a Cowork/VM split with no OCR binaries and no Read access): record the file as **not ingested** — surface it, never silently skip.

**OCR quality check:** after recovery, re-run `textquality.py` on the `.ocr.pdf`. If it still reports `text-layer-corrupt`, or the text does not read as coherent legal prose, mark the file **OCR-low-confidence**. For coverage purposes (Step 11) this counts as *not fully ingested*, the same as not-ingested. Re-scoring is the check — an OCR pass that ran without error is not evidence that it worked.

## Hand-off to the subagents

Pass the resulting file paths — and each file's ingestion outcome (`ingested-text` / `OCR-recovered` / `OCR-low-confidence` / `image-read` / `not-ingested`, plus the method used) — to the fact-checking and brief-matching subagents, which must report it back (see Pass 4 / Pass 6) so the main context can reconcile coverage in Step 11.

**Web mode (no Bash):** None of the shell tools above run. The Read tool renders a PDF's pages as images regardless of any text layer, so an image-only file is normally still readable — read it directly. The detection signals and OCR ladder do not apply. Only if the Read tool itself cannot render a file (corrupt, or too large to load) does it become `not-ingested`; track that outcome inline and feed it to Step 11 the same way (there are no subagents in web mode, so you hold the ingestion outcomes yourself).

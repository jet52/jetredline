# Pass 4: Fact Check — Subagent Instructions

You are a jetredline subagent. The caller's prompt supplies: a numbered list of factual claims from the draft (with ¶ references and a `Cited Records` column of record citations like "R 58," "App. 42," "Tr. 145"), and the PDF source file paths with each file's ingestion outcome from the caller's preparation step. Return **only** the results table, Ingestion Status table, and summary specified below.

- For each PDF source file, extract text locally: `pdftotext <file>.pdf <file>.txt`
- **Image-only fallback (OCR-first):** Detect image-only files and recover them with the detection + OCR recovery ladder below. OCR yields a `.txt` that feeds the Grep steps unchanged; persist any `<file>.ocr.pdf` next to the original so re-runs need no re-OCR. **Do not skip an image-only file** and do not treat "no text layer" as "unreviewable."
- **Track ingestion per file.** For every source PDF, record its outcome — `ingested-text` / `OCR-recovered` / `OCR-low-confidence` / `image-read` / `not-ingested`, plus the method. You must return this (see the Ingestion Status table below).
- Use Grep to search the extracted `.txt` files for passages relevant to each claim — **do not** read entire documents into context
- For claims with cited record items, search those files first. Then search the remaining record-item files for corroborating or contradicting evidence.
- For each claim, build a row:

| ¶ | Claim | Source Document(s) | Result | Notes |
|---|-------|-------------------|--------|-------|
| [¶ ref] | [Factual assertion] | [Source with pinpoint cite] | Verified / Unverified / Discrepancy | [Explanation] |

- Return the completed table with a summary line: [X] facts checked, [Y] verified, [Z] discrepancies, [W] unverified.
- **Also return an Ingestion Status table** (one row per source PDF) so the caller can reconcile coverage:

| Source file | Pages | Ingestion | Method |
|---|---|---|---|
| [file.pdf] | [N] | ingested-text / OCR-recovered / OCR-low-confidence / image-read / not-ingested | [pdftotext / ocrmypdf / tesseract / Read / none] |

If any file is `not-ingested` or `OCR-low-confidence`, say so plainly in the summary — the facts that depended on it are unverified, not checked.

## Detection + OCR recovery ladder

**Detection (two signals; either one ⇒ treat as image-only). Both tools are optional — degrade, don't error:**
- `pdffonts <file>.pdf` reports **zero embedded fonts** (near-certain image-only). If `pdffonts` is absent, skip this signal and rely on the next one.
- After `pdftotext`, the output stripped of form-feeds/whitespace has **< ~50 characters per page** (catches the one-form-feed-per-page case where the byte count is tiny but nonzero). If `pdftotext` itself is absent (no poppler at all), go straight to the Read-as-images rung; if that is also unavailable, mark the file `not-ingested`.

**Recovery (escalate in order, stop at first success):**
1. Probe tooling once and branch on what exists: `command -v pdffonts pdftotext ocrmypdf pdftoppm tesseract`. `pdffonts`/`pdftotext`/`pdftoppm` ship together in poppler; `ocrmypdf` and `tesseract` are separate. A missing tool just disables its rung — never a hard failure.
2. **Preferred — ocrmypdf:** `ocrmypdf --skip-text --quiet <file>.pdf <file>.ocr.pdf` then `pdftotext <file>.ocr.pdf <file>.txt`. Persist `<file>.ocr.pdf`. (`--skip-text` is safe on pages that already carry text.)
3. **Fallback — pdftoppm + tesseract:** if `ocrmypdf` is unavailable, `pdftoppm -r 300 -png <file>.pdf <tmpdir>/page` then `tesseract` each page, concatenating output to `<file>.txt`.
4. **Last resort — Read-as-images:** if no OCR binary is present, read the PDF directly with the Read tool (renders pages as images).
5. **None available:** record the file as **not-ingested** — surface it, never silently skip.

**OCR quality check:** after recovery, sample the recovered text. If it does not read as coherent legal prose — garbled, mostly non-words, or still near-empty — mark the file **OCR-low-confidence** (counts as not fully ingested for coverage purposes).

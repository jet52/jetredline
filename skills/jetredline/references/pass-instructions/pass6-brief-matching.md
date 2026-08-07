# Pass 6: Brief Matching — Subagent Instructions

You are a jetredline subagent. The caller's prompt supplies the draft document's path and the party brief file paths (with any known ingestion outcomes). Return **only** the results table, Ingestion Status table, and summary specified below.

## Shell command hygiene (CLI mode)

Permission allowlists match a command's **first token**, so a command whose
first token is unstable prompts the user even when the underlying tool is
approved. Keep every Bash call matchable:

- **Never `cd`.** `cd dir && cmd` makes the first token `cd`. Pass absolute
  paths to the command instead, or use its own `-C`/`--directory` flag.
- **Never prefix a command with variable assignments** (`TMPDIR=… cmd`,
  `SP="…"; …`). Put the value in the argument directly.
- **Invoke the venv python by the literal absolute path the caller gave you**,
  with no shell variable standing in for it.
- **Prefer a shipped helper to a throwaway script.** Writing a one-off `.py`
  into a temp directory and running it yields a unique, unmatchable command
  every time. Use `<SKILL_ROOT>/pdf_page_grep.py` for "find this string and
  tell me its page" — it searches an adjacent `.txt` when present, else
  `pdftotext`, else pypdf, and reports `file:page: …snippet…`.
- **Write absolute paths in full and quote any containing spaces.** `~` and
  `$HOME` are not expanded when matching, so they always prompt.

`pdf_page_grep.py` collapses whitespace before matching, so a phrase that
`pdftotext -layout` wrapped across a line still matches. A hand-rolled substring search misses it silently and reads as "the
record does not say this" — the wrong conclusion, reached invisibly.

Read the draft document and the party briefs at the supplied paths.

For each brief, extract text locally: `pdftotext <file>.pdf <file>.txt`

**Image-only fallback (OCR-first):** Detect image-only briefs and recover them with the detection + OCR recovery ladder below. Persist any `<file>.ocr.pdf`. **Do not skip an image-only brief** — a brief that cannot be read means the court's coverage of that party's arguments is unverified, which you must report (Step 5 below), not bury.

**Step 1:** Extract every distinct argument or contention from each party's brief. For each argument, record:
- The party (Appellant/Appellee/Petitioner/Respondent)
- A one-sentence summary of the argument
- The brief and page range where the argument appears (e.g., "Appellant's Brief, pp. 12–15")

**Step 2:** For each argument, search the draft document for responsive discussion. An argument is "addressed" if the document engages with the substance of the contention — not merely mentioning the topic. Classify as:
- **Yes** — the document directly addresses the argument
- **Partial** — the document touches on the topic but does not fully engage (e.g., acknowledges without analysis)
- **No** — no responsive discussion found

**Step 3:** Build the results table:

| ¶ | Argument | Party | Brief Source | Addressed | Notes |
|---|----------|-------|-------------|-----------|-------|
| [¶ ref or "—"] | [Argument summary] | [Party] | [Brief, pp. X–Y] | Yes / Partial / No | [Where addressed, or what's missing] |

The ¶ column references where in the draft the argument is addressed (or "—" if not addressed).

**Step 4:** Return the table and a summary: [X] arguments identified across [N] briefs. [Y] directly addressed. [Z] partially addressed. [W] not addressed.

**Step 5:** Also return an **Ingestion Status** table (one row per brief) so the caller can reconcile coverage:

| Brief file | Pages | Ingestion | Method |
|---|---|---|---|
| [brief.pdf] | [N] | ingested-text / OCR-recovered / OCR-low-confidence / image-read / not-ingested | [pdftotext / ocrmypdf / tesseract / Read / none] |

If a brief is `not-ingested` or `OCR-low-confidence`, state it in the summary and mark that party's arguments **coverage unverified** rather than implying they were checked against the draft.

## Detection + OCR recovery ladder

**Detection (two signals; either one ⇒ treat as image-only). Both tools are optional — degrade, don't error:**
- `pdffonts <file>.pdf` reports **zero embedded fonts** (near-certain image-only). If `pdffonts` is absent, skip this signal and rely on the next one.
- After `pdftotext`, the output stripped of form-feeds/whitespace has **< ~50 characters per page**. If `pdftotext` itself is absent (no poppler at all), go straight to the Read-as-images rung; if that is also unavailable, mark the file `not-ingested`.

**Recovery (escalate in order, stop at first success):**
1. Probe tooling once: `command -v pdffonts pdftotext ocrmypdf pdftoppm tesseract`. A missing tool just disables its rung — never a hard failure.
2. **Preferred — ocrmypdf:** `ocrmypdf --skip-text --quiet <file>.pdf <file>.ocr.pdf` then `pdftotext <file>.ocr.pdf <file>.txt`. Persist `<file>.ocr.pdf`.
3. **Fallback — pdftoppm + tesseract:** `pdftoppm -r 300 -png <file>.pdf <tmpdir>/page` then `tesseract` each page, concatenating output to `<file>.txt`.
4. **Last resort — Read-as-images:** read the PDF directly with the Read tool.
5. **None available:** record the file as **not-ingested** — surface it, never silently skip.

**OCR quality check:** after recovery, sample the recovered text. If it does not read as coherent legal prose, mark the file **OCR-low-confidence** (counts as not fully ingested for coverage purposes).

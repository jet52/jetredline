---
name: jetredline
version: 4.13.0
description: "Appellate judicial opinion and bench memo editor and proofreader. Produces a Word document (.docx) with tracked changes showing proposed edits, plus a separate analysis document with explanations. Use when the user provides a draft judicial opinion, court order, bench memo, or legal memorandum for editing, proofreading, or style review. Triggers: edit opinion, proofread opinion, review draft opinion, judicial writing review, court opinion edit, redline opinion, edit draft order, appellate opinion editing, edit memo, edit bench memo, proofread memo, review bench memo, jetredline, redline this draft, redline this opinion, redline this memo, redline this order. Applies Garner's Redbook, Bluebook citation format, and style preferences drawn from opinions issued by the North Dakota Supreme Court within the last ten years, Guberman's Point Taken, and Justices Gorsuch, Kagan, and Thomas."
---

# JetRedline

Edit draft judicial opinions and bench memos to improve grammar, clarity, conciseness, professional tone, citation accuracy, and analytical rigor. Produce a Word document with tracked changes and a companion analysis document.

## Audit Mode (Caller Integration)

Another skill (e.g., jetmemo) may invoke jetredline programmatically to audit a memo it just generated and feed the findings back into its own draft. When the caller's prompt says it is invoking jetredline in **audit mode**, this section *overrides* parts of the standard workflow below. Everything not overridden here is unchanged.

**Detect audit mode** from the caller's prompt: it will say "audit mode" and supply a draft path, a pass list, and a request to return results rather than write files. When in audit mode:

1. **Fixed settings** — do not ask, do not auto-detect:
   - `DOC_TYPE = memo` (the caller only audits bench memos in this mode).
   - Output = **analysis-only**. **Write no files** — no .docx, no `-ANALYSIS.md`, no `cite-review.html`. Return everything inline to the caller.
   - The draft arrives as a **markdown file path** (or pasted text), not a .docx. Read it directly; skip Step 0's `.docx`/`.pdf` scan, the temp-dir setup, and the docx-plugin discovery.
   - **Preserve markdown link syntax.** The memo arrives with record-citation hyperlinks (`[R45](url)`) and possibly authority links already in it. Never edit a URL, and when an edit touches linked text, keep the `[text](url)` wrapper intact.

2. **Run inline.** Execute all selected passes inline in this context (as in Web mode) — do **not** delegate to Task subagents. The caller has already spawned you as a subagent. For passes whose detailed instructions live in `references/pass-instructions/` (Pass 1, Pass 4, Pass 6), Read the matching file and apply it inline.

3. **Pass selection** — the caller supplies the list. The standard audit-mode selection is **passes 1, 2, 3C, 4, 5, 6**, with these adjustments:
   - **Skip Pass 3A and Pass 3B** (Bluebook format + substantive citation verification). The caller owns citation verification separately; running it here duplicates work and can produce divergent tallies.
   - **Keep Pass 3C** (negative-treatment / overruling scan via `detect_overruled_in_draft`). It is additive and cheap.
   - **Pass 4** (fact-check) and **Pass 6** (brief-matching): run both. **Reuse the caller's existing `<file>.txt` extractions** — the caller will pass their paths; do **not** re-run `pdftotext` on PDFs that already have a `.txt`.
   - **Pass 5** (analytical rigor): run all checks **except Readability Metrics** — skip `readability_metrics.py` entirely (not needed for the caller's internal audience).
   - **Pass 1** (jurisdictional, memo variant) and **Pass 2** (style/grammar): run normally, inline.
   - Pass 7 is N/A (memo).

4. **Return contract** — return exactly two parts, in this order, and nothing else:

   **Part 1 — Mechanical edits (JSON).** A fenced ` ```json ` block containing an array of *style/grammar* edits only — the direct `replace` edits from Pass 2. Each entry:
   ```json
   { "type": "replace", "para": 7, "old": "<exact text, full sentence for unique match>", "new": "<replacement>", "comment": "<rule, e.g. Redbook §11.3>", "source_pass": "style" }
   ```
   Include here **only** safe, mechanical Pass 2 replacements. Do **not** put analytical rewrites, restructuring proposals, or anything from Passes 1/3C/4/5/6 in this block. If a Pass 2 item is better expressed as a note than a direct substitution, route it to Part 2 instead.

   **Part 2 — Substantive Concerns (markdown).** Everything that needs human (caller) judgment, grouped under these headings (omit a heading if it has no findings):
   - `### Jurisdiction` — Pass 1 findings/warnings.
   - `### Fact-Check` — Pass 4 discrepancy table (`¶ | Claim | Source | Result | Notes`).
   - `### Brief Coverage` — Pass 6 table (`¶ | Argument | Party | Brief Source | Addressed | Notes`). This is the table the caller mines for omitted-argument remediation, so keep the `Party`, `Brief Source` (page range), and `Addressed` (Yes/Partial/No) columns precise.
   - `### Analytical Rigor` — Pass 5 findings (internal consistency, standard-of-review application, memo checks: issue completeness, balance/steelman, recommendation support, analytical gaps). No readability section.
   - `### Negative Treatment` — Pass 3C flagged cases (advisory; "verify").
   - `### Style Notes` — any Pass 2 `comment`-type items not suitable as direct edits.
   - `### Coverage` — any source PDF not fully ingested (`not-ingested` or `OCR-low-confidence`): file, reason, and affected passes (4/6). Omit the heading if all inputs were fully ingested.

   End Part 2 with a one-line summary: `Audit: N mechanical edits | brief gaps: A not-addressed, B partial | F fact discrepancies | T treatment flags | coverage: K of M inputs ingested`.

The standard CLI/Web workflow, output documents, and Step 12 summary do not apply in audit mode — Parts 1 and 2 above are the entire deliverable.

## Environment Detection

Determine your runtime environment from available capabilities:

- **CLI mode**: You have access to the Bash, Task, TaskOutput, and AskUserQuestion tools, and can read/write the local file system. Follow the full workflow as written.
- **Web mode**: You are running in Claude Projects or a similar web environment without access to Bash, Task, or file system tools. Follow the **Web mode** fallbacks noted throughout this document.

Do not ask the user which mode to use — sense it from your available tools.

## Python Environment (Bootstrap)

**Web mode:** skip — CLI only.

At the start of each CLI session, run the bootstrap script once with any
system Python (`python3`, or `python` on Windows/PowerShell):

```bash
python3 "${CLAUDE_SKILL_DIR}/bootstrap_env.py"
```

(`${CLAUDE_SKILL_DIR}` here and throughout is replaced by the harness with
this skill's absolute directory before you read this file; the commands you
see contain a literal path. Keep paths double-quoted — on Windows the
substituted path may contain spaces.)

The script finds or builds the skill's virtual environment and prints one line:

```
VENV_PYTHON=<absolute path>
```

**Capture that path as a literal string** and use it in place of
`$VENV_PYTHON` in every Python command below (same pattern as `TMPDIR`; no
command substitution). It works in every install layout: a prebuilt `.venv`
inside the skill directory (used and, if a package is missing, repaired in
place), else a cached venv at `~/.cache/jet-skills/jetredline/<version>/`
(built on first use), else a temp-dir venv (read-only home, e.g. Cowork).
Packages provided: `defusedxml`, `httpx[socks]`, `pdfplumber`, `pypdf`,
`textstat`. Never create a venv in the working directory.

The script is idempotent and cheap after the first run. If it fails outright
(exit 1 — no writable location or no network for the first build), fall back
to manual creation and use its python the same way:

```bash
python3 -m venv /tmp/jetredline-venv
/tmp/jetredline-venv/bin/pip install -r "${CLAUDE_SKILL_DIR}/requirements.txt" -q
```

**Environment variable syntax** differs by shell:
- Bash (macOS/Linux/Git Bash): `VAR=val command`
- PowerShell (Windows): `$env:VAR='val'; command`

## Skill and Docx Plugin Path Discovery

**Web mode:** Skip this section and the Node.js Environment and Temporary Files sections (and the Python bootstrap above) — they apply only in CLI mode. Proceed to Workflow.

The skill directory is `${CLAUDE_SKILL_DIR}` — the harness substitutes the
absolute path (standalone install, plugin cache, or Cowork mount alike), and
the "Base directory for this skill:" line at the top of this document carries
the same value. Set it once, with probes as a fallback in case substitution
ever fails (an unsubstituted placeholder expands to an empty string):

```bash
SKILL_DIR="${CLAUDE_SKILL_DIR}"
if [ ! -d "$SKILL_DIR" ]; then
  if [ -d "$HOME/.claude/skills/jetredline" ]; then
    SKILL_DIR="$HOME/.claude/skills/jetredline"
  elif [ -d "/mnt/.skills/skills/jetredline" ]; then
    SKILL_DIR="/mnt/.skills/skills/jetredline"
  fi
fi
```

**Docx plugin (conditional — usually not needed).** Reading a .docx draft uses `extract_text.py` and applying edits uses `apply_edits.py`; both operate directly on the .docx ZIP and need no plugin. The docx plugin is required **only** when creating a new .docx from scratch (plain-text/markdown input plus tracked-changes .docx output — the Step 9 alternative path). Run this discovery (and Step 2's docx-skill read) only when that path applies. The plugin has different directory structures in Claude Code vs. Cowork:

```bash
# Detect docx plugin location and layout (new-.docx creation path only)
if [ -d "/mnt/.skills/skills/docx" ]; then
  DOCX_SKILL="/mnt/.skills/skills/docx"
  UNPACK_SCRIPT="$DOCX_SKILL/scripts/office/unpack.py"
  PACK_SCRIPT="$DOCX_SKILL/scripts/office/pack.py"
elif [ -d "$HOME/.claude/plugins/marketplaces/anthropic-agent-skills/skills/docx" ]; then
  DOCX_SKILL="$HOME/.claude/plugins/marketplaces/anthropic-agent-skills/skills/docx"
  UNPACK_SCRIPT="$DOCX_SKILL/scripts/office/unpack.py"
  PACK_SCRIPT="$DOCX_SKILL/scripts/office/pack.py"
else
  # Claude Code plugin cache (hash may vary)
  DOCX_SKILL=$(ls -d "$HOME/.claude/plugins/cache/anthropic-agent-skills/document-skills"/*/skills/docx 2>/dev/null | head -1)
  UNPACK_SCRIPT="$DOCX_SKILL/ooxml/scripts/unpack.py"
  PACK_SCRIPT="$DOCX_SKILL/ooxml/scripts/pack.py"
fi
```

Use `$SKILL_DIR` in all subsequent commands; `$DOCX_SKILL`, `$UNPACK_SCRIPT`, and `$PACK_SCRIPT` exist only when the creation-path discovery above was run.

| Resource | Path |
|----------|------|
| This skill | `$SKILL_DIR` |
| Docx skill | `$DOCX_SKILL` (conditional — new-.docx creation only) |
| Venv python | `$VENV_PYTHON` (from `bootstrap_env.py` — see Python Environment above) |
| Text extraction | `$SKILL_DIR/extract_text.py` |
| splitmarks | `$SKILL_DIR/splitmarks.py` |
| Node modules | `$NODE_PATH` (from `bootstrap_env.py --node` — new-.docx creation only) |
| ND opinions (markdown) | `$OPINIONS_MD` → `~/cDocs/refs/ndsc_opinions/markdown/` |
| Citation checker | `$SKILL_DIR/cite_check.py` |
| Readability metrics | `$SKILL_DIR/readability_metrics.py` |
| Legal refs | `~/refs/` (opin/, statute/, reg/, cnst/, rule/) |
| OOXML fixup | `$SKILL_DIR/ooxml_fixup.py` |
| OOXML validate | `$SKILL_DIR/ooxml_validate.py` |
| Citation review | `$SKILL_DIR/cite_review.py` |
| Batch edit helper | `$SKILL_DIR/apply_edits.py` |

The opinions directory contains markdown copies of published ND Supreme Court opinions organized as `<year>/<year>ND<number>.md` (e.g., `2022/2022ND210.md` for *Feickert v. Feickert*, 2022 ND 210). Paragraphs are marked `[¶N]`. Use `$OPINIONS_MD` in commands; fall back to the hardcoded path if the variable is unset.

The `~/refs/` directory contains a local repository of legal materials in markdown format: opinions (`opin/{reporter}/`), statutes (`statute/NDCC/`, `statute/USC/`), constitutions (`cnst/ND/`, `cnst/US/`), regulations (`reg/NDAC/`, `reg/CFR/`), and court rules (`rule/{set}/`). The citation checker resolves these paths automatically via jetcite.

## Temporary Files

**CRITICAL:** In Step 0, create a uniquely-named temp directory and capture its **absolute path** as a literal string. Use that literal path (no command substitution) in all subsequent `TMPDIR=` prefixes.

**Step 0 temp-dir setup (run once):**
```bash
# Use /tmp if cwd is under a restricted mount (Cowork), otherwise use cwd
if [[ "$(pwd)" == /mnt/* ]]; then
  TMPBASE="/tmp"
else
  TMPBASE="$(pwd)"
fi
python3 -c "import uuid,os,sys; d=os.path.join(sys.argv[1],'.tmp-'+str(uuid.uuid4())[:12]); os.makedirs(d,exist_ok=True); print(d)" "$TMPBASE"
```
This generates a UUID-based unique directory name (e.g., `.tmp-a1b2c3d4e5f6`), preventing collisions between concurrent sessions. Uses `python3` directly — no shell command substitution needed. In Cowork, temp files go to `/tmp/` to avoid permission issues on mounted filesystems.

**Capture the output** (the absolute path printed by `echo`) and use it as a literal string in all subsequent commands. For example, if the output is `/path/to/cases/smith/.tmp-a1b2c3d4e5f6`, then every later command uses:
```
TMPDIR=/path/to/cases/smith/.tmp-a1b2c3d4e5f6
```
**Never** use `TMPDIR="$(pwd)/.tmp"` — the command substitution triggers unnecessary permission prompts on every invocation.

## Node.js Environment

Needed **only** for the new-.docx creation path (Step 9 alternative). The `docx` npm package is either bundled in this skill's directory or installed once into the user cache by the bootstrap script:

```bash
python3 "${CLAUDE_SKILL_DIR}/bootstrap_env.py" --node
```

Capture the printed `NODE_PATH=<path>` value as a literal (alongside the `VENV_PYTHON=` line). `NODE_PATH=NONE` means npm is unavailable — the docx-creation path is then off the table; note it and continue with the direct-edit path. Never run `npm install` yourself; the script handles it.

When running Node scripts that use `docx`, set `NODE_PATH` to the captured value:
```bash
NODE_PATH=<captured NODE_PATH> node script.js
```

When running docx skill scripts (new-.docx creation path only; always include TMPDIR — use the literal absolute path from Step 0):
```bash
TMPDIR=<TMPDIR> PYTHONPATH=$DOCX_SKILL $VENV_PYTHON script.py
```
where `<TMPDIR>` is the literal path captured in Step 0 (e.g., `/path/to/cases/smith/.tmp-apple-walrus-quilt`).

Note: `apply_edits.py` operates directly on the .docx ZIP archive — pure Python (`zipfile` + `defusedxml`), no unpack/pack pipeline and no external converter.

## Workflow

### Step 0: Initialize and Scan Working Directory

**Web mode:** Skip temp directory creation, update check, and directory scanning. The user will paste text or upload .docx/.pdf files directly in the conversation. Claude can read uploaded .docx and .pdf files natively. Proceed to Step 0.1.

**Update check:** Run `python3 "${CLAUDE_SKILL_DIR}/check_update.py"` silently. If it prints output, include it as a note to the user.

**First, create the temp directory** with a unique random name:
```bash
if [[ "$(pwd)" == /mnt/* ]]; then TMPBASE="/tmp"; else TMPBASE="$(pwd)"; fi
python3 -c "import uuid,os,sys; d=os.path.join(sys.argv[1],'.tmp-'+str(uuid.uuid4())[:12]); os.makedirs(d,exist_ok=True); print(d)" "$TMPBASE"
```
**Capture the absolute path** printed by this command (e.g., `/path/to/cases/smith/.tmp-a1b2c3d4e5f6`). Use this literal path as `TMPDIR=<path>` in all subsequent commands — never use `$(pwd)` or other command substitution for TMPDIR.

Then scan the current working directory for:
- **`.docx` files** — potential draft opinions, memos, or dissents
- **`.pdf` files** — potential briefs, record packets, or supporting references

If **exactly one `.docx`** is found, use it as the draft document.
If **exactly one `.pdf`** is found, use it as the record/briefs packet for fact-checking.
If **more than one `.docx`** or **more than one `.pdf`** is found, ask the user which file(s) to use and their roles (e.g., majority opinion, dissent, bench memo, briefs packet, supporting reference).
If **no `.docx`** is found, ask the user to provide the document text.

**Preparing PDF packets (do not read into main context):** PDF source materials are used only by the Pass 4 fact-checking subagent. In Step 0, identify and prepare the files but **do not read their contents**.

For PDF files **> 10 MB**, use `splitmarks` to split the PDF at its top-level bookmarks into individual documents:
```bash
# Preview what bookmarks exist
$VENV_PYTHON "${CLAUDE_SKILL_DIR}/splitmarks.py" packet.pdf --dry-run -vv

# Split into individual files in an output directory, flagging image-scanned output
$VENV_PYTHON "${CLAUDE_SKILL_DIR}/splitmarks.py" packet.pdf -o split_output -v --check-text
```

`--check-text` runs `pdftotext` over each output file and prints a `WARNING: <file> … appears image-scanned` line to stderr for anything under ~50 chars/page, naming the file and suggesting `ocrmypdf`. **Read those warnings — they tell you which files need the OCR ladder below before any subagent touches them.** The flag needs `pdftotext` on `PATH`; without poppler it degrades to "can't check," so its silence is not proof of a text layer.

**Recursive split:** After the initial split, check the resulting files. If any single file is still **> 10 MB** (typically a record bundle containing many individual record items), split it again into a subdirectory:
```bash
$VENV_PYTHON "${CLAUDE_SKILL_DIR}/splitmarks.py" split_output/Record-Bundle.pdf -o split_output/record_items -v --check-text
```
This produces individual record-item files (e.g., `R1-Application.pdf`, `R58-Amended-Petition.pdf`) that can be targeted efficiently during fact-checking.

**Image-scanned / image-only PDFs (detection + OCR recovery):** Court e-filing systems (e.g., C-Track) routinely produce raster-scanned briefs with no text layer at all. **Detect and recover such files — do not skip them.** A brief the court never read is not a footnote; treat an unreadable input as a coverage failure (Step 11), not a stall.

`splitmarks --check-text` flags split *outputs* proactively (above). It does **not** cover PDFs that were never split — anything ≤ 10 MB that went straight to a subagent — so run the detection signals below on those, and use them as a backstop whenever `--check-text` was unavailable or silent.

**Detection (two signals; either one ⇒ treat as image-only). Both tools are optional — degrade, don't error:**
- `pdffonts <file>.pdf` reports **zero embedded fonts** (near-certain image-only). If `pdffonts` is not on the probe (see below), skip this signal and rely on the next one.
- After `pdftotext`, the output stripped of form-feeds/whitespace has **< ~50 characters per page** (catches the one-form-feed-per-page case where the byte count is tiny but nonzero). If `pdftotext` itself is absent (no poppler at all), you cannot extract or detect via text — go straight to the Read-as-images rung, and if that is also unavailable, mark the file `not-ingested`.

**OCR recovery ladder (CLI mode — escalate in order, stop at first success):**
1. Probe tooling once and branch on what exists: `command -v pdffonts pdftotext ocrmypdf pdftoppm tesseract`. `pdffonts`/`pdftotext`/`pdftoppm` ship together in poppler (present or absent as a set); `ocrmypdf` and `tesseract` are separate. A missing tool just disables its rung — never a hard failure.
2. **Preferred — ocrmypdf:** `ocrmypdf --skip-text --quiet <file>.pdf <file>.ocr.pdf` then `pdftotext <file>.ocr.pdf <file>.txt`. **Persist `<file>.ocr.pdf`** next to the original so re-runs need no re-OCR. (`--skip-text` is safe on pages that already carry text.)
3. **Fallback — pdftoppm + tesseract:** if `ocrmypdf` is unavailable, `pdftoppm -r 300 -png <file>.pdf <TMPDIR>/page` then `tesseract` each page, concatenating output to `<file>.txt`.
4. **Last resort — Read-as-images:** if no OCR binary is present, read the PDF directly with the Read tool (renders pages as images).
5. **None available** (e.g., a Cowork/VM split with no OCR binaries and no Read access): record the file as **not ingested** — surface it, never silently skip.

**OCR quality check:** after recovery, sample the recovered text. If it does not read as coherent legal prose — garbled, mostly non-words, or still near-empty — mark the file **OCR-low-confidence**. For coverage purposes (Step 11) this counts as *not fully ingested*, the same as not-ingested.

Pass the resulting file paths — and each file's ingestion outcome (`ingested-text` / `OCR-recovered` / `OCR-low-confidence` / `image-read` / `not-ingested`, plus the method used) — to the fact-checking and brief-matching subagents, which must report it back (see Pass 4 / Pass 6) so the main context can reconcile coverage in Step 11.

**Web mode (no Bash):** None of the shell tools above run. The Read tool renders a PDF's pages as images regardless of any text layer, so an image-only file is normally still readable — read it directly. The detection signals and OCR ladder do not apply. Only if the Read tool itself cannot render a file (corrupt, or too large to load) does it become `not-ingested`; track that outcome inline and feed it to Step 11 the same way (there are no subagents in web mode, so you hold the ingestion outcomes yourself).

### Step 0.1: Determine Document Type

Classify the document as `DOC_TYPE = opinion` or `DOC_TYPE = memo`. **Auto-detect without asking the user** unless genuinely ambiguous (no markers found at all).

1. **Invocation keywords:** If the user's prompt contains "bench memo", "memo", "law clerk draft", or similar → `memo`
2. **Opinion markers:** If the document contains "FILED", a case caption with docket number, "OPINION OF THE COURT", "We affirm", "We reverse", "PER CURIAM", or similar appellate opinion markers → `opinion`
3. **Memo markers:** If the document contains "BENCH MEMORANDUM", "BENCH MEMO", "Issues Presented", "Recommendation", "Staff Attorney" heading patterns → `memo`
4. **Ambiguous (no markers found):** Only if none of the above signals are present, ask the user. **CLI mode:** Use `AskUserQuestion`. **Web mode:** Ask directly.
   - **Question:** "Is this a draft judicial opinion or a bench memo?"
   - **Header:** "Doc type"
   - **Options:**
     1. **Judicial opinion** — Draft opinion, concurrence, or dissent
     2. **Bench memo** — Staff attorney or law clerk memo to the court
5. **Default:** `opinion`

When auto-detecting, briefly state the detected type (e.g., "Detected: judicial opinion (FILED marker found)") and proceed. Do not ask for confirmation.

Store `DOC_TYPE` and reference it in conditional sections of Passes 1 and 5 and the analysis document output.

### Step 0.5: Determine Output Preferences

**Web mode:** Do not ask for output preferences. Only the markdown analysis document is available — tracked-changes .docx and the interactive citation review HTML both require CLI tools (Bash, Python, file system access). State this briefly: "In this environment I can produce a markdown analysis report but not a tracked-changes .docx or citation review page." Proceed unless the user objects.

**CLI mode:** Default to producing **both** documents (tracked-changes .docx + analysis document) without asking. Only ask if the user explicitly specified a different preference in their invocation (e.g., "just the redline" or "analysis only").

If the user did specify a preference, honor it:
- If **both** (default): Follow the full workflow through Step 10
- If **tracked-changes only**: Complete all editing passes, produce the .docx in Step 9, skip Step 10 (analysis document)
- If **analysis only**: Complete all editing passes and collect findings, produce only the analysis document in Step 10, skip Step 9 (.docx creation)

**Note:** Even when producing analysis only, you must still perform all editing passes (1–7) to identify issues and generate findings for the analysis. You simply skip the final .docx assembly step.

### Step 0.6: Review Scope & Run Announcement

**Do not ask the user to choose a depth or scope of review.** jetredline runs the full pass suite by default. Never present a "what depth of redline" question or a checklist of passes. (The only sanctioned scoping questions remain the *doc type* question in Step 0.1, asked only when genuinely ambiguous, and nothing else.)

**Announce the full run.** After detecting `DOC_TYPE` (Step 0.1) and before launching passes, state in one short paragraph: (a) that you're doing a complete review, (b) the passes that will run, (c) the deliverables, and (d) that the user can narrow the scope next time by saying so at invocation. Keep it to a few lines — do **not** turn it into a checklist or a question. Suggested form (trim passes that don't apply, e.g. omit dissent/concurrence cross-check when none is present):

> I'll run a **complete review** — all of jetredline's passes:
> • Jurisdiction & standard of review
> • Line/copy editing — grammar, word choice, sentence structure, Redbook style
> • Citations — existence, accurate quotation, correct Bluebook/Redbook form, and negative-treatment (overruling) scan
> • Fact-checking against the record and briefs
> • Analytical rigor — logical gaps, unsupported conclusions, missing steps
> • Dissent/concurrence cross-check
>
> Deliverables: a **tracked-changes .docx** you can accept/reject in Word, plus a **companion analysis document** explaining each change.
>
> *Want something narrower next time? Just say so when you invoke — e.g.* "jetredline, citations only" *or* "light copy edit, don't touch my reasoning" *— and I'll limit the passes accordingly.*

**Scope-keyword map (only when the user *volunteered* a narrower scope in their invocation).** Do not prompt for this; apply it only when the user's own words signal a narrower intent. Map their words to passes and run only those, plus the always-on jurisdictional check (Pass 1):

| If the user says… | Run |
|---|---|
| "copy edit," "light edit," "proofread only," "style only" | Pass 2 |
| "citations only," "check cites," "cite check" | Pass 3A–C |
| "substance only," "analysis only," "rigor" | Passes 4, 5, 6, 7 |
| "no substantive changes," "don't rewrite my reasoning" | Passes 2, 3; skip 5 |

When you narrow the scope, say which passes you skipped and why, and adjust the announcement above to describe only the passes you will actually run. (Note: "analysis only" as a *scope* keyword means substantive passes; it is distinct from the *output* preference in Step 0.5, which governs which documents are produced. If the user's intent is ambiguous between the two, briefly confirm.)

### Steps 1–10: Core Workflow
1. Read `references/style-guide.md`
2. **Docx skill (conditional — usually skip).** Only when the draft is *not* a .docx **and** a tracked-changes .docx will be produced (Step 9 must create one from scratch): run the docx-plugin discovery above, then Read `SKILL.md` from `$DOCX_SKILL` (and `ooxml.md` if it exists as a separate file; **do not** read `docx-js.md`, `document.py`, or other files). When the draft **is** a .docx, skip all of this — `extract_text.py` and `apply_edits.py` are self-contained.
3. Read the draft opinion. **If the draft is a .docx**, first extract its text deterministically (zero model tokens — never transcribe a .docx by hand and never read raw OOXML into context):
```bash
$VENV_PYTHON $SKILL_DIR/extract_text.py --input <draft.docx> --output <TMPDIR>/<stem>.md
```
   Then Read the generated markdown — it is the `<opinion_md_path>` used by Pass 3 and Step 11. The script preserves literal ¶ markers, reconstructs Word automatic paragraph numbering (including style-based numbering like the chambers template's MainBody `[¶N]`), extracts footnotes as `[^N]` references, and resolves any existing tracked changes to the as-accepted view; its stderr summary reports those counts — if the input already carries tracked changes, mention that to the user. For pasted text or a markdown file, read it directly. **Count paragraphs** (¶ markers or logical paragraphs) to determine opinion length.
4. **Delegate Pass 1** (jurisdictional check) to a subagent — see Pass 1 below
5. **Delegate Pass 3** (citation verification) to a subagent — see Pass 3 below
6. **Delegate Pass 4** (fact-checking) to a subagent if PDF materials were identified in Step 0 — see Pass 4 below
6a. **Delegate Pass 6** (brief matching) to a subagent if briefs were identified in Step 0 — see Pass 6 below
6b. **Delegate Pass 7** (dissent/concurrence cross-check) to a subagent if a dissent or concurrence was identified in Step 0 and `DOC_TYPE == opinion` — see Pass 7 below
7. **Pass 2 routing:** If the opinion has **more than 30 paragraphs**, delegate Pass 2 to a subagent — see "Delegated Pass 2" below. Otherwise, perform Pass 2 in main context. **Pass 5** (analytical rigor) is always performed in main context. Pass 2 (when not delegated) and Pass 5 can proceed in parallel with subagents.
8. Collect subagent results from Passes 1, 3, 4, 6, 7, and (if delegated) Pass 2 — **use the `TaskOutput` tool**, not Bash `tail`
8a. **Caption mismatches → edits (closed-loop rule).** Check the Pass 3B results table for Caption Check mismatches. Generate a correcting tracked-change edit **only** when the *same* citation resolved to an official caption and the draft's name is a near-match typo of it (high `name_similarity`) — e.g., a comment "Official caption per 2023 ND 219: 'Tracey v. Tracey'". **Never** harmonize names across two *different* citations (different cite = presumptively different case), and do not auto-correct low-similarity or unresolved names — add a comment for human review instead. Include qualifying edits in the edits JSON alongside Pass 2/3A/5 edits. Likewise apply the **parallel-cite corrections** flagged by Pass 3B's parallel-cite check — add a missing N.W.2d/N.W.3d parallel to a *full* cite, or fix a wrong one, using the `formatted` value from ndlaw.
8b. **Treatment flags → comments.** If the Pass 3C overruling scan flagged any cited case for possible negative treatment, add a *comment* (not an edit) on each occurrence, quoting the citing context, for human review. Never auto-edit on a treatment signal.
9. **If user requested tracked-changes .docx** (both or tracked-changes only): Produce tracked-changes .docx output using the batch edit workflow (see Step 9 details below)
10. **If user requested analysis document** (both or analysis only): Produce the companion analysis document (incorporating all subagent results). If also producing .docx, create both outputs in the same response
10a. **Stamp a provenance footer on the analysis document** (CLI mode, after it is written to `<stem>-ANALYSIS.md`). This records which Claude model and which jetredline version generated the analysis, and on what date, for later validation and comparison as the model and skill change:
```bash
python3 "${CLAUDE_SKILL_DIR}/provenance.py" --file <stem>-ANALYSIS.md \
  --model "{runtime model — friendly name and exact ID, e.g. Claude Opus 4.8 (claude-opus-4-8)}"
```
Footer, e.g.: *Report generated by Claude Opus 4.8 (claude-opus-4-8) using jetredline v4.4.0 on 2026-06-05. AI-generated first draft for internal use; verify all citations and findings before relying.* Version and date are sourced deterministically by the script (version from frontmatter/`VERSION`, date from the system clock); you supply only `--model` from your runtime context — the script never guesses the model. The stamp is idempotent. **Stamp only the analysis document — never the tracked-changes `.docx`, which is the user's own opinion text and must not be altered with a footer.** In **audit mode** (no files written) and **web mode** (analysis returned inline, no filesystem), skip the script; in web mode you may append the same footer line manually as the report's last line.
11. **Generate citation review HTML** (CLI and Cowork): After Pass 3 completes, generate an interactive citation review page for human verification.

    **11a. Refresh ND authority text + direct URLs from ndlaw (zero token cost).** Run the export script first — it pulls each cited ND opinion's authoritative text and the court's direct opinion URL (`https://www.ndcourts.gov/supreme-court/opinions/<id>`) from the ndlaw corpus into `~/refs`, plus a metadata map for the review page. It auto-selects a backend: a local `opinions.db` (`NDLAW_DB` env or the default dev path), else a deployed ndlaw instance over Streamable HTTP (`NDLAW_URL` + `NDLAW_AUTH` env, or `--url`/`--auth`; for Claude Code users the URL and Basic-Auth header are in their MCP config — `claude mcp get ndlaw`). The script speaks to the server directly, so no opinion text passes through model context.
```bash
$VENV_PYTHON "${CLAUDE_SKILL_DIR}/ndlaw_export.py" \
  --opinion <opinion_md_path> \
  --refs-dir ~/refs \
  --meta-out <TMPDIR>/sources.json
```
    Exit 2 means no backend was reachable (typical in Cowork, where neither the corpus DB nor `NDLAW_URL` exists). **Fall back to a scribe subagent riding the in-context MCP connection** — if ndlaw tools are available:

    1. From the cite JSON, list the corpus-eligible authorities that still lack refs text: case entries (not `pin_cite`, not `is_repeat`) whose `normalized` is an ND neutral cite (`YYYY ND N`) or N.W.-family reporter cite, with `local_exists` false.
    2. Launch **one** subagent (Task tool, `model: haiku`, subagent_type `general-purpose`) with that list and these instructions: for each citation, call `lookup_opinion(<cite>)` and record `case_name`, `url`, `url_source`, `date_filed`, and `citations`; then page through `get_opinion_text(<cite>, offset=..., limit=50000)` until `has_more` is false and **Write the concatenated text verbatim** (do not summarize, reformat, or strip the frontmatter block) to the refs path: `~/refs/opin/ND/<year>/<year>ND<n>.md` for `YYYY ND N`; `~/refs/opin/NW2d/<vol>/<page>.md` for `V N.W.2d P` (analogously `NW3d`, `NW`). Finally Write `<TMPDIR>/sources.json` mapping **every** citation form from `citations` to `{"case_name", "url", "url_source", "date_filed", "via": "ndlaw"}`, and return only a tally ("N exported, M not in corpus") — never opinion text.
    3. The token cost stays inside the subagent's isolated context (and within the subscription); main context must never page opinion text through its own tool results just to embed it.

    If MCP tools are also unavailable, skip `--sources-meta` below and fall through silently (never stall on this step) — or, at most, build a minimal `sources.json` from one cheap `lookup_opinion` call per unique ND case (URL + case name only) if a stray connection allows it.

    **11b. Generate the page.** Write a `via.json` mapping each citation (as written, or its normalized form) to the tier from the Pass 3B **Via** column — e.g. `{"2024 ND 156": "ndlaw", "445 U.S. 684": "CourtListener", "N.D.C.C. § 14-05-24": "local"}`:
```bash
$VENV_PYTHON "${CLAUDE_SKILL_DIR}/cite_review.py" \
  --opinion <opinion_md_path> \
  --refs-dir ~/refs \
  --title "<case caption>" \
  --via-json <TMPDIR>/via.json \
  --sources-meta <TMPDIR>/sources.json \
  --passages-json <TMPDIR>/passages.json \
  --facts-json <TMPDIR>/facts.json \
  --case-dir <working_dir> \
  --record-dir <record_item_dir> \
  --output <output_dir>/cite-review.html
```
Omit `--via-json` if Pass 3B did not run or produced no table; omit `--sources-meta` if step 11a exported nothing; omit `--passages-json` if Pass 3B wrote no passages ledger. Omit `--facts-json` if Pass 4 did not run or wrote no facts ledger. `--case-dir` is the working directory holding the case PDFs (pass it because the opinion markdown lives in TMPDIR); a `manifest.json` there is picked up automatically for docket-number and brief-name resolution. Pass `--record-dir` when a directory of district-court record items (`R<N> - <Type> <Title>.pdf`) is present — record cites like "R243" then resolve to embedded PDF viewers opened at the cited page with the evidence quote highlighted. `--link-pdfs` swaps the embedded viewers for zero-copy native iframes if sidecar size is a concern.

**Local-PDF authorities.** If a cited authority has no online or refs source but a PDF copy sits in the working directory (an obscure treatise, an out-of-state slip opinion, a session-law scan), add to the step 11a `sources.json` entry for that citation: `"pdf": "<path relative to the working dir>"`, plus optional `"page": N` and `"quote": "<verbatim passage>"`. The review page then offers a "Local PDF" source mode with the same embedded viewer, opened at the page/quote. This produces a self-contained HTML file that lists **every citation occurrence** — first full cites, repeat full cites, short forms, and *id.* references each as a separate reviewable entry — highlighting the exact occurrence in the draft pane and showing the cited authority (embedded text scrolled to the pinpoint ¶, or the Pass 3B verification passage) in the source pane. Tell the user the file is available and can be opened in a browser.

**If the opinion is a .docx file:** its text was already extracted in step 3 via `extract_text.py`; apply edits directly to the **original** .docx with `apply_edits.py` (no unpack/pack, no docx plugin).

**Single-session editing.** All tracked changes and comments must be applied in a single `apply_edits.py` execution against the original .docx. Do not run apply_edits.py → edit its output → run it again on that output. Multiple cycles cause ID collisions and orphaned artifacts. If retrying, start fresh from the original .docx.

**If the opinion is plain text or another format:** create a new .docx using the docx skill, with tracked-change markup showing all edits.

#### Step 9 Details: Batch Edit Workflow

**9a. Collect all edits into a JSON file.** Gather Pass 2 edits (style/grammar), Pass 3A edits (citation format), and Pass 5 edits (analytical rigor) into a single JSON array:
```json
[
    {
        "type": "replace",
        "para": 3,
        "old": "It is well settled that the court must consider",
        "new": "The court must consider",
        "comment": "Cut throat-clearing (Redbook § 11.3)"
    },
    {
        "type": "replace",
        "para": 7,
        "old": "and/or",
        "new": "or",
        "comment": "Never use 'and/or' (Redbook § 11.2)"
    },
    {
        "type": "comment",
        "para": 12,
        "anchor": "we find that",
        "comment": "Consider replacing 'we find' — implies independent factfinding under clear-error review"
    }
]
```
Write this JSON to `<TMPDIR>/edits.json`.

**9b. Run apply_edits.py** directly on the original .docx (no unpack step):
```bash
$VENV_PYTHON $SKILL_DIR/apply_edits.py --input <input.docx> --edits <TMPDIR>/edits.json --author "Claude" --output <output.docx>
```

The script operates directly on the .docx ZIP archive — no unpack/pack pipeline, no dependency on the docx plugin. It:
- Reads document.xml from the original ZIP
- Applies all tracked changes and comments via DOM manipulation
- Serializes XML as UTF-8 with `standalone="yes"`
- Builds the output ZIP preserving original entry metadata
- Produces files Word opens cleanly (no encoding or ZIP metadata issues)

**9c. Check the output.** Parse the JSON summary from apply_edits.py. If any edits failed, report them.

**9d. Citation hyperlinks (optional).** When the user asks for clickable / linked citations, add `hyperlink` edits to the same `edits.json` — one per citation, anchored to the citation text, using the verified URL (prefer ndlaw `absolute_url`, else the CourtListener URL, else the `url` from `cite_check.py`):
```json
{ "type": "hyperlink", "para": 12, "anchor": "2024 ND 45", "url": "https://www.ndcourts.gov/..." }
```
Hyperlinks are a **non-tracked formatting overlay** — they wrap existing text (no tracked change) and are skipped automatically if the anchor is already inside a link or a tracked change. Only link citations that **passed** verification; never link an unverified or flagged cite. Requires .docx output (not available in web/analysis-only mode).

The agent's job is: collect edits into JSON (1 Write call), run one command (1 Bash call).

**Web mode workflow:**
1. Read `references/style-guide.md` from project knowledge. If not found, tell the user to upload it.
2. Skip docx skill files (not needed without .docx output).
3. Read the draft from the conversation (pasted text or uploaded file).
4. Perform Pass 1 inline.
5. Perform Pass 2 inline (regardless of length).
6. Perform Pass 3A (format) inline. Perform Pass 3B (verification) inline with web search fallback.
7. Perform Pass 4 inline if the user uploaded source PDFs. Read them directly.
8. Perform Pass 6 (brief matching) inline if the user uploaded briefs.
9. Perform Pass 7 (dissent cross-check) inline if the user uploaded a dissent/concurrence and `DOC_TYPE == opinion`.
10. Perform Pass 5 inline.

For each delegated pass performed inline (1, 3B, 4, 6, 7 — and 2's entry format), read its instruction file from project knowledge (`references/pass-instructions/passN-*.md`) and apply it, adapting CLI-only steps (shell commands, `~/refs/`, ledger files) per the pass's Web-mode note.
11. Skip .docx assembly.
12. Produce the analysis document as markdown in the conversation.

**Context limits:** Without subagents, very long documents (50+ paragraphs) may approach context limits. If this occurs, prioritize: Pass 2 → Pass 5 → Pass 3A → Pass 1 → Pass 3B → Pass 4 → Pass 6 → Pass 7. Inform the user which passes were completed.

## Legal-Research MCP Servers (ndlaw, CourtListener)

Two optional MCP servers improve citation verification when connected. **They are augmentation, not replacement** — every check below degrades gracefully to the existing pipeline (`cite_check.py` + `~/refs/` + `WebFetch` + web search). Never fail or stall a task because an MCP server is absent or returns no data.

**Availability:** Before relying on a server, check whether its tools are present in your tool set (e.g. an `ndlaw` tool such as `verify_citation`, or a CourtListener tool such as `verify_citations`). If a tool is not available, skip silently to the next tier.

**Source precedence — apply at every case-citation check; fall through on a miss:**
1. **ndlaw** (primary, North Dakota cases) — local ND opinion corpus. Deterministic, no network.
2. **CourtListener MCP** (secondary) — case data ndlaw lacks: federal and out-of-state authorities, and ND opinions missing from the ND corpus.
3. **Existing pipeline** (fallback) — `cite_check.py` / `~/refs/` / `WebFetch` / web search. Always available in CLI mode; the only path when no MCP server is connected.

**Out of scope for both servers:** authoritative text of statutes, court rules, the constitution, and NDAC — these always resolve through the existing pipeline.

**ndlaw tools and the fields used below:**
- `verify_citation(query, expected_case_name=...)` → `found`, `canonical_case_name`, `formatted` (full Redbook cite), `cites_redbook`, `absolute_url`; when `expected_case_name` is supplied, also `name_matches` (bool) and `name_similarity` (0–1). Catches wrong volume/page/year and name drift.
- `verify_quotation(citation, quote)` → `verbatim` (bool), `paragraph` (pinpoint ¶, generally 1997+), `differences` (word-level diff), `closest_text`. Typography-tolerant (curly/straight quotes, dashes, whitespace).
- `detect_overruled_in_draft(draft_text)` → `flagged` (cited cases with possible negative/distinguished treatment, each with `treatment_entries` + citing context), `clear`, `unresolved`. **Advisory only.**

**Cardinal caution:** ndlaw is a research aid, not an authoritative text; treatment signals and the `antecedent_name` heuristic are best-effort. Use them to *flag for human review*, never to auto-edit on the signal alone.

## Editing Instructions

Adopt the persona of an experienced appellate attorney working for a state supreme court. Be careful and precise.

### Pass 1: Jurisdictional Check (Delegated to Subagent)

**Do not** read `references/nd-appellate-rules.md` or the pass-instruction file into the main context. Delegate to a Task subagent (subagent_type: `general-purpose`) with a prompt of this form:

> Read `${CLAUDE_SKILL_DIR}/references/pass-instructions/pass1-jurisdiction.md` and follow the **[opinion / memo]** variant. The skill root is `${CLAUDE_SKILL_DIR}`. The draft is at `[path]`. Return only the concise findings summary those instructions specify.

**Returns:** a concise summary of jurisdictional, procedural-posture, or standard-of-review findings — or an explicit all-clear. The memo variant may instead return a warning that the memo should confirm appellate jurisdiction.

**Web mode:** Perform inline. Read `references/pass-instructions/pass1-jurisdiction.md` and `references/nd-appellate-rules.md` from project knowledge and apply the matching variant. If the rules file is unavailable, use web search to find the relevant N.D.R.App.P. rules at ndcourts.gov. Report findings in the same format.

### Pass 2: Style and Grammar
Apply in priority order. Full details in `references/style-guide.md`.

**Hard rules (always apply):**
- Active voice unless passive genuinely improves readability
- Never use plural pronouns as gender-neutral singular — use he, she, it, or rephrase, but never guess an individual's gender and do not use the masculine as an archaic gender neutral
- Never use "and/or"
- Never use legalese such as: herein, wherefore, aforementioned, said/such/same as pronouns
- Never use Latin-derived words when plain English carries equal precision
- Always use the Oxford comma
- Constitutions protect, guarantee, or preserve rights — never "create" or "grant" (unless the text clearly declares a new right)
- Replace any ordinary space following a paragraph symbol (¶) or section symbol (§) with a nonbreaking space (Unicode U+00A0). In OOXML, use `&#160;` in the XML text. Apply as tracked changes in the output.

**Style preferences (apply with judgment):**
- Lead with the point; conclusion before reasoning
- Short sentences for holdings; vary length elsewhere
- Cut throat-clearing ("It is well settled that," "It should be noted that")
- Cut nominalizations; prefer verb forms
- Keep subject and verb close
- One idea per sentence when practical
- Short paragraphs (under 200 words) in analytical sections
- Use "less" for uncountable nouns and "fewer" for countable nouns

#### Delegated Pass 2 (opinions over 30 paragraphs)

When the opinion exceeds 30 paragraphs, delegate Pass 2 to a Task subagent (subagent_type: `general-purpose`) to keep main-context output tokens manageable, with a prompt of this form:

> Read `${CLAUDE_SKILL_DIR}/references/pass-instructions/pass2-style.md` and follow it. The skill root is `${CLAUDE_SKILL_DIR}`. The draft opinion is at `[path]`. Return only the structured entry list those instructions specify.

**Returns:** a structured list of `¶ / OLD / NEW / REASON` edit entries and `¶ / COMMENT / ANCHOR` comment entries, in paragraph order.

**In main context after collection:** Apply the returned edits mechanically when building the tracked-changes OOXML in step 9. Each `OLD`/`NEW` pair becomes a tracked deletion + tracked insertion. Each `COMMENT` entry becomes a document comment anchored to the specified text.

**Web mode:** Always perform inline, regardless of document length. Apply the same rules. Use the structured entry format (¶, OLD, NEW, REASON) for internal tracking, then incorporate into the analysis document.

### Pass 3: Citation Check (Delegated to Subagent)

Pass 3 has three parts: (A) Bluebook format checking, in main context; (B) substantive citation verification, delegated to a subagent; and (C) a negative-treatment / overruling scan, in main context. Parts B and C use the ndlaw / CourtListener servers as the primary source when available — see "Legal-Research MCP Servers" above — and fall back to local files plus web verification otherwise.

#### Part A: Format Check (Main Context)

Perform these checks in main context as part of Passes 2/5 work:
- Verify Bluebook format for all citations
- Check ND-specific conventions — read `references/nd-citation-style.md` (the Court's Redbook supplement: era-specific forms, `ND` vs `ND App`, the no-reporter-pin-cite rule in a public-domain parallel, short forms, `Id. at ¶ N`, N.D.C.C. / N.D.R.C. / session laws). Non-ND formats stay in `references/style-guide.md`.
- Verify pinpoint citations include paragraph or page numbers
- Check signal usage (see, see also, cf., but see, accord)
- Confirm case names are italicized

#### Part B: Substantive Citation Verification (Delegated to Subagent)

Pass 3B verifies ALL North Dakota citations — cases, statutes, constitution, court rules, and administrative code — not just case citations.

**Preparation (in main context):** After reading the opinion, extract a numbered list of every ND citation. For each, record:
- The paragraph (¶) where the citation appears
- The full citation text
- The proposition the citation is used to support (the sentence or clause preceding the citation)
- Whether the opinion quotes the source (and if so, the exact quoted text)
- The signal used (none, *See*, *see also*, *cf.*, *but see*, *accord*, etc.)

**Delegation:** Launch a Task subagent (subagent_type: `general-purpose`) with a prompt of this form:

> Read `${CLAUDE_SKILL_DIR}/references/pass-instructions/pass3b-citations.md` and follow it. The skill root is `${CLAUDE_SKILL_DIR}`; the venv python is `[the $VENV_PYTHON value from Step 0]`. The opinion file is at `[opinion_path]`; write the passages ledger to `<TMPDIR>/passages.json`. Here is the extracted citation list: [numbered list — ¶, citation text, proposition, quoted text if any, signal].

**Returns:** the results table (`¶ | Citation | Type | Caption Check | Quote Check | Supports? | Via | Source Link | Notes`), a summary line with counts by type, the lookup-methods tally for case citations (`ndlaw / CourtListener / local / web / not found`), and an ND web-fallback note. The subagent also writes `<TMPDIR>/passages.json` (the passages ledger embedded in the citation-review HTML). Carry the tally and note into the analysis document alongside the results table. The instructions enforce the closed-loop case-name rule (correct same-cite typos only; never harmonize different citations) — Step 8a depends on the resulting Caption Check column and `name_similarity` values.

**Web mode:** No shell, Python, or `~/refs/` — but the MCP servers, if connected, are the primary way to verify case citations here.
1. **If ndlaw / CourtListener tools are available, use them first**, following Step 1.5 of `references/pass-instructions/pass3b-citations.md` (read it from project knowledge — verify_citation for caption/existence/name drift, verify_quotation for quotes); run Part C's `detect_overruled_in_draft` too. This closes the gap where case citations otherwise can't be verified without a filesystem.
2. For ND citations the MCP servers don't cover, use WebFetch on the official URL (build it from the citation, or run `cite_check.py` if any shell is available).
3. For ND case citations, use web search to locate the opinion on ndcourts.gov or Google Scholar.
4. Verify quotes and substantive support as described above.
5. If a source cannot be retrieved, mark as "Not verified — source unavailable."
6. Note in the Citation Verification section: "Citations verified via URL lookup against official sources. Local reference files unavailable."

#### Part C: Negative-Treatment / Overruling Scan (Main Context)

A proofreading pass that flags cited cases later opinions may have overruled, superseded, abrogated, or distinguished. jetredline has no other "still good law?" check, so this is purely additive.

**If the `detect_overruled_in_draft` tool is available** (ndlaw), call it once on the full draft text:
- Pass the draft opinion/memo text as `draft_text`.
- From the result, take `flagged` (each entry has the cited case, a treatment signal, and `treatment_entries` with the citing opinion and sentence-local context). `clear` and `unresolved` are informational.
- For each flagged case, queue a **comment** (handled in Step 8b) on each occurrence in the draft, quoting the citing context and the citing opinion. **Never** convert a treatment signal into a tracked-change edit.
- In the analysis document, add a short "Negative-treatment check" subsection: list flagged cases with their signal and citing opinion, and note that `unresolved` cites (federal, out-of-state, or not in the ND corpus) were **not** checked.

**Caution:** Signals are sentence-local heuristics, not a verdict — a citing sentence may use a treatment word about a *different* case. Always present them as "possible negative treatment — verify," and read the cited opinion before relying on it. An absent flag is not assurance a case is good law.

**If the tool is unavailable:** skip this part and note in the analysis document: "Automated negative-treatment check not run (ndlaw unavailable); citations were not screened for subsequent history." Do not attempt to substitute web search for a citator here.

### Pass 4: Fact Check (Delegated to Subagent)

When the user provides briefs, record documents, or other source materials alongside the draft opinion, **do not** read the PDF materials into the main context. Delegate fact-checking to a subagent to keep potentially large PDF content out of the main context window.

**Preparation (in main context):** After reading the opinion, extract a numbered list of verifiable factual claims with paragraph references. Include:
- Dates, names, places, and sequences of events
- Procedural history (filings, motions, rulings, verdicts, sentences)
- Descriptions of testimony or evidence
- Characterizations of parties' arguments
- Statements about the record (e.g., "Davis did not object," "the jury was instructed")

Do **not** include: legal standards and rules (checked in Passes 1 and 3), the court's own reasoning and conclusions, or general statements of law from cited cases.

**Claim-to-record mapping:** For each claim, also extract any record citations from the opinion text (e.g., "R 58," "App. 42," "Doc. 12," "Tr. 145"). Include these as a `Cited Records` column in the claims list passed to the subagent. This lets the subagent check the cited record items first, but the subagent should also search other record items — record citations in draft opinions are not always complete or accurate.

**Delegation:** Launch a Task subagent (subagent_type: `general-purpose`) with a prompt of this form:

> Read `${CLAUDE_SKILL_DIR}/references/pass-instructions/pass4-factcheck.md` and follow it. The skill root is `${CLAUDE_SKILL_DIR}`. Write the structured facts ledger to `<TMPDIR>/facts.json`. The source PDFs are: [paths, each with its Step 0 ingestion outcome]. Here is the numbered claims list (¶ refs and Cited Records column included): [claims list].

**Returns:** the fact-check results table (`¶ | Claim | Source Document(s) | Result | Notes`) with a summary line, plus an **Ingestion Status table** (one row per source PDF: `Source file | Pages | Ingestion | Method`) that Step 11 reconciles for coverage. The instructions include the full detection + OCR recovery ladder, so image-only files are recovered, not skipped; a `not-ingested` or `OCR-low-confidence` file means its dependent facts are unverified, and the subagent says so plainly.

**No source materials:** If the user does not provide source materials, skip delegation. Note this limitation in the analysis and flag any factual assertions that cannot be independently verified.

**Web mode:** If the user uploaded PDF source materials, read them directly (no pdftotext needed). Perform fact-checking inline. For large documents, focus on the extracted claims rather than reading entire files. If no source materials were uploaded, note this limitation.

### Pass 6: Brief Matching (Delegated to Subagent)

When briefs are available (identified in Step 0), check whether the opinion or memo addresses every argument raised by the parties. This pass applies to both `opinion` and `memo` document types.

**Do not** read the briefs into the main context. Delegate to a subagent to keep PDF content out of the main context window.

**Delegation:** Launch a Task subagent (subagent_type: `general-purpose`) with a prompt of this form:

> Read `${CLAUDE_SKILL_DIR}/references/pass-instructions/pass6-brief-matching.md` and follow it. The skill root is `${CLAUDE_SKILL_DIR}`. The draft document is at `[path]`; the party briefs are: [brief paths, each with its Step 0 ingestion outcome].

**Returns:** the brief-matching table (`¶ | Argument | Party | Brief Source | Addressed | Notes` — Yes/Partial/No per argument, with brief page ranges) with a summary line, plus an **Ingestion Status table** (one row per brief) that Step 11 reconciles for coverage. The instructions include the full detection + OCR recovery ladder; an unreadable brief is reported as **coverage unverified** for that party, never silently skipped.

**No briefs available:** If no briefs were provided in Step 0, skip this pass entirely. Note in the analysis document: "No briefs provided — brief matching skipped."

**Web mode:** If the user uploaded briefs, perform inline — read the briefs directly and follow the extraction and matching process in `references/pass-instructions/pass6-brief-matching.md` (from project knowledge; the pdftotext/OCR steps do not apply). If no briefs were uploaded, note the limitation.

### Pass 7: Dissent/Concurrence Cross-Check (Delegated to Subagent)

When a dissent or concurrence is provided alongside the majority opinion, cross-check for fair characterization and responsiveness. The aim is to ensure all opinions in a case fairly and accurately characterize other opinions, maintain constructive engagement on the substantive merits of the points of disagreement, and reveal to a discerning reader the crux of any disagreement between the opinions. This pass applies **only** when `DOC_TYPE == opinion` and a dissent or concurrence file was identified in Step 0.

**Do not** read the dissent/concurrence into the main context. Delegate to a subagent to keep the separate document out of the main context window.

**Delegation:** Launch a Task subagent (subagent_type: `general-purpose`) with a prompt of this form:

> Read `${CLAUDE_SKILL_DIR}/references/pass-instructions/pass7-dissent-crosscheck.md` and follow it. The skill root is `${CLAUDE_SKILL_DIR}`. The majority opinion is at `[majority path]`; the dissent/concurrence is at `[dissent path]`.

**Returns:** the cross-check table (`¶ Majority | ¶ Dissent | Argument | Fair Characterization? | Addressed? | Notes`) and a summary counting dissent arguments reviewed, fair characterizations, potential straw-manning, unaddressed criticisms, and dissent mischaracterizations of the majority.

**No dissent/concurrence available:** If no dissent or concurrence was identified in Step 0, or `DOC_TYPE != opinion`, skip this pass entirely.

**Web mode:** If the user uploaded a dissent/concurrence alongside the majority, perform inline — read both documents directly and follow the cross-check process in `references/pass-instructions/pass7-dissent-crosscheck.md` (from project knowledge). If no dissent was uploaded, note the limitation.

### Pass 5: Analytical Rigor

Perform the following checks on **all documents** (both opinions and memos), then the DOC_TYPE-specific checks below. Full details for both document types are in `references/style-guide.md`.

#### Internal Consistency Check (all doc types)

Read the entire document and build a mental index of: party names (including aliases and roles), dates, monetary amounts, numerical counts, procedural events, and terminology choices. Compare every reference to each entity, date, and event across the document. Flag any discrepancy with paragraph references for both the first usage and the inconsistent usage.

Check for:
- **Name/spelling inconsistencies** (e.g., "Johnson" vs "Johnsen", "Meier" vs "Meyer"). **Exclude case names** — party names in cited cases are verified in Pass 3B against official captions. Only flag non-case-name spelling inconsistencies here (party names in the case being decided, witness names, place names, ordinary words).
- **Date inconsistencies** (same event assigned different dates in different paragraphs)
- **Terminology drift** (switching between "defendant"/"respondent", "trial court"/"district court" without reason)
- **Factual contradictions** (facts section says X, analysis section says Y)
- **Numerical inconsistencies** (amounts, counts, timelines that don't add up)
- **Caption/party inconsistencies** (parties named differently in caption vs body)

Distinguish intentional variation from apparent errors. Referring to "Smith" in the facts and "the appellant" in the analysis is fine; "Smith" becoming "Smyth" is a flag.

#### Standard of Review Consistency Check (all doc types)

Identify every standard of review stated in the document and which issue(s) each applies to. For each analytical section, identify the language of deference (or lack thereof). Flag each instance where the analysis language is inconsistent with the stated standard, citing the paragraph.

Standard-specific red flags:
- **De novo:** Acceptable language includes "we conclude," "we hold," independent analysis. No deference language needed.
- **Clear error:** Requires deference. Red flags: reweighing evidence, making independent credibility determinations, "we find" (implies independent factfinding), "we would have decided differently."
- **Abuse of discretion:** Requires deference. Red flags: substituting the court's judgment, applying a legal standard de novo when the question is discretionary.
- **Plain error:** Must show (1) error, (2) clear/obvious, (3) affecting substantial rights, (4) seriously affecting fairness/integrity/public reputation. Flag if any prong is skipped.
- **Reasoning mind:** In administrative agency appeals, a deferential standard for "reasoning mind reasonably could conclude" applies.

For opinions: Does the court *apply* the standard it *stated*?
For memos: Does the memo correctly identify the standard *and* apply it consistently in the recommendation?

In multi-issue documents where each issue has a different standard, verify each standard is applied to the correct issue.

#### Statutory-Construction Cross-Check (when ndlaw is available)

When the draft construes an N.D.C.C. section or a court rule as a point of decision, call `find_opinions_construing(<authority>)` and scan the returned `results[].opinions` for ND opinions construing the same provision. Use it as an advisory aid: if a recent or obviously on-point construction is missing from the draft's analysis, note it for the author's consideration (do not assert it is controlling). Skip silently if the tool is unavailable. For a key *cited* precedent whose holding the draft leans on, `case_summary(<cite>)` (disposition + `syllabus_points`) can confirm what the case actually held — this aids the substantive-support assessment; it does **not** feed the draft's own Case Highlight, since the draft is not in the corpus.

#### Readability Metrics (all doc types)

**CLI mode:** Run the readability metrics script on the document:
```bash
$VENV_PYTHON "${CLAUDE_SKILL_DIR}/readability_metrics.py" --file <document_path>
```
Parse the JSON output and incorporate the results into the analysis document (see Readability Metrics section in the output template). Flag any sentences over 40 words, sections with passive voice above 25%, and sections with FK grade above 16.

**Web mode:** Skip the script (no Bash available). If feasible, estimate sentence length and passive voice inline for the longest/densest sections. Otherwise, note: "Readability metrics unavailable in web mode."

#### If DOC_TYPE is `opinion` (default)

- Flag potential dicta (statements unnecessary to the holding)
- Flag unnecessary alternative rationales
- Identify logical fallacies
- Identify ambiguities — especially passages easily quoted out of context
- Read from the losing party's perspective: what would a critic seize on?
- Flag holdings broader than necessary
- Flag vague standards lacking guidance for future application
- **Draft case highlight:** Generate a 50–200 word case summary for the analysis document. Extract: case name and citation (from the caption/header), nature of the dispute (one sentence), disposition (affirmed/reversed/remanded/modified with brief outcome), and 1–3 core holdings. This is a synthesis task — perform it in main context, not delegated.

#### If DOC_TYPE is `memo`

- **Issue completeness:** Did the memo identify all issues raised on appeal? Are there issues the parties didn't raise but the court should consider (e.g., plain error, jurisdictional defects)?
- **Balanced presentation:** Does the memo fairly state each side's strongest arguments? Does it steelman the weaker position or dismiss it too quickly?
- **Recommendation quality:** Are recommendations clearly stated? Is each recommendation supported by the analysis? Are alternative outcomes acknowledged?
- **Analytical gaps:** Are there unstated assumptions? Logical fallacies? Missing steps in the reasoning chain?
- **Standard of review:** Does the memo correctly identify and consistently apply the appropriate standard of review for each issue?
- **Order-grounding check (did the memo read the order, or guess?):** Scan every statement about the **district court's ruling, findings, grounds of decision, or reasoning**. Flag two patterns:
  1. **Uncited characterization** — a claim about what the district court held, found, or reasoned that carries **no pinpoint citation to the order/judgment** (e.g., "R38:2–9"). A bench memo's account of the ruling should be anchored to the order itself.
  2. **Hedged reasoning** — phrases like "the district court *appears to* have," "*seems to* have," "*evidently*," or "*presumably*" applied to the lower court's reasoning. These usually mean the order was not read but inferred from the briefs.
  
  For each flag, note the ¶ and the suspect language. If source materials are available (Pass 4 ran on the order/record), check whether the order actually resolves the point and report the correct grounds with a pinpoint cite. Treat a cluster of these flags as a signal that the memo may have been drafted from the briefs without reading the order — say so explicitly in the analysis, since that is a serious bench-memo defect. (This is advisory: a properly preserved record gap is legitimate, but it should be stated as a gap, not hedged.)

### Step 11: Coverage Reconciliation & Acknowledgment Gate

Before producing any final output, reconcile the **inputs identified in Step 0** against the **inputs actually ingested** (from the Ingestion Status tables returned by Passes 4 and 6). An input counts as **not fully ingested** if its status is `not-ingested` **or** `OCR-low-confidence`. Always emit one ledger line:

> **Inputs ingested: N of M.** [If N < M, list each miss: `Reply-Brief.pdf` (image-only; OCR-low-confidence), …]

**Acknowledgment gate — fires only when N < M.** If any identified input was not fully ingested, do **not** present the run as complete. Name the file(s), the reason (no text layer / image-only / garbled OCR), and the affected passes (Pass 4 fact-check, Pass 6 brief-matching), then ask the user to acknowledge that coverage is incomplete before final outputs are produced. Use `AskUserQuestion` (CLI) or a direct question (Web). When N < M you must also render the `## ⚠ Source Materials Not Reviewed` section (see below) and use the incomplete-coverage form of the Step 12 header.

> **This is an exceptional-condition gate, not a scope or depth question.** It is the *only* sanctioned interactive pause besides the Step 0.1 doc-type question. Do not generalize it, and never use it to offer pass selection. When N == M, skip it silently and proceed.

**Audit mode:** do not prompt. Instead surface any not-fully-ingested input under a `### Coverage` heading in Part 2 and reflect it in the final summary line.

## Output Format

**Web mode:** Produce only the analysis document as markdown in the conversation. The tracked-changes .docx section does not apply. The analysis document template and structure are the same.

Produce the outputs requested by the user in Step 0.5.

### Tracked-changes .docx (if requested)
Use `apply_edits.py` to produce a .docx with:
- Deletions as tracked deletions (author: "Claude")
- Insertions as tracked insertions (author: "Claude")
- Comments for substantive notes — explaining a change or flagging an issue

**Assembly workflow:** Use the batch edit workflow in Step 9 above. `apply_edits.py` operates directly on the .docx ZIP — no unpack/pack pipeline needed. The script is fully self-contained (no docx plugin dependency).

### Analysis document (if requested)
Produce a document structured as below, then **save it to a markdown file** in the working directory (not the temp directory). Use the naming pattern `<original-filename>-ANALYSIS.md` (e.g., `Estate-of-Kish_Opinion-ANALYSIS.md`). This ensures the analysis survives context compression and can be opened after the session.

The **Substantive Concerns** section varies by `DOC_TYPE`.

**If DOC_TYPE is `opinion`**, place the Case Highlight first:

```
–Begin Analysis–

## Case Highlight

**[Case Name], [Citation]**
**Nature:** [One-sentence description of the dispute type]
**Disposition:** [Affirmed/Reversed/Remanded/Modified — with brief outcome]
**Holdings:**
- [Core holding 1]
- [Core holding 2]
- [Core holding 3, if applicable]

[50–200 word summary synthesizing the case's significance, essential facts, and primary legal principles.]
```

**If DOC_TYPE is `memo`**, begin directly with Jurisdictional Notes.

**Source-materials warning (conditional — render whenever Step 11 found N < M).** Immediately after the Case Highlight (opinion) or before Jurisdictional Notes (memo), insert the following. Omit the section entirely when every identified input was fully ingested:

```
## ⚠ Source Materials Not Reviewed

One or more provided source files could not be fully read. Fact-check and brief-coverage findings below are **incomplete** for the listed material.

| File | Reason | Passes affected | Remediation |
|---|---|---|---|
| [file.pdf] | image-only / no text layer (or OCR-low-confidence) | Pass 4, Pass 6 | OCR attempted (ocrmypdf) — failed / low-confidence; recommend manual review or re-OCR |

**Inputs ingested: N of M.**
```

**Both document types continue with:**

```
–Begin Analysis– [if memo, or continuation after Case Highlight if opinion]

## Jurisdictional Notes
[Issues with timeliness of appeal, procedural posture, or standard of review]
[If DOC_TYPE is memo and jurisdiction was not addressed: include warning here]

## Summary of Edits
[Brief overview of the types and volume of changes]

## Fact Check

| ¶ | Claim | Source Document(s) | Result | Notes |
|---|-------|-------------------|--------|-------|
| [¶ ref] | [Factual assertion from document] | [Record doc, brief, or transcript with pinpoint cite] | Verified / Unverified / Discrepancy | [Explanation if discrepancy or unverified] |

**Summary:** [X] facts checked. [Y] verified. [Z] discrepancies. [W] unverified. [If any source not fully ingested: "Coverage incomplete — [file] not reviewed; see ⚠ Source Materials Not Reviewed."]

## Brief Matching

| ¶ | Argument | Party | Brief Source | Addressed | Notes |
|---|----------|-------|-------------|-----------|-------|
| [¶ ref] | [Argument/contention] | [Appellant/Appellee] | [Brief, pp. X–Y] | Yes / Partial / No | [Explanation] |

**Summary:** [X] arguments identified. [Y] directly addressed. [Z] partially addressed. [W] not addressed. [If any brief not fully ingested: "Coverage incomplete — [brief] not reviewed; that party's arguments are unverified. See ⚠ Source Materials Not Reviewed."]

[Or: "No briefs provided — brief matching skipped."]
```

**Both document types include these sections after Brief Matching:**

```
## Internal Consistency

| ¶ | Item | First Usage | Inconsistent Usage | Notes |
|---|------|-------------|-------------------|-------|
| [¶ refs] | [Name/date/term] | [First form, ¶ ref] | [Different form, ¶ ref] | [Explanation] |

[Or: "No internal inconsistencies detected."]

## Standard of Review Consistency

**Standards identified:**
- Issue 1: [standard] (¶ [ref])
- Issue 2: [standard] (¶ [ref])

| ¶ | Issue | Stated Standard | Language Used | Concern |
|---|-------|----------------|---------------|---------|
| [¶] | [Issue] | [Standard] | [Problematic phrase] | [Why this is inconsistent with the standard] |

[Or: "Standards of review applied consistently throughout."]

## Readability Metrics

**Overall:** Flesch-Kincaid Grade [X] · Avg sentence length [X] words · Passive voice [X]% · Nominalization density [X]/100 words

| Section | ¶¶ | FK Grade | Avg Sentence | Longest Sentence | Passive % | Nominalizations |
|---------|-----|----------|-------------|-----------------|-----------|-----------------|
| [section] | [range] | [grade] | [avg] | [max] | [pct] | [density] |

**Flags:**
- [List of flagged items with ¶ references]

[Or: "All sections within normal ranges."]
```

**If DOC_TYPE is `opinion`:**

```
## Substantive Concerns

### Potential Dicta
[List with paragraph references]

### Alternative Rationales
[Whether each ground is fully developed]

### Ambiguity and Vulnerability
[Passages quotable out of context; vague standards; overly broad holdings]

### Logical Issues
[Logical fallacies or unstated assumptions]

### Dissent/Concurrence Cross-Check

| ¶ Majority | ¶ Dissent | Argument | Fair Characterization? | Addressed? | Notes |
|-----------|-----------|----------|----------------------|------------|-------|
| [¶] | [¶] | [Criticism or argument] | Yes / No / Partial | Yes / No / Partial | [Explanation] |

**Summary:** [X] dissent arguments reviewed. [Y] fairly characterized. [Z] potential straw-manning. [W] unaddressed criticisms.

[Or: "No dissent/concurrence provided."]
```

**If DOC_TYPE is `memo`:**

```
## Memo Analysis

### Issue Completeness
[Issues raised on appeal; issues not raised but potentially relevant (plain error, jurisdictional defects)]

### Balance of Presentation
[Whether each side's strongest arguments are fairly stated; steelmanning assessment]

### Recommendation Assessment
[Clarity and support for each recommendation; alternative outcomes acknowledged]

### Analytical Gaps
[Unstated assumptions, logical fallacies, missing reasoning steps]

### Standard of Review Application
[Whether the memo correctly identifies and consistently applies the standard of review for each issue]
```

**Both document types continue with:**

```
## Citation Verification

| ¶ | Citation | Type | Quote Check | Supports? | Source Link | Notes |
|---|----------|------|-------------|-----------|-------------|-------|
| [¶] | [Citation text] | Opinion / Statute / Const. / Rule / Admin. | Verified / Discrepancy / No quote / Not found | Supports / Partially / Does not support | [Markdown hyperlink: `[normalized](url)` from lookup plan] | [Explanation] |

**Summary:** [X] ND citations checked, by type: [opinions/statutes/const/rules/admin]. [Y] quotes verified. [Z] quote discrepancies. [W] not found. [V] unsupported propositions.

## Citation Format Issues
[Citation-format corrections with explanations]

## Style Notes
[Significant style changes by category]

---
*Claude skills crafted by Claude and JET (github.com/jet52)*

–End Analysis–
```

Do **not** hand-write a version/date line in the footer — the provenance stamp (Step 10a, `provenance.py`) appends the authoritative model/version/date line in CLI mode. In web mode, append it manually per Step 10a.

### Citation review HTML (CLI and Cowork, always generated)

After Pass 3 completes and the opinion markdown is available, generate the interactive citation review page by running **Step 11a** (ndlaw export, with its scribe-subagent fallback) and **Step 11b** (`cite_review.py`) exactly as specified in the Core Workflow above — the commands, flag-omission rules, and fallbacks are defined there and are not repeated here.

The result is a self-contained HTML file with:
- A sidebar listing **every citation occurrence** — first full cites, repeat full cites, short forms, and *id.* references each as a separate reviewable entry — with verification status and its **Via** provenance badge (the tier that verified it)
- A split main pane: draft paragraph (with the exact occurrence highlighted) on top; on the bottom, the cited authority — embedded source text scrolled to the pinpoint ¶, the Pass 3B verification passage when no full text is available, or a web fallback — with a link bar carrying the court's direct opinion URL
- Keyboard navigation (`j`/`k` to move, `v`/`f`/`s` to verify/flag/skip, `Space`/`Enter` to verify and advance, `a` to toggle auto-advance, `h`/`l` to switch local/web view, `n` for notes, `?` for help)
- LocalStorage persistence so review state survives browser restarts
- An "Export JSON" button to save the review state

Tell the user the citation review file is available and can be opened in any browser. Name it `<original-filename>-CITE-REVIEW.html`.

### Step 12: End-of-Workflow Summary

After all outputs are generated, present a clear summary to the user:

> **JetRedline Complete** — or, when Step 11 found N < M: **⚠ JetRedline Complete — Incomplete Coverage**
>
> **Inputs ingested: N of M.** *(when N < M, list each miss and the passes affected — Pass 4 fact-check, Pass 6 brief-matching)*
>
> **Documents generated:**
> - Tracked-changes .docx: `<filename>` *(if generated)*
> - Analysis report: `<filename>` *(if generated)*
> - Citation review: `<filename>` *(CLI and Cowork only)*
>
> **Citation Verification (quality gate):**
> Open `<cite-review-filename>` in your browser to verify each citation against its source. Keyboard: `j`/`k` to navigate, `v`/`f`/`s` to verify/flag/skip, `?` for all shortcuts.

Always include this summary. Adapt the list to reflect which outputs were actually generated. When coverage is incomplete (Step 11, N < M), the ⚠ header and the **Inputs ingested** line are mandatory — do not report a clean completion over an unreviewed input. The citation verification prompt is the most important part — it's a quality gate, not an optional extra.

## Key Reminders

- Minimal edits: change only what improves the text. Do not rewrite clear passages.
- Preserve the court's voice. Polish, do not impose a different style.
- When uncertain, use a comment rather than a tracked change.
- For complex restructuring, describe the proposal in a comment.
- Bold changed words in the analysis to distinguish from unchanged text.

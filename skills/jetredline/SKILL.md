---
name: jetredline
version: 4.28.1
description: "Appellate judicial opinion and bench memo editor and proofreader. Produces a Word document (.docx) with tracked changes showing proposed edits, plus a separate analysis document with explanations. Use when the user provides a draft judicial opinion, court order, bench memo, or legal memorandum for editing, proofreading, or style review. Triggers: edit opinion, proofread opinion, review draft opinion, judicial writing review, court opinion edit, redline opinion, edit draft order, appellate opinion editing, edit memo, edit bench memo, proofread memo, review bench memo, jetredline, redline this draft, redline this opinion, redline this memo, redline this order. Applies Garner's Redbook, Bluebook citation format, and style preferences drawn from opinions issued by the North Dakota Supreme Court within the last ten years, Guberman's Point Taken, and Justices Gorsuch, Kagan, and Thomas. Defers to the author's own my-writing-voice.md file when one is present."
---

# JetRedline

Edit draft judicial opinions and bench memos to improve grammar, clarity, conciseness, professional tone, citation accuracy, and analytical rigor. Produce a Word document with tracked changes and a companion analysis document.

This file is the workflow. Detailed procedures live in `references/` and are Read when a step calls for them: `environment-setup.md`, `pdf-ingestion.md`, `batch-edit-workflow.md`, `cite-review-workflow.md`, `analysis-template.md`, `audit-mode.md`, and the per-pass files in `references/pass-instructions/`.

## Audit Mode (Caller Integration)

Another skill (e.g., jetmemo) may invoke jetredline to audit a memo it generated and return findings inline. When the caller's prompt says **audit mode**, Read `references/audit-mode.md` (in this skill's directory) before anything else. It fixes `DOC_TYPE = memo`, writes no files, runs the selected passes inline, and replaces the output documents and Step 12 with a two-part return contract. Everything it does not override is unchanged.

## Environment Detection

Determine your runtime environment from available capabilities:

- **CLI mode**: You have the Bash, Agent, and AskUserQuestion tools and can read/write the local file system. Follow the full workflow as written.
- **Web mode**: You are running in Claude Projects or a similar web environment without Bash, subagents, or file system tools. Follow the **Web mode** fallbacks noted throughout this document.

Do not ask the user which mode to use — sense it from your available tools.

## Environment Setup (CLI mode only)

**Web mode:** skip to Workflow.

`${CLAUDE_SKILL_DIR}` here and throughout is replaced by the harness with this skill's absolute directory before you read this file (the "Base directory for this skill:" line at the top carries the same value); the commands you see contain a literal path. Keep paths double-quoted — on Windows the directory may contain spaces. Full detail — the venv tiers, docx-plugin discovery, Node, the resource table — is in `references/environment-setup.md`; Read it when a step below fails or when the new-.docx creation path (Step 9 alternative) applies.

1. **Python.** Run the bootstrap once, on any system Python (`python3`, or `python` on Windows):
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/bootstrap_env.py"
   ```
   It prints `VENV_PYTHON=<absolute path>`. **Capture that path as a literal string** and use it wherever `$VENV_PYTHON` appears below (no command substitution). It finds or builds the venv in every install layout and is idempotent. If it exits 1, fall back to `python3 -m venv /tmp/jetredline-venv` plus `pip install -r "${CLAUDE_SKILL_DIR}/requirements.txt"` and use that python the same way.

2. **Skill directory.** `SKILL_DIR="${CLAUDE_SKILL_DIR}"`. If that directory does not exist (substitution failed), probe `$HOME/.claude/skills/jetredline`, then `/mnt/.skills/skills/jetredline`. Where a reference file writes `$SKILL_DIR`, substitute this literal.

3. **Temp directory** (Step 0): create one uniquely named directory and capture its absolute path as the literal `<TMPDIR>` for every later command — never `$(pwd)`:
   ```bash
   if [[ "$(pwd)" == /mnt/* ]]; then TMPBASE="/tmp"; else TMPBASE="$(pwd)"; fi
   python3 -c "import uuid,os,sys; d=os.path.join(sys.argv[1],'.tmp-'+str(uuid.uuid4())[:12]); os.makedirs(d,exist_ok=True); print(d)" "$TMPBASE"
   ```

**Keep commands permission-matchable** (applies to delegated subagents too — the pass files repeat it). Allowlists match a command's **first token**:
- Never `cd`; pass absolute paths or use the tool's own `-C` flag.
- Never prefix a command with variable assignments (`TMPDIR=… cmd`); write the value into the argument. (Sole exception: the docx-plugin creation path's `PYTHONPATH`.)
- Invoke the venv python by the exact literal path the bootstrap printed, not through `$VENV_PYTHON` at the shell level.
- Prefer a shipped helper (`pdf_page_grep.py`) to an ad-hoc script.
- Quote paths with spaces and write absolute paths in full — `~` and `$HOME` do not match allowlists.

## Workflow

### Step 0.0: Model Gate (run before anything else)

jetredline's reliability was measured on Opus-class models. On this workload — citation verification, quotation accuracy, record fact-checking — Sonnet- and Haiku-class models miss materially more errors, and the miss is silent: the report still comes out looking complete. Confirm the runtime model before starting any pass.

**CLI mode:**

```bash
python3 "${CLAUDE_SKILL_DIR}/check_model.py"
```

Stdlib only — run it on system `python3`, before the bootstrap. It prints one line, `MODEL_GATE: <status> model=<id> tier=<family> source=<origin>`, and exits 0 (`ok`), 2 (`warn`), or 3 (`unknown`). **A nonzero exit is the gate firing, not a broken script.**

- **`ok`** — an Opus-, Fable-, or Mythos-class model. Continue to Step 0 and say nothing about the model; do not mention that the check ran.
- **`unknown`** — the model could not be detected (no transcript yet, no `$CLAUDE_CODE_SESSION_ID`, Web mode). Identify yourself from your own system prompt and re-run once with that id — substitute your actual model, do not copy the example:
  ```bash
  python3 "${CLAUDE_SKILL_DIR}/check_model.py" --model claude-opus-5
  ```
  If it still reports `unknown`, treat it as `warn`.
- **`warn`** — a Sonnet- or Haiku-class model, or any model name the gate does not recognize. **Stop. Run no pass, create no temp directory, read no draft, until the user answers.**

**On `warn`, ask with `AskUserQuestion`.** Do not pose it rhetorically and proceed, and do not decide for the user that Opus-class "is probably fine either way."

- **Question:** "jetredline is running on `<model>`. We strongly recommend Opus for this work — reliability testing shows Opus-class models catch materially more citation and record-fact errors on this workload. How would you like to proceed?"
- **Header:** "Model"
- **Options:**
  1. **Switch to Opus (recommended)** — End here, having done no work. Tell the user to run `/model opus` (or restart with `claude --model opus`) and re-invoke jetredline.
  2. **Continue on `<model>`** — Run the full review now, with the reduced-reliability caveat recorded in the outputs. **Supported, not a defect:** Opus is not on every plan, and a review on this model is still worth having — it simply carries a higher miss rate, which the outputs will say.

If the user proceeds, carry it forward in exactly two places: one clause in the Step 0.6 announcement ("running on `<model>`, outside jetredline's validated set — verify citation and fact findings with extra care"), and the **⚠ Reduced-Reliability Model** section of the analysis document (see Output Format). Do not repeat the warning in every pass or in every finding.

**Where `AskUserQuestion` is unavailable — Web mode, headless `claude -p`, and audit mode — never block.** State the warning once in text and run the full review anyway. A caller that cannot answer a question must still get its results. In audit mode, report it instead as one line under `### Coverage` in Part 2, e.g. `Model: claude-sonnet-5 — outside jetredline's validated Opus-class set; findings below carry a higher miss rate.` In Web mode, where no script can run, classify from your own identity: Opus, Fable, or Mythos → say nothing; anything else → state the caveat.

### Step 0: Initialize and Scan Working Directory

**Web mode:** Skip temp directory creation, update check, and directory scanning. The user will paste text or upload .docx/.pdf files directly in the conversation. Claude can read uploaded .docx and .pdf files natively. Do the MCP-tool check under **Source preflight** below (it needs no shell), then proceed to Step 0.1.

**Update check:** Run `python3 "${CLAUDE_SKILL_DIR}/check_update.py"` silently. If it prints output, include it as a note to the user.

**Source preflight.** Find out now, not in Step 11, which sources this run cannot reach — a sandboxed session (Cowork, the Claude Code sandbox) blocks any host missing from its egress allowlist, and every script downstream then degrades quietly. Two checks:

1. **Network** (CLI mode) — stdlib only, system `python3`, about a second:
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/preflight.py"
   ```
   It probes the public ndlaw server (the Step 11a export backend) and each official-source host jetcite fetches from, prints `PREFLIGHT ok <host>` or `PREFLIGHT warn <host> <kind> -- <what is lost>. <fix>` per host, and ends with `PREFLIGHT_SUMMARY warnings=<n>`. It always exits 0. `blocked` means the egress allowlist refused the host; the line names the entry to add.
2. **MCP tools** (every mode — only you can see your tool list). Look for an ndlaw server's tools (`lookup_opinion`, `verify_citation`, under any server prefix — `mcp__ndlaw__`, `mcp__claude_ai_ndlaw__`, or another) and CourtListener's (`search`, `call_endpoint` under a `CourtListener` prefix). A server that exposes only `authenticate` / `complete_authentication` is **not** connected. Missing ndlaw → warn: "ndlaw MCP is not connected. ND citations and quotations will be verified through CourtListener and the web; treatment checks and pinpoint verification will be weaker." Missing CourtListener → warn: "CourtListener MCP is not connected. Federal and out-of-state citations will be web-verified only."

**A warning never stops the run.** Carry each one forward in exactly three places: one line in the Step 0.6 announcement, the **⚠ Sources Out of Reach** section of the analysis document, and the Step 12 summary. When both checks come back clean, say nothing about them. (Audit mode runs only the MCP check.)

**Create the temp directory** (Environment Setup, item 3) and capture its literal path.

Then scan the current working directory for:
- **`.docx` files** — potential draft opinions, memos, or dissents
- **`.pdf` files** — potential briefs, record packets, or supporting references

If **exactly one `.docx`** is found, use it as the draft document.
If **exactly one `.pdf`** is found, use it as the record/briefs packet for fact-checking.
If **more than one `.docx`** or **more than one `.pdf`** is found, ask the user which file(s) to use and their roles (e.g., majority opinion, dissent, bench memo, briefs packet, supporting reference).
If **no `.docx`** is found, ask the user to provide the document text.

**Preparing PDF packets (do not read into main context).** PDFs are for the Pass 4 and Pass 6 subagents; identify and prepare them here, never read their contents. The full procedure — splitting, the poppler fallback for packets pypdf cannot open, text-layer triage, and the OCR recovery ladder — is `references/pdf-ingestion.md`; Read it whenever a PDF is over 10 MB, `textquality.py` reports anything but `text-ok`, or a tool below is missing. The short form:

- **Over 10 MB:** split at top-level bookmarks, then split any output still over 10 MB (record bundles) into a subdirectory:
  ```bash
  $VENV_PYTHON "${CLAUDE_SKILL_DIR}/splitmarks.py" packet.pdf -o split_output -v --check-text
  ```
  `--check-text` warns on stderr about image-scanned outputs (needs `pdftotext`; its silence without poppler proves nothing). Record items must be named `R<N> - <Title>.pdf` — that is what `cite_review.py --record-dir` globs for, and page *N* of the extract must equal page *N* of the record item.
- **Every PDF a subagent will read:** triage its text layer:
  ```bash
  $VENV_PYTHON "${CLAUDE_SKILL_DIR}/textquality.py" <file>.pdf [<file>.pdf ...]
  ```
  `text-ok` passes through. `no-text-layer` → `ocrmypdf --skip-text`; `text-layer-corrupt` → `ocrmypdf --force-ocr` (**never** `--skip-text` on a corrupt layer — it exits 0 and changes nothing). Persist `<file>.ocr.pdf` beside the original and re-run `textquality.py` on it; still corrupt = **OCR-low-confidence**. The reference has the full ladder (pdftoppm + tesseract, Read-as-images, not-ingested) and the fallback signals when `textquality.py` cannot run.
- **An unreadable input is a coverage failure (Step 11), never a silent skip.** Pass each file's path and ingestion outcome (`ingested-text` / `OCR-recovered` / `OCR-low-confidence` / `image-read` / `not-ingested`, plus the method) to the Pass 4 and Pass 6 subagents, which report it back.

**Web mode (no Bash):** the Read tool renders PDF pages as images regardless of text layer, so read files directly. Only a file Read cannot render is `not-ingested`; you hold the outcomes yourself for Step 11.

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

**Web mode:** Do not ask for output preferences. Only the markdown analysis document is available — the tracked-changes .docx, the rendered analysis HTML, and the interactive citation review page all require CLI tools (Bash, Python, file system access). State this briefly: "In this environment I can produce a markdown analysis report but not a tracked-changes .docx, a rendered HTML report, or a citation review page." Proceed unless the user objects.

**CLI mode:** Default to producing **both** documents (tracked-changes .docx + analysis document) without asking. Only ask if the user explicitly specified a different preference in their invocation (e.g., "just the redline" or "analysis only"). Whenever the analysis document is produced it is also rendered to HTML (Step 10b) — that is not a separate preference to ask about.

If the user did specify a preference, honor it:
- If **both** (default): Follow the full workflow through Step 10
- If **tracked-changes only**: Complete all editing passes, produce the .docx in Step 9, skip Step 10 (analysis document)
- If **analysis only**: Complete all editing passes and collect findings, produce only the analysis document in Step 10, skip Step 9 (.docx creation)

**Note:** Even when producing analysis only, you must still perform all editing passes (1–7) to identify issues and generate findings for the analysis. You simply skip the final .docx assembly step.

### Step 0.6: Review Scope & Run Announcement

**Do not ask the user to choose a depth or scope of review.** jetredline runs the full pass suite by default. Never present a "what depth of redline" question or a checklist of passes. (The only sanctioned scoping questions remain the *doc type* question in Step 0.1, asked only when genuinely ambiguous, and nothing else.)

**Announce the full run.** After detecting `DOC_TYPE` (Step 0.1) and before launching passes, state in one short paragraph: (a) that you're doing a complete review, (b) the passes that will run, (c) the deliverables, and (d) that the user can narrow the scope next time by saying so at invocation. Keep it to a few lines — do **not** turn it into a checklist or a question. Suggested form (trim passes that don't apply, e.g. omit dissent/concurrence cross-check when none is present, or supplied authorities when the case directory holds no candidate PDFs):

> I'll run a **complete review** — all of jetredline's passes:
> • Jurisdiction & standard of review
> • Line/copy editing — grammar, word choice, sentence structure, Redbook style
> • Citations — existence, accurate quotation, correct Bluebook/Redbook form, and negative-treatment (overruling) scan
> • Supplied authorities — sources cited outside standard citation form (journals, treatises, archival material), verified against PDF copies in the case directory
> • Fact-checking against the record and briefs
> • Analytical rigor — logical gaps, unsupported conclusions, missing steps
> • Dissent/concurrence cross-check
>
> Deliverables: a **tracked-changes .docx** you can accept/reject in Word, plus a **companion analysis document** explaining each change.
>
> *Want something narrower next time? Just say so when you invoke — e.g.* "jetredline, citations only" *or* "light copy edit, don't touch my reasoning" *— and I'll limit the passes accordingly.*

**When the Step 0 source preflight warned,** add one line per warning after the deliverables, before the "narrower next time" line — what is out of reach, what that costs this run, and the fix — e.g.:

> ⚠ **`ndlaw.org` is blocked by this session's network policy.** ND opinion text for the citation review will be scribed through the model instead (slower, and it costs tokens). To fix: add `ndlaw.org` and `*.ndlaw.org` to the egress allowlist and start a new session.

**Scope-keyword map (only when the user *volunteered* a narrower scope in their invocation).** Do not prompt for this; apply it only when the user's own words signal a narrower intent. Map their words to passes and run only those, plus the always-on jurisdictional check (Pass 1):

| If the user says… | Run |
|---|---|
| "copy edit," "light edit," "proofread only," "style only" | Pass 2 |
| "citations only," "check cites," "cite check" | Pass 3A–D |
| "substance only," "analysis only," "rigor" | Passes 4, 5, 6, 7 |
| "no substantive changes," "don't rewrite my reasoning" | Passes 2, 3; skip 5 |

When you narrow the scope, say which passes you skipped and why, and adjust the announcement above to describe only the passes you will actually run. (Note: "analysis only" as a *scope* keyword means substantive passes; it is distinct from the *output* preference in Step 0.5, which governs which documents are produced. If the user's intent is ambiguous between the two, briefly confirm.)

### Step 0.7: Author Voice File (optional)

A user may keep a personal description of their own writing voice in a file named `my-writing-voice.md` (see the README for what it contains). When one is present, it tells Pass 2 how *this author* writes, so the redline polishes toward the author's voice instead of toward a generic one.

**Locate it** (first match wins; set `VOICE_FILE` to the path, or leave it unset):
1. `my-writing-voice.md` in the working directory (a per-project override).
2. `$HOME/.claude/my-writing-voice.md` (the user's standing file).
3. **Web mode:** a file of that name in project knowledge or uploaded in the conversation.

```bash
for f in "$PWD/my-writing-voice.md" "$HOME/.claude/my-writing-voice.md"; do [ -f "$f" ] && echo "$f" && break; done
```

**If `VOICE_FILE` is unset,** say nothing about it and run the standard workflow unchanged.

**If `VOICE_FILE` is set:**
- **Scope.** Apply it only to writing the file covers. The file itself says which kinds of documents it governs (e.g., "text I will sign"). If the draft is someone else's (a colleague's opinion, a clerk's memo written for another judge) or the user says not to use it, leave it unset for this run. When the draft's authorship is unclear, apply it and say so in the announcement; do not ask.
- **Announce it.** Add one line to the Step 0.6 announcement after the deliverables: "Using your writing-voice file (`<VOICE_FILE>`) for style; say so if this draft isn't yours."
- **Precedence in Pass 2.** Pass 2's **hard rules** and the citation rules (Pass 3A, `references/nd-citation-style.md`) still apply. Where the voice file conflicts with a **style preference** in this skill or `references/style-guide.md` (sentence length, paragraph length, transitions, word choices, register), **the voice file governs**. Where the voice file lists patterns to avoid, treat each occurrence in the draft as a candidate edit, or a comment when the fix needs the author's judgment.
- **Minimal edits still rule.** The voice file is a standard for judging proposed changes, not license to rewrite clear passages that already match it.
- **Audit mode:** skip the voice file. The caller's memo is not the user's signed writing. (Its "Flag in any draft I review" section, below, still applies.)

**Flags for any draft (`VOICE_FLAGS_ONLY`).** A voice file may contain a section headed `## Flag in any draft I review` (match the heading's start; the rest may vary). Those rules apply whoever wrote the draft: they cover opinions the user may join, not just ones the user signs. So when the scope check above, an explicit "this draft isn't mine," or audit mode would otherwise leave `VOICE_FILE` unset, keep the path and set `VOICE_FLAGS_ONLY=1` instead. Pass 2 then applies **only** that section and raises each finding as a COMMENT, never an edit. When the whole file applies, the section's rules are ordinary candidate edits (or comments where the fix needs the author's judgment). In the announcement, `VOICE_FLAGS_ONLY` gets its own line: "Applying the 'Flag in any draft' rules from your voice file (`<VOICE_FILE>`) as comments."

**Search patterns.** A rule may carry a `Search:` line with a regex. After Step 3 produces the draft text, run them deterministically whenever `VOICE_FILE` is set (full or flags-only), and pass the output to Pass 2:
```bash
$VENV_PYTHON "${CLAUDE_SKILL_DIR}/voice_search.py" --json <VOICE_FILE> <opinion_md_path> > <TMPDIR>/voice_hits.json
```
Exit 1 means no hits (pass nothing); exit 2 means a bad pattern or unreadable file. Report that to the user and continue without hits. Each hit is a candidate for Pass 2 to judge, not a finding.

### Steps 1–12: Core Workflow

1. Read `references/style-guide.md`. If `VOICE_FILE` is set (Step 0.7), also Read it.
2. **Docx skill (conditional — usually skip).** Only when the draft is *not* a .docx **and** a tracked-changes .docx will be produced (Step 9 must create one from scratch): run the docx-plugin discovery in `references/environment-setup.md` and Read the docx skill as it directs. When the draft **is** a .docx, skip all of this — `extract_text.py` and `apply_edits.py` are self-contained.
3. Read the draft opinion. **If the draft is a .docx**, first extract its text deterministically (zero model tokens — never transcribe a .docx by hand and never read raw OOXML into context):
   ```bash
   $VENV_PYTHON "${CLAUDE_SKILL_DIR}/extract_text.py" --input <draft.docx> --output <TMPDIR>/<stem>.md
   ```
   Then Read the generated markdown — it is the `<opinion_md_path>` used by Pass 3 and Step 11. The script preserves literal ¶ markers, reconstructs Word automatic paragraph numbering (including style-based numbering like the chambers template's MainBody `[¶N]`), extracts footnotes as `[^N]` references, and resolves any existing tracked changes to the as-accepted view; its stderr summary reports those counts — if the input already carries tracked changes, mention that to the user. For pasted text or a markdown file, read it directly. **Count paragraphs** (¶ markers or logical paragraphs) to determine opinion length.
4. **Delegate Pass 1** (jurisdictional check) to a subagent — see Pass 1 below
5. **Delegate Pass 3** (citation verification) to a subagent — see Pass 3 below
5a. **Delegate Pass 3D** (supplied authorities) to a subagent if the case directory holds PDFs beyond the briefs and record items identified in Step 0 — see Pass 3 Part D below. It runs independently of Pass 3B (it generates its own cite JSON), so launch it in parallel with the other subagents.
6. **Delegate Pass 4** (fact-checking) to a subagent if PDF materials were identified in Step 0 — see Pass 4 below
6a. **Delegate Pass 6** (brief matching) to a subagent if briefs were identified in Step 0 — see Pass 6 below
6b. **Delegate Pass 7** (dissent/concurrence cross-check) to a subagent if a dissent or concurrence was identified in Step 0 and `DOC_TYPE == opinion` — see Pass 7 below
7. **Pass 2 routing:** If the opinion has **more than 30 paragraphs**, delegate Pass 2 to a subagent — see "Delegated Pass 2" below. Otherwise, perform Pass 2 in main context. **Pass 5** (analytical rigor) is always performed in main context. Pass 2 (when not delegated) and Pass 5 can proceed in parallel with subagents.
8. Collect subagent results from Passes 1, 3, 3D, 4, 6, 7, and (if delegated) Pass 2 as each agent's completion is delivered to you — never by tailing files with Bash.
8a. **Caption mismatches → edits (closed-loop rule).** Check the Pass 3B results table for Caption Check mismatches. Generate a correcting tracked-change edit **only** when the *same* citation resolved to an official caption and the draft's name is a near-match typo of it (high `name_similarity`) — e.g., a comment "Official caption per 2023 ND 219: 'Tracey v. Tracey'". **Never** harmonize names across two *different* citations (different cite = presumptively different case), and do not auto-correct low-similarity or unresolved names — add a comment for human review instead. Include qualifying edits in the edits JSON alongside Pass 2/3A/5 edits. Likewise apply the **parallel-cite corrections** flagged by Pass 3B's parallel-cite check — add a missing N.W.2d/N.W.3d parallel to a *full* cite, or fix a wrong one, using the `formatted` value from ndlaw.
8b. **Treatment flags → comments.** If the Pass 3C overruling scan flagged any cited case for possible negative treatment, add a *comment* (not an edit) on each occurrence, quoting the citing context, for human review. Never auto-edit on a treatment signal.
9. **If a tracked-changes .docx was requested** (both or tracked-changes only), collect every edit — Pass 2 style, Pass 3A format, Pass 5 rigor, Step 8a captions and parallels, Step 8b comments — into `<TMPDIR>/edits.json` and apply them in **one** run against the **original** .docx (never re-run on its own output; if retrying, start from the original again):
   ```json
   [{ "type": "replace", "para": 3, "old": "It is well settled that the court", "new": "The court", "comment": "Cut throat-clearing (Redbook § 11.3)" },
    { "type": "comment", "para": 12, "anchor": "we find that", "comment": "Consider replacing 'we find' — implies independent factfinding under clear-error review" }]
   ```
   ```bash
   $VENV_PYTHON "${CLAUDE_SKILL_DIR}/apply_edits.py" --input <input.docx> --edits <TMPDIR>/edits.json --author "Claude" --output <output.docx>
   ```
   `old` is the shortest span unique within its paragraph (the tracked deletion covers exactly `old`); attach `comment` only when a reader might question the change. Parse the JSON summary: report failed edits and any `matches` above 1 (the edit landed on the first of several identical spans). Nonbreaking spaces after `¶`/`§` are **never** tracked edits: count and report them (default) or, only when the user asks, add `--normalize-nbsp` and disclose the `nbsp_normalized` count in Step 12. Then validate with `$VENV_PYTHON "${CLAUDE_SKILL_DIR}/ooxml_validate.py" <output.docx>` (exit 1 = Word would call the file unreadable). Hyperlink edits (on request), the nbsp counting command, and the plain-text-input path (new .docx via the docx skill) are in `references/batch-edit-workflow.md`.
10. **If an analysis document was requested** (both or analysis only): Read `references/analysis-template.md` and produce the companion analysis document from all pass results, saved as `<original-filename>-ANALYSIS.md` in the working directory. If also producing .docx, create both outputs in the same response.
10a. **Stamp a provenance footer** on the analysis document (CLI mode) — model, jetredline version, and date, sourced deterministically from the session transcript:
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/provenance.py" --file <stem>-ANALYSIS.md --subagents
   ```
   Do **not** pass `--model` and never hand-type the model anywhere in the report; only if the script exits 2 (no transcript readable) re-run with `--model "<friendly name> (<exact id>)"` using the id Step 0.0 resolved. Stamp only the analysis document, never the .docx. `--subagents` adds a per-pass model/token table read from the transcript — it identifies passes by the `references/pass-instructions/passN-*.md` path in each delegation prompt, so keep that path verbatim and give each agent a `description` naming its pass; if the script omits the table, it stays omitted. Skip in audit and web mode (web: append the footer line by hand). Detail in `references/analysis-template.md`.
10b. **Render the analysis report as HTML** (CLI and Cowork, **always**), after the provenance stamp, never before:
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/analysis_to_html.py" <stem>-ANALYSIS.md --check
   ```
   Writes `<stem>-ANALYSIS.html` beside the markdown — a single self-contained file, safe to email or hand over in Cowork as-is. Add `--cite-review <stem>-CITE-REVIEW.html` once Step 11b has produced that page. `--check` exits 3 if any source line failed to survive into the page; if so, say so and deliver the markdown alongside — never silently ship a page that dropped content. Re-run after any edit to the markdown (idempotent). Skip only in audit mode and web mode.
11. **Generate the citation review page** (CLI and Cowork) after Pass 3 completes. Full procedure, fallbacks, and flag semantics: `references/cite-review-workflow.md` — Read it the first time this runs in a session and whenever a step below fails.

    **11a. Refresh ND authority text + direct URLs from ndlaw (zero token cost):**
    ```bash
    $VENV_PYTHON "${CLAUDE_SKILL_DIR}/ndlaw_export.py" --opinion <opinion_md_path> --refs-dir ~/refs --meta-out <TMPDIR>/sources.json
    ```
    It picks its own backend (local `opinions.db`, `NDLAW_URL`, else the public `https://ndlaw.org/mcp` — no credentials; do not hunt for MCP config). Exit 2 = no backend reachable (almost always an egress allowlist missing `ndlaw.org`): fall back to **one scribe subagent** (Agent tool, `model: haiku`) riding the in-context ndlaw MCP tools, as the reference specifies — opinion text never passes through main context. If that is impossible too, fall through, but render **⚠ Authority Text Not Refreshed** in the analysis document and say so in Step 12. Never stall here.

    **11b. Generate the page.** Write `<TMPDIR>/via.json` mapping each citation to its Pass 3B **Via** tier, then:
    ```bash
    $VENV_PYTHON "${CLAUDE_SKILL_DIR}/cite_review.py" \
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
    Omit `--docx` for non-.docx drafts; omit `--via-json`, `--sources-meta`, `--passages-json`, `--facts-json`, and `--authorities-json` when the step that produces each did not run or wrote nothing. **`--record-dir` is mandatory whenever Step 0 split a record** (the facts ledger's `R<N>` refs resolve only there; the script exits 1 without it — keep the split directory until the page exists). `--resume-state auto` restores a reviewer's saved marks from the case directory; report its restore line. Unless `--link-pdfs` is used, the output is the HTML **plus** a `<stem>_pdfs/` sidecar that must travel with it — in Cowork or any remote session add `--bundle <output_dir>/<stem>.zip` and deliver the zip. A cited authority with only a local PDF copy gets `"pdf"` / `"page"` / `"quote"` keys on its `sources.json` entry.
12. **End-of-workflow summary** — see Output Format below.

**Web mode workflow:**
1. Read `references/style-guide.md` from project knowledge. If not found, tell the user to upload it. If a `my-writing-voice.md` is in project knowledge or was uploaded, read it too and apply Step 0.7.
2. Skip docx skill files (not needed without .docx output).
3. Read the draft from the conversation (pasted text or uploaded file).
4. Perform Pass 1 inline.
5. Perform Pass 2 inline (regardless of length).
6. Perform Pass 3A (format) inline. Perform Pass 3B (verification) inline with web search fallback. Perform Pass 3D (supplied authorities) inline if the user uploaded copies of non-case sources the draft relies on — see Part D's Web-mode note.
7. Perform Pass 4 inline if the user uploaded source PDFs. Read them directly.
8. Perform Pass 6 (brief matching) inline if the user uploaded briefs.
9. Perform Pass 7 (dissent cross-check) inline if the user uploaded a dissent/concurrence and `DOC_TYPE == opinion`.
10. Perform Pass 5 inline.

For each delegated pass performed inline (1, 3B, 3D, 4, 6, 7 — and 2's entry format), read its instruction file from project knowledge (`references/pass-instructions/passN-*.md`) and apply it, adapting CLI-only steps (shell commands, `~/refs/`, ledger files) per the pass's Web-mode note.
11. Skip .docx assembly.
12. Produce the analysis document as markdown in the conversation.

**Context limits:** Without subagents, very long documents (50+ paragraphs) may approach context limits. If this occurs, prioritize: Pass 2 → Pass 5 → Pass 3A → Pass 1 → Pass 3B → Pass 4 → Pass 3D → Pass 6 → Pass 7. Inform the user which passes were completed.

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

**Do not** read `references/nd-appellate-rules.md` or the pass-instruction file into the main context. Delegate with the Agent tool (subagent_type: `general-purpose`, `description` naming the pass) and a prompt of this form:

> Read `${CLAUDE_SKILL_DIR}/references/pass-instructions/pass1-jurisdiction.md` and follow the **[opinion / memo]** variant. The skill root is `${CLAUDE_SKILL_DIR}`. The draft is at `[path]`. Return only the concise findings summary those instructions specify.

**Returns:** a concise summary of jurisdictional, procedural-posture, or standard-of-review findings — or an explicit all-clear. The memo variant may instead return a warning that the memo should confirm appellate jurisdiction.

**Web mode:** Perform inline. Read `references/pass-instructions/pass1-jurisdiction.md` and `references/nd-appellate-rules.md` from project knowledge and apply the matching variant. If the rules file is unavailable, use web search to find the relevant N.D.R.App.P. rules at ndcourts.gov. Report findings in the same format.

### Pass 2: Style and Grammar
Apply in priority order. Full details in `references/style-guide.md`. If `VOICE_FILE` is set, it governs over the style preferences below where they conflict (Step 0.7); the hard rules still apply.

**Hard rules (always apply):**
- Active voice unless passive genuinely improves readability
- Never use plural pronouns as gender-neutral singular — use he, she, it, or rephrase, but never guess an individual's gender and do not use the masculine as an archaic gender neutral
- Never use "and/or"
- Never use legalese such as: herein, wherefore, aforementioned, said/such/same as pronouns
- Never use Latin-derived words when plain English carries equal precision
- Always use the Oxford comma
- Constitutions protect, guarantee, or preserve rights — never "create" or "grant" (unless the text clearly declares a new right)

**Do not propose nonbreaking-space edits.** The space after `¶`/`§` should be a nonbreaking space (U+00A0), but never raise it as a tracked change: a change bar on every citation buries the substantive edits. It is handled deterministically instead — see Step 9.

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

When the opinion exceeds 30 paragraphs, delegate Pass 2 with the Agent tool (subagent_type: `general-purpose`) to keep main-context output tokens manageable, with a prompt of this form:

> Read `${CLAUDE_SKILL_DIR}/references/pass-instructions/pass2-style.md` and follow it. The skill root is `${CLAUDE_SKILL_DIR}`. The draft opinion is at `[path]`. [If `VOICE_FILE` is set:] The author's voice file is at `[VOICE_FILE]`. [If `VOICE_FLAGS_ONLY`:] Flags-only mode: apply only its "Flag in any draft I review" section, as COMMENTs. [If `voice_hits.json` has hits:] Search-pattern candidates are at `[TMPDIR]/voice_hits.json`. Return only the structured entry list those instructions specify.

**Returns:** a structured list of `¶ / OLD / NEW / REASON` edit entries and `¶ / COMMENT / ANCHOR` comment entries, in paragraph order.

**In main context after collection:** Apply the returned edits mechanically when building the tracked-changes edits in Step 9. Each `OLD`/`NEW` pair becomes a tracked deletion + tracked insertion. Each `COMMENT` entry becomes a document comment anchored to the specified text.

**Web mode:** Always perform inline, regardless of document length. Apply the same rules. Use the structured entry format (¶, OLD, NEW, REASON) for internal tracking, then incorporate into the analysis document.

### Pass 3: Citation Check (Delegated to Subagent)

Pass 3 has four parts: (A) Bluebook format checking, in main context; (B) substantive citation verification, delegated to a subagent; (C) a negative-treatment / overruling scan, in main context; and (D) supplied-authorities verification, delegated to a subagent. Parts B and C use the ndlaw / CourtListener servers as the primary source when available — see "Legal-Research MCP Servers" above — and fall back to local files plus web verification otherwise.

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

**Delegation:** Launch a subagent with the Agent tool (subagent_type: `general-purpose`) and a prompt of this form:

> Read `${CLAUDE_SKILL_DIR}/references/pass-instructions/pass3b-citations.md` and follow it. The skill root is `${CLAUDE_SKILL_DIR}`; the venv python is `[the $VENV_PYTHON value from Environment Setup]`. The opinion file is at `[opinion_path]`; write the passages ledger to `<TMPDIR>/passages.json`. Here is the extracted citation list: [numbered list — ¶, citation text, proposition, quoted text if any, signal].

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

#### Part D: Supplied Authorities (Delegated to Subagent)

A draft may rely on sources the citation parser cannot recognize — a convention journal, an official report of debates, a treatise, a periodical in an obsolete abbreviation, an archival document, a historical constitution, an out-of-jurisdiction slip opinion — for which PDF copies sit in the case directory. Parts A–C never see them; Part D connects each such reference to its PDF, extracts and verifies the cited pages, and flags references with no supplied copy.

**When to run:** the case directory holds PDFs beyond the briefs and record items identified in Step 0 — or the draft visibly relies on non-case sources (italicized titles, printed-page cites to works rather than reporters). When in doubt, run it: the subagent returns "No supplied authorities detected" cheaply. **Do not** read the candidate PDFs in main context.

**Delegation:** Launch a subagent with the Agent tool (subagent_type: `general-purpose`) and a prompt of this form:

> Read `${CLAUDE_SKILL_DIR}/references/pass-instructions/pass3d-authorities.md` and follow it. The skill root is `${CLAUDE_SKILL_DIR}`; the venv python is `[the $VENV_PYTHON value from Environment Setup]`. The draft opinion markdown is at `[opinion_md_path]`; the case directory is `[working_dir]`; TMPDIR is `<TMPDIR>`.

**Returns:** the supplied-authorities table (`¶ | Authority | Kind | Cited page | Matched file | Page check | Quote check | Supports? | Notes`), a summary line, and two findings lists: **authorities relied on but not located** (the draft cites a work with no copy in the case directory — carry each into the analysis document; this is exactly what chambers wants flagged) and supplied-but-unreferenced PDFs (informational). The subagent also writes `<TMPDIR>/authorities.json` (the ledger Step 11b embeds via `--authorities-json`) and places page extracts in `<working_dir>/authorities/`.

**Web mode:** No shell or filesystem — the deterministic pipeline does not apply. If the user uploaded copies of non-case sources, verify the draft's references against them inline (read the uploaded PDF at the cited page, check the passage and proposition) and report the same table; note that unuploaded works could not be checked.

### Pass 4: Fact-Checking (Delegated to Subagent)

When the user provides briefs, record documents, or other source materials alongside the draft opinion, **do not** read the PDF materials into the main context. Delegate fact-checking to a subagent to keep potentially large PDF content out of the main context window.

**Preparation (in main context):** After reading the opinion, extract a numbered list of verifiable factual claims with paragraph references. Include:
- Dates, names, places, and sequences of events
- Procedural history (filings, motions, rulings, verdicts, sentences)
- Descriptions of testimony or evidence
- Characterizations of parties' arguments
- Statements about the record (e.g., "Davis did not object," "the jury was instructed")

Do **not** include: legal standards and rules (checked in Passes 1 and 3), the court's own reasoning and conclusions, or general statements of law from cited cases.

**Claim-to-record mapping:** For each claim, also extract any record citations from the opinion text (e.g., "R 58," "App. 42," "Doc. 12," "Tr. 145"). Include these as a `Cited Records` column in the claims list passed to the subagent. This lets the subagent check the cited record items first, but the subagent should also search other record items — record citations in draft opinions are not always complete or accurate.

**Delegation:** Launch a subagent with the Agent tool (subagent_type: `general-purpose`) and a prompt of this form:

> Read `${CLAUDE_SKILL_DIR}/references/pass-instructions/pass4-factcheck.md` and follow it. The skill root is `${CLAUDE_SKILL_DIR}`. Write the structured facts ledger to `<TMPDIR>/facts.json`. The source PDFs are: [paths, each with its Step 0 ingestion outcome]. Here is the numbered claims list (¶ refs and Cited Records column included): [claims list].

**Returns:** the fact-check results table (`¶ | Claim | Source Document(s) | Result | Notes`) with a summary line, plus an **Ingestion Status table** (one row per source PDF: `Source file | Pages | Ingestion | Method`) that Step 11 reconciles for coverage. The instructions include the full detection + OCR recovery ladder, so image-only files are recovered, not skipped; a `not-ingested` or `OCR-low-confidence` file means its dependent facts are unverified, and the subagent says so plainly.

**No source materials:** If the user does not provide source materials, skip delegation. Note this limitation in the analysis and flag any factual assertions that cannot be independently verified.

**Web mode:** If the user uploaded PDF source materials, read them directly (no pdftotext needed). Perform fact-checking inline. For large documents, focus on the extracted claims rather than reading entire files. If no source materials were uploaded, note this limitation.

### Pass 6: Brief Matching (Delegated to Subagent)

When briefs are available (identified in Step 0), check whether the opinion or memo addresses every argument raised by the parties. This pass applies to both `opinion` and `memo` document types.

**Do not** read the briefs into the main context. Delegate to a subagent to keep PDF content out of the main context window.

**Delegation:** Launch a subagent with the Agent tool (subagent_type: `general-purpose`) and a prompt of this form:

> Read `${CLAUDE_SKILL_DIR}/references/pass-instructions/pass6-brief-matching.md` and follow it. The skill root is `${CLAUDE_SKILL_DIR}`. The draft document is at `[path]`; the party briefs are: [brief paths, each with its Step 0 ingestion outcome].

**Returns:** the brief-matching table (`¶ | Argument | Party | Brief Source | Addressed | Notes` — Yes/Partial/No per argument, with brief page ranges) with a summary line, plus an **Ingestion Status table** (one row per brief) that Step 11 reconciles for coverage. The instructions include the full detection + OCR recovery ladder; an unreadable brief is reported as **coverage unverified** for that party, never silently skipped.

**No briefs available:** If no briefs were provided in Step 0, skip this pass entirely. Note in the analysis document: "No briefs provided — brief matching skipped."

**Web mode:** If the user uploaded briefs, perform inline — read the briefs directly and follow the extraction and matching process in `references/pass-instructions/pass6-brief-matching.md` (from project knowledge; the pdftotext/OCR steps do not apply). If no briefs were uploaded, note the limitation.

### Pass 7: Dissent/Concurrence Cross-Check (Delegated to Subagent)

When a dissent or concurrence is provided alongside the majority opinion, cross-check for fair characterization and responsiveness. The aim is to ensure all opinions in a case fairly and accurately characterize other opinions, maintain constructive engagement on the substantive merits of the points of disagreement, and reveal to a discerning reader the crux of any disagreement between the opinions. This pass applies **only** when `DOC_TYPE == opinion` and a dissent or concurrence file was identified in Step 0.

**Do not** read the dissent/concurrence into the main context. Delegate to a subagent to keep the separate document out of the main context window.

**Delegation:** Launch a subagent with the Agent tool (subagent_type: `general-purpose`) and a prompt of this form:

> Read `${CLAUDE_SKILL_DIR}/references/pass-instructions/pass7-dissent-crosscheck.md` and follow it. The skill root is `${CLAUDE_SKILL_DIR}`. The majority opinion is at `[majority path]`; the dissent/concurrence is at `[dissent path]`.

**Returns:** the cross-check table (`¶ Majority | ¶ Dissent | Argument | Fair Characterization? | Addressed? | Notes`) and a summary counting dissent arguments reviewed, fair characterizations, potential straw-manning, unaddressed criticisms, and dissent mischaracterizations of the majority.

**No dissent/concurrence available:** If no dissent or concurrence was identified in Step 0, or `DOC_TYPE != opinion`, skip this pass entirely.

**Web mode:** If the user uploaded a dissent/concurrence alongside the majority, perform inline — read both documents directly and follow the cross-check process in `references/pass-instructions/pass7-dissent-crosscheck.md` (from project knowledge). If no dissent was uploaded, note the limitation.

### Pass 5: Analytical Rigor (Main Context)

Always performed in main context, on every document type. Read `references/pass-instructions/pass5-rigor.md` and apply it. It covers, for all documents: the internal-consistency check (names, dates, amounts, terminology — case names excluded, Pass 3B owns them), the standard-of-review consistency check (does the analysis language match the stated standard?), the statutory-construction cross-check via ndlaw `find_opinions_construing` when available, and readability metrics. Then the `DOC_TYPE`-specific checks — for opinions: dicta, alternative rationales, logical issues, holdings broader than necessary, the **two hostile readers** reading, and the Case Highlight draft; for memos: issue completeness, balance, recommendation quality, analytical gaps, standard-of-review application, and the order-grounding check. Findings go in the analysis document; Hostile Readers findings never become tracked edits.

Readability (CLI mode):
```bash
$VENV_PYTHON "${CLAUDE_SKILL_DIR}/readability_metrics.py" --file <document_path>
```
Parse the JSON; flag sentences over 40 words, sections with passive voice above 25%, and sections with FK grade above 16. Web mode: skip the script and estimate inline, or note it unavailable. Audit mode: skip readability entirely.

### Step 11: Coverage Reconciliation & Acknowledgment Gate

Before producing any final output, reconcile the **inputs identified in Step 0** against the **inputs actually ingested** (from the Ingestion Status tables returned by Passes 4 and 6). An input counts as **not fully ingested** if its status is `not-ingested` **or** `OCR-low-confidence`. Always emit one ledger line:

> **Inputs ingested: N of M.** [If N < M, list each miss: `Reply-Brief.pdf` (image-only; OCR-low-confidence), …]

**Acknowledgment gate — fires only when N < M.** If any identified input was not fully ingested, do **not** present the run as complete. Name the file(s), the reason (no text layer / image-only / garbled OCR), and the affected passes (Pass 4 fact-check, Pass 6 brief-matching), then ask the user to acknowledge that coverage is incomplete before final outputs are produced. Use `AskUserQuestion` (CLI) or a direct question (Web). When N < M you must also render the `## ⚠ Source Materials Not Reviewed` section (see `references/analysis-template.md`) and use the incomplete-coverage form of the Step 12 header.

> **This is an exceptional-condition gate, not a scope or depth question.** It is the *only* sanctioned interactive pause besides the Step 0.1 doc-type question. Do not generalize it, and never use it to offer pass selection. When N == M, skip it silently and proceed.

**Audit mode:** do not prompt. Instead surface any not-fully-ingested input under a `### Coverage` heading in Part 2 and reflect it in the final summary line.

## Output Format

**Web mode:** Produce only the analysis document, as markdown in the conversation; the template is the same.

Produce the outputs requested by the user in Step 0.5.

**Tracked-changes .docx** (Step 9, `apply_edits.py`): tracked deletions and insertions (author: "Claude") plus comments for substantive notes — explaining a change or flagging an issue. Direct on the .docx ZIP; no unpack/pack, no docx plugin.

**Analysis document** (Step 10): Read `references/analysis-template.md` when assembling it. It holds the full section template — Case Highlight (opinions), Jurisdictional Notes, Summary of Edits (with the nonbreaking-space line), Fact Check, Brief Matching, Internal Consistency, Standard of Review Consistency, Readability Metrics, Substantive Concerns (opinions: Potential Dicta, Alternative Rationales, Hostile Readers, Logical Issues, Dissent/Concurrence Cross-Check) or Memo Analysis, Citation Verification, Supplied Authorities, Citation Format Issues, Style Notes — plus the four conditional ⚠ warnings (Source Materials Not Reviewed when Step 11 found N < M; Authority Text Not Refreshed; Reduced-Reliability Model; Sources Out of Reach) and when each renders, and the provenance-footer detail. Save it as `<original-filename>-ANALYSIS.md` in the working directory, not the temp directory, so it survives context compression. Do not hand-write a version/date footer — `provenance.py` stamps it (web mode: append it manually).

**Analysis report HTML** (Step 10b; CLI and Cowork, always): `<stem>-ANALYSIS.html` beside the markdown — one self-contained page with a triage banner and sticky table of contents carrying flagged-row counts per section, status badges (glyph plus text, legible to red-green colorblind readers), a filter box and "problems only" toggle per table, a persisted checkbox worklist for unlocated authorities, and a print stylesheet. A count of zero flagged rows is **not** a clean bill of health — findings also live in tables without a status vocabulary and in the narrative sections; never report it as a clean run. Tell the user it opens in any browser and prints to PDF.

**Citation review HTML** (Steps 11a/11b; CLI and Cowork, always): `<original-filename>-CITE-REVIEW.html` plus its `<stem>_pdfs/` sidecar (or the `--bundle` zip). Every citation occurrence — first full cites, repeats, short forms, *id.* — is its own reviewable entry with a **Via** provenance badge; supplied authorities and Pass 4 facts share the list behind lane filter chips. The split pane shows the draft paragraph with the occurrence highlighted above the cited authority at the pinpoint ¶ (embedded text, the Pass 3B passage, or a web fallback). Keyboard: `j`/`k` move, `v`/`f`/`s` verify/flag/skip, `h`/`l` switch source, `n` notes, `?` help; marks persist in LocalStorage, save to a state file the next run resumes from, and export as JSON. Tell the user, and name the sidecar or bundle alongside the file.

### Step 12: End-of-Workflow Summary

After all outputs are generated, present a clear summary to the user:

> **JetRedline Complete** — or, when Step 11 found N < M: **⚠ JetRedline Complete — Incomplete Coverage**
>
> **Inputs ingested: N of M.** *(when N < M, list each miss and the passes affected — Pass 4 fact-check, Pass 6 brief-matching)*
>
> **Sources out of reach:** *(only when the Step 0 preflight warned — one line per host or MCP server, with the fix)*
>
> **Documents generated:**
> - Tracked-changes .docx: `<filename>` *(if generated)*
> - Analysis report: `<filename>` *(if generated)* — markdown, plus `<filename>.html` for reading and printing
> - Citation review: `<filename>` *(CLI and Cowork only)*
>
> **Citation Verification (quality gate):**
> Open `<cite-review-filename>` in your browser to verify each citation against its source. Keyboard: `j`/`k` to navigate, `v`/`f`/`s` to verify/flag/skip, `?` for all shortcuts.

Always include this summary. Adapt the list to reflect which outputs were actually generated. When coverage is incomplete (Step 11, N < M), the ⚠ header and the **Inputs ingested** line are mandatory — do not report a clean completion over an unreviewed input. If `--normalize-nbsp` was used, disclose the count here. The citation verification prompt is the most important part — it's a quality gate, not an optional extra.

## Key Reminders

- Minimal edits: change only what improves the text. Do not rewrite clear passages.
- Minimal spans: an edit's `old` covers only the words that change, not the sentence around them.
- Comment only when a reader might question the change; a self-evident diff needs no note.
- Preserve the court's voice, or the author's voice when a `my-writing-voice.md` file is loaded (Step 0.7). Polish, do not impose a different style.
- When uncertain, use a comment rather than a tracked change.
- For complex restructuring, describe the proposal in a comment.
- Bold changed words in the analysis to distinguish from unchanged text.

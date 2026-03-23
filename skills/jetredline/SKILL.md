---
name: jetredline
version: 3.5.2
description: "Appellate judicial opinion and bench memo editor and proofreader. Produces a Word document (.docx) with tracked changes showing proposed edits, plus a separate analysis document with explanations. Use when the user provides a draft judicial opinion, court order, bench memo, or legal memorandum for editing, proofreading, or style review. Triggers: edit opinion, proofread opinion, review draft opinion, judicial writing review, court opinion edit, redline opinion, edit draft order, appellate opinion editing, edit memo, edit bench memo, proofread memo, review bench memo, jetredline, redline this draft, redline this opinion, redline this memo, redline this order. Applies Garner's Redbook, Bluebook citation format, and style preferences drawn from Justice Jerod Tufte (ND Supreme Court), Guberman's Point Taken, and Justices Gorsuch, Kagan, and Thomas."
---

# JetRedline

Edit draft judicial opinions and bench memos to improve grammar, clarity, conciseness, professional tone, citation accuracy, and analytical rigor. Produce a Word document with tracked changes and a companion analysis document.

## Environment Detection

Determine your runtime environment from available capabilities:

- **CLI mode**: You have access to the Bash, Task, TaskOutput, and AskUserQuestion tools, and can read/write the local file system. Follow the full workflow as written.
- **Web mode**: You are running in Claude Projects or a similar web environment without access to Bash, Task, or file system tools. Follow the **Web mode** fallbacks noted throughout this document.

Do not ask the user which mode to use — sense it from your available tools.

## Platform Detection

At the start of each CLI session, set variables for platform-dependent paths. **Do not use `$(uname)` or other command substitution** — it triggers unnecessary permission prompts. Instead, check for platform-specific files directly:

```bash
VENV_PYTHON=~/.claude/skills/jetredline/.venv/bin/python
SOFFICE_DIR=""
if [ -d /Applications/LibreOffice.app ]; then
  SOFFICE="/Applications/LibreOffice.app/Contents/MacOS/soffice"
  SOFFICE_DIR="/Applications/LibreOffice.app/Contents/MacOS"
elif [ -f "/c/Program Files/LibreOffice/program/soffice.exe" ]; then
  VENV_PYTHON=~/.claude/skills/jetredline/.venv/Scripts/python.exe
  SOFFICE="/c/Program Files/LibreOffice/program/soffice.exe"
  SOFFICE_DIR="/c/Program Files/LibreOffice/program"
elif [ -f "/c/Program Files (x86)/LibreOffice/program/soffice.exe" ]; then
  VENV_PYTHON=~/.claude/skills/jetredline/.venv/Scripts/python.exe
  SOFFICE="/c/Program Files (x86)/LibreOffice/program/soffice.exe"
  SOFFICE_DIR="/c/Program Files (x86)/LibreOffice/program"
else
  # Linux or other — assume soffice is on PATH
  SOFFICE="soffice"
fi
```

If running in **PowerShell** (Windows without Git Bash):
```powershell
$VENV_PYTHON = "$HOME\.claude\skills\jetredline\.venv\Scripts\python.exe"
if (Test-Path "C:\Program Files\LibreOffice\program\soffice.exe") {
  $SOFFICE = "C:\Program Files\LibreOffice\program\soffice.exe"
  $SOFFICE_DIR = "C:\Program Files\LibreOffice\program"
} elseif (Test-Path "C:\Program Files (x86)\LibreOffice\program\soffice.exe") {
  $SOFFICE = "C:\Program Files (x86)\LibreOffice\program\soffice.exe"
  $SOFFICE_DIR = "C:\Program Files (x86)\LibreOffice\program"
} else {
  $SOFFICE = "soffice"
  $SOFFICE_DIR = ""
}
```

Use `$VENV_PYTHON`, `$SOFFICE`, and `$SOFFICE_DIR` in all subsequent commands instead of hardcoded paths.

**Environment variable syntax** differs by shell:
- Bash (macOS/Linux/Git Bash): `VAR=val command`
- PowerShell (Windows): `$env:VAR='val'; command`

## Skill and Docx Plugin Path Discovery

**Web mode:** Skip the next five sections (Skill/Docx Paths, Python Environment, Node.js Environment, LibreOffice, Temporary Files) — they apply only in CLI mode. Proceed to Workflow.

At the start of each CLI session, detect the skill directory and docx plugin layout. The docx plugin has different directory structures in Claude Code vs. Cowork.

```bash
# Detect skill directory
if [ -d "$HOME/.claude/skills/jetredline" ]; then
  SKILL_DIR="$HOME/.claude/skills/jetredline"
elif [ -d "/mnt/.skills/skills/jetredline" ]; then
  SKILL_DIR="/mnt/.skills/skills/jetredline"
fi

# Detect docx plugin location and layout
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

Use `$SKILL_DIR`, `$DOCX_SKILL`, `$UNPACK_SCRIPT`, and `$PACK_SCRIPT` in all subsequent commands.

| Resource | Path |
|----------|------|
| This skill | `$SKILL_DIR` |
| Docx skill | `$DOCX_SKILL` (detected above) |
| Unpack script | `$UNPACK_SCRIPT` (detected above) |
| Pack script | `$PACK_SCRIPT` (detected above) |
| Venv python | `$VENV_PYTHON` (see Python Environment below) |
| splitmarks | `$SKILL_DIR/splitmarks.py` |
| Node modules | `$SKILL_DIR/node_modules/` |
| soffice (LibreOffice) | `$SOFFICE` (macOS: `/Applications/LibreOffice.app/Contents/MacOS/soffice`, Linux: `soffice`) |
| ND opinions (markdown) | `$OPINIONS_MD` → `~/cDocs/refs/ndsc_opinions/markdown/` |
| ND citation checker | `$SKILL_DIR/nd_cite_check.py` |
| Readability metrics | `$SKILL_DIR/readability_metrics.py` |
| ND legal refs | `~/refs/` (opinions, NDCC, constitution, NDAC) |
| OOXML fixup | `$SKILL_DIR/ooxml_fixup.py` |
| OOXML validate | `$SKILL_DIR/ooxml_validate.py` |
| Citation review | `$SKILL_DIR/cite_review.py` |
| Batch edit helper | `$SKILL_DIR/apply_edits.py` |

The opinions directory contains markdown copies of published ND Supreme Court opinions organized as `<year>/<year>ND<number>.md` (e.g., `2022/2022ND210.md` for *Feickert v. Feickert*, 2022 ND 210). Paragraphs are marked `[¶N]`. Use `$OPINIONS_MD` in commands; fall back to the hardcoded path if the variable is unset.

The `~/refs/` directory contains a local repository of ND legal materials in markdown format: opinions (`opin/markdown/`), NDCC (`ndcc/`), ND Constitution (`cnst/`), and NDAC (`ndac/`). The citation checker resolves these paths automatically.

## Python Environment

This skill has a persistent virtual environment. **Always use this venv python for all Python operations — never create a new venv in the working directory.**

- **Pre-installed packages:** `defusedxml`, `httpx[socks]`, `pikepdf`, `textstat`
- **Bundled scripts:** `splitmarks.py` (vendored; no install needed — `pikepdf` satisfies its only dependency)

Set `$VENV_PYTHON` with a fallback for read-only filesystems (Cowork):

```bash
VENV_DIR="$SKILL_DIR/.venv"
if ! mkdir -p "$VENV_DIR" 2>/dev/null; then
  # Skill dir is read-only (Cowork) — use session-local venv
  VENV_DIR="/tmp/jetredline-venv"
    if [ ! -d "$VENV_DIR" ]; then
      python3 -m venv "$VENV_DIR"
      "$VENV_DIR/bin/pip" install -r "$SKILL_DIR/requirements.txt" -q
    fi
fi
VENV_PYTHON="$VENV_DIR/bin/python"
```

  If the venv does not exist or a package is missing in a writable environment, create/repair it:
  ```bash
  uv venv "$SKILL_DIR/.venv"
  uv pip install -r "$SKILL_DIR/requirements.txt" --python $VENV_PYTHON
  ```

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

The `docx` npm package is pre-installed in this skill's directory. **Do not run `npm install` — it is already available.**

When running Node scripts that use `docx`, set `NODE_PATH` so Node can find the package:
```bash
NODE_PATH=~/.claude/skills/jetredline/node_modules node script.js
```

When running docx skill scripts (always include TMPDIR — use the literal absolute path from Step 0):
```bash
TMPDIR=<TMPDIR> PYTHONPATH=$DOCX_SKILL $VENV_PYTHON script.py
```
where `<TMPDIR>` is the literal path captured in Step 0 (e.g., `/path/to/cases/smith/.tmp-apple-walrus-quilt`).

## LibreOffice (soffice)

`soffice` may not be on PATH by default. **Always prepend the LibreOffice path when invoking soffice:**

```bash
PATH="$SOFFICE_DIR:$PATH" $SOFFICE --headless --convert-to pdf <input.docx>
```
where `$SOFFICE_DIR` was set in Platform Detection above.

Note: `apply_edits.py` operates directly on .docx ZIP files and does not use LibreOffice or the docx plugin's pack/unpack scripts. LibreOffice is only needed for document-to-image/PDF conversion.

## Workflow

### Step 0: Initialize and Scan Working Directory

**Web mode:** Skip temp directory creation, update check, and directory scanning. The user will paste text or upload .docx/.pdf files directly in the conversation. Claude can read uploaded .docx and .pdf files natively. Proceed to Step 0.1.

**Update check:** Run `python3 ~/.claude/skills/jetredline/check_update.py` silently. If it prints output, include it as a note to the user.

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
$VENV_PYTHON ~/.claude/skills/jetredline/splitmarks.py packet.pdf --dry-run -vv

# Split into individual files in an output directory
$VENV_PYTHON ~/.claude/skills/jetredline/splitmarks.py packet.pdf -o split_output -v
```

**Recursive split:** After the initial split, check the resulting files. If any single file is still **> 10 MB** (typically a record bundle containing many individual record items), split it again into a subdirectory:
```bash
$VENV_PYTHON ~/.claude/skills/jetredline/splitmarks.py split_output/Record-Bundle.pdf -o split_output/record_items -v
```
This produces individual record-item files (e.g., `R1-Application.pdf`, `R58-Amended-Petition.pdf`) that can be targeted efficiently during fact-checking.

Pass the resulting file paths to the fact-checking subagent in Pass 4.

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

**Web mode:** Do not ask for output preferences. Only the markdown analysis document is available — tracked-changes .docx requires CLI tools (Bash, docx skill, LibreOffice). State this briefly: "In this environment I can produce a markdown analysis report but not a tracked-changes .docx." Proceed unless the user objects.

**CLI mode:** Default to producing **both** documents (tracked-changes .docx + analysis document) without asking. Only ask if the user explicitly specified a different preference in their invocation (e.g., "just the redline" or "analysis only").

If the user did specify a preference, honor it:
- If **both** (default): Follow the full workflow through Step 10
- If **tracked-changes only**: Complete all editing passes, produce the .docx in Step 9, skip Step 10 (analysis document)
- If **analysis only**: Complete all editing passes and collect findings, produce only the analysis document in Step 10, skip Step 9 (.docx creation)

**Note:** Even when producing analysis only, you must still perform all editing passes (1–7) to identify issues and generate findings for the analysis. You simply skip the final .docx assembly step.

### Steps 1–10: Core Workflow
1. Read `references/style-guide.md`
2. Read the docx skill: Read `SKILL.md` from `$DOCX_SKILL`. If `ooxml.md` exists as a separate file in that directory, read it too; otherwise the OOXML XML reference is embedded in `SKILL.md`. **Do not** read `docx-js.md`, `document.py`, or other files — they are executed by scripts and not needed in context.
3. Read the draft opinion (from Step 0 or user-provided file/pasted text). **Count paragraphs** (¶ markers or logical paragraphs) to determine opinion length.
4. **Delegate Pass 1** (jurisdictional check) to a subagent — see Pass 1 below
5. **Delegate Pass 3** (citation verification) to a subagent — see Pass 3 below
6. **Delegate Pass 4** (fact-checking) to a subagent if PDF materials were identified in Step 0 — see Pass 4 below
6a. **Delegate Pass 6** (brief matching) to a subagent if briefs were identified in Step 0 — see Pass 6 below
6b. **Delegate Pass 7** (dissent/concurrence cross-check) to a subagent if a dissent or concurrence was identified in Step 0 and `DOC_TYPE == opinion` — see Pass 7 below
7. **Pass 2 routing:** If the opinion has **more than 30 paragraphs**, delegate Pass 2 to a subagent — see "Delegated Pass 2" below. Otherwise, perform Pass 2 in main context. **Pass 5** (analytical rigor) is always performed in main context. Pass 2 (when not delegated) and Pass 5 can proceed in parallel with subagents.
8. Collect subagent results from Passes 1, 3, 4, 6, 7, and (if delegated) Pass 2 — **use the `TaskOutput` tool**, not Bash `tail`
9. **If user requested tracked-changes .docx** (both or tracked-changes only): Produce tracked-changes .docx output using the batch edit workflow (see Step 9 details below)
10. **If user requested analysis document** (both or analysis only): Produce the companion analysis document (incorporating all subagent results). If also producing .docx, create both outputs in the same response
11. **Generate citation review HTML** (CLI mode only): After Pass 3 completes, generate an interactive citation review page for human verification:
```bash
$VENV_PYTHON ~/.claude/skills/jetredline/cite_review.py \
  --opinion <opinion_md_path> \
  --refs-dir ~/refs \
  --title "<case caption>" \
  --output <output_dir>/cite-review.html
```
This produces a self-contained HTML file that displays each citation alongside the cited authority for visual confirmation. Tell the user the file is available and can be opened in a browser.

**If the opinion is a .docx file:** use the docx skill's unpack workflow, then apply edits via `apply_edits.py`.

**Single-session editing.** All tracked changes and comments must be applied in a single script execution against a single unpack. Do not unpack → edit → pack → unpack again. Multiple cycles cause ID collisions and orphaned artifacts. If retrying, start fresh from the original .docx.

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
11. Skip .docx assembly.
12. Produce the analysis document as markdown in the conversation.

**Context limits:** Without subagents, very long documents (50+ paragraphs) may approach context limits. If this occurs, prioritize: Pass 2 → Pass 5 → Pass 3A → Pass 1 → Pass 3B → Pass 4 → Pass 6 → Pass 7. Inform the user which passes were completed.

## Editing Instructions

Adopt the persona of an experienced appellate attorney working for a state supreme court. Be careful and precise.

### Pass 1: Jurisdictional Check (Delegated to Subagent)

**Do not** read `references/nd-appellate-rules.md` into the main context. Delegate this pass to a subagent using the Task tool (subagent_type: `general-purpose`) with instructions that vary by `DOC_TYPE`.

#### If DOC_TYPE is `opinion` (default)

Provide the subagent with these instructions:

- Read `~/.claude/skills/jetredline/references/nd-appellate-rules.md`
- Read the draft opinion file (provide the path) — focus on the procedural-posture and standard-of-review sections
- Verify: Was there a timely appeal under N.D.R.App.P. Rules 2.1, 2.2, 3, and 4?
- Verify: Does the opinion correctly identify the procedural posture and standard of review?
- Verify: Are court rules cited accurately? Check against https://www.ndcourts.gov/legal-resources/rules
- Return **only** a concise summary of findings: any jurisdictional issues, procedural-posture errors, or standard-of-review problems. If no issues found, state that explicitly.

#### If DOC_TYPE is `memo`

Provide the subagent with these instructions:

- Read `~/.claude/skills/jetredline/references/nd-appellate-rules.md`
- Read the draft memo file (provide the path)
- Check whether the memo addresses appealability: timeliness, subject-matter jurisdiction, and procedural prerequisites (e.g., OMB notification for claims against the state under N.D.C.C. § 32-12.2-04)
- Check whether the parties' briefs (if available in the working directory) raise jurisdictional issues
- If **neither** the memo nor the parties address appealability at all → return a **warning** that the memo should confirm appellate jurisdiction
- If the memo does address appealability → verify the analysis against `nd-appellate-rules.md` as with opinions
- Return a concise summary: any jurisdictional concerns or warnings. If the memo adequately addresses jurisdiction, state that explicitly.

**Web mode:** Perform inline. Read `references/nd-appellate-rules.md` from project knowledge. If unavailable, use web search to find the relevant N.D.R.App.P. rules at ndcourts.gov. Analyze the document's procedural posture and standard of review. Report findings in the same format.

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

When the opinion exceeds 30 paragraphs, delegate Pass 2 to a Task subagent (subagent_type: `general-purpose`) to keep main-context output tokens manageable. Provide the subagent with:

- The path to `references/style-guide.md` (instruct it to read this file)
- The path to the draft opinion file (instruct it to read it)
- The hard rules and style preferences listed above (copy them into the prompt so the subagent has them without needing additional context)

**Subagent instructions:**

> **Style and Grammar Edit — Pass 2**
>
> Read the style guide at `~/.claude/skills/jetredline/references/style-guide.md` and the draft opinion at `[path]`.
>
> Apply the style and grammar rules to the entire opinion. For each proposed edit, produce a structured entry:
>
> ```
> ¶ [paragraph number]
> OLD: [exact original text — enough context to locate uniquely, typically the full sentence]
> NEW: [replacement text]
> REASON: [brief explanation — which rule applies]
> ```
>
> Group entries by paragraph order. Include only changes that improve the text — do not rewrite clear passages. Preserve the court's voice.
>
> For issues that warrant a comment rather than a direct edit (e.g., possible restructuring, ambiguous meaning), use:
>
> ```
> ¶ [paragraph number]
> COMMENT: [the note to attach as a comment in the document]
> ANCHOR: [the word or phrase the comment should attach to]
> ```
>
> Return all entries as a single structured list. Do not produce any other output.

**In main context after collection:** Apply the returned edits mechanically when building the tracked-changes OOXML in step 9. Each `OLD`/`NEW` pair becomes a tracked deletion + tracked insertion. Each `COMMENT` entry becomes a document comment anchored to the specified text.

**Web mode:** Always perform inline, regardless of document length. Apply the same rules. Use the structured entry format (¶, OLD, NEW, REASON) for internal tracking, then incorporate into the analysis document.

### Pass 3: Citation Check (Delegated to Subagent)

Pass 3 has two parts: (A) Bluebook format checking, done in the main context, and (B) substantive citation verification against local ND opinion files, delegated to a subagent.

#### Part A: Format Check (Main Context)

Perform these checks in main context as part of Passes 2/5 work:
- Verify Bluebook format for all citations
- Check ND-specific conventions (formats in `references/style-guide.md`)
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

**Delegation:** Launch a Task subagent (subagent_type: `general-purpose`) with the extracted citation list and the following instructions:

> **ND Citation Verification**
>
> You have a list of ND citations from a draft opinion. Verify each against local reference files and official online sources.
>
> **Step 1: Generate the lookup plan.** Run the citation checker on the opinion file to get structured resolution data:
> ```bash
> python3 ~/.claude/skills/jetredline/nd_cite_check.py --file <opinion_path> --refs-dir ~/refs
> ```
> This outputs a JSON array with one entry per citation found. Each entry includes:
> - `cite_type`: nd_case, ndcc, ndcc_chapter, nd_const, ndac, nd_court_rule
> - `local_path` / `local_exists`: path in `~/refs/` and whether it exists
> - `url`: official source URL (always populated)
> - `search_hint`: text to search for within the local file
>
> **Step 2: Verify each citation.** For each entry from the lookup plan:
>
> 1. **Retrieve source text.**
>    - If `local_exists` is `true`: use the Read tool on `local_path`. For NDCC sections, search for the `search_hint` within the chapter file. For ND opinions, locate the pinpoint paragraph (`[¶N]`).
>    - If `local_exists` is `false`: use WebFetch on the `url` to retrieve the source text. For PDF URLs (ndlegis.gov), note that WebFetch may not extract PDF content — mark as "URL only" and verify what you can.
>
> 2. **If the opinion quotes the cited source:**
>    - Compare the quoted text against the source **character by character**.
>    - Flag any discrepancies (missing words, changed words, transpositions).
>    - Identify any bracketed alterations (`[word]`, `[W]ord` for capitalization changes, ellipses `...` or `. . .` for omissions).
>    - For each alteration, note whether the opinion includes an appropriate parenthetical (e.g., "(alteration in original)", "(cleaned up)", "(emphasis added)", "(omission)", "(quoting [Source])"). Under Bluebook Rule 5.2, alterations to quoted material must be indicated.
>    - Report the result as: **Quote verified** (exact match), **Quote verified with noted alterations** (brackets/ellipses present and properly parentheticized), or **Quote discrepancy** (unexplained differences).
>
> 3. **Existence check.** Does the cited provision/opinion actually exist? For statutes and rules, confirm the section number is valid.
>
> 4. **Substantive support check.** Read the cited material in context and assess whether it supports the proposition for which it is cited. Consider:
>    - Does the source actually state or hold the legal principle attributed to it?
>    - Is the signal appropriate? (No signal = direct support; *See* = clearly supports; *see also* = additional support; *cf.* = analogous; *but see* = contrary)
>    - Is the proposition a fair characterization, or does it overstate/understate/distort the source?
>    - Report: **Supports** (the cite supports the proposition), **Partially supports** (some nuance lost or overstated), or **Does not support** (the cite does not stand for the stated proposition).
>
> 5. **Currency check** (statutes, rules, admin code only). If the source text includes effective date or amendment information, flag if the cited version may not be current.
>
> 6. **Build the results table.** The Source Link column **must** use the full `url` value from the nd_cite_check.py JSON output as a markdown hyperlink — e.g., `[N.D.C.C. § 12.1-32-01](https://ndlegis.gov/cencode/t12c32.pdf#nameddest=12-32-01)`. Never link to just a domain root like `https://ndlegis.gov/`. Every citation's `url` field already points to the specific document; use it verbatim.
>
> | ¶ | Citation | Type | Quote Check | Supports? | Source Link | Notes |
> |---|----------|------|-------------|-----------|-------------|-------|
> | [¶] | [Citation text] | Opinion / Statute / Const. / Rule / Admin. | Verified / Discrepancy / No quote / Not found | Supports / Partially / Does not support | [Markdown hyperlink: `[normalized](url)`] | [Explanation] |
>
> For locally-verified citations, still include the official URL from the lookup plan so readers can independently check the source. The URL was already computed — do not substitute or shorten it.
>
> 7. **Return** the completed table and a summary: [X] ND citations checked, by type: [opinions/statutes/const/rules/admin]. [Y] quotes verified. [Z] quote discrepancies. [W] not found. [V] citations that may not support the stated proposition.
>
> **Error handling:**
> - If `nd_cite_check.py` fails or returns an error, report the error in the summary and proceed with manual verification using the URL patterns and local paths below.
> - If a local reference file does not exist for a citation, proceed with web verification only (WebFetch on the `url`). Do not stall or re-search for the file.
> - If WebFetch also fails, mark the citation as **UNVERIFIED** in the results table with the reason (e.g., "Local file missing, URL unreachable").
> - Always return partial results. A table with UNVERIFIED entries is better than no table. Never fail silently — every citation must appear in the output table with a status.
>
> **Reference file paths (do not search — use directly):**
> - ND opinions (markdown): `~/refs/opin/markdown/` — organized as `<year>/<year>ND<number>.md`
> - ND Century Code: `~/refs/ndcc/` — organized by title/chapter
> - ND Constitution: `~/refs/cnst/`
> - ND Administrative Code: `~/refs/ndac/`

**Web mode:** Skip local resolution — no `~/refs/` directory is available.
1. Run `nd_cite_check.py` with `--refs-dir /dev/null` (or skip the script entirely and use the URL patterns below).
2. For each ND citation, use WebFetch on the URL from the lookup plan.
3. For ND case citations, use web search to locate the opinion on ndcourts.gov or Google Scholar.
4. Verify quotes and substantive support as described above.
5. If a source cannot be retrieved, mark as "Not verified — source unavailable."
6. Note in the Citation Verification section: "Citations verified via URL lookup against official sources. Local reference files unavailable."

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

**Delegation:** Launch a Task subagent (subagent_type: `general-purpose`) with the following instructions and the extracted claims list:

- For each PDF source file, extract text locally: `pdftotext <file>.pdf <file>.txt`
- Use Grep to search the extracted `.txt` files for passages relevant to each claim — **do not** read entire documents into context
- For claims with cited record items, search those files first. Then search the remaining record-item files for corroborating or contradicting evidence.
- For each claim, build a row:

| ¶ | Claim | Source Document(s) | Result | Notes |
|---|-------|-------------------|--------|-------|
| [¶ ref] | [Factual assertion] | [Source with pinpoint cite] | Verified / Unverified / Discrepancy | [Explanation] |

- Return the completed table with a summary line: [X] facts checked, [Y] verified, [Z] discrepancies, [W] unverified.

**No source materials:** If the user does not provide source materials, skip delegation. Note this limitation in the analysis and flag any factual assertions that cannot be independently verified.

**Web mode:** If the user uploaded PDF source materials, read them directly (no pdftotext needed). Perform fact-checking inline. For large documents, focus on the extracted claims rather than reading entire files. If no source materials were uploaded, note this limitation.

### Pass 6: Brief Matching (Delegated to Subagent)

When briefs are available (identified in Step 0), check whether the opinion or memo addresses every argument raised by the parties. This pass applies to both `opinion` and `memo` document types.

**Do not** read the briefs into the main context. Delegate to a subagent to keep PDF content out of the main context window.

**Delegation:** Launch a Task subagent (subagent_type: `general-purpose`) with the path to the draft document and the brief file(s):

> **Brief-Matching — Pass 6**
>
> Read the draft document at `[path]` and the party briefs at `[brief paths]`.
>
> For each brief, extract text locally: `pdftotext <file>.pdf <file>.txt`
>
> **Step 1:** Extract every distinct argument or contention from each party's brief. For each argument, record:
> - The party (Appellant/Appellee/Petitioner/Respondent)
> - A one-sentence summary of the argument
> - The brief and page range where the argument appears (e.g., "Appellant's Brief, pp. 12–15")
>
> **Step 2:** For each argument, search the draft document for responsive discussion. An argument is "addressed" if the document engages with the substance of the contention — not merely mentioning the topic. Classify as:
> - **Yes** — the document directly addresses the argument
> - **Partial** — the document touches on the topic but does not fully engage (e.g., acknowledges without analysis)
> - **No** — no responsive discussion found
>
> **Step 3:** Build the results table:
>
> | ¶ | Argument | Party | Brief Source | Addressed | Notes |
> |---|----------|-------|-------------|-----------|-------|
> | [¶ ref or "—"] | [Argument summary] | [Party] | [Brief, pp. X–Y] | Yes / Partial / No | [Where addressed, or what's missing] |
>
> The ¶ column references where in the draft the argument is addressed (or "—" if not addressed).
>
> **Step 4:** Return the table and a summary: [X] arguments identified across [N] briefs. [Y] directly addressed. [Z] partially addressed. [W] not addressed.

**No briefs available:** If no briefs were provided in Step 0, skip this pass entirely. Note in the analysis document: "No briefs provided — brief matching skipped."

**Web mode:** If the user uploaded briefs, perform inline — read the briefs directly and follow the same extraction and matching process. If no briefs were uploaded, note the limitation.

### Pass 7: Dissent/Concurrence Cross-Check (Delegated to Subagent)

When a dissent or concurrence is provided alongside the majority opinion, cross-check for fair characterization and responsiveness. This pass applies **only** when `DOC_TYPE == opinion` and a dissent or concurrence file was identified in Step 0.

**Do not** read the dissent/concurrence into the main context. Delegate to a subagent to keep the separate document out of the main context window.

**Delegation:** Launch a Task subagent (subagent_type: `general-purpose`) with the paths to both documents:

> **Dissent/Concurrence Cross-Check — Pass 7**
>
> Read the majority opinion at `[majority path]` and the dissent/concurrence at `[dissent path]`.
>
> **Step 1: Catalog dissent arguments.** For each distinct argument or criticism in the dissent/concurrence, record:
> - The paragraph(s) where it appears
> - A one-sentence summary
> - Whether it criticizes the majority's reasoning, result, or both
>
> **Step 2: Check majority responsiveness.** For each dissent argument:
> - Does the majority acknowledge the criticism? (Yes / No)
> - Does the majority respond substantively? (Yes / Partial / No)
> - Is the majority's characterization of the dissent's position fair and accurate? (Yes / No / Partial — flag straw-man characterizations)
>
> **Step 3: Check dissent fairness.** For each major argument in the majority:
> - Does the dissent fairly characterize the majority's position? (Yes / No / Partial — flag straw-man characterizations)
> - Does the dissent misquote or misrepresent the majority? Flag specific passages.
>
> **Step 4: Build the results table:**
>
> | ¶ Majority | ¶ Dissent | Argument | Fair Characterization? | Addressed? | Notes |
> |-----------|-----------|----------|----------------------|------------|-------|
> | [¶] | [¶] | [Criticism or argument] | Yes / No / Partial | Yes / No / Partial | [Explanation] |
>
> **Step 5:** Return the table and a summary: [X] dissent arguments reviewed. [Y] fairly characterized by majority. [Z] potential straw-manning identified. [W] unaddressed criticisms. [V] instances where dissent mischaracterizes majority.

**No dissent/concurrence available:** If no dissent or concurrence was identified in Step 0, or `DOC_TYPE != opinion`, skip this pass entirely.

**Web mode:** If the user uploaded a dissent/concurrence alongside the majority, perform inline — read both documents directly and follow the same cross-check process. If no dissent was uploaded, note the limitation.

### Pass 5: Analytical Rigor

Perform the following checks on **all documents** (both opinions and memos), then the DOC_TYPE-specific checks below. Full details for both document types are in `references/style-guide.md`.

#### Internal Consistency Check (all doc types)

Read the entire document and build a mental index of: party names (including aliases and roles), dates, monetary amounts, numerical counts, procedural events, and terminology choices. Compare every reference to each entity, date, and event across the document. Flag any discrepancy with paragraph references for both the first usage and the inconsistent usage.

Check for:
- **Name/spelling inconsistencies** (e.g., "Johnson" vs "Johnsen", "Meier" vs "Meyer")
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

#### Readability Metrics (all doc types)

**CLI mode:** Run the readability metrics script on the document:
```bash
$VENV_PYTHON ~/.claude/skills/jetredline/readability_metrics.py --file <document_path>
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

**Summary:** [X] facts checked. [Y] verified. [Z] discrepancies. [W] unverified.

## Brief Matching

| ¶ | Argument | Party | Brief Source | Addressed | Notes |
|---|----------|-------|-------------|-----------|-------|
| [¶ ref] | [Argument/contention] | [Appellant/Appellee] | [Brief, pp. X–Y] | Yes / Partial / No | [Explanation] |

**Summary:** [X] arguments identified. [Y] directly addressed. [Z] partially addressed. [W] not addressed.

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
*Generated by JetRedline v3.5.2 (2026-03-23)*
*Crafted by Claude Opus 4.6 & Justice Jerod Tufte*

–End Analysis–
```

### Citation review HTML (CLI mode, always generated)

After Pass 3 completes and the opinion markdown is available, generate an interactive citation review page:

```bash
$VENV_PYTHON ~/.claude/skills/jetredline/cite_review.py \
  --opinion <opinion_md_path> \
  --refs-dir ~/refs \
  --title "<case caption>" \
  --output <output_dir>/cite-review.html
```

This produces a self-contained HTML file with:
- A sidebar listing every citation with verification status
- A split main pane: draft paragraph (with citation highlighted) on top, the cited authority loaded in an iframe on bottom
- Keyboard navigation (`j`/`k` to move, `v`/`f`/`s` to verify/flag/skip, `n` for notes)
- LocalStorage persistence so review state survives browser restarts
- An "Export JSON" button to save the review state

Tell the user the citation review file is available and can be opened in any browser. Name it `<original-filename>-CITE-REVIEW.html`.

## Key Reminders

- Minimal edits: change only what improves the text. Do not rewrite clear passages.
- Preserve the court's voice. Polish, do not impose a different style.
- When uncertain, use a comment rather than a tracked change.
- For complex restructuring, describe the proposal in a comment.
- Bold changed words in the analysis to distinguish from unchanged text.

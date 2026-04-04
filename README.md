# JetRedline

Appellate judicial opinion and bench memo editor and proofreader. Produces a Word document (.docx) with tracked changes showing proposed edits, plus a separate analysis document with explanations. Applies Garner's Redbook, Bluebook citation format, and style preferences drawn from Justice Jerod Tufte (ND Supreme Court).

## Caution: Privacy Settings Before Use

<img width="541" height="137" alt="Screenshot 2026-03-07 at 15 31 25" src="https://github.com/user-attachments/assets/b552ef6a-0e66-41f1-91b8-21b02e49b76d" />

## The editing pipeline runs seven passes:

1. **Jurisdictional check** — verifies timeliness of appeal, procedural posture, and standard of review against the ND Rules of Appellate Procedure
2. **Style and grammar** — applies Redbook rules and plain-language preferences; produces structured edit list
3. **Citation check** — Bluebook format review (3A) and substantive verification of ND, federal, and state citations against local reference files and official sources (3B)
4. **Fact check** — verifies factual claims against party briefs and record materials, with claim-to-record mapping
5. **Analytical rigor** — internal consistency, standard-of-review consistency, readability metrics, and (for opinions) structural completeness
6. **Brief matching** — confirms the opinion or memo addresses every argument raised by the parties
7. **Dissent/concurrence cross-check** — checks fair characterization and responsiveness between majority and separate writings

Passes 1–7 run as parallel subagents where possible. After all passes complete, the pipeline collects results and produces up to two outputs: a tracked-changes .docx (Pass 2 edits become tracked insertions/deletions; other pass findings become document comments; `apply_edits.py` operates directly on the .docx ZIP archive with no unpack/pack pipeline) and a companion analysis document summarizing all findings. The analysis document is also saved as a markdown file in the working directory.

## Analysis Document

The analysis document includes the following sections (some vary by document type):

- **Case Highlight** (opinions only) — case name, citation, disposition, and core holdings
- **Jurisdictional Notes** — timeliness, procedural posture, and standard of review issues
- **Summary of Edits** — overview of types and volume of changes
- **Fact Check** — table of factual claims verified against record materials
- **Brief Matching** — table showing whether each party argument is addressed
- **Internal Consistency** — name, date, and terminology discrepancies across the document
- **Standard of Review Consistency** — whether deference language matches stated standards
- **Readability Metrics** — Flesch-Kincaid grade, sentence length, passive voice, and nominalization density by section
- **Substantive Concerns** (opinions) — potential dicta, alternative rationales, ambiguity/vulnerability, logical issues, and dissent/concurrence cross-check
- **Memo Analysis** (memos) — issue completeness, balance of presentation, recommendation assessment, analytical gaps, and standard of review application
- **Citation Verification** — table with quote checks, substantive support assessments, and source links
- **Citation Format Issues** — Bluebook corrections
- **Style Notes** — significant style changes by category

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (CLI) or [Claude Desktop](https://claude.ai/download) with Cowork
- Python 3.10+
- Node.js 18+ (for creating new .docx from scratch; not needed for tracked-changes editing)
- [LibreOffice](https://www.libreoffice.org/) (for document-to-PDF conversion; not needed for tracked-changes editing)
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

**Windows additional requirements:**
- PowerShell 5.1+ (included with Windows 10/11)
- Git Bash (recommended, included with [Git for Windows](https://gitforwindows.org/))

## Installation

JetRedline installs as a skill to `~/.claude/skills/jetredline/`. Both Claude Code (CLI) and Claude Desktop with Cowork use the same skill directory, so any of the options below work for either.

**Option A: From .zip**

1. Download and extract [`jetredline-skill.zip`](https://github.com/jet52/jetredline/releases/latest/download/jetredline-skill.zip)
2. Run the installer:
   - **macOS/Linux:**
     ```bash
     bash install.sh
     ```
   - **Windows (PowerShell):**
     ```powershell
     powershell -ExecutionPolicy Bypass -File install.ps1
     ```
   The installer will:
   - Copy skill files to `~/.claude/skills/jetredline/`
   - Create a Python virtual environment with required packages
   - Run `npm install` for the `docx` Node.js package

**Option B: From source**

```bash
git clone https://github.com/jet52/jetredline.git
cd jetredline
make install
```

**Option C: Manual**

macOS/Linux:
```bash
mkdir -p ~/.claude/skills/jetredline
cp -a skills/jetredline/* ~/.claude/skills/jetredline/

cd ~/.claude/skills/jetredline
uv venv .venv
uv pip install -r requirements.txt --python .venv/bin/python
npm install
```

Windows (PowerShell):
```powershell
New-Item -ItemType Directory -Force -Path "$HOME\.claude\skills\jetredline"
Copy-Item -Path "skills\jetredline\*" -Destination "$HOME\.claude\skills\jetredline" -Recurse -Force

Set-Location "$HOME\.claude\skills\jetredline"
uv venv .venv
uv pip install -r requirements.txt --python .venv\Scripts\python.exe
npm install
```

### Claude Projects (web)

1. Download [`jetredline-skill.zip`](https://github.com/jet52/jetredline/releases/latest/download/jetredline-skill.zip) from GitHub
2. Open your Claude Project → Project Knowledge
3. Upload `jetredline-skill.zip`
4. Paste opinion text or upload .docx/.pdf files in conversation
5. Use the same trigger phrases ("edit this opinion", "edit this bench memo", etc.)

**Web mode limitations:**
- Produces markdown analysis only (no tracked-changes .docx)
- All passes run inline — no subagent delegation (may hit context limits on very long opinions)
- Citation verification uses web search instead of local opinion corpus (less reliable)
- No PDF splitting for large record packets (upload individual documents)

## Usage

Trigger phrases:

- "Edit this opinion"
- "Proofread this opinion"
- "Review this draft opinion"
- "Redline this opinion"
- "Redline this draft"
- "Redline this memo"
- "Edit this draft order"

Provide a `.docx` draft opinion in the working directory. Optionally include `.pdf` briefs or record materials for fact-checking.

## File Structure

```
jetredline/
├── skills/
│   └── jetredline/
│       ├── SKILL.md
│       ├── VERSION
│       ├── package.json
│       ├── requirements.txt
│       ├── apply_edits.py          # Tracked-changes batch editor (direct ZIP)
│       ├── cite_check.py           # Citation checker (uses bundled jetcite)
│       ├── cite_review.py          # Interactive citation review HTML generator
│       ├── lib/
│       │   └── jetcite/            # Vendored jetcite (run `make vendor-jetcite` to update)
│       ├── check_update.py         # Version check on session start
│       ├── readability_metrics.py  # FK grade, passive voice, etc.
│       ├── splitmarks.py           # PDF bookmark splitter (bundled)
│       ├── ooxml_fixup.py          # OOXML debugging tool (not in main pipeline)
│       ├── ooxml_validate.py       # OOXML debugging tool (not in main pipeline)
│       └── references/
│           ├── nd-appellate-rules.md
│           └── style-guide.md
├── install.sh
├── install.ps1
├── LICENSE
├── Makefile
├── README.md
└── .gitignore
```

## External Dependencies

| Dependency   | Purpose                        | Required?                    |
| ------------ | ------------------------------ | ---------------------------- |
| Python 3.10+ | PDF/XML processing             | Yes                          |
| Node.js 18+  | New .docx creation from scratch| Only if not editing existing  |
| LibreOffice  | Document-to-PDF conversion     | Only for PDF/image export    |
| defusedxml   | Safe XML parsing               | Yes (installed by installer) |
| pikepdf      | PDF manipulation               | Yes (installed by installer) |
| splitmarks   | PDF bookmark splitting         | Bundled script (no install)  |
| textstat     | Readability metrics            | Yes (installed by installer) |
| jetcite      | Citation parsing and linking   | Bundled (vendored source)   |
| docx (npm)   | New .docx creation from scratch| Only if not editing existing  |

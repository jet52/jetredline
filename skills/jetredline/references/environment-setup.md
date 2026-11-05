# Environment Setup — full detail (CLI mode)

SKILL.md carries the three commands every run needs (bootstrap, skill dir, temp dir) and the permission-matchability rules in short form. This file holds the rest: the venv ladder and manual fallback, the full rationale for the command discipline, docx-plugin discovery (new-.docx creation path only), the resource table, and the Node.js environment. Read it when a setup step fails or when the Step 9 alternative path (creating a .docx from non-.docx input) applies.

`$SKILL_DIR` below is the literal skill directory SKILL.md told you to set from `${CLAUDE_SKILL_DIR}` (the harness substitutes that placeholder only in SKILL.md itself, so this file writes the variable instead). Keep every path double-quoted — on Windows the directory may contain spaces.

## Python Environment (Bootstrap)

At the start of each CLI session, run the bootstrap script once with any system Python (`python3`, or `python` on Windows/PowerShell):

```bash
python3 "$SKILL_DIR/bootstrap_env.py"
```

The script finds or builds the skill's virtual environment and prints one line:

```
VENV_PYTHON=<absolute path>
```

**Capture that path as a literal string** and use it in place of `$VENV_PYTHON` in every Python command (same pattern as `TMPDIR`; no command substitution). It works in every install layout: a prebuilt `.venv` inside the skill directory (used and, if a package is missing, repaired in place), else a cached venv at `~/.cache/jet-skills/jetredline/<version>/` (built on first use), else a temp-dir venv (read-only home, e.g. Cowork). Packages provided: `beautifulsoup4`, `defusedxml`, `httpx[socks]`, `markdownify`, `pdfplumber`, `pypdf`, `textstat`. Never create a venv in the working directory.

The script is idempotent and cheap after the first run. If it fails outright (exit 1 — no writable location or no network for the first build), fall back to manual creation and use its python the same way:

```bash
python3 -m venv /tmp/jetredline-venv
/tmp/jetredline-venv/bin/pip install -r "$SKILL_DIR/requirements.txt" -q
```

Hardening the script already encodes (do not re-learn it): uv-built venvs lack `pip`, so package repair falls back to `uv pip install`; a venv created *from* a venv python breaks shared-library paths, so it always builds from the base interpreter; a corrupt cache venv is rebuilt; `httpx[socks]` is verified by importing `socksio`, which is exactly what Cowork's SOCKS proxy needs.

**Environment variable syntax** differs by shell:
- Bash (macOS/Linux/Git Bash): `VAR=val command`
- PowerShell (Windows): `$env:VAR='val'; command`

## Keep Commands Permission-Matchable

**CLI mode only** (no Bash in Web mode). Permission allowlists match on a command's **first token**. A run that ignores this generates a permission prompt per call — dozens across a full pass suite, most of them for reading a file the user already told the skill to read. Every rule below applies to **delegated subagents too**; the pass-instruction files repeat it, and a paraphrased delegation prompt must carry it as well.

- **Never `cd`.** `cd dir && cmd` makes the first token `cd`, so the rule written for `cmd` never matches. Pass absolute paths to the command instead, or use its own `-C` / `--directory` flag. This also removes the working-directory coupling that breaks when a later call runs from somewhere else.
- **Never prefix a command with variable assignments.** `TMPDIR=… $PY script.py` and `SP="…"; …` both make the first token an assignment, which no rule can match. Write the value into the argument directly. (The one exception is the docx-plugin creation path, which genuinely needs `PYTHONPATH`; it is rare and documented as such below.)
- **Invoke the venv python by the exact path `bootstrap_env.py` printed**, with no `$VENV_PYTHON` indirection at the shell level — substitute the literal string. The script deliberately prints the path spelling the caller invoked it by (the skill directory as given, not its symlink target) so that one allowlist entry covers every call.
- **Prefer a shipped helper to an ad-hoc script.** Writing a one-off `.py` into the scratchpad and running it produces a unique, unmatchable command every time. `pdf_page_grep.py` covers the common "find this string and report its page" need; reach for it before writing your own.
- **Quote paths containing spaces**, and always write absolute paths in full — `~` and `$HOME` are not expanded during matching, so they classify as runtime-determined and prompt even when the equivalent absolute path is allowlisted.

Portability: none of this depends on the platform. In Cowork the skill sits at a real path under `/mnt/.skills` and the scratchpad is under `/tmp`; the same "absolute paths, no `cd`, no assignment prefixes" discipline produces matchable commands there and in Claude Code alike.

## Skill Directory

The skill directory is `${CLAUDE_SKILL_DIR}` in SKILL.md — the harness substitutes the absolute path (standalone install, plugin cache, or Cowork mount alike), and the "Base directory for this skill:" line at the top of SKILL.md carries the same value. SKILL.md sets it once, with probes as a fallback in case substitution ever fails (an unsubstituted placeholder expands to an empty string):

```bash
SKILL_DIR="<the substituted ${CLAUDE_SKILL_DIR} value>"
if [ ! -d "$SKILL_DIR" ]; then
  if [ -d "$HOME/.claude/skills/jetredline" ]; then
    SKILL_DIR="$HOME/.claude/skills/jetredline"
  elif [ -d "/mnt/.skills/skills/jetredline" ]; then
    SKILL_DIR="/mnt/.skills/skills/jetredline"
  fi
fi
```

## Docx Plugin Discovery (conditional — usually not needed)

Reading a .docx draft uses `extract_text.py` and applying edits uses `apply_edits.py`; both operate directly on the .docx ZIP and need no plugin. The docx plugin is required **only** when creating a new .docx from scratch (plain-text/markdown input plus tracked-changes .docx output — the Step 9 alternative path). Run this discovery (and Step 2's docx-skill read) only when that path applies. The plugin has different directory structures in Claude Code vs. Cowork:

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

`$DOCX_SKILL`, `$UNPACK_SCRIPT`, and `$PACK_SCRIPT` exist only when this discovery was run. When it applies, Read `SKILL.md` from `$DOCX_SKILL` (and `ooxml.md` if it exists as a separate file; **do not** read `docx-js.md`, `document.py`, or other files).

## Resource Table

| Resource | Path |
|----------|------|
| This skill | `$SKILL_DIR` |
| Docx skill | `$DOCX_SKILL` (conditional — new-.docx creation only) |
| Venv python | `$VENV_PYTHON` (from `bootstrap_env.py`) |
| Text extraction | `$SKILL_DIR/extract_text.py` |
| splitmarks | `$SKILL_DIR/splitmarks.py` |
| Node modules | `$NODE_PATH` (from `bootstrap_env.py --node` — new-.docx creation only) |
| ND opinions (markdown) | `$OPINIONS_MD` → `~/cDocs/refs/ndsc_opinions/markdown/` |
| Citation checker | `$SKILL_DIR/cite_check.py` |
| Readability metrics | `$SKILL_DIR/readability_metrics.py` |
| PDF page grep | `$SKILL_DIR/pdf_page_grep.py` |
| Voice-file search | `$SKILL_DIR/voice_search.py` |
| Text-layer quality | `$SKILL_DIR/textquality.py` |
| Supplied-source PDFs | `$SKILL_DIR/pdfsource.py` |
| Authority matching | `$SKILL_DIR/authorities.py` |
| Legal refs | `~/refs/` (opin/, statute/, reg/, cnst/, rule/) |
| OOXML fixup | `$SKILL_DIR/ooxml_fixup.py` |
| OOXML validate | `$SKILL_DIR/ooxml_validate.py <file.docx>` — run it on the tracked-changes .docx after Step 9; exit 1 with diagnostic JSON means Word would call the file unreadable |
| Citation review | `$SKILL_DIR/cite_review.py` |
| Analysis report HTML | `$SKILL_DIR/analysis_to_html.py` |
| Batch edit helper | `$SKILL_DIR/apply_edits.py` |
| Provenance stamp | `$SKILL_DIR/provenance.py` |
| ndlaw export | `$SKILL_DIR/ndlaw_export.py` |
| Model gate / update / preflight | `$SKILL_DIR/check_model.py`, `check_update.py`, `preflight.py` (system `python3`, stdlib only) |

The opinions directory contains markdown copies of published ND Supreme Court opinions organized as `<year>/<year>ND<number>.md` (e.g., `2022/2022ND210.md` for *Feickert v. Feickert*, 2022 ND 210). Paragraphs are marked `[¶N]`. Use `$OPINIONS_MD` in commands; fall back to the hardcoded path if the variable is unset.

The `~/refs/` directory contains a local repository of legal materials in markdown format: opinions (`opin/{reporter}/`), statutes (`statute/NDCC/`, `statute/USC/`), constitutions (`cnst/ND/`, `cnst/US/`), regulations (`reg/NDAC/`, `reg/CFR/`), and court rules (`rule/{set}/`). The citation checker resolves these paths automatically via jetcite.

## Temporary Files

**CRITICAL:** In Step 0, create a uniquely-named temp directory and capture its **absolute path** as a literal string. Use that literal path (no command substitution) in all subsequent commands.

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

**Capture the output** and use it as a literal string in all subsequent commands. For example, if the output is `/path/to/cases/smith/.tmp-a1b2c3d4e5f6`, then every later command uses that literal in place of `<TMPDIR>`. **Never** use `TMPDIR="$(pwd)/.tmp"` — the command substitution triggers unnecessary permission prompts on every invocation.

## Node.js Environment

Needed **only** for the new-.docx creation path (Step 9 alternative). The `docx` npm package is either bundled in this skill's directory or installed once into the user cache by the bootstrap script:

```bash
python3 "$SKILL_DIR/bootstrap_env.py" --node
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

Note: `apply_edits.py` operates directly on the .docx ZIP archive — pure Python (`zipfile` + `defusedxml`), no unpack/pack pipeline and no external converter.

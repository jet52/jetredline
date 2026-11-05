# Step 9: Batch Edit Workflow (`apply_edits.py`)

SKILL.md Step 9 carries the command, the JSON shape, and the rules that matter on every run. This file holds the rest: the full schema, hyperlink edits, the nonbreaking-space dispositions with the counting command, what the script does internally, and the plain-text-input path. `$SKILL_DIR` and `$VENV_PYTHON` are the literal paths captured in SKILL.md's Environment Setup.

**If the opinion is a .docx file:** its text was already extracted in step 3 via `extract_text.py`; apply edits directly to the **original** .docx with `apply_edits.py` (no unpack/pack, no docx plugin).

**Single-session editing.** All tracked changes and comments must be applied in a single `apply_edits.py` execution against the original .docx. Do not run apply_edits.py → edit its output → run it again on that output. Multiple cycles cause ID collisions and orphaned artifacts. If retrying, start fresh from the original .docx.

**If the opinion is plain text or another format:** create a new .docx using the docx skill (discovery and reading rules in `references/environment-setup.md`), with tracked-change markup showing all edits.

## 9a. Collect all edits into a JSON file

Gather Pass 2 edits (style/grammar), Pass 3A edits (citation format), Pass 5 edits (analytical rigor), Step 8a caption and parallel-cite corrections, and Step 8b treatment comments into a single JSON array:
```json
[
    {
        "type": "replace",
        "para": 3,
        "old": "It is well settled that the court",
        "new": "The court",
        "comment": "Cut throat-clearing (Redbook § 11.3)"
    },
    {
        "type": "replace",
        "para": 7,
        "old": "and/or",
        "new": "or"
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

**Span width.** `old` and `new` are applied literally: the tracked deletion covers exactly `old` and the insertion covers exactly `new`. Use the **shortest span that is unique within its paragraph** — a phrase or clause, not the surrounding sentence — so the strikethrough covers only what actually changed. If `old` turns out to repeat within its paragraph, the first occurrence is edited and the result carries `"matches": N`; lengthen the span and re-run if that picked the wrong one.

**Comments are optional.** Attach `comment` only when a reader might question the change. Omit it when the diff is self-evident (`and/or` → `or`, an added Oxford comma, a cut throat-clearer). Repeated boilerplate comments on mechanical edits make the redline slower to review, not faster.

## 9b. Run `apply_edits.py`

Directly on the original .docx (no unpack step):
```bash
$VENV_PYTHON "$SKILL_DIR/apply_edits.py" --input <input.docx> --edits <TMPDIR>/edits.json --author "Claude" --output <output.docx>
```

**Nonbreaking spaces.** The space after `¶`/`§` should be a nonbreaking space (U+00A0), but this is **never** proposed as a tracked change — a change bar on every citation drowns out the substantive edits. Two dispositions, in order of preference:

1. **Default — report it.** Count the offending spaces in the extracted markdown and note them in the analysis document (see `references/analysis-template.md`, Summary of Edits). The user fixes them in Word with one find/replace.
2. **On request only — normalize deterministically.** If the user asks for the nonbreaking spaces to be applied, add `--normalize-nbsp` to the 9b command. It rewrites the space after each `¶`/`§` **without tracked changes** (no change bars), leaves struck text alone, and is idempotent. Report the `nbsp_normalized` count from the summary in your Step 12 message — an untracked change must always be disclosed. Never pass this flag unprompted.

To count for disposition 1 (locale-proof — bracket expressions over multibyte characters are unreliable in BSD grep):
```bash
$VENV_PYTHON -c "import re,sys; print(len(re.findall(r'[¶§]{1,2} ', open(sys.argv[1]).read())))" <TMPDIR>/<draft>.md
```

The script operates directly on the .docx ZIP archive — no unpack/pack pipeline, no dependency on the docx plugin. It:
- Reads document.xml from the original ZIP
- Applies all tracked changes and comments via DOM manipulation
- Serializes XML as UTF-8 with `standalone="yes"`
- Builds the output ZIP preserving original entry metadata
- Produces files Word opens cleanly (no encoding or ZIP metadata issues)

## 9c. Check the output

Parse the JSON summary from apply_edits.py. If any edits failed, report them. Also check each result for a `matches` count above 1 — that edit landed on the first of several identical spans, so confirm it hit the intended one. If `--normalize-nbsp` was used, note `nbsp_normalized` for the Step 12 disclosure. Then validate the file:
```bash
$VENV_PYTHON "$SKILL_DIR/ooxml_validate.py" <output.docx>
```
Exit 1 with diagnostic JSON means Word would call the file unreadable — fix before delivering.

## 9d. Citation hyperlinks (optional)

When the user asks for clickable / linked citations, add `hyperlink` edits to the same `edits.json` — one per citation, anchored to the citation text, using the verified URL (prefer ndlaw `absolute_url`, else the CourtListener URL, else the `url` from `cite_check.py`):
```json
{ "type": "hyperlink", "para": 12, "anchor": "2024 ND 45", "url": "https://www.ndcourts.gov/..." }
```
Hyperlinks are a **non-tracked formatting overlay** — they wrap existing text (no tracked change) and are skipped automatically if the anchor is already inside a link or a tracked change. Only link citations that **passed** verification; never link an unverified or flagged cite. Requires .docx output (not available in web/analysis-only mode).

The agent's job is: collect edits into JSON (1 Write call), run one command (1 Bash call).

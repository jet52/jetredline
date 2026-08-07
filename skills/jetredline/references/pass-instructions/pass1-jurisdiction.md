# Pass 1: Jurisdictional Check — Subagent Instructions

You are a jetredline subagent. The caller's prompt tells you the document type (`opinion` or `memo`), the draft's file path, and the skill root — written as `<SKILL_ROOT>` below (if the caller omitted it, use the directory two levels above this file). Follow the matching variant below. Return **only** what the variant specifies — no preamble, no restatement of these instructions.

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

## If DOC_TYPE is `opinion`

- Read `<SKILL_ROOT>/references/nd-appellate-rules.md`
- Read the draft opinion file (path supplied by the caller) — focus on the procedural-posture and standard-of-review sections
- Verify: Was there a timely appeal under N.D.R.App.P. Rules 2.1, 2.2, 3, and 4?
- Verify: Does the opinion correctly identify the procedural posture and standard of review?
- Verify: Are court rules cited accurately? Check against https://www.ndcourts.gov/legal-resources/rules
- Return **only** a concise summary of findings: any jurisdictional issues, procedural-posture errors, or standard-of-review problems. If no issues found, state that explicitly.

## If DOC_TYPE is `memo`

- Read `<SKILL_ROOT>/references/nd-appellate-rules.md`
- Read the draft memo file (path supplied by the caller)
- Check whether the memo addresses appealability: timeliness, subject-matter jurisdiction, and procedural prerequisites (e.g., OMB notification for claims against the state under N.D.C.C. § 32-12.2-04)
- Check whether the parties' briefs (if available in the working directory) raise jurisdictional issues
- If **neither** the memo nor the parties address appealability at all → return a **warning** that the memo should confirm appellate jurisdiction
- If the memo does address appealability → verify the analysis against `nd-appellate-rules.md` as with opinions
- Return a concise summary: any jurisdictional concerns or warnings. If the memo adequately addresses jurisdiction, state that explicitly.

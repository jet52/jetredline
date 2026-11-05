# Analysis Document — template, conditional warnings, provenance, HTML render

Read this file when assembling the analysis document (Step 10). SKILL.md's Output Format section names the sections; this file holds their exact shape, the conditions under which each ⚠ warning renders, the provenance-footer rules (Step 10a), and what the HTML render (Step 10b) does with the result.

**Web mode:** the template and structure are the same; the document is returned as markdown in the conversation.

## Tracked-changes .docx (if requested)

Use `apply_edits.py` (Step 9, `references/batch-edit-workflow.md`) to produce a .docx with deletions as tracked deletions (author: "Claude"), insertions as tracked insertions (author: "Claude"), and comments for substantive notes — explaining a change or flagging an issue. The script operates directly on the .docx ZIP — no unpack/pack pipeline, no docx plugin dependency.

## Analysis document (if requested)

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

### Conditional warnings (render near the top, in this order)

**Source-materials warning (conditional — render whenever Step 11 found N < M).** Immediately after the Case Highlight (opinion) or before Jurisdictional Notes (memo), insert the following. Omit the section entirely when every identified input was fully ingested:

```
## ⚠ Source Materials Not Reviewed

One or more provided source files could not be fully read. Fact-check and brief-coverage findings below are **incomplete** for the listed material.

| File | Reason | Passes affected | Remediation |
|---|---|---|---|
| [file.pdf] | image-only / no text layer (or OCR-low-confidence) | Pass 4, Pass 6 | OCR attempted (ocrmypdf) — failed / low-confidence; recommend manual review or re-OCR |

**Inputs ingested: N of M.**
```

**Authority-text warning (conditional — render whenever Step 11a reached neither the ndlaw corpus nor the MCP connection).** Place it with the other warnings near the top. Omit it entirely when the refresh succeeded:

```
## ⚠ Authority Text Not Refreshed

The ndlaw corpus was not reachable for this run, so cited authorities were checked against whatever local copies `~/refs` already held. Those copies carry no record of when they were fetched, and the corpus has since corrected opinion text in ways a cached copy cannot reflect. **Quotation and citation findings below are weaker than usual in both directions** — an unverified quotation may be accurate, and a verified one may rest on superseded text. Re-run with the corpus reachable to settle them.
```

**Reduced-reliability model warning (conditional — render only when Step 0.0 reported `warn` and the user chose to proceed).** Place it immediately after the source-materials warning, or in its place when every input was ingested. Omit the section entirely on an Opus-, Fable-, or Mythos-class model:

```
## ⚠ Reduced-Reliability Model

This review ran on **[model id]**, which is outside the Opus-class set jetredline's reliability testing is based on. Citation, quotation, and record-fact findings below carry a higher miss rate than the same review on an Opus-class model — a clean section is weaker evidence than usual. Re-running on Opus is the way to raise confidence.
```

**Sources-out-of-reach warning (conditional — render only when the Step 0 source preflight warned).** Place it after the reduced-reliability warning, or where that section would go. One bullet per warning, carried over from the preflight — host or MCP server, what the run lost, the fix. Omit the section entirely when both checks were clean:

```
## ⚠ Sources Out of Reach

This run could not reach the sources below, so the checks that depend on them fell back to weaker ones. Findings in those areas are not confirmations; treat "no problem found" there as "not checked against the primary source."

- **[host or MCP server]** — [what was lost]. Fix: [allowlist entry or connection step].
```

### Body

**Both document types continue with:**

```
–Begin Analysis– [if memo, or continuation after Case Highlight if opinion]

## Jurisdictional Notes
[Issues with timeliness of appeal, procedural posture, or standard of review]
[If DOC_TYPE is memo and jurisdiction was not addressed: include warning here]

## Summary of Edits
[Brief overview of the types and volume of changes]

[Nonbreaking spaces — include this line only when the count is above zero, and only if --normalize-nbsp was NOT used:]
**Nonbreaking spaces:** [N] ordinary spaces follow `¶`/`§`. Not redlined — a change bar on every citation would bury the substantive edits. Fix globally in Word: Find `¶ ` → Replace `¶^s`; Find `§ ` → Replace `§^s` (repeat for `¶¶ ` and `§§ `). `^s` is Word's nonbreaking-space code.

[If --normalize-nbsp WAS used, replace the line above with:]
**Nonbreaking spaces:** [N] ordinary spaces after `¶`/`§` were replaced with nonbreaking spaces (U+00A0) **without tracked changes** — typographic normalization, invisible in print, not shown as a revision.

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

### Hostile Readers
[Passages quotable out of context or open to willful misreading, each with the misreading, whether a fair reader could reach it, and the fix; vague standards; overly broad holdings]

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

## Supplied Authorities

[Include this section only when Pass 3D ran and found references. Rows come from the Pass 3D table.]

| ¶ | Authority | Kind | Cited page | Matched file | Page check | Quote check | Supports? | Notes |
|---|-----------|------|------------|--------------|------------|-------------|-----------|-------|
| [¶] | [short title] | [journal/treatise/…] | [printed page] | [filename or **none found**] | Verified / Unverified / N/A | Verified / Discrepancy / Not found / No quote | Supports / Partially / Does not support | [explanation] |

**Summary:** [N] references to supplied authorities. [M] matched to PDFs in the case directory, [P] page-verified, [Q] passages verified.

**Authorities relied on but not located** [omit when empty — but never omit silently when Pass 3D reported any]:
- [ ] *[Title]* (¶ [ref]) — no copy in the case directory; obtain and verify before publication.

## Citation Format Issues
[Citation-format corrections with explanations]

## Style Notes
[Significant style changes by category]

---
*Claude skills crafted by Claude and JET (github.com/jet52)*

–End Analysis–
```

Also carry into the Citation Verification section: the Pass 3B lookup-methods tally (`ndlaw / CourtListener / local / web / not found`), its ND web-fallback note, and — when Pass 3C ran — a short "Negative-treatment check" subsection listing flagged cases with their signal and citing opinion, noting that `unresolved` cites were not checked (or the "not run (ndlaw unavailable)" line when it did not).

Do **not** hand-write a version/date line in the footer — the provenance stamp (Step 10a, `provenance.py`) appends the authoritative model/version/date line in CLI mode. In web mode, append it manually per Step 10a.

## Provenance footer (Step 10a) — detail

```bash
python3 "$SKILL_DIR/provenance.py" --file <stem>-ANALYSIS.md --subagents
```

Footer, e.g.: *Report generated by Claude Opus 4.8 (claude-opus-4-8) using jetredline v4.4.0 on 2026-06-05. AI-generated first draft for internal use; verify all citations and findings before relying.* Model, version, and date are all sourced deterministically by the script — version from frontmatter/`VERSION`, date from the system clock, and the model from this session's transcript (the same place the per-pass rows below come from). **Do not pass `--model`**, and do not hand-type the model anywhere in the report: your own recollection of which model you are is exactly the self-report a validation record must not rest on. If the script exits 2 because no transcript is readable, then and only then re-run it with `--model "<friendly name> (<exact id>)"` using the id Step 0.0 resolved. The stamp is idempotent. **Stamp only the analysis document — never the tracked-changes `.docx`, which is the user's own opinion text and must not be altered with a footer.** In **audit mode** (no files written) and **web mode** (analysis returned inline, no filesystem), skip the script; in web mode you may append the same footer line manually as the report's last line.

`--subagents` adds a table of the delegated passes below that line — the model each subagent actually ran on and what it consumed:

| Pass | Model | Tokens | Tools | Time |
|---|---|---|---|---|
| 1 — Jurisdiction | claude-opus-5[1m] | 124.1k | 37 | 4m 48s |
| 4 — Fact check | claude-opus-5[1m] | 111.4k | 29 | 9m 26s |

The script reads those figures from this session's transcript (located via `$CLAUDE_CODE_SESSION_ID`), identifying each pass by the `references/pass-instructions/passN-*.md` path in its delegation prompt — **so keep that path in the delegated prompts verbatim**, and give each agent a `description` naming its pass, which is the fallback label. Only numbers and the model ID cross into the report; no prompt or result text does.

**Tokens is a single total per agent, by necessity.** Background subagents (the default) report completion through a `<task-notification>` carrying one `subagent_tokens` figure with no input/output/cache breakdown, so a wider schema cannot be filled. Synchronous agents still emit the older self-contained record, which the script also reads; those rows show `—` for Model, which that record omits. The table is omitted whenever nothing was delegated (Web mode, inline mode, short opinions run in main context) and whenever the transcript can't be read — the transcript is an undocumented internal format, so a missing table is expected behavior, never an error to chase. Do **not** hand-write this table from your own recollection of the passes; if the script omits it, it stays omitted.

## Analysis report HTML (Step 10b; CLI and Cowork, always generated)

```bash
python3 "$SKILL_DIR/analysis_to_html.py" <stem>-ANALYSIS.md --check [--cite-review <stem>-CITE-REVIEW.html]
```

Run it **after** the provenance stamp, never before: Step 10a appends the footer and the subagent-token table to the markdown, and the HTML is a render of whatever the file holds at that moment. It writes `<stem>-ANALYSIS.html` beside the markdown — a single self-contained page, light-only, no network fetches, no sidecar directory, safe to email or hand over in Cowork as-is. Add `--cite-review` once Step 11b has produced that page, so the report links to it. `--check` verifies that every source line survived into the page and exits 3 if any did not; if it reports misses, say so and deliver the markdown alongside — never silently ship a page that dropped content. The markdown stays the source of truth; if you edit the report afterward, re-run the command (idempotent, about a second). Skip it only in audit mode and web mode.

The report is a triage document, and the page is built to be read that way:
- a **triage banner** and a sticky **table of contents**, each carrying the count of flagged rows per section, so the reader sees where to look before reading a word;
- **status badges** on the report's status columns (`Result`, `Addressed`, `Quote check`, `Page check`, `Supports?`, `Caption check`, `Matched file`) — each badge carries a glyph and its text label, so color is never load-bearing, and the palette is legible to red-green colorblind readers;
- a **filter box and a "problems only" toggle** on each substantial table — the fastest way through a 60-row citation table;
- **checkbox persistence** for the "Authorities relied on but not located" worklist;
- a **print stylesheet**: printing or saving to PDF from the browser produces a clean chambers document, with wide tables shrunk to fit, header rows repeated across pages, and link URLs printed after their text.

A count of zero flagged rows is **not** a clean bill of health, and the page says so: only columns with a recognized status vocabulary are counted, and findings also live in tables without one and in the narrative sections. Do not report it as a clean run.

Tell the user the file is available and can be opened in any browser or printed to PDF. Name it alongside the markdown.

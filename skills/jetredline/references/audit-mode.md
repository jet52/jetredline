# Audit Mode (Caller Integration)

Read this file only when the caller's prompt invokes jetredline in **audit mode**. It *overrides* parts of SKILL.md's standard workflow; everything not overridden here is unchanged.

Another skill (e.g., jetmemo) may invoke jetredline programmatically to audit a memo it just generated and feed the findings back into its own draft. **Detect audit mode** from the caller's prompt: it will say "audit mode" and supply a draft path, a pass list, and a request to return results rather than write files. When in audit mode:

1. **Fixed settings** — do not ask, do not auto-detect:
   - `DOC_TYPE = memo` (the caller only audits bench memos in this mode).
   - Output = **analysis-only**. **Write no files** — no .docx, no `-ANALYSIS.md`, no `cite-review.html`. Return everything inline to the caller.
   - The draft arrives as a **markdown file path** (or pasted text), not a .docx. Read it directly; skip Step 0's `.docx`/`.pdf` scan, the temp-dir setup, and the docx-plugin discovery.
   - **Preserve markdown link syntax.** The memo arrives with record-citation hyperlinks (`[R45](url)`) and possibly authority links already in it. Never edit a URL, and when an edit touches linked text, keep the `[text](url)` wrapper intact.
   - **Model gate: report, never block.** Run Step 0.0's `check_model.py`. On `warn` or `unknown`, do not ask the caller anything and do not stop — add one line under `### Coverage` in Part 2 naming the model and continue the audit.
   - **Source preflight: MCP check only.** Skip `preflight.py` (no Step 11 export runs here), but do Step 0's MCP-tool check — Pass 3C needs ndlaw's `detect_overruled_in_draft`. A missing server is one line under `### Coverage`, never a stop.
   - **Voice file:** skip it — the caller's memo is not the user's signed writing. Its `## Flag in any draft I review` section still applies as comments (SKILL.md Step 0.7, `VOICE_FLAGS_ONLY`).

2. **Run inline.** Execute all selected passes inline in this context (as in Web mode) — do **not** delegate to Agent subagents. The caller has already spawned you as a subagent. For passes whose detailed instructions live in `references/pass-instructions/` (Pass 1, Pass 4, Pass 5, Pass 6), Read the matching file and apply it inline.

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
   { "type": "replace", "para": 7, "old": "<shortest span unique within its paragraph>", "new": "<replacement>", "comment": "<optional — rule, e.g. Redbook §11.3; omit when the diff is self-evident>", "source_pass": "style" }
   ```
   Keep `old` as short as it can be while remaining unique in its paragraph — the redline deletes and reinserts exactly that span. Omit `comment` for edits whose rationale the diff already shows.
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

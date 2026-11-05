# Pass 5: Analytical Rigor — Main-Context Instructions

Pass 5 is **always performed in main context**, never delegated; this file lives beside the subagent pass files only so every pass's detailed instructions sit in one place. Perform the following checks on **all documents** (both opinions and memos), then the `DOC_TYPE`-specific checks below. Full style detail for both document types is in `references/style-guide.md`. Findings go in the analysis document; a Pass 5 item becomes a tracked edit only when it is a safe, local wording fix — anything that touches the author's reasoning is a comment or an analysis-document finding.

## Internal Consistency Check (all doc types)

Read the entire document and build a mental index of: party names (including aliases and roles), dates, monetary amounts, numerical counts, procedural events, and terminology choices. Compare every reference to each entity, date, and event across the document. Flag any discrepancy with paragraph references for both the first usage and the inconsistent usage.

Check for:
- **Name/spelling inconsistencies** (e.g., "Johnson" vs "Johnsen", "Meier" vs "Meyer"). **Exclude case names** — party names in cited cases are verified in Pass 3B against official captions. Only flag non-case-name spelling inconsistencies here (party names in the case being decided, witness names, place names, ordinary words).
- **Date inconsistencies** (same event assigned different dates in different paragraphs)
- **Terminology drift** (switching between "defendant"/"respondent", "trial court"/"district court" without reason)
- **Factual contradictions** (facts section says X, analysis section says Y)
- **Numerical inconsistencies** (amounts, counts, timelines that don't add up)
- **Caption/party inconsistencies** (parties named differently in caption vs body)

Distinguish intentional variation from apparent errors. Referring to "Smith" in the facts and "the appellant" in the analysis is fine; "Smith" becoming "Smyth" is a flag.

## Standard of Review Consistency Check (all doc types)

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

## Statutory-Construction Cross-Check (when ndlaw is available)

When the draft construes an N.D.C.C. section or a court rule as a point of decision, call `find_opinions_construing(<authority>)` and scan the returned `results[].opinions` for ND opinions construing the same provision. Use it as an advisory aid: if a recent or obviously on-point construction is missing from the draft's analysis, note it for the author's consideration (do not assert it is controlling). Skip silently if the tool is unavailable. For a key *cited* precedent whose holding the draft leans on, `case_summary(<cite>)` (disposition + `syllabus_points`) can confirm what the case actually held — this aids the substantive-support assessment; it does **not** feed the draft's own Case Highlight, since the draft is not in the corpus.

## Readability Metrics (all doc types)

**CLI mode:** Run the readability metrics script on the document:
```bash
$VENV_PYTHON "$SKILL_DIR/readability_metrics.py" --file <document_path>
```
Parse the JSON output and incorporate the results into the analysis document (see the Readability Metrics section of `references/analysis-template.md`). Flag any sentences over 40 words, sections with passive voice above 25%, and sections with FK grade above 16.

**Web mode:** Skip the script (no Bash available). If feasible, estimate sentence length and passive voice inline for the longest/densest sections. Otherwise, note: "Readability metrics unavailable in web mode."

**Audit mode:** skip readability entirely.

## If DOC_TYPE is `opinion` (default)

- Flag potential dicta (statements unnecessary to the holding)
- Flag unnecessary alternative rationales
- Identify logical fallacies
- Identify ambiguities — especially passages easily quoted out of context
- **Two hostile readers.** Read the opinion twice, each time as a specific adversary:
  1. *The losing party's lawyer*, who will quote the opinion in the next brief to stretch or shrink the holding.
  2. *The motivated misreader*: anyone who wants the opinion to look bad and reads it to that end. Cycle through several: a judge who rejects the author's interpretive method and would enjoy seeing the author look foolish; a reporter hunting a headline quote; an ideological opponent from either direction; an advocacy group drafting a fundraising letter; a conspiracy-minded reader who finds hidden intent in every word. Which sentences would those readers willfully misread, lift out of context, or hold up as inconsistent with the author's stated method, a relied-on precedent, or the author's past opinions? Watch for a sentence that works as a headline on its own, a clause that says something else when cut at the comma, policy-sounding reasoning, overstatement that would fit in a dissent or a law-review footnote, a word with a loaded meaning outside the law, and anything that sounds like a swipe at precedent, the lower court, counsel, or a party.

  For each finding, quote the passage, state the misreading in one sentence, say whether a fair reader could also reach it, and propose a fix or say the passage should stand. Report only misreadings plausible enough to survive a reply; skip mere snark. Findings go in the analysis document under "Hostile Readers," never into tracked edits — the fix is the author's call.
- Flag holdings broader than necessary
- Flag vague standards lacking guidance for future application
- **Draft case highlight:** Generate a 50–200 word case summary for the analysis document. Extract: case name and citation (from the caption/header), nature of the dispute (one sentence), disposition (affirmed/reversed/remanded/modified with brief outcome), and 1–3 core holdings. This is a synthesis task — perform it in main context, not delegated.

## If DOC_TYPE is `memo`

- **Issue completeness:** Did the memo identify all issues raised on appeal? Are there issues the parties didn't raise but the court should consider (e.g., plain error, jurisdictional defects)?
- **Balanced presentation:** Does the memo fairly state each side's strongest arguments? Does it steelman the weaker position or dismiss it too quickly?
- **Recommendation quality:** Are recommendations clearly stated? Is each recommendation supported by the analysis? Are alternative outcomes acknowledged?
- **Analytical gaps:** Are there unstated assumptions? Logical fallacies? Missing steps in the reasoning chain?
- **Standard of review:** Does the memo correctly identify and consistently apply the appropriate standard of review for each issue?
- **Order-grounding check (did the memo read the order, or guess?):** Scan every statement about the **district court's ruling, findings, grounds of decision, or reasoning**. Flag two patterns:
  1. **Uncited characterization** — a claim about what the district court held, found, or reasoned that carries **no pinpoint citation to the order/judgment** (e.g., "R38:2–9"). A bench memo's account of the ruling should be anchored to the order itself.
  2. **Hedged reasoning** — phrases like "the district court *appears to* have," "*seems to* have," "*evidently*," or "*presumably*" applied to the lower court's reasoning. These usually mean the order was not read but inferred from the briefs.

  For each flag, note the ¶ and the suspect language. If source materials are available (Pass 4 ran on the order/record), check whether the order actually resolves the point and report the correct grounds with a pinpoint cite. Treat a cluster of these flags as a signal that the memo may have been drafted from the briefs without reading the order — say so explicitly in the analysis, since that is a serious bench-memo defect. (This is advisory: a properly preserved record gap is legitimate, but it should be stated as a gap, not hedged.)

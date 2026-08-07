# Pass 3B: ND Citation Verification — Subagent Instructions

You are a jetredline subagent. The caller's prompt supplies: a numbered list of every ND citation in the draft (each with its ¶, full citation text, the proposition it supports, any exact quoted text, and the signal used), the opinion file's path, a TMPDIR path for the passages ledger, the skill root (written as `<SKILL_ROOT>` below; if omitted, use the directory two levels above this file), and the venv python path (written as `<VENV_PYTHON>` below; if omitted, use `python3`). Verify each citation against local reference files and official online sources. Return **only** the results table, tallies, and notes specified in Steps 7–8.

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

## Source precedence (apply at every case-citation check; fall through on a miss)

1. **ndlaw** (primary, North Dakota cases) — local ND opinion corpus. Deterministic, no network. Check whether its tools (e.g. `verify_citation`) are present in your tool set; if not, skip silently to the next tier.
2. **CourtListener MCP** (secondary) — federal and out-of-state authorities, and ND opinions missing from the ND corpus.
3. **Existing pipeline** (fallback) — `cite_check.py` / `~/refs/` / WebFetch / web search. Always available in CLI mode.

Statutes, court rules, the constitution, and NDAC always resolve through the existing pipeline (tier 3) — the MCP servers are out of scope for them. ndlaw is a research aid, not an authoritative text: use its signals to *flag for human review*, never to auto-edit on a signal alone. Never fail or stall because an MCP server is absent or returns no data.

## Step 1: Generate the lookup plan

Run the citation checker on the opinion file to get structured resolution data:
```bash
<VENV_PYTHON> "<SKILL_ROOT>/cite_check.py" --file <opinion_path> --refs-dir ~/refs --cache
```
The `--cache` flag auto-fetches and caches any case citations (ND, federal, other states) not already in `~/refs/`. This builds the local cache progressively so future runs have more local hits.

This outputs a JSON array with one entry per citation found. Each entry includes:
- `cite_type`: neutral_cite, statute, statute_chapter, constitution, regulation, court_rule, regional_reporter, federal_reporter, us_supreme_court
- `local_path` / `local_exists`: path in `~/refs/` and whether it exists
- `url`: official source URL (always populated)
- `search_hint`: text to search for within the local file
- `antecedent_name`: the case name jetcite saw immediately before the cite (heuristic; may be null, and may include stray leading words) — seeds the case-name drift check in Step 1.5
- `improper_parallel_pincite: true`: the reporter half of a ND public-domain pair that carries a page pin cite — a style defect under the Court's Redbook supplement (see the parallel-cite bullet in Step 1.5)
- ND Court of Appeals cites normalize as `YYYY ND App N` and are a **different court** from `YYYY ND N` — `2005 ND 7` and `2005 ND App 7` are different cases. Never conflate them or drop the `App` token.
- `cite_type: "pin_cite"` entries are Bluebook short forms in the draft (`491 F.3d at 363`, `Goss at 365`, `Niemeyer, ¶ 12`, `Id. ¶ 15`, bare `Rule 60(b)`) back-referencing the full cite in `parent_normalized`, with the pinpoint in `pin_page`/`pin_paragraph`. Verify these against the **parent's** opinion (`parent_local_path` when `parent_local_exists`, else the parent entry's source): for ND cases call `get_pinpoint(<parent cite>, paragraph=N)`; for reporter pins confirm the page falls within the opinion's span. **The parent is not always a case:** an *Id.* after a rule/statute/constitution cite, and a bare `Rule 60(b)` short form (attributed to its rule set — parent like `N.D.R.Civ.P. 60`, subdivision in `pinpoint`), resolve to that authority — verify the referenced subdivision against the parent's text in Step 2, not against an opinion. An entry carrying `pinpoint_inherited: true` is a **bare *Id.*** whose pinpoint was adopted from the antecedent cite (Bluebook: same authority, same page/paragraph) rather than written in the draft — verify the proposition against that ¶/page as usual, but attribute any mismatch to the *antecedent's* pinpoint, not to the *Id.* itself. An entry carrying `pin_warning` is an **unresolved short form** — no earlier full cite in the draft matches it (digit-transposed volume, or an *id.* after an ambiguous string cite). Flag it as a probable drafting error; when `antecedent_name` is present (e.g. "Goss"), check whether the named case's actual volume/page was intended and propose that correction. Pin entries are excluded from `--cache` fetching by design.
- Entries with `is_repeat: true` are repeat full-form case cites — the second and later textual appearances of the same authority (e.g. a short cite written out as `Olson, 2024 ND 156, ¶ 12`), linked to the first occurrence via `parent_normalized` and carrying `parent_local_path`/`parent_local_exists` like pins. **Verify each repeat's own pinpoint** (each usually supports a different proposition) against the parent's opinion, but run the caption check and parallel-cite check only once, on the first occurrence. Repeats are excluded from `--cache` fetching by design.

## Step 1.5: Case citations — verify via ndlaw first (if the tools are available)

For each **case** citation only (statutes, rules, constitution, and admin code use Step 2):

- **Existence + caption + name drift:** Call `verify_citation(<cite>, expected_case_name=<case name as written in the draft>)`. Use the draft's case name; if you don't have a clean one, derive it from the `antecedent_name` field — it is a heuristic, so strip leading signal words ("See", "In", "accord", etc.) and any prior-sentence fragment down to the `X v. Y` (or `In re X`) core. Record `canonical_case_name`, `formatted` (official caption + full Redbook cite), `name_matches`, and `name_similarity`.
- **Quote check:** If the draft quotes the case, call `verify_quotation(<cite>, <exact quoted text>)`; record `verbatim`, `paragraph` (the pinpoint ¶), and any `differences`.
- **Parallel cite (NDSC — required in full cites):** From the `cites_redbook` / `formatted` returned above (or `get_parallel_citations(<cite>)`), check the N.W.2d/N.W.3d parallel. In a **full** (first-reference) ND cite, a *missing* parallel is a defect — flag it to be added (no pin cite to the reporter); a parallel with the *wrong* volume/page should be corrected to match `formatted`. Do **not** add a parallel to short-form or *id.* cites.
- **Improper reporter pin cite in a parallel:** an entry carrying `improper_parallel_pincite: true` is the reporter half of a ND public-domain pair that also carries a page pin cite — e.g. `1997 ND 231, ¶ 10, 571 N.W.2d 358, 360`. Per the Court's Redbook supplement the reporter gets its **first page only** (the ¶ is the pinpoint), so propose deleting the trailing page. jetcite raises this only for ND pairs and never for a pre-1997 cite, where the reporter pin cite is the correct form — so treat the flag as reliable rather than re-deriving the era rule yourself.
- **Pinpoint ¶:** If the cite carries a pinpoint (¶ N) but the draft does not quote the case, call `get_pinpoint(<cite>, paragraph=N)`; confirm the ¶ exists and read its `text` for the substantive-support check. Flag a pinpoint to a ¶ that does not exist.
- **Not found in ndlaw** (federal, out-of-state, or absent from the ND corpus): if CourtListener `verify_citations` is available, try it next; otherwise fall through to Step 2.

**Page-break splice backstop (prevents the 2025 ND 13 phantom):** before reporting any cite as nonexistent or as resolving to an unrelated case, check its `cite_text` for an embedded line break or stray page-furniture digits (the scanner strips page furniture, but a splice it misses yields a neutral cite whose opinion number was actually a page footer). If the raw text looks spliced — or the cite fails to resolve while its `antecedent_name` clearly names a different case than the resolved caption — rejoin the cite with the adjacent numeric token across the break (e.g. `2025 ND [13-footer] 127` → `2025 ND 127`) and re-verify before writing the finding. Never report "cite X = unrelated case Y" without this step.

**Closed-loop case-name rule (prevents the Tracey/Tracy error):**
- Propose a spelling correction **only** when the *same* citation resolves and `name_matches` is false with **high `name_similarity`** (≥ 0.85) — that is the same case with a typo. Report the mismatch with `canonical_case_name` so the caller can generate the correction.
- **Never** harmonize two citations that differ in *both* spelling **and** cite number (e.g., `Tracey v. Tracey, 2023 ND 219` vs. `Tracy v. Tracy, 2024 ND 195`) — different cites are presumptively different cases. Add a note, not a correction.
- Low `name_similarity` on a single cite signals a probable wrong cite or wrong name — flag for human review; do not auto-correct.

## Step 2: Verify each citation

(All non-case citations, and any case citation Step 1.5 could not resolve.) For each such entry from the lookup plan:

1. **Retrieve source text.**
   - If `local_exists` is `true`: use the Read tool on `local_path`. For NDCC sections, search for the `search_hint` within the chapter file. For ND opinions, locate the pinpoint paragraph (`[¶N]`).
   - If `local_exists` is `false`: use WebFetch on the `url` to retrieve the source text. For PDF URLs (ndlegis.gov), note that WebFetch may not extract PDF content — mark as "URL only" and verify what you can.

2. **If the opinion quotes the cited source:**
   - Compare the quoted text against the source **character by character**.
   - Flag any discrepancies (missing words, changed words, transpositions).
   - Identify any bracketed alterations (`[word]`, `[W]ord` for capitalization changes, ellipses `...` or `. . .` for omissions).
   - For each alteration, note whether the opinion includes an appropriate parenthetical (e.g., "(alteration in original)", "(cleaned up)", "(emphasis added)", "(omission)", "(quoting [Source])"). Under Bluebook Rule 5.2, alterations to quoted material must be indicated.
   - Report the result as: **Quote verified** (exact match), **Quote verified with noted alterations** (brackets/ellipses present and properly parentheticized), or **Quote discrepancy** (unexplained differences).

3. **Existence check.** Does the cited provision/opinion actually exist? For statutes and rules, confirm the section number is valid.

4. **Case-name verification** (case citations only). Compare the case name as it appears in the draft opinion against the official caption in the source text. The official caption appears in the first 10–15 lines of ND opinion markdown files (e.g., `~/refs/opin/ND/2023/2023ND219.md` shows "Monica Tracey" and "David Tracey") and at the top of fetched opinion pages. If the draft says "Tracy v. Tracy, 2023 ND 219" but the official caption reads "Tracey v. Tracey," report the mismatch with the official caption so the caller can generate a correction. **Apply the same closed-loop rule as Step 1.5:** correct only same-cite typos; never harmonize two different citations. For non-case citations (statutes, rules, etc.), mark as N/A.

5. **Substantive support check.** Read the cited material in context and assess whether it supports the proposition for which it is cited. Consider:
   - Does the source actually state or hold the legal principle attributed to it?
   - Is the signal appropriate? (No signal = direct support; *See* = clearly supports; *see also* = additional support; *cf.* = analogous; *but see* = contrary)
   - Is the proposition a fair characterization, or does it overstate/understate/distort the source?
   - Report: **Supports** (the cite supports the proposition), **Partially supports** (some nuance lost or overstated), or **Does not support** (the cite does not stand for the stated proposition).

6. **Currency check** (statutes, rules, admin code only). If the source text includes effective date or amendment information, flag if the cited version may not be current.

7. **Build the results table.** The Source Link column **must** use the full `url` value from the cite_check.py JSON output as a markdown hyperlink — e.g., `[N.D.C.C. § 12.1-32-01](https://ndlegis.gov/cencode/t12c32.pdf#nameddest=12-32-01)`. Never link to just a domain root like `https://ndlegis.gov/`. Every citation's `url` field already points to the specific document; use it verbatim.

   The **Via** column records the tier that actually produced the verification — `ndlaw`, `CourtListener`, `local` (a `~/refs/` file), `web` (WebFetch or web search), or `not found` — following the source precedence you applied in Steps 1.5 and 2. This is the *method*, not the Source Link (which is the canonical URL regardless of how the cite was checked). It is the provenance for any edit generated from this row, so record the tier that supplied the value you relied on.

   | ¶ | Citation | Type | Caption Check | Quote Check | Supports? | Via | Source Link | Notes |
   |---|----------|------|---------------|-------------|-----------|-----|-------------|-------|
   | [¶] | [Citation text] | Opinion / Statute / Const. / Rule / Admin. | Matches / Mismatch: official is [X] / N/A | Verified / Discrepancy / No quote / Not found | Supports / Partially / Does not support | ndlaw / CourtListener / local / web / not found | [Markdown hyperlink: `[normalized](url)`] | [Explanation] |

   For locally-verified citations, still include the official URL from the lookup plan so readers can independently check the source. The URL was already computed — do not substitute or shorten it.

7a. **Write the passages ledger.** As you verify, accumulate every passage you actually read for a pinpoint or quote check — the `text` from `get_pinpoint`, the `closest_text` from `verify_quotation`, or the paragraph you read from a local/web source — and write them to `<TMPDIR>/passages.json` as a JSON array of `{"cite": "<parent full cite, normalized>", "paragraph": "<¶ number>" | "page": "<page number>", "text": "<the passage>"}`. One entry per distinct (cite, pinpoint) you checked; keep each passage to the cited paragraph (or the quoted page passage), not whole opinions. This ledger is embedded in the citation-review HTML so the human reviewer sees the exact text the verification relied on when no full source text is available.

8. **Return** the completed table and a summary: [X] ND citations checked, by type: [opinions/statutes/const/rules/admin]. [Y] quotes verified. [Z] quote discrepancies. [W] not found. [V] citations that may not support the stated proposition.

   Then add a **lookup-methods tally for case citations** (roll up the Via column over opinions only — statutes, rules, constitution, and admin code resolve via local/web by design and are out of scope):

   `Lookup methods (cases) — ndlaw: N | CourtListener: N | local: N | web: N | not found: N`

   Followed by an **ND web-fallback note**: if every ND *case* was resolved via ndlaw or a local file, write "All ND cases via MCP/local." If any ND case fell through to the web, list those cites and the reason (e.g., "ndlaw not connected" or "MCP returned no match"). This makes any web fallback for ND opinions — and the confidence basis of edits drawn from it — explicit rather than silent.

## Error handling

- If `cite_check.py` fails or returns an error, report the error in the summary and proceed with manual verification using the URL patterns and local paths below.
- If a local reference file does not exist for a citation, proceed with web verification only (WebFetch on the `url`). Do not stall or re-search for the file.
- If WebFetch also fails, mark the citation as **UNVERIFIED** in the results table with the reason (e.g., "Local file missing, URL unreachable").
- Always return partial results. A table with UNVERIFIED entries is better than no table. Never fail silently — every citation must appear in the output table with a status.

## Reference file paths (do not search — use directly)

- Opinions: `~/refs/opin/{reporter}/` — e.g., `opin/ND/2024/2024ND156.md`, `opin/NW2d/585/351.md`
- Statutes: `~/refs/statute/NDCC/` (by title/chapter), `~/refs/statute/USC/`
- Constitution: `~/refs/cnst/ND/`, `~/refs/cnst/US/`
- Regulations: `~/refs/reg/NDAC/`, `~/refs/reg/CFR/`
- Court Rules: `~/refs/rule/{set}/` — e.g., `rule/ndrcivp/rule-56.md`

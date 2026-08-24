# Cite review UI — options for a better review surface

Research logged 2026-08-15 against jetredline 4.19.2; scoped for build 2026-08-24
(§G). Sections A–F are research only — **nothing in them is built**.
The question that prompted it: could an Artifact or a cross-platform app framework
give a better cite-review surface than the current self-contained HTML page —
specifically by escaping the `X-Frame-Options` limitation, by making source review
faster, and by giving check-off somewhere to go?

Short answer: the framing block is real but is the *third* most expensive problem,
and only a shell that is a real browser engine can fix all of it. The two cheaper
problems need no new framework at all.

(Deliberately written without matter-identifying detail; this file is tracked and
pushed. Working notes live in the gitignored `TODO.md`.)

---

## A. Measured: framing status by source

Response headers probed live on 2026-08-15 with browser-identical request headers
(UA, `Accept`, `Accept-Language`, `Sec-Fetch-*`, `Upgrade-Insecure-Requests`).
Re-probe before relying on this — sites change their edge configuration.

| Source | Supplies | Embeds? | Why not |
|---|---|---|---|
| `ndcourts.gov` | ND opinions, court rules | yes | — |
| `ndlegis.gov` | N.D.C.C., N.D.A.C. | yes | — |
| `ndconst.org` | ND Constitution | yes | — |
| `tile.loc.gov` | Official U.S. Reports scans | yes | — |
| `avalon.law.yale.edu` | Founding documents | yes | — |
| `govinfo.gov` | U.S.C., C.F.R. | **no** | `X-Frame-Options: SAMEORIGIN` + `frame-ancestors 'self'` |
| `law.cornell.edu` | U.S.C. (LII) | **no** | `X-Frame-Options` + `frame-ancestors 'self'` |
| `supreme.justia.com` | Federal cases | **no** | header block **and** `cf-mitigated: challenge` |
| `constitution.congress.gov` | U.S. Constitution | **no** | header block **and** `cf-mitigated: challenge` |
| `courtlistener.com` | F.3d, N.W.2d, federal | **no** | scripted requests get 403 / 202, not content |

Every North Dakota source already embeds cleanly. The home jurisdiction was never
the problem — `_IFRAME_OK_DOMAINS` in `cite_review.py` is correct as it stands.

### A.1 The taxonomy that drives everything below

The blocks are **two different failures at two different hops**:

- **Header block** (govinfo, Cornell) — the site answers a scripted fetch with `200`;
  it only refuses to sit in someone else's frame. A local process can fetch and
  re-serve it. *Proxyable.*
- **Bot-managed** (Justia, congress.gov, CourtListener) — the site answers a scripted
  fetch with a Cloudflare managed challenge, not the page. **No proxy in any language
  gets past this**, and building something that does means defeating a bot-detection
  control we should not defeat. *Not proxyable.*

Consequence: "swap the app shell and the framing problem goes away" is only true for
a shell that **is** a real browser engine carrying a real session. Every proxy-shaped
option fixes the header class and stalls on the bot class.

---

## B. Three problems, ranked by review time lost

Framing is the one you notice. It is not the one that costs the most.

**1. The check-off goes nowhere.** `exportReviewState()` (`cite_review.py:2764`)
builds a JSON blob and drops it in `~/Downloads/cite-review-state.json`. Nothing in
jetredline reads that file. Verification marks, flags, and notes live in
`localStorage` on one browser profile and never rejoin the run. The entire review is
unrecoverable work, and nothing downstream knows a cite was cleared.

**2. The queue counts occurrences, not authorities.** The tracked Baker fixture
(`test-data/20250258_State-v-Baker-CITE-REVIEW.html`) lists 69 rows; a single case
occupies three of them because parallel cites are separate textual occurrences.
Roughly a third of the queue is re-verification of a book already checked.
(`_dedup_parallel_citations` exists but the review unit is still the occurrence.)

**3. The source pane hands you a document, not an answer.** Even where framing
works, an iframe yields a page to hunt through. The real question is narrower —
*does the draft's quotation match the source at the pinpoint?* A frame cannot
highlight, cannot diff, and cannot confirm the pin landed.

Problems 1 and 2 are pure plumbing, cost more time than problem 3, and need no new
UI framework. That is the case against reaching for a desktop shell first.

---

## C. Options considered

### A — Local companion server (`cite_review.py --serve`)
*~200 lines · half a day to a day*

Serve the existing page from `127.0.0.1` via a Python stdlib server instead of
opening it as a file. Same HTML, same keybindings.

- **Fixes:** problem 1 outright (marks POST back into the run directory — resumable,
  readable by the analysis pass); the header-block class via same-origin proxy;
  local record PDFs stop fighting `file://` path rules.
- **Costs:** a process to start and stop; the page is no longer a single portable
  file; does nothing for the bot-managed class. **Must bind `127.0.0.1` only** — an
  unreleased draft must not listen on the LAN.
- **Verdict:** cheapest real win available. Worth doing regardless of what else is chosen.

### B — Text-first evidence pane
*3–5 days · needs a free CourtListener API token*

Stop embedding pages. Resolve each authority's text during the run, locate the
pinpoint, and render the passage with the draft's quotation diffed against it.

- **Fixes:** problem 3 outright, and makes framing irrelevant because nothing is
  framed. ND authorities already have local text; LOC scans cover SCOTUS;
  CourtListener's API covers the federal reporters.
- **Costs:** the largest build of the six. Cached text goes stale and must carry
  provenance and a retrieval date, or it becomes an unsourced quotation — exactly the
  failure the tool exists to catch.
- **Verdict:** the option that changes how review feels. Iframes become the fallback,
  not the mechanism.
- **Why it matters:** *offense* vs. *offence* is the error class that survives every
  other check — citation real, case right, page right, quotation still wrong. An
  iframe structurally cannot catch it. Much of the machinery already exists: the
  passages ledger, `pdfsource find`'s exact→folded→proximity match ladder, and
  ndlaw's `verify_quotation`. What is missing is the pane that displays the result.

### C — Electron desktop app
*3–7 days to first build, then permanent upkeep*

`session.webRequest.onHeadersReceived` strips `X-Frame-Options` and CSP
`frame-ancestors` before Chromium sees them.

- **Fixes:** the only option touching *both* block classes — a real Chromium engine,
  so a Cloudflare challenge can actually run. Filesystem access makes state
  write-back and local PDFs free.
- **Costs:** we would now maintain an application (build toolchain, ~150 MB bundle,
  macOS signing and notarization, update path). Stripping framing headers
  deliberately disables a control the publisher set — defensible for reading public
  law on one's own machine, but worth naming. Cloudflare challenges often will not
  complete *inside a frame* anyway, so even here the win is partial. Fixes nothing
  about problems 1 and 2 that option A doesn't fix for a twentieth of the effort.
- **Verdict:** hold in reserve. Justified only if B leaves a real gap.

### D — Tauri desktop app
*Rejected*

- **No response-header interception** — Tauri has no `webRequest` equivalent, so the
  standard workarounds are a separate webview per source or a Rust-side proxy. A Rust
  proxy is the same proxy as option A and dies on the bot-managed class identically:
  pay for a desktop app, get option A's coverage. Adds Rust and a new build chain to a
  codebase that is Python and vanilla JS end to end.
- **Verdict:** for this specific problem it costs more than Electron and does less.

### E — Chrome header-stripping extension
*~2–3 hours · unpacked, local · zero change to jetredline*

One Manifest V3 `declarativeNetRequest` rule removing `x-frame-options` on a fixed
allowlist of legal-source domains.

- **Fixes:** the header-block class in an afternoon with no change to the tool. Runs
  in a real browser session, so unlike a proxy it has a genuine shot at the
  bot-managed class.
- **Costs:** Chrome-only, loaded unpacked, and it becomes a permanent
  header-weakening extension in an everyday browser. Keep the allowlist to named
  legal domains, never `*`. Fixes nothing about problems 1, 2, or 3.
- **Verdict:** legitimate stopgap for quick relief. Not a destination.

### F — Claude Artifact
*Rejected for the review tool*

- **Confidentiality first.** An artifact is hosted on claude.ai; cite review runs
  against unreleased draft opinions. That is a decision about court work product, not
  a technical detail.
- A strict CSP blocks *every* external host — not just Justia, but `ndcourts.gov`
  too. Artifacts frame **less** than the current page, not more.
- No filesystem, so record PDFs and the local ND corpus are unreachable.
- 16 MB page ceiling; one 85-page findings order compresses to ~3.3 MB, so a real
  record blows past it.
- Available capabilities are `downloads` and `mcp` connectors only — and the ndlaw
  server is a local stdio server, which is not a claude.ai connector.
- **Verdict:** wrong tool for reviewing. Genuinely good for a *shareable summary* of
  a finished review — the sanitized "what was checked, what was flagged" page — once
  an opinion is public.

---

## D. Recommendation and sequencing

**A then B, with E as an optional stopgap. Not a new application shell.**

1. **Serve the page and land the marks.** Add `--serve`. Bind `127.0.0.1`, POST each
   mark to the run directory, reload without losing state. Worst problem, least work,
   and it makes review resumable across sessions.
2. **Group the queue by authority.** Collapse parallel cites into one card carrying
   its occurrence list; one decision applied to every occurrence, with per-occurrence
   override. Roughly a third fewer stops.
3. **Build the evidence pane.** ND authorities and local PDFs first — the majority of
   a typical run, needing no new source. Federal reporters follow once a CourtListener
   token is in place.
4. **Keep the iframe as fallback** for sources that still embed cleanly and for
   anything the text resolver misses. Nothing regresses.
5. **Revisit Electron only if step 3 leaves a gap** — decide then, with evidence.

---

## E. Open questions and unverified claims

- **CourtListener token.** The search endpoint answers anonymously and usefully —
  a citation query returns one record carrying *all* parallel citations, which is
  exactly the data needed to collapse the occurrence problem. But `/api/rest/v4/opinions/`
  returns **401 without a token**, so full text needs a free registered account.
  Not yet obtained. The session's CourtListener MCP connector was unauthenticated
  when this was written.
- **Does a browser engine actually clear the bot-managed sources *inside a frame*?**
  Not tested. Challenge pages have their own framing behavior, so Electron's advantage
  over option E may be smaller than it looks. This is the crux for option C — test it
  before spending a week on a desktop app.
- **Is cached authority text good enough to verify against?** Working view: yes for
  the quotation check, no for the currency check — a cached copy proves the words, not
  that the case is still good law. That keeps the citator pass where it is and lets the
  evidence pane work offline.
- Framework behavior for Electron, Tauri, and Manifest V3 is from vendor documentation
  and issue threads, **not tested here**.

## F. References

- Options write-up with diagrams and UI mockups:
  <https://claude.ai/code/artifact/2d97f8de-f8f4-4d34-a2b0-7f3c10b54a53>
- [chrome.declarativeNetRequest](https://developer.chrome.com/docs/extensions/reference/api/declarativeNetRequest)
- [Electron #32630 — Ignore X-Frame-Options](https://github.com/electron/electron/issues/32630)
- [Tauri #2709 — BrowserView for embedding web content](https://github.com/tauri-apps/tauri/issues/2709)
- [MDN — X-Frame-Options](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Frame-Options)


---

## G. Scoped work items (2026-08-24)

Revisits A–F under constraints that were not on the table when they were written:

- **Users are non-technical staff without admin rights.** No installs. This removes
  options C, D, and E outright — Electron, Tauri, and a loaded-unpacked extension all
  require something the users cannot do.
- **They work in Cowork, not Claude Code.** Cowork is a sandboxed Linux container
  (`/mnt` read-only, `~` is `/root`, network via SOCKS proxy). The skill's filesystem
  is not the staff member's filesystem.
- **Confidence comes from human eyes on the raw source** — an official government page
  or a scan of the record — *not* from text filtered through OCR or a model. Trust in
  the OCR must not be a precondition of trusting the review.

### G.0 The principle that replaces option B

**OCR and model output are navigation aids, never evidence.** Using a located pinpoint
to turn the reviewer to the right page of the right scan is legitimate; rendering
extracted text *as the thing being verified against* is not, because it moves the trust
anchor from the source to the pipeline.

This demotes §C option B from "the option that changes how review feels" to a
page-finding aid behind the existing PDF viewers. The review surface stays what it is
today: the official page or the scanned record image, embedded and read by a human.
The passages ledger and `pdfsource find` keep their value — they decide *which page to
open*, not what the reviewer reads.

### G.1 Parallel-citation consistency check — **BUILT** (`parallel_check.py`)

**The defect.** `_dedup_parallel_citations` (`cite_review.py:2851`) already collapses
parallel cites to the lead reporter — that part works. But it decides what to drop
**by reporter type alone, without resolving anything**: any `S. Ct.` or `L. Ed.` cite
is dropped unconditionally, as is any `N.W.2d/3d` cite carrying a parallel link. A
*wrong* parallel is therefore not shown as a redundant row — it is silently deleted
from the queue and no human ever sees it. The collapse actively conceals the error
class it should be catching.

**Worked example** (verified 2026-08-24). A draft reading
`Whalen v. United States, 445 U.S. 684, 100 S. Ct. 1371` is wrong — *Whalen* is
100 S. Ct. **1432**. `100 S. Ct. 1371` is *Payton v. New York*, 445 U.S. 573, decided
the day before. Two adjacent SCOTUS cases from the same term; entirely plausible on the
page. Today that cite is dropped unread.

**Grouping.** jetcite links parallels **pairwise**, not as a set — for
`445 U.S. 684, 100 S. Ct. 1371, 63 L. Ed. 2d 639`, each entry carries only
`parallel_cite` (singular, `parallel_cites[0]` per `legacy.py:253`). Union-find over
those links recovers the full group.

**Ground truth is jurisdiction-specific — this is the load-bearing finding.**

| Cite class | Authoritative source | Verified |
|---|---|---|
| ND neutral (`2020 ND 30`), N.W./2d/3d | ndlaw corpus via `ndlaw_export.py` backends | yes |
| U.S., S. Ct., L. Ed., F.2d/F.3d | CourtListener search API (anonymous, no token) | yes |

**CourtListener must not be used for ND cites.** It returned `2020 ND 30` with *no*
N.W.2d parallel, and `938 N.W.2d 897` and `10 N.W.3d 500` as not found at all. Treating
that as ground truth would manufacture false mismatches on the most common cite class
in this tool. `ndlaw_export.py` already provides exactly what is needed via both its
sqlite and MCP-over-HTTP backends: `lookup()` returns `citations: [...]`, the full
parallel set ordered `is_primary DESC`.

**Verdicts.** A negative counts only from a source authoritative for that cite
class; absence from a non-authoritative source is silence, not evidence.
(Consistent with the standing rule that unmatched references are reported as "not
located," never "does not exist.")

**Corpus gap vs. corpus conflict — corrected during the build.** The first cut
treated "authoritative source has no record of this citation" as a finding. That
was wrong, and testing caught it: the ndlaw corpus holds `2024 ND 156`
(*Fiebiger v. Anderson*) with **no N.W.3d parallel recorded at all**, because
reporter assignments lag the opinion. Flagging that would have fired a false
mismatch on every recent ND case — the same trap identified for CourtListener,
one level down. The rule that replaces it turns on **reporter series**:

- the source records a cite of the *same series* and it differs → **conflict**
  (`mismatch`), and the badge names the cite the source records;
- the source records *no cite of that series* for the case → **gap**
  (`unverified`), collapse as before.

| Verdict | Condition | Rows | Badge |
|---|---|---|---|
| `consistent` | every asserted parallel confirmed same case | 1, lead reporter | `parallels ok` |
| `mismatch` | a parallel resolves to a different case, **or** conflicts with a recorded cite of its own series | all kept, **not** collapsed | `parallel mismatch` |
| `not_found` | no member resolves at all, though a claiming source was asked | all kept, **not** collapsed | `parallel not located` |
| `unverified` | corpus gap in that series, no source, or offline | 1, lead reporter | `parallels unchecked` |

Verified end to end 2026-08-24: *Whalen* + *Payton*'s `100 S. Ct. 1371` →
`mismatch`; `938 N.W.2d 879` → `mismatch` naming the recorded `938 N.W.2d 897`;
`100 S. Ct. 999999` → `mismatch` naming `100 S. Ct. 1432`; *Fiebiger* + its
N.W.3d → `unverified`, no false alarm; correct pairs → `consistent`.

**Known limitation — a pin page breaks the group.** jetcite links parallels by
adjacency, so `445 U.S. 684, 691, 100 S. Ct. 1371, 63 L. Ed. 2d 715` leaves the
*lead* cite unlinked: the group becomes `{100 S. Ct. 1371, 63 L. Ed. 2d 715}` and
`445 U.S. 684` carries no badge. The mismatch is still caught and still shown —
the badge just sits on the S. Ct./L. Ed. rows rather than on the U.S. row above
them. Fixing it properly belongs in jetcite's parallel linker (spanning a pin
page); bridging it here by text position would be a heuristic over a heuristic.
**Logged upstream 2026-08-24** as an open jetcite issue with root cause, a
one-line fix and its dry-run verification ("Bug: a bare page pin between
parallel cites breaks the parallel link"). When it lands, re-vendor and this
limitation disappears with no change to `parallel_check.py` — `build_groups`
already takes the transitive closure and will simply see the complete group.
jetredline's `TODO.md` carries the re-vendor checklist.

**Bug found and fixed while building: an infinite loop in the existing
collapse.** `_dedup_parallel_citations` walked alias chains with an unguarded
`while target in alias`. jetcite links parallels pairwise, so a `S. Ct.` and an
`L. Ed.` cite whose `U.S.` cite went unlinked — the pin-page case above — each
name the other as their parallel. Both match a drop rule, the alias map holds
`A -> B` and `B -> A`, and the walk never terminates. This is **shipped
behavior**, reachable today on an ordinary citation form; the new check masked
it on the default path (a flagged group never enters the alias map), which is
how `--no-parallel-check` surfaced it. Fixed with cycle detection that elects a
lead and keeps it — the unguarded version would also have dropped *every*
member, deleting the authority from review entirely. Four regression tests.

**Lead-reporter selection stays as-is.** The existing type rules (ND neutral leads for
ND; U.S. leads for SCOTUS) already produce Redbook order, so the resolver's `is_primary`
is not needed to pick the lead and is not wired in — avoiding a change to `authority`
grouping keys and the regressions that would invite.

**Offline behavior.** `--local-only` and any unreachable backend yield `unverified`
everywhere: collapse as today, but visibly badged so nobody reads a short queue as a
checked one. `--no-parallel-check` restores pre-build behavior exactly.

**Shipped surface.** `parallel_check.py` (resolvers, grouping, verdicts; also runs
standalone against a cite JSON for debugging), `lookup_meta()` added to both
`ndlaw_export.py` backends so the check never pulls full opinion text, verdict
plumbing through `_dedup_parallel_citations` into the page, a colorblind-safe
badge on the sidebar group header, and flags `--no-parallel-check` / `--ndlaw-db`.
23 new tests; 390 pass.

### G.2 Review-state round-trip — **BUILT** (`review_state.py`)

**The constraint that decides it.** The File System Access API
(`showSaveFilePicker`) requires a secure context, and `file://` is not one. A
double-clicked local HTML page **cannot write to any folder**, in any browser, with or
without admin rights. The round-trip cannot be a silent file write.

**What makes it work anyway:** the case folder is a *shared/synced* folder visible to
both the staff member's machine and Cowork. So the export needs to land there and be
findable:

- export as `cite-review-state__<case-id>__<timestamp>.json`, carrying case id, schema
  version, and cite counts so the skill can confirm the file belongs to this case;
- the staff member saves it into the folder the review page came from. Chrome/Edge's
  **"Ask where to save each file"** (per-user, no admin) makes this one click; without
  it the file lands in Downloads and is dragged over;
- the skill globs that folder for the newest matching file, ingests it, and reloads it
  into a regenerated page so review **resumes** rather than restarting.

**Open question:** how Cowork reads that shared folder — a Drive/SharePoint connector,
or a per-session upload. Determines whether the skill finds the file itself or is
handed it. Does not change the design.

**Restoring is the part that had to be careful.** Marks are keyed by character
offset (`stateKey()` in the page JS), and jetredline exists to edit drafts — so
offsets move, and a mark restored onto a shifted offset would show a citation as
verified that nobody verified. Nothing is restored by offset. Each exported entry
carries what identifies it to a *reader* — kind, citation text, paragraph, and
occurrence within that paragraph — and the offset is re-derived. Matching is two
tiers:

1. **same paragraph and occurrence** — exact identity;
2. **the paragraph moved, but the citation is unique on both sides** — exactly one
   entry can be meant, so no guess is involved. This recovers a renumbered draft,
   which tier 1 alone would drop entirely.

Anything still unmatched is **dropped and named on stderr**, never guessed. Tier 2
refuses to choose between candidates: a citation appearing more than once on
either side drops instead. A `draft_sha256` in the payload reports whether the
draft changed at all, so a clean resume is distinguishable from a remapped one.

**Merge policy in the page is additive.** A restored mark fills an entry this
browser has not touched and never overwrites work done locally; the page
announces `Restored N mark(s) from the previous review` rather than restoring
silently, since silent restoration is indistinguishable from the reviewer's own
work.

**Shipped surface.** `review_state.py` (schema, validation, newest-export
discovery, two-tier restore; also a standalone CLI that summarizes a review and
lists what was flagged), a `META`/`RESUME` channel into the page, `Save review`
and `Copy` buttons with a confirmation line telling the reviewer what to do with
the file, and `--resume-state PATH|auto` on `cite_review.py`. Files are named
`cite-review-state__<case-id>__<YYYYMMDD-HHMMSS>.json`; `find_latest` sorts on the
embedded stamp rather than mtime, because copying a file into a shared folder
rewrites mtime and would make an older review look newer. A malformed or foreign
file warns and starts a fresh review — it never blocks the page being built.
28 new tests; 418 pass.

**Verified end to end 2026-08-24:** unchanged draft → 6/6 restored; draft with a
paragraph inserted above → 6/6, one re-matched by tier 2, draft-change reported;
vanished citation → dropped and named; foreign JSON → warned and skipped.

**Not pursued:** serving over `localhost` would give a secure context and a silent
POST, but depends on Cowork port-forwarding, which is untested.

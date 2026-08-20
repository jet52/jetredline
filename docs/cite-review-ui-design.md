# Cite review UI — options for a better review surface

Research logged 2026-08-15 against jetredline 4.19.2. **Nothing here is built.**
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

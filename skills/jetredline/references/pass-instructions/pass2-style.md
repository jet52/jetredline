# Pass 2: Style and Grammar Edit — Subagent Instructions

You are a jetredline subagent. The caller's prompt supplies the draft opinion's file path and the skill root — written as `<SKILL_ROOT>` below (if the caller omitted it, use the directory two levels above this file). Return **only** the structured entry list specified below.

Read the style guide at `<SKILL_ROOT>/references/style-guide.md` and the draft opinion at the supplied path. The style guide contains the full hard rules and style preferences — apply them in priority order (hard rules always; style preferences with judgment).

One additional hard rule not in the style guide:

- Use "less" for uncountable nouns and "fewer" for countable nouns.

**Do not propose nonbreaking-space edits.** The space after `¶`/`§` should be a nonbreaking space (U+00A0), but never raise it as an entry: a change bar on every citation buries the substantive edits. The caller handles it deterministically.

Apply the style and grammar rules to the entire opinion. For each proposed edit, produce a structured entry:

```
¶ [paragraph number]
OLD: [exact original text — the SHORTEST span that is unique within its paragraph. The redline deletes and reinserts exactly this span, so extra context widens the strikethrough for no benefit. A phrase or clause usually suffices; use the full sentence only when nothing shorter is unique or the rewrite genuinely spans it.]
NEW: [replacement text]
REASON: [brief explanation — which rule applies. Write `self-evident` when the diff speaks for itself (and/or → or, a comma added, a nominalization unwound); the caller then attaches no comment. Reserve a real reason for edits a reader might question.]
```

Group entries by paragraph order. Include only changes that improve the text — do not rewrite clear passages. Preserve the court's voice.

For issues that warrant a comment rather than a direct edit (e.g., possible restructuring, ambiguous meaning), use:

```
¶ [paragraph number]
COMMENT: [the note to attach as a comment in the document]
ANCHOR: [the word or phrase the comment should attach to]
```

Return all entries as a single structured list. Do not produce any other output.

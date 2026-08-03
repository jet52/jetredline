# Pass 2: Style and Grammar Edit — Subagent Instructions

You are a jetredline subagent. The caller's prompt supplies the draft opinion's file path and the skill root — written as `<SKILL_ROOT>` below (if the caller omitted it, use the directory two levels above this file). Return **only** the structured entry list specified below.

Read the style guide at `<SKILL_ROOT>/references/style-guide.md` and the draft opinion at the supplied path. The style guide contains the full hard rules and style preferences — apply them in priority order (hard rules always; style preferences with judgment).

Two additional hard rules not in the style guide:

- Replace any ordinary space following a paragraph symbol (¶) or section symbol (§) with a nonbreaking space (Unicode U+00A0). In OOXML, use `&#160;` in the XML text. Propose these as edits like any other.
- Use "less" for uncountable nouns and "fewer" for countable nouns.

Apply the style and grammar rules to the entire opinion. For each proposed edit, produce a structured entry:

```
¶ [paragraph number]
OLD: [exact original text — enough context to locate uniquely, typically the full sentence]
NEW: [replacement text]
REASON: [brief explanation — which rule applies]
```

Group entries by paragraph order. Include only changes that improve the text — do not rewrite clear passages. Preserve the court's voice.

For issues that warrant a comment rather than a direct edit (e.g., possible restructuring, ambiguous meaning), use:

```
¶ [paragraph number]
COMMENT: [the note to attach as a comment in the document]
ANCHOR: [the word or phrase the comment should attach to]
```

Return all entries as a single structured list. Do not produce any other output.

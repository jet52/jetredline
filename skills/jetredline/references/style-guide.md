# Style Guide for Judicial Opinion Editing

## Priority Order of Style Authorities

1. Bryan Garner's *The Redbook: A Manual on Legal Style* (primary style authority)
2. Opinions by Justice Jerod Tufte, North Dakota Supreme Court
3. Ross Guberman, *Point Taken: How to Write Like the World's Best Judges*
4. Opinions of Justice Neil Gorsuch, Justice Elena Kagan, Justice Clarence Thomas

## Core Style Principles

### Voice and Tone
- Favor active voice. Use passive only when it genuinely improves readability or when the actor is unknown or irrelevant.
- Write with directness and confidence. Avoid hedging language unless the court is genuinely uncertain.
- Prefer short, declarative sentences for key holdings. Use longer sentences sparingly and only when syntactic complexity serves clarity.

### Word Choice
- Never use "and/or." Rewrite to specify the intended meaning (X, Y, or both; X or Y; etc.).
- Never use legalese: herein, hereinbefore, hereinafter, wherefore, aforementioned, said (as adjective), such (as pronoun), same (as pronoun).
- Never use Latin when a plain English word carries the same precision (e.g., "before" not "prior to"; "about" not "approximately" unless precision matters; "among" not "inter alia").
- Exception: Latin terms of art with no English equivalent may be retained (e.g., habeas corpus, certiorari, res judicata, stare decisis, amicus curiae).
- Prefer concrete nouns over nominalizations (e.g., "the court decided" not "the court's determination was").
- Avoid throat-clearing phrases: "It is well settled that," "It is important to note that," "It should be noted that."

### Pronouns and Gender-Neutral Writing
- Prefer invisible gender-neutrality: rephrase to avoid gendered pronouns when the referent's gender is unknown or irrelevant.
- Techniques: use a plural noun as the antecedent (allowing plural pronouns naturally), repeat the noun, restructure the sentence, replace a pronoun with an article, or use "a person who" or "one."
  - Not this: "An accused person must actively waive his right to speak to his lawyer."
  - But this: "An accused person must actively waive the right to speak to a lawyer."
- If all parties in a case consistently use a specific pronoun to refer to a person, do not deviate from that usage.
- Do not use singular "they" to refer to a specific, identified individual whose pronouns are otherwise clear from context.

### Constitutional Language
- Where the text of a constitutional provision is framed as recognizing or protecting a pre-existing right, preserve that framing. Do not rephrase such provisions as granting, creating, or giving the right.
- Correct: "The Fourth Amendment protects against unreasonable searches." (The text says "shall not be violated," presupposing the right.)
- Incorrect: "The Fourth Amendment grants a right against unreasonable searches."
- If a provision's text expressly establishes a new governmental structure or process, "creates" or "establishes" may be appropriate.

### Oxford Comma
- Always use the Oxford comma (serial comma before "and" or "or" in a list of three or more).

### Conciseness
- Eliminate unnecessary words: "in order to" → "to"; "at this point in time" → "now"; "due to the fact that" → "because"; "the fact that" → "that."
- Remove "clearly," "obviously," "of course" — if the point is clear, these are unnecessary; if not, they do not make it so.
- Avoid doubling: "null and void," "each and every," "cease and desist" (unless quoting).
- One idea per sentence when possible. Break compound sentences that carry two independent thoughts.

### Sentence Structure
- Lead with the point. Put the conclusion or holding first, then the reasoning. (Guberman: "The bottom line goes on top.")
- Vary sentence length. Follow a long, complex sentence with a short one for emphasis.
- Keep subject and verb close together. Avoid separating them with long parentheticals or subordinate clauses.
- Avoid stacking prepositional phrases (more than two in sequence signals a need to restructure).

### Paragraph Structure
- Topic sentence first. Each paragraph should have one main idea.
- Transitional phrases between paragraphs should signal the logical relationship (but, however, moreover, accordingly, in contrast).
- Keep paragraphs under 200 words for readability, especially in analytical sections.

## Citation Format (Bluebook)

### General Rules
- Follow *The Bluebook: A Uniform System of Citation* for all citations.
- Use full citation on first reference; short form thereafter.
- Verify that all case names are italicized (or underlined consistently).
- Verify pinpoint cites include specific page numbers.
- Signal usage: check that "see," "see also," "cf.," "but see," "accord" are used correctly per Bluebook rules 1.2-1.4.

### North Dakota-Specific Conventions
- North Dakota Supreme Court cases: *Party v. Party*, year ND volume, paragraph cite (e.g., *State v. Smith*, 2024 ND 45, ¶ 12).
- Parallel citations to N.W.2d or N.W.3d are not required for ND opinions but may appear.
- North Dakota Century Code: N.D.C.C. § XX-XX-XX.
- North Dakota Constitution: N.D. Const. art. X, § X.
- North Dakota Rules of Civil Procedure: N.D.R.Civ.P. Rule XX.
- North Dakota Rules of Criminal Procedure: N.D.R.Crim.P. Rule XX.
- North Dakota Rules of Appellate Procedure: N.D.R.App.P. Rule XX.
- North Dakota Rules of Evidence: N.D.R.Ev. Rule XXX.
- North Dakota Administrative Code: N.D. Admin. Code § XX-XX-XX-XX.

## Analytical Rigor Checks

### Dicta
- Flag any statement that is not necessary to the decision's holding.
- Distinguish: (a) statements that address issues not raised by the parties, (b) alternative rationales that could be removed without affecting the outcome, (c) broad pronouncements beyond what the facts require.
- Note whether dicta could be misread as holding.

### Alternative Rationales
- Flag when the opinion provides two or more independent grounds for the same result.
- Assess whether each ground is fully developed or whether one is stronger.
- Consider whether an underdeveloped alternative rationale weakens the opinion or invites confusion.

### Logical Fallacies
- Check for: begging the question, straw man, false dichotomy, slippery slope, appeal to authority (beyond precedent), post hoc reasoning, equivocation, hasty generalization.
- Check for unstated assumptions that reasonable minds might not share.

### Ambiguity and Vulnerability
- Read the opinion from the perspective of the losing party. Identify passages that could be quoted out of context to distort the holding.
- Identify vague standards ("reasonable," "appropriate," "under the circumstances") that lack sufficient guidance for future application.
- Flag any sentence that could be read two ways and suggest clarification.
- Consider whether the holding is broader than necessary and might apply to unintended situations.

## Analytical Rigor Checks — Bench Memos

These checks apply when editing bench memos (`DOC_TYPE = memo`). They replace the opinion-specific dicta/holdings/ambiguity checks above.

### Issue Completeness
- Verify the memo identifies every issue raised by the parties on appeal.
- Check for issues the parties did not raise but the court should consider: plain error, jurisdictional defects, mootness, standing, or issues apparent from the record.
- Flag any issue that appears in the briefs but is absent from the memo.

### Balanced Presentation
- Each side's strongest arguments should be fairly stated. The memo should not strawman or understate either position.
- Steelman the weaker position: if the memo dismisses an argument in a sentence or two, flag it and assess whether the argument deserves more engagement.
- Check whether the memo acknowledges contrary authority or distinguishes it, rather than ignoring it.

### Recommendation Quality
- Each recommendation should be clearly stated — not buried in analysis or implied.
- Each recommendation must be supported by the preceding analysis. Flag any recommendation that appears to leap past the reasoning.
- Alternative outcomes should be acknowledged. If the court could reasonably go either way, the memo should say so and explain the tradeoffs.
- If the memo recommends affirming or reversing, check whether it addresses remedy (remand, modification, etc.).

### Analytical Gaps
- Identify unstated assumptions that reasonable minds might not share.
- Check for logical fallacies: begging the question, false dichotomy, straw man, slippery slope, post hoc reasoning.
- Flag missing steps in the reasoning chain — where the conclusion does not follow from the stated premises.
- Check for circular reasoning, especially in standard-of-review application (e.g., concluding the district court was "not clearly erroneous" without examining the evidence).

### Standard of Review Application
- Verify the memo correctly identifies the standard of review for each issue (de novo, clearly erroneous, abuse of discretion, etc.).
- Check that the memo consistently applies the identified standard throughout the analysis — not just naming it at the outset and then ignoring it.
- Flag instances where the analysis applies a stricter or more lenient standard than the one identified.

## Characteristics of Target Judicial Styles

### Justice Tufte (ND Supreme Court)
- Direct, economical prose. No wasted words.
- Clear roadmapping: tells the reader where the opinion is going.
- Careful attention to standard of review and its application.
- Precise use of facts — includes only facts that matter to the analysis.
- Short paragraphs, often with clear topic sentences.

### Justice Gorsuch
- Conversational tone that remains dignified.
- Concrete, vivid language. Uses real-world analogies.
- Short sentences for emphasis after longer analytical passages.
- Strong opening sentences that frame the stakes.

### Justice Kagan
- Accessible, engaging prose. Often opens with a narrative hook.
- Skilled at distilling complex legal questions into plain language.
- Uses rhetorical questions effectively.
- Careful structural signposting.

### Justice Thomas
- Originalist framing with careful attention to text and history.
- Direct, spare prose with little ornamentation.
- Thorough engagement with source materials.
- Willingness to address first principles.

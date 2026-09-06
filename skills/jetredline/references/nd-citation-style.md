# North Dakota Supreme Court — Supplement to the Redbook (4th ed.)

The Court's house adjustments to Bluebook/Redbook citation form, for use when
**drafting or editing** opinions, bench memos, and other court work product.

> **Canonical source.** This file lives in the `jetcite` repository at
> `reference/nd-citation-style.md` and is vendored into the consuming skills
> (`jetmemo`, `jetredline`, `jetrehearing`) by `make vendor-citestyle`. Edit it
> **here** — a vendored copy edited in place will be reported by each skill's
> `make drift-check` and overwritten on the next vendor.

**Precedence.** A North Dakota rule overrides a conflicting Bluebook or Redbook
convention. Within ND authority the order is: N.D.R.App.P. and other court rules
→ this supplement → Redbook → Bluebook.

---

## Full citation form

Cite by era:

| Period | Form |
| ------ | ---- |
| 1997–present | `Keller v. Keller, 2017 ND 119, ¶ 12, 894 N.W.2d 883.` |
| 1954–1997 | `Gissel v. Kenmare Twp., 512 N.W.2d 470, 477 (N.D. 1994).` |
| 1890–1953 | `Koller v. State, 19 N.W.2d 822, 823 (N.D. 1945).` |

**For cases before 1997, cite only N.W. or N.W.2d — omit the N.D. Reports
citation.**

Note the difference in pinpoint practice between the eras: a pre-1997 cite
carries a **page** pin cite to the reporter (`512 N.W.2d 470, 477`); a
public-domain cite carries a **paragraph** pin cite and no reporter pin cite
(below).

## Public domain / medium-neutral citations

After the case name, give the year of the decision and the court abbreviation:

- **`ND`** — North Dakota Supreme Court
- **`ND App`** — North Dakota Court of Appeals

Use a paragraph symbol for the pinpoint, with a **non-breaking space** between
the symbol and the number. Include the parallel citation to the North Western
Reporter, but **do not give a pin cite to the North Western Reporter** — the
paragraph number is the pinpoint, and it is found in both sources.

**Proper:**

```
Miller v. MedCenter One, 1997 ND 231, ¶ 10, 571 N.W.2d 358.
Johnson v. State, 2005 ND App 8, ¶ 7, 700 N.W.2d 723.
```

**Improper:**

```
Miller v. MedCenter One, 1997 ND 231, ¶ 10, 571 N.W.2d 358, 360.
Johnson v. State, 2005 ND App 8, ¶ 7, 700 N.W.2d 723, 726.
```

> The Supreme Court and the Court of Appeals share a year/number space —
> `2005 ND 7` and `2005 ND App 7` are **different cases**. Never drop the `App`
> token, and never treat the two as the same authority.

## Short form citations

See the **most recent edition of the Bluebook** at B10.2 (Short Form Citation)
and R10.9 (Short Forms for Cases). Cite the rules by number rather than by page:
rule numbering is stable across editions, pagination is not.

For parallel citations to a public domain source the short form differs from
ordinary Bluebook practice: a parallel citation to the North Western Reporter
would be included only to the first page of the opinion, because the paragraph
number is found in both sources. **To be concise, do not repeat the N.W.2d cite
in the short form at all.** Thus:

```
State v. Erickson, 2018 ND 133, ¶ 7, 911 N.W.2d 913.
```

becomes:

```
Erickson, 2018 ND 133, ¶ 7.
```

### Id.

Where a parallel citation to a public domain source is required, the `id.` form
is:

```
Id. ¶ 7.
```

No `at` before a paragraph pin — the supplement dropped it here as it did in
the special short form below.

### Special short form — full form or full short form in the same paragraph

Often `id.` is unavailable because another citation intervenes between the
reference and the one you wish to `id.` to. Where `id.` is not permissible, and
**if — and only if —** the full form or the full short form has previously been
cited **in the same paragraph**, a short form using only the first party's name,
a comma, and the pin cite may be used. A **page** pin takes `at`; a
**paragraph** pin does not:

```
State v. Falcon, 546 N.W.2d 835, 836 (N.D. 1996)   →   Falcon, at 836.
Kuntz v. State, 2019 ND 46, ¶ 11, 923 N.W.2d 513   →   Kuntz, ¶ 11.
```

The same-paragraph condition is a real limit, not a formality: this form is
improper if the antecedent full cite is in an earlier paragraph.

---

## Citations to briefs

**Author preference.** Neither the Bluebook nor the Redbook supplies these
abbreviations; BT1 has no short form for "appellant" or "appellee." This is a
local convention, not a rule of the Court. It is collected here so the drafting
skills apply one form.

North Dakota briefs carry numbered paragraphs, and a reference to material in a
document with numbered paragraphs "must be to the paragraph number."
N.D.R.App.P. 32(a)(7); *see also* N.D.R.App.P. 32(b)(1). Pages are numbered from
the cover, N.D.R.App.P. 32(a)(4), so a page pin locates the paragraph quickly
without displacing it.

Cite the shorthand title of the brief, then the page, then the paragraph:

```
(At. Br. 1, ¶ 2)
(Ae. Br. 2, ¶ 3)
```

No `at` before either pin — consistent with Bluebook practice for court
documents, and with the paragraph forms above. Put a **non-breaking space**
between `¶` and the number, as in a case-law cite.

### Placement

**Within a sentence**, parenthesize, with no period inside the parentheses:

```
The appellant argues the statute is ambiguous (At. Br. 1, ¶ 2), but the text
admits of only one reading.
```

**After a sentence**, as a separate citation sentence, omit the parentheses and
close with a period:

```
The appellee reads the same clause as a limitation. Ae. Br. 3, ¶ 9.
```

### Shorthand titles

| Document | Form |
| -------- | ---- |
| Appellant's brief | `At. Br.` |
| Appellee's brief | `Ae. Br.` |
| Reply brief | `At. Reply Br.` |
| Cross-appellee's reply brief | `Ae. Reply Br.` |
| Supplemental brief | `At. Supp. Br.` / `Ae. Supp. Br.` |
| Amicus brief | `Amicus Br.` — name the amicus if more than one: `Amicus Br. (ACLU) 5, ¶ 11` |
| Petitioner's brief (writ proceedings) | `Pet. Br.` |
| Respondent's brief (writ proceedings) | `Resp. Br.` |

Where more than one party occupies a side, name the party rather than relying on
the shorthand alone: `At. Br. (Johnson) 6, ¶ 14`.

### Pin cites, spans, and non-compliant briefs

- **Multiple paragraphs** take `¶¶` and an en dash: `(At. Br. 3, ¶¶ 9–11)`.
- **A span crossing pages** gives both spans: `(At. Br. 3–4, ¶¶ 9–11)`.
- **No `id.`** for briefs. Repeat the shorthand: `At. Br. 4, ¶ 9`, never
  `Id. ¶ 9` — the shorthand is three characters, and an `id.` here is
  indistinguishable from an `id.` to a case paragraph.
- **A brief without numbered paragraphs** — an older filing, or one that does
  not comply with N.D.R.App.P. 32(a)(7) — is cited to the page alone:
  `(At. Br. 7)`. Note the defect rather than passing the page-only cite off as
  the normal form.

---

## Statutes and session laws

### North Dakota Century Code

Use `N.D.C.C.` followed by the section symbol `§` and the section number.

```
N.D.C.C. § 12.1-32-01
```

A parenthetical year — `(1969)`, `(Supp. 1997)` — is **not generally
necessary**. Context may require it in cases involving statutes that have since
been amended or repealed.

(For other states' codes, see Bluebook T1.)

### North Dakota Revised Code

May be cited as `N.D.R.C.`, in the same way as the N.D.C.C. — **except that a
reference to the year should always be provided.**

```
N.D.R.C. § 27-0501 (1943)
```

### Laws of North Dakota

```
1997 N.D. Sess. Laws ch. 564, § 8.
```

---

## Paragraph symbol

Never write "para." or "paras." Use `¶` (singular) or `¶¶` (plural).

- **Case law citations** (Bluebook) — space between the symbol and the number:
  `2024 ND 156, ¶ 12`, `¶¶ 6–8`. The supplement specifies a **non-breaking**
  space here.
- **Record citations** (N.D.R.App.P. 30) — **no** space: `R45:12:¶15`,
  `¶¶7–14`. The rule governs, so this differs from the case-law convention
  above by design.

---

## Which of these rules are checked mechanically

`jetcite` (≥ 2.8.0) detects three of these; the rest are drafting rules a
reviewer or model must apply.

| Rule | Detection |
| ---- | --------- |
| `ND App` is a distinct court sharing a number space with `ND` | Parsed; `components["court"]`, normalized as `YYYY ND App N`, cached under `opin/NDApp/` so it cannot collide with a Supreme Court cite |
| No pin cite to the reporter in a public-domain parallel | `improper_parallel_pincite: true` on the reporter half of the pair. Scoped to ND pairs, and **not** raised for pre-1997 cites, where the reporter pin cite is correct |
| Special short form (`Kuntz, ¶ 11`; `Falcon, at 836`) | Parsed as a pin cite and resolved to its parent full cite |

Not mechanically checked — apply by reading:

- The era rules (which form a given year takes, and omitting N.D. Reports).
- Whether the special short form's antecedent is in the **same paragraph**.
- Whether a `(year)` parenthetical is warranted on an N.D.C.C. cite because the
  statute was later amended or repealed.
- Non-breaking vs ordinary space before a case-law `¶`.
- Brief citations — the shorthand titles, the page/paragraph pair, and the
  parenthetical-vs-citation-sentence placement. `jetcite` does not parse them.

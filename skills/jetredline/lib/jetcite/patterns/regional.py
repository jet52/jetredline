"""Regional and state-specific reporter citation patterns."""

import re

from jetcite.models import Citation, CitationType, Source
from jetcite.patterns import register
from jetcite.patterns.base import BaseMatcher
from jetcite.sources.courtlistener import courtlistener_url

# Each tuple: (compiled_regex, reporter_format_func, has_edition_group)
# reporter_format_func takes the match and returns (reporter_string, edition_or_None)

_REPORTERS: list[tuple[re.Pattern, str, bool]] = []


def _add(pattern: str, reporter_template: str, has_edition: bool = True):
    _REPORTERS.append((re.compile(pattern), reporter_template, has_edition))


# Regional reporters with editions (series suffix is mandatory; the first
# series is handled by the separate patterns below with negative lookahead).
# Making the series mandatory prevents the regex engine from backtracking on
# inputs like "491 F.3d at 363" or "409 So. 3d at 188" and producing a
# truncated phantom citation ("491 F. 3", "409 So. 3").
# Two-letter abbreviations tolerate an internal space/newline ("N. W. 2d"):
# West's bound-volume house style prints them spaced; normalized output stays
# compact.
_add(r'(\d+)\s+N\.\s?W\.\s?([23]d)\s+(\d+)', "N.W.{ed}", True)
_add(r'(\d+)\s+A\.([23]d)\s+(\d+)', "A.{ed}", True)
_add(r'(\d+)\s+N\.\s?E\.\s?([23]d)\s+(\d+)', "N.E.{ed}", True)
_add(r'(\d+)\s+S\.\s?E\.\s?(2d)\s+(\d+)', "S.E.{ed}", True)
_add(r'(\d+)\s+So\.\s?([23]d)\s+(\d+)', "So. {ed}", True)
_add(r'(\d+)\s+S\.\s?W\.\s?([23]d)\s+(\d+)', "S.W.{ed}", True)
_add(r'(\d+)\s+P\.([23]d)\s+(\d+)', "P.{ed}", True)

# First series (no edition group)
# Negative lookahead prevents matching "300 So. 2" when the actual text is "300 So. 2d 100"
#
# The optional "Rep." is the 1880s-1900s house style: the regional reporters
# were cited "62 N. W. Rep. 594" before the suffix was dropped, and the ND
# corpus carries ~2,950 such sites that matched nothing at all before jetcite
# 2.10.  It belongs ONLY to the first series -- N.W.2d postdates the convention
# by forty years -- so it is never added to the series-suffixed patterns above,
# where it would buy nothing and hand the engine one more way to backtrack.
# The "Rep." group sits BEFORE the mandatory whitespace, not after it, so the
# unspaced print form "1 N.W.Rep. 691" is reached as well as "62 N. W. Rep. 594".
_REP = r'(?:\s*Rep\.)?'
_add(r'(\d+)\s+N\.\s?W\.' + _REP + r'\s+(\d+)(?!d\b)', "N.W.", False)
_add(r'(\d+)\s+N\.\s?E\.' + _REP + r'\s+(\d+)(?!d\b)', "N.E.", False)
_add(r'(\d+)\s+A\.' + _REP + r'\s+(\d+)(?!d\b)', "A.", False)
_add(r'(\d+)\s+P\.' + _REP + r'\s+(\d+)(?!d\b)', "P.", False)
_add(r'(\d+)\s+S\.\s?E\.' + _REP + r'\s+(\d+)(?!d\b)', "S.E.", False)
_add(r'(\d+)\s+So\.' + _REP + r'\s+(\d+)(?!d\b)', "So.", False)
_add(r'(\d+)\s+S\.\s?W\.' + _REP + r'\s+(\d+)(?!d\b)', "S.W.", False)

# Reporter NAMES the modern abbreviation no longer resembles: the patterns above
# cannot reach these because `P\.` does not match the "P" of "Pac.", nor `A\.`
# the "A" of "Atl.".
#
# The "Rep." here is OPTIONAL, and getting that wrong was the 2.10.0 bug: it
# shipped mandatory on the claim that "a bare 'Pac.' in this corpus is prose."
# The corpus says otherwise -- 3,585 bare "Pac.", 1,005 bare "Atl.", 454 bare
# "South." -- and the claim came from a scan that only searched strings already
# containing "Rep.", so it could not have found its own counterexample.
#
# What actually keeps these safe is the DIGIT on both sides, not the "Rep.":
# "Southern Pac. Ry. Co." has no leading volume, and "5 Fed. Cas. 563" /
# "9 Sup. Ct. Rules" fail because a reporter name, not a page, follows.
# ("Am. Rep." and "Am. St. Rep." are NOT this class: those reporters are still
#  named with the "Rep.", and they are out of scope -- see PLAN.md.)
_add(r'(\d+)\s+Pac\.' + _REP + r'\s*(\d+)', "P.", False)
_add(r'(\d+)\s+Atl?\.' + _REP + r'\s*(\d+)', "A.", False)
_add(r'(\d+)\s+South\.' + _REP + r'\s*(\d+)', "So.", False)

# State-specific reporters (modern series only — first series for these
# reporters is rare in ND practice and not currently supported).
_add(r'(\d+)\s+Cal\.\s?(2d|3d|4th|5th)\s+(\d+)', "Cal. {ed}", True)
_add(r'(\d+)\s+Cal\.\s?Rptr\.\s?(2d|3d)\s+(\d+)', "Cal. Rptr. {ed}", True)
_add(r'(\d+)\s+N\.\s?Y\.([23]d)\s+(\d+)', "N.Y.{ed}", True)
_add(r'(\d+)\s+N\.\s?Y\.\s?S\.([23]d)\s+(\d+)', "N.Y.S.{ed}", True)
_add(r'(\d+)\s+Ohio\s+St\.\s?([23]d)\s+(\d+)', "Ohio St. {ed}", True)
_add(r'(\d+)\s+Ill\.\s?(2d)\s+(\d+)', "Ill. {ed}", True)
_add(r'(\d+)\s+Ill\.\s?Dec\.\s+(\d+)', "Ill. Dec.", False)
_add(r'(\d+)\s+Wash\.\s?(2d)\s+(\d+)', "Wash. {ed}", True)
_add(r'(\d+)\s+Wash\.\s?App\.\s?(2d)\s+(\d+)', "Wash. App. {ed}", True)

# North Dakota Reports: 50 N.D. 123 (volumes 1-79, published 1890-1953).
# Volume capped at 1–79 so e.g. "224 N.D. 898" is never a Reports cite.
# Use a negative lookahead to avoid matching "N.D.C." (NDCC) or "N.D.A." (NDAC)
# ("N. D." spaced form per West house style; the lookahead still blocks the
# spaced "N. D. C. C." statute form because the page must be a digit run).
# `(?<!\d)` stops a 4-digit year from being truncated into a volume
# ("2024 N.D. 156" must NOT become "024 N.D. 156"; neutral wins that form).
# There is no separate N.D. App. *print* reporter — Court of Appeals cites
# are medium-neutral (`YYYY ND App N` / period-spelled variants in neutral.py).
_ND_REPORTS_VOL = r'(?:[1-9]|[1-7]\d)'  # 1–79
_add(r'(?<!\d)(' + _ND_REPORTS_VOL + r')\s+N\.\s?D\.' + _REP + r'\s+(?!C|A)(\d+)', "N.D.", False)

# Archaic "N. Dak." / "N.Dak." spelling of the N.D. Reports reporter
# (early opinions; normalize to compact N.D.). Same 1–79 volume cap + year guard.
_add(r'(?<!\d)(' + _ND_REPORTS_VOL + r')\s+N\.\s*Dak\.' + _REP + r'\s+(\d+)', "N.D.", False)

# Malformed NW2d fallback (case-insensitive)
_add(r'(\d+)\s+(?:NW\.?\s?2d|N\.W2d)\s+(\d+)', "N.W.2d", False)

# Other state reporters (no edition)
_STATE_REPORTERS = re.compile(
    r'(\d+)\s+'
    r'(Ariz\.(?:\s+App\.)?|Conn\.|Ga\.|Haw\.|Kan\.|Mass\.|Md\.|Mich\.|N\.C\.|N\.J\.|Neb\.|Or\.|Pa\.|S\.C\.|Va\.)'
    r'\s+(\d+)'
)

class RegionalReporterMatcher(BaseMatcher):
    def find_all(self, text: str) -> list[Citation]:
        results = []

        for pattern, template, has_edition in _REPORTERS:
            for m in pattern.finditer(text):
                if has_edition:
                    volume, page = m.group(1), m.group(3)
                    edition = m.group(2)
                    if edition:
                        reporter = template.replace("{ed}", edition)
                    else:
                        reporter = template.replace("{ed}", "")
                else:
                    volume, page = m.group(1), m.group(2)
                    reporter = template

                # Clean up double spaces
                reporter = reporter.strip()

                sources = [Source("courtlistener",
                                  courtlistener_url(reporter, volume, page))]

                jur = "nd" if reporter == "N.D." else "us"

                results.append(Citation(
                    raw_text=m.group(0),
                    cite_type=CitationType.CASE,
                    jurisdiction=jur,
                    normalized=f"{volume} {reporter} {page}",
                    components={"volume": volume, "reporter": reporter, "page": page},
                    sources=sources,
                    position=m.start(),
                ))

        # Other state reporters
        for m in _STATE_REPORTERS.finditer(text):
            volume, reporter, page = m.group(1), m.group(2), m.group(3)
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.CASE,
                jurisdiction="us",
                normalized=f"{volume} {reporter} {page}",
                components={"volume": volume, "reporter": reporter, "page": page},
                sources=[Source("courtlistener",
                                courtlistener_url(reporter, volume, page))],
                position=m.start(),
            ))

        return results


register(6, RegionalReporterMatcher())

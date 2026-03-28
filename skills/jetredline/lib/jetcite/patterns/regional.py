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


# Regional reporters with editions
_add(r'(\d+)\s+N\.W\.\s?([23]d)\s+(\d+)', "N.W.{ed}", True)
_add(r'(\d+)\s+A\.([23]d)\s+(\d+)', "A.{ed}", True)
_add(r'(\d+)\s+N\.E\.\s?([23]d)\s+(\d+)', "N.E.{ed}", True)
_add(r'(\d+)\s+S\.E\.\s?(?:(2d)\s+)?(\d+)', "S.E.{ed}", True)
_add(r'(\d+)\s+So\.\s?(?:([23]d)\s+)?(\d+)', "So.{ed}", True)
_add(r'(\d+)\s+S\.W\.\s?(?:([23]d)\s+)?(\d+)', "S.W.{ed}", True)
_add(r'(\d+)\s+P\.([23]d)\s+(\d+)', "P.{ed}", True)

# First series (no edition group)
# Negative lookahead prevents matching "300 So. 2" when the actual text is "300 So. 2d 100"
_add(r'(\d+)\s+N\.W\.\s+(\d+)(?!d\b)', "N.W.", False)
_add(r'(\d+)\s+N\.E\.\s+(\d+)(?!d\b)', "N.E.", False)
_add(r'(\d+)\s+A\.\s+(\d+)(?!d\b)', "A.", False)
_add(r'(\d+)\s+P\.\s+(\d+)(?!d\b)', "P.", False)
_add(r'(\d+)\s+S\.E\.\s+(\d+)(?!d\b)', "S.E.", False)
_add(r'(\d+)\s+So\.\s+(\d+)(?!d\b)', "So.", False)
_add(r'(\d+)\s+S\.W\.\s+(\d+)(?!d\b)', "S.W.", False)

# State-specific reporters
_add(r'(\d+)\s+Cal\.\s?(?:(2d|3d|4th|5th)\s+)?(\d+)', "Cal.{ed}", True)
_add(r'(\d+)\s+Cal\.\s?Rptr\.\s?(?:(2d|3d)\s+)?(\d+)', "Cal. Rptr.{ed}", True)
_add(r'(\d+)\s+N\.Y\.(?:([23]d)\s+)?(\d+)', "N.Y.{ed}", True)
_add(r'(\d+)\s+N\.Y\.S\.(?:([23]d)\s+)?(\d+)', "N.Y.S.{ed}", True)
_add(r'(\d+)\s+Ohio\s+St\.\s?(?:([23]d)\s+)?(\d+)', "Ohio St.{ed}", True)
_add(r'(\d+)\s+Ill\.\s?(?:(2d)\s+)?(\d+)', "Ill.{ed}", True)
_add(r'(\d+)\s+Ill\.\s?Dec\.\s+(\d+)', "Ill. Dec.", False)
_add(r'(\d+)\s+Wash\.\s?(?:(2d)\s+)?(\d+)', "Wash.{ed}", True)
_add(r'(\d+)\s+Wash\.\s?App\.\s?(?:(2d)\s+)?(\d+)', "Wash. App.{ed}", True)

# North Dakota Reports: 50 N.D. 123 (volumes 1-79, published 1890-1953)
# Use a negative lookahead to avoid matching "N.D.C." (NDCC) or "N.D.A." (NDAC)
_add(r'(\d{1,3})\s+N\.D\.\s+(?!C|A)(\d+)', "N.D.", False)

# Malformed NW2d fallback (case-insensitive)
_add(r'(\d+)\s+(?:NW\.?\s?2d|N\.W2d)\s+(\d+)', "N.W.2d", False)

# Other state reporters (no edition)
_STATE_REPORTERS = re.compile(
    r'(\d+)\s+'
    r'(Conn\.|Ga\.|Haw\.|Kan\.|Mass\.|Md\.|Mich\.|N\.C\.|N\.J\.|Neb\.|Or\.|Pa\.|S\.C\.|Va\.)'
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
                        reporter = template.replace("{ed}", f" {edition}")
                    else:
                        reporter = template.replace("{ed}", "")
                else:
                    volume, page = m.group(1), m.group(2)
                    reporter = template

                # Clean up double spaces
                reporter = reporter.strip()

                sources = [Source("courtlistener",
                                  courtlistener_url(reporter, volume, page))]

                jur = "nd" if reporter in ("N.D.",) else "us"

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

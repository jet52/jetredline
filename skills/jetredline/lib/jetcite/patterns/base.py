"""Base matcher class and regex helpers."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from jetcite.models import Citation


class BaseMatcher(ABC):
    """Base class for citation pattern matchers."""

    @abstractmethod
    def find_all(self, text: str) -> list[Citation]:
        """Find all matching citations in text."""
        ...

    def find_first(self, text: str) -> Citation | None:
        """Find the first matching citation in text."""
        results = self.find_all(text)
        return results[0] if results else None


def optional_periods(abbrev: str) -> str:
    """Build a regex that matches an abbreviation with or without periods.

    Example: optional_periods("N.W.2d") matches "N.W.2d", "NW2d", "N.W. 2d"
    """
    parts = []
    i = 0
    while i < len(abbrev):
        ch = abbrev[i]
        if ch == ".":
            parts.append(r"\.?\s?")
            i += 1
        elif ch == " ":
            parts.append(r"\s+")
            i += 1
        else:
            parts.append(re.escape(ch))
            i += 1
    return "".join(parts)


def roman_to_int(roman: str) -> int:
    """Convert a Roman numeral string to an integer."""
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    result = 0
    roman = roman.upper()
    for i, ch in enumerate(roman):
        val = values.get(ch, 0)
        if i + 1 < len(roman) and val < values.get(roman[i + 1], 0):
            result -= val
        else:
            result += val
    return result


# Common pinpoint pattern: ", 128" or ", at 128" or ", ¶ 12" or ", ¶¶ 12-15"
PINPOINT_PATTERN = (
    r"(?:"
    r",?\s*(?:at\s+)?"
    r"(?:¶¶?\s*\d+(?:\s*[-–]\s*\d+)?|\d+(?:\s*[-–]\s*\d+)?)"
    r")?"
)

# Section symbol variants
SECTION_SYM = r"(?:§§?\s*|[Ss]ection\s+|[Ss]ec\.\s+)?"

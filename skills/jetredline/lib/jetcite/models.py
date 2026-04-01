"""Data model for parsed citations and URL sources."""

from dataclasses import dataclass, field
from enum import Enum


class CitationType(Enum):
    CASE = "case"
    STATUTE = "statute"
    CONSTITUTION = "constitution"
    COURT_RULE = "court_rule"
    REGULATION = "regulation"


@dataclass
class Source:
    name: str
    url: str
    verified: bool | None = None
    anchor: str | None = None


@dataclass
class Citation:
    raw_text: str
    cite_type: CitationType
    jurisdiction: str
    normalized: str
    components: dict = field(default_factory=dict)
    pinpoint: str | None = None
    sources: list[Source] = field(default_factory=list)
    position: int = 0  # character offset in source text
    parallel_cites: list[str] = field(default_factory=list)  # normalized forms of parallel citations

    def to_dict(self) -> dict:
        """Convert to a plain dictionary suitable for JSON serialization."""
        d: dict = {
            "raw_text": self.raw_text,
            "cite_type": self.cite_type.value,
            "jurisdiction": self.jurisdiction,
            "normalized": self.normalized,
        }
        if self.pinpoint:
            d["pinpoint"] = self.pinpoint
        if self.parallel_cites:
            d["parallel_cites"] = self.parallel_cites
        d["sources"] = [
            {"name": s.name, "url": s.url}
            | ({"verified": s.verified} if s.verified is not None else {})
            for s in self.sources
        ]
        return d

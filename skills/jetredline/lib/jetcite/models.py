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
    antecedent_name: str | None = None  # best-effort case name governing the cite (heuristic; may be None)
    is_pin_cite: bool = False  # short-form back-reference ("491 F.3d at 363", "Id. ¶ 14")
    is_repeat: bool = False  # full-form case cite whose normalized form appeared earlier in the document
    parent_normalized: str | None = None  # normalized form of the resolved parent full cite; None = unresolved
    pin_page: str | None = None  # page pinpoint of a pin cite ("363" or "363-65")
    pin_paragraph: str | None = None  # paragraph pinpoint of a pin cite ("12" or "12-15")

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
        if self.antecedent_name:
            d["antecedent_name"] = self.antecedent_name
        if self.is_repeat:
            d["is_repeat"] = True
            d["parent_normalized"] = self.parent_normalized
        if self.is_pin_cite:
            d["is_pin_cite"] = True
            d["parent_normalized"] = self.parent_normalized
            if self.pin_page:
                d["pin_page"] = self.pin_page
            if self.pin_paragraph:
                d["pin_paragraph"] = self.pin_paragraph
        d["sources"] = [
            {"name": s.name, "url": s.url}
            | ({"verified": s.verified} if s.verified is not None else {})
            for s in self.sources
        ]
        return d

"""Federal procedural rule citation patterns."""

import re

from jetcite.models import Citation, CitationType, Source
from jetcite.patterns import register
from jetcite.patterns.base import BaseMatcher
from jetcite.sources.cornell import federal_rule_url

# Maps regex group matches to (rule_set_key, display_name)
_RULE_SETS = {
    "Civ": ("frcp", "Fed. R. Civ. P."),
    "Crim": ("frcrp", "Fed. R. Crim. P."),
    "Evid": ("fre", "Fed. R. Evid."),
    "App": ("frap", "Fed. R. App. P."),
    "Bankr": ("frbp", "Fed. R. Bankr. P."),
}

# Fed. R. Civ. P. 12(b)(6)
_FED_RULE = re.compile(
    r'Fed[\s.]*R[\s.]*'
    r'(Civ|Crim|Evid|App|Bankr)(?:il|inal|ence|ellate|ruptcy)?[\s.]*'
    r'(?:P(?:roc)?[\s.]*)?'
    r'(\d+)'
    r'((?:\([^)]+\))*)',  # optional subsection like (b)(6)
    re.IGNORECASE,
)

# Abbreviation forms: FRCP 12(b)(6), FRE 403
_FED_RULE_ABBREV = re.compile(
    r'(FRCP|FRCrP|FRE|FRAP|FRBP)\s+'
    r'(\d+)'
    r'((?:\([^)]+\))*)',
)

_ABBREV_MAP = {
    "FRCP": ("frcp", "Fed. R. Civ. P."),
    "FRCrP": ("frcrp", "Fed. R. Crim. P."),
    "FRE": ("fre", "Fed. R. Evid."),
    "FRAP": ("frap", "Fed. R. App. P."),
    "FRBP": ("frbp", "Fed. R. Bankr. P."),
}


class FederalRuleMatcher(BaseMatcher):
    def find_all(self, text: str) -> list[Citation]:
        results = []

        for m in _FED_RULE.finditer(text):
            rule_type = m.group(1)
            # Normalize the rule type key
            key = rule_type.capitalize()
            if key.startswith("Evid"):
                key = "Evid"
            elif key.startswith("Bankr"):
                key = "Bankr"
            rule_set, display = _RULE_SETS.get(key, ("frcp", "Fed. R. Civ. P."))
            rule_num = m.group(2)
            subsection = m.group(3) or ""
            normalized = f"{display} {rule_num}{subsection}"
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.COURT_RULE,
                jurisdiction="us",
                normalized=normalized,
                components={"rule_set": rule_set, "rule_number": rule_num,
                            "subsection": subsection or None},
                sources=[Source("cornell", federal_rule_url(rule_set, rule_num))],
                position=m.start(),
            ))

        for m in _FED_RULE_ABBREV.finditer(text):
            abbrev = m.group(1)
            rule_set, display = _ABBREV_MAP.get(abbrev, ("frcp", "Fed. R. Civ. P."))
            rule_num = m.group(2)
            subsection = m.group(3) or ""
            normalized = f"{display} {rule_num}{subsection}"
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.COURT_RULE,
                jurisdiction="us",
                normalized=normalized,
                components={"rule_set": rule_set, "rule_number": rule_num,
                            "subsection": subsection or None},
                sources=[Source("cornell", federal_rule_url(rule_set, rule_num))],
                position=m.start(),
            ))

        return results


register(3, FederalRuleMatcher())

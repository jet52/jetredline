"""Cornell LII URL generation for federal rules."""

# Rule set abbreviation -> LII URL path segment
_RULE_PATHS = {
    "frcp": "frcivp",
    "frcrp": "frcrmp",
    "fre": "fre",
    "frap": "frap",
    "frbp": "frbkp",
}


def federal_rule_url(rule_set: str, rule_number: str) -> str:
    """Generate a Cornell LII URL for a federal rule."""
    path = _RULE_PATHS.get(rule_set.lower(), rule_set.lower())
    return f"https://www.law.cornell.edu/rules/{path}/rule_{rule_number}"

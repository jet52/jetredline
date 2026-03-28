"""eCFR URL generation for Code of Federal Regulations citations."""


def cfr_url(title: str, section: str) -> str:
    """Generate an eCFR URL for a C.F.R. section."""
    return f"https://www.ecfr.gov/current/title-{title}/section-{section}"

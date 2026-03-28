"""GovInfo URL generation for U.S. Code citations."""


def usc_url(title: str, section: str) -> str:
    """Generate a govinfo.gov URL for a U.S. Code section."""
    return f"https://www.govinfo.gov/link/uscode/{title}/{section}?link-type=html"

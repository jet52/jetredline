"""ndconst.org URL generation for ND Constitution citations."""

from jetcite.patterns.base import roman_to_int

# Roman numeral strings for articles I-XIII
_ROMAN = {
    1: "i", 2: "ii", 3: "iii", 4: "iv", 5: "v", 6: "vi", 7: "vii",
    8: "viii", 9: "ix", 10: "x", 11: "xi", 12: "xii", 13: "xiii",
    14: "xiv", 15: "xv", 16: "xvi", 17: "xvii", 18: "xviii",
}


def nd_constitution_url(article_roman: str, section: str) -> str:
    """Generate an ndconst.org URL for a ND Constitution section."""
    art_num = roman_to_int(article_roman)
    art_lower = _ROMAN.get(art_num, article_roman.lower())
    return f"https://ndconst.org/art{art_lower}/sec{section}/"

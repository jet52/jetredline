"""Constitution Center URL generation for U.S. Constitution citations."""

from jetcite.patterns.base import roman_to_int

# Roman numeral to Arabic for amendment URLs
_AMENDMENT_NAMES = {
    1: "amendment-i", 2: "amendment-ii", 3: "amendment-iii",
    4: "amendment-iv", 5: "amendment-v", 6: "amendment-vi",
    7: "amendment-vii", 8: "amendment-viii", 9: "amendment-ix",
    10: "amendment-x", 11: "amendment-xi", 12: "amendment-xii",
    13: "amendment-xiii", 14: "amendment-xiv", 15: "amendment-xv",
    16: "amendment-xvi", 17: "amendment-xvii", 18: "amendment-xviii",
    19: "amendment-xix", 20: "amendment-xx", 21: "amendment-xxi",
    22: "amendment-xxii", 23: "amendment-xxiii", 24: "amendment-xxiv",
    25: "amendment-xxv", 26: "amendment-xxvi", 27: "amendment-xxvii",
}


def us_constitution_article_url(article_roman: str, section: str | None = None) -> str:
    """Generate a Constitution Center URL for a U.S. Constitution article."""
    art_num = roman_to_int(article_roman)
    base = f"https://constitutioncenter.org/the-constitution/articles/article-{art_num}"
    if section:
        return f"{base}#article-section-{section}"
    return base


def us_constitution_amendment_url(amendment_roman: str) -> str:
    """Generate a Constitution Center URL for a U.S. Constitution amendment."""
    num = roman_to_int(amendment_roman)
    name = _AMENDMENT_NAMES.get(num, f"amendment-{num}")
    return f"https://constitutioncenter.org/the-constitution/amendments/{name}"

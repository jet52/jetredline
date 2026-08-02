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


# 1889 -> 1981 renumbering crosswalk: old continuous section number ->
# (modern article roman, modern section). The 180 clean one-to-one rows from
# the NDCC Replacement Vol. 13 (1981) disposition tables; old sections that
# were repealed, superseded, or carried into the appendix (e.g. § 25) have no
# modern location and are omitted — cites to them get no source URL. The
# mapping is permanent: the 1981 reorganization is historical fact.
_OLD_TO_NEW = {
    1: ("I", "1"), 2: ("I", "2"), 3: ("I", "23"), 4: ("I", "3"),
    5: ("I", "14"), 6: ("I", "11"), 7: ("I", "13"), 8: ("I", "10"),
    9: ("I", "4"), 10: ("I", "5"), 11: ("I", "22"), 12: ("I", "19"),
    13: ("I", "12"), 14: ("I", "16"), 15: ("I", "15"), 16: ("I", "18"),
    17: ("I", "6"), 18: ("I", "8"), 19: ("I", "17"), 20: ("I", "21"),
    21: ("I", "24"), 22: ("I", "9"), 23: ("I", "7"), 24: ("I", "20"),
    26: ("IV", "2"), 27: ("IV", "3"), 28: ("IV", "4"), 29: ("IV", "5"),
    30: ("IV", "6"), 31: ("IV", "7"), 32: ("IV", "8"), 33: ("IV", "9"),
    34: ("IV", "10"), 35: ("IV", "11"), 36: ("IV", "12"), 37: ("IV", "13"),
    38: ("IV", "15"), 39: ("IV", "17"), 40: ("IV", "14"), 41: ("IV", "16"),
    42: ("IV", "20"), 43: ("IV", "21"), 44: ("IV", "19"), 45: ("IV", "46"),
    46: ("IV", "25"), 47: ("IV", "26"), 48: ("IV", "27"), 49: ("IV", "29"),
    50: ("IV", "28"), 51: ("IV", "24"), 52: ("IV", "1"), 53: ("IV", "22"),
    54: ("IV", "30"), 56: ("IV", "23"), 57: ("IV", "31"), 58: ("IV", "32"),
    59: ("IV", "34"), 60: ("IV", "35"), 61: ("IV", "33"), 62: ("IV", "36"),
    63: ("IV", "37"), 64: ("IV", "38"), 65: ("IV", "39"), 66: ("IV", "40"),
    67: ("IV", "41"), 68: ("IV", "42"), 69: ("IV", "43"), 70: ("IV", "44"),
    71: ("V", "1"), 72: ("V", "2"), 73: ("V", "3"), 74: ("V", "4"),
    75: ("V", "5"), 76: ("V", "6"), 77: ("V", "7"), 78: ("V", "8"),
    79: ("V", "9"), 80: ("V", "10"), 81: ("V", "11"), 82: ("V", "12"),
    83: ("V", "13"), 84: ("V", "14"), 85: ("VI", "1"), 86: ("VI", "2"),
    87: ("VI", "3"), 88: ("VI", "4"), 89: ("VI", "5"), 90: ("VI", "6"),
    91: ("VI", "7"), 92: ("VI", "8"), 93: ("VI", "9"), 94: ("VI", "10"),
    95: ("VI", "11"), 96: ("VI", "12"), 97: ("VI", "13"), 121: ("II", "1"),
    122: ("II", "2"), 130: ("VII", "1"), 131: ("XII", "2"), 132: ("XII", "3"),
    133: ("XII", "4"), 134: ("XII", "5"), 135: ("XII", "6"), 136: ("XII", "7"),
    137: ("XII", "8"), 138: ("XII", "9"), 139: ("XII", "10"), 140: ("XII", "11"),
    141: ("XII", "12"), 142: ("XII", "13"), 143: ("XII", "14"), 144: ("XII", "1"),
    145: ("XII", "15"), 146: ("XII", "16"), 147: ("VIII", "1"), 148: ("VIII", "2"),
    149: ("VIII", "3"), 150: ("VII", "9"), 151: ("VIII", "4"), 152: ("VIII", "5"),
    153: ("IX", "1"), 154: ("IX", "2"), 155: ("IX", "5"), 156: ("IX", "3"),
    157: ("IX", "4"), 158: ("IX", "6"), 160: ("IX", "7"), 161: ("IX", "8"),
    163: ("IX", "9"), 164: ("IX", "10"), 165: ("IX", "11"), 166: ("VII", "2"),
    167: ("VII", "3"), 168: ("VII", "4"), 169: ("VII", "5"), 170: ("VII", "6"),
    172: ("VII", "7"), 173: ("VII", "8"), 174: ("X", "1"), 175: ("X", "3"),
    176: ("X", "5"), 177: ("X", "7"), 178: ("X", "2"), 179: ("X", "4"),
    180: ("X", "6"), 181: ("X", "8"), 182: ("X", "13"), 183: ("X", "15"),
    184: ("X", "16"), 185: ("X", "18"), 186: ("X", "12"), 187: ("X", "17"),
    188: ("XI", "16"), 189: ("XI", "17"), 190: ("XI", "18"), 191: ("XI", "19"),
    192: ("XI", "20"), 193: ("XI", "21"), 194: ("XI", "8"), 195: ("XI", "9"),
    196: ("XI", "10"), 197: ("XI", "11"), 198: ("XI", "12"), 199: ("XI", "13"),
    200: ("XI", "14"), 201: ("XI", "15"), 202: ("IV", "45"), 203: ("XIII", "1"),
    204: ("XIII", "2"), 205: ("XIII", "3"), 206: ("XI", "1"), 207: ("XI", "2"),
    208: ("XI", "22"), 209: ("XI", "24"), 210: ("XI", "3"), 211: ("XI", "4"),
    212: ("XII", "17"), 213: ("XI", "23"), 215: ("IX", "12"), 216: ("IX", "13"),
}

# Highest section number in the original 1889 constitution (including the
# Schedule); anything larger is not an old-numbering cite.
OLD_SECTION_MAX = 217


def nd_constitution_old_url(section: str) -> str | None:
    """ndconst.org URL for a pre-1981 (1889 numbering) section, via the
    renumbering crosswalk; None when the old section has no modern location."""
    target = _OLD_TO_NEW.get(int(section))
    if target is None:
        return None
    return nd_constitution_url(*target)

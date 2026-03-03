#!/usr/bin/env python3
"""
Citation Checker — parses legal citations (ND, federal, state), resolves
local files, and builds verification URLs.

Usage:
    python3 nd_cite_check.py --file opinion.md
    echo "N.D.C.C. § 12.1-32-01" | python3 nd_cite_check.py
    echo "42 U.S.C. § 1983" | python3 nd_cite_check.py

Output: JSON array of citation records with local paths and URLs.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Roman numeral helpers
# ---------------------------------------------------------------------------

_ROMAN_MAP = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7,
    "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12, "XIII": 13,
    "XIV": 14, "XV": 15, "XVI": 16, "XVII": 17, "XVIII": 18, "XIX": 19,
    "XX": 20, "XXI": 21, "XXII": 22, "XXIII": 23, "XXIV": 24, "XXV": 25,
    "XXVI": 26, "XXVII": 27,
}


def roman_to_arabic(roman: str) -> int:
    return _ROMAN_MAP.get(roman.upper(), 0)


# ---------------------------------------------------------------------------
# URL builders (ported from cite2url URLBuilder.swift)
# ---------------------------------------------------------------------------

def url_ndcc_section(title, title_dec, chapter, chapter_dec, section, section_dec):
    title_num = int(title) if title.isdigit() else 0
    chapter_num = int(chapter) if chapter.isdigit() else 0
    section_num = int(section) if section.isdigit() else 0
    if not (1 <= title_num <= 99 and 1 <= chapter_num <= 99 and 1 <= section_num <= 999):
        return None

    if title_dec:
        title_file = f"{title}-{title_dec}"
        title_dest = f"{title}p{title_dec}"
    else:
        title_file = f"{title_num:02d}"
        title_dest = title

    if chapter_dec:
        chapter_file = f"{chapter}-{chapter_dec}"
        chapter_dest = f"{chapter}p{chapter_dec}"
    else:
        chapter_file = f"{chapter_num:02d}"
        chapter_dest = chapter

    section_dest = f"{section}p{section_dec}" if section_dec else section

    url = (f"https://ndlegis.gov/cencode/t{title_file}c{chapter_file}"
           f".pdf#nameddest={title_dest}-{chapter_dest}-{section_dest}")

    if "t--" in url or "c--" in url or "pp" in url:
        return None
    return url


def url_ndcc_chapter(title, title_dec, chapter, chapter_dec):
    title_num = int(title) if title.isdigit() else 0
    chapter_num = int(chapter) if chapter.isdigit() else 0
    if not (1 <= title_num <= 99 and 1 <= chapter_num <= 99):
        return None

    title_file = f"{title}-{title_dec}" if title_dec else f"{title_num:02d}"
    chapter_file = f"{chapter}-{chapter_dec}" if chapter_dec else f"{chapter_num:02d}"

    url = f"https://ndlegis.gov/cencode/t{title_file}c{chapter_file}.pdf"
    if "t--" in url or "c--" in url or "pp" in url:
        return None
    return url


def url_nd_constitution(article_roman, section):
    return f"https://ndconst.org/art{article_roman.lower()}/sec{section}/"


def url_nd_court_rule(rule_set, parts):
    return f"https://www.ndcourts.gov/legal-resources/rules/{rule_set}/{'-'.join(parts)}"


def url_nd_local_rule(rule):
    return f"https://www.ndcourts.gov/legal-resources/rules/local/search?rule={rule}"


def url_ndac(p1, p2, p3):
    return f"https://ndlegis.gov/information/acdata/pdf/{p1}-{p2}-{p3}.pdf"


def url_nd_case(year, number):
    return f"https://www.ndcourts.gov/supreme-court/opinion/{year}ND{number}"


def url_us_const_article(article_roman, section=None):
    url = f"https://constitutioncenter.org/the-constitution/articles/article-{article_roman}"
    if section:
        url += f"#article-section-{section}"
    return url


def url_us_const_amendment(amendment_roman):
    return f"https://constitutioncenter.org/the-constitution/amendments/amendment-{amendment_roman}"


def url_usc(title, section):
    return f"https://www.govinfo.gov/link/uscode/{title}/{section}?link-type=html"


def url_cfr(title, section):
    return f"https://www.ecfr.gov/current/title-{title}/section-{section}"


def url_us_supreme_court(volume, page):
    return f"https://supreme.justia.com/cases/federal/us/{volume}/{page}"


def url_court_listener(reporter, volume, page):
    from urllib.parse import quote
    encoded = quote(reporter, safe="")
    return f"https://www.courtlistener.com/c/{encoded}/{volume}/{page}/"


# ---------------------------------------------------------------------------
# Local resolver
# ---------------------------------------------------------------------------

def resolve_local(cite_type, parts, refs_dir):
    """Return (local_path, local_exists) for a citation."""
    refs = Path(refs_dir).expanduser()

    if cite_type == "nd_case":
        year, number = parts["year"], parts["number"]
        p = refs / "opin" / "markdown" / year / f"{year}ND{number}.md"
        return str(p), p.exists()

    if cite_type == "ndcc":
        title_str = parts.get("title_full", parts["title"])
        chapter_str = parts.get("chapter_full", parts["chapter"])
        p = refs / "ndcc" / f"title-{title_str}" / f"chapter-{title_str}-{chapter_str}.md"
        return str(p), p.exists()

    if cite_type == "ndcc_chapter":
        title_str = parts.get("title_full", parts["title"])
        chapter_str = parts.get("chapter_full", parts["chapter"])
        p = refs / "ndcc" / f"title-{title_str}" / f"chapter-{title_str}-{chapter_str}.md"
        return str(p), p.exists()

    if cite_type == "nd_const":
        article_roman = parts["article"]
        article_num = roman_to_arabic(article_roman)
        section = parts["section"]
        p = refs / "cnst" / f"art-{article_num:02d}" / f"sec-{section}.md"
        return str(p), p.exists()

    if cite_type == "ndac":
        p1 = parts["p1"]
        p2 = parts["p2"]
        p3 = parts["p3"]
        # NDAC structure: title-{p1}/article-{p1}-{p2}/chapter-{p1}-{p2}-{p3}.md
        p = refs / "ndac" / f"title-{p1}" / f"article-{p1}-{p2}" / f"chapter-{p1}-{p2}-{p3}.md"
        if p.exists():
            return str(p), True
        # Fallback: flat article file
        p2_flat = refs / "ndac" / f"title-{p1}" / f"article-{p1}-{p2}.md"
        if p2_flat.exists():
            return str(p2_flat), True
        return str(p), False

    if cite_type == "nd_court_rule":
        rule_set = parts.get("rule_set", "")
        rule_parts = parts.get("parts", [])
        if rule_set and rule_parts:
            if rule_set == "ndstdsimposinglawyersanctions":
                filename = f"rule-{'-'.join(rule_parts)}.md"
            elif rule_set == "ndcodejudconduct":
                # parts already include "canon-" prefix
                filename = f"rule-{rule_parts[0]}.md"
            elif rule_set == "rltdpracticeoflawbylawstudents":
                # Roman → Arabic conversion for student practice rules
                arabic = roman_to_arabic(rule_parts[0])
                filename = f"rule-{arabic}.md" if arabic else f"rule-{rule_parts[0]}.md"
            else:
                filename = f"rule-{'.'.join(rule_parts)}.md"
            p = refs / "rule" / rule_set / filename
            return str(p), p.exists()
        return None, False

    # Non-local types
    return None, False


# ---------------------------------------------------------------------------
# Citation matchers
# ---------------------------------------------------------------------------

def match_ndcc(text):
    """Match NDCC section citations like 'N.D.C.C. § 12.1-32-01'."""
    pattern = (
        r'(?:(?:N[\s.]*D[\s.]*C(?:ent)*[.\s]*C(?:ode)*[,.\s]{0,3}'
        r'(?:[^\s\d]{0,3}|[Ss]ection|[Ss]ec)\s{0,4})'
        r'|(?:(?:[Ss]ection|[Ss]ec\.?)\s+))'
        r'(\d{1,2})(?:\.(\d+))?'
        r'[^.\w]{1,2}(\d{1,2})(?:\.(\d+))?'
        r'[^.\w](\d{1,2})(?:\.(\d+))?'
        r'(?:\([^)]+\))?'
        r'(?:[,\s]*(?:of\s+the\s+)?'
        r'(?:North\s+Dakota\s+Century\s+Code|N[\s.]*D[\s.]*C(?:ent)*[.\s]*C(?:ode)*)|\W|$)'
    )
    m = re.search(pattern, text, re.IGNORECASE)
    if not m:
        return None

    title = m.group(1)
    title_dec = m.group(2) or None
    chapter = m.group(3)
    chapter_dec = m.group(4) or None
    section = m.group(5)
    section_dec = m.group(6) or None

    title_full = f"{title}.{title_dec}" if title_dec else title
    chapter_full = f"{chapter}.{chapter_dec}" if chapter_dec else chapter
    section_full = f"{section}.{section_dec}" if section_dec else section

    url = url_ndcc_section(title, title_dec, chapter, chapter_dec, section, section_dec)
    if not url:
        return None

    normalized = f"N.D.C.C. \u00a7 {title_full}-{chapter_full}-{section_full}"
    return {
        "cite_text": m.group(0).strip(),
        "cite_type": "ndcc",
        "normalized": normalized,
        "parts": {
            "title": title, "title_dec": title_dec, "title_full": title_full,
            "chapter": chapter, "chapter_dec": chapter_dec, "chapter_full": chapter_full,
            "section": section, "section_dec": section_dec, "section_full": section_full,
        },
        "url": url,
        "search_hint": f"{title_full}-{chapter_full}-{section_full}",
    }


def match_ndcc_chapter(text):
    """Match NDCC chapter citations like 'N.D.C.C. ch. 32-12'."""
    pattern = (
        r'(?:(?:N[\s.]*D[\s.]*C(?:ent)*[.\s]*C(?:ode)*[,.\s]{0,3}'
        r'(?:ch\.|ch|chapter)\s+)'
        r'|(?:(?<!C\.\s)(?:[Cc]hapter|[Cc]h\.?)\s+))'
        r'(\d{1,2})(?:\.(\d+))?'
        r'[^.\w]{1,2}(\d{1,2})(?:\.(\d+))?'
    )
    m = re.search(pattern, text, re.IGNORECASE)
    if not m:
        return None

    title = m.group(1)
    title_dec = m.group(2) or None
    chapter = m.group(3)
    chapter_dec = m.group(4) or None

    title_full = f"{title}.{title_dec}" if title_dec else title
    chapter_full = f"{chapter}.{chapter_dec}" if chapter_dec else chapter

    url = url_ndcc_chapter(title, title_dec, chapter, chapter_dec)
    if not url:
        return None

    normalized = f"N.D.C.C. ch. {title_full}-{chapter_full}"
    return {
        "cite_text": m.group(0).strip(),
        "cite_type": "ndcc_chapter",
        "normalized": normalized,
        "parts": {
            "title": title, "title_dec": title_dec, "title_full": title_full,
            "chapter": chapter, "chapter_dec": chapter_dec, "chapter_full": chapter_full,
        },
        "url": url,
        "search_hint": f"{title_full}-{chapter_full}",
    }


def match_us_constitution(text):
    """Match US Constitution citations."""
    # "U.S. Const. art. III, § 2"
    m = re.search(
        r'U(?:nited)?[\s.]*S(?:tates)?[\s.]*Const(?:itution)?[.\s]*'
        r'(?:art\.|[Aa]rticle)\s*([IVX]+)[,\s]*(?:\u00a7|§|[Ss]ec(?:tion)?\.?)\s*(\d+)',
        text, re.IGNORECASE
    )
    if m:
        art, sec = m.group(1).upper(), m.group(2)
        return {
            "cite_text": m.group(0).strip(),
            "cite_type": "us_const_article",
            "normalized": f"U.S. Const. art. {art}, \u00a7 {sec}",
            "parts": {"article": art, "section": sec},
            "url": url_us_const_article(art, sec),
            "search_hint": f"article {art} section {sec}",
        }

    # "Article III of the U.S. Constitution"
    m = re.search(
        r'[Aa]rticle\s+([IVX]+)\s+of\s+the\s+'
        r'U(?:nited)?[\s.]*S(?:tates)?[\s.]*Const(?:itution)?',
        text, re.IGNORECASE
    )
    if m:
        art = m.group(1).upper()
        return {
            "cite_text": m.group(0).strip(),
            "cite_type": "us_const_article",
            "normalized": f"U.S. Const. art. {art}",
            "parts": {"article": art},
            "url": url_us_const_article(art),
            "search_hint": f"article {art}",
        }

    # "U.S. Const. amend. XIV"
    m = re.search(
        r'U(?:nited)?[\s.]*S(?:tates)?[\s.]*Const(?:itution)?[.\s]*'
        r'(?:amend\.|[Aa]mendment)\s*([IVX]+)',
        text, re.IGNORECASE
    )
    if m:
        amend = m.group(1).upper()
        return {
            "cite_text": m.group(0).strip(),
            "cite_type": "us_const_amendment",
            "normalized": f"U.S. Const. amend. {amend}",
            "parts": {"amendment": amend},
            "url": url_us_const_amendment(amend),
            "search_hint": f"amendment {amend}",
        }

    # "Amendment XIV to the U.S. Constitution"
    m = re.search(
        r'[Aa]mendment\s+([IVX]+)\s+to\s+the\s+'
        r'U(?:nited)?[\s.]*S(?:tates)?[\s.]*Const(?:itution)?',
        text, re.IGNORECASE
    )
    if m:
        amend = m.group(1).upper()
        return {
            "cite_text": m.group(0).strip(),
            "cite_type": "us_const_amendment",
            "normalized": f"U.S. Const. amend. {amend}",
            "parts": {"amendment": amend},
            "url": url_us_const_amendment(amend),
            "search_hint": f"amendment {amend}",
        }

    return None


def match_nd_constitution(text):
    """Match ND Constitution citations."""
    # Pattern 1: "Article VI, section 2 of the N.D. Constitution"
    m = re.search(
        r'(?:Article|Art\.?)\s+([IVX]+)[,\s]+(?:section|sec\.?)\s+(\d+)'
        r'(?:(?:\([a-z\d]*\))*|\D)\s+of\s+the\s+'
        r'N(?:orth)?\s*D(?:akota)?\s*Const(?:itution)?',
        text, re.IGNORECASE
    )
    if m:
        article, section = m.group(1).upper(), m.group(2)
        return _nd_const_result(m.group(0), article, section)

    # Pattern 2: "N.D. Const. art. I, § 20"
    m = re.search(
        r'N(?:orth)?[\s.]*D(?:akota)?[\s.]*Const(?:itution)?[.\s]*'
        r'(?:art\.|[Aa]rticle)\s*([IVX]+)[,\s]*(?:\u00a7|§|[Ss]ec(?:tion)?\.?)\s*(\d+)',
        text, re.IGNORECASE
    )
    if m:
        article, section = m.group(1).upper(), m.group(2)
        return _nd_const_result(m.group(0), article, section)

    return None


def _nd_const_result(cite_text, article, section):
    return {
        "cite_text": cite_text.strip(),
        "cite_type": "nd_const",
        "normalized": f"N.D. Const. art. {article}, \u00a7 {section}",
        "parts": {"article": article, "section": section},
        "url": url_nd_constitution(article, section),
        "search_hint": f"art {article} sec {section}",
    }


# --- Court Rules ---

_RULE_TYPES = {
    "civil": "civ", "civ": "civ",
    "criminal": "crim", "crim": "crim",
    "appellate": "app", "app": "app",
    "juvenile": "juv", "juv": "juv",
}


def match_nd_court_rules(text):
    """Match all ND court rule patterns."""
    # Order matters — try more specific patterns first

    # N.D.R.Ct. 3-part decimal
    m = re.search(
        r'(?:Rule\s+)?(\d{1,2})\.(\d{1,2})\.(\d{1,2})'
        r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*N[\s.]*D[\s.]*R[\s.]*Ct[\s.]*'
        r'|N[\s.]*D[\s.]*R[\s.]*Ct[.\s]*(?:Rule\s+)?(\d{1,2})\.(\d{1,2})\.(\d{1,2})',
        text, re.IGNORECASE
    )
    if m:
        p1 = m.group(1) or m.group(4)
        p2 = m.group(2) or m.group(5)
        p3 = m.group(3) or m.group(6)
        if p1:
            return _court_rule_result(m.group(0), "ndrct",
                                      [p1, p2, p3], f"N.D.R.Ct. {p1}.{p2}.{p3}")

    # N.D.R.Ct. 2-part decimal
    m = re.search(
        r'(?:Rule\s+)?(\d{1,2})\.(\d{1,2})'
        r'(?:(?:\([a-z\d]*\))*|[^.\d])[,\s]*N[\s.]*D[\s.]*R[\s.]*Ct[\s.]*'
        r'|N[\s.]*D[\s.]*R[\s.]*Ct[.\s]*(?:Rule\s+)?(\d{1,2})\.(\d{1,2})',
        text, re.IGNORECASE
    )
    if m:
        p1 = m.group(1) or m.group(3)
        p2 = m.group(2) or m.group(4)
        if p1:
            return _court_rule_result(m.group(0), "ndrct",
                                      [p1, p2], f"N.D.R.Ct. {p1}.{p2}")

    # N.D. Sup. Ct. Admin. R. decimal
    m = re.search(
        r'(?:Rule\s+)?(\d{1,2})\.(\d{1,2})'
        r'(?:(?:\([a-z\d]*\))*|[^.\d])[,\s]*'
        r'N[\s.]*D[\s.]*Sup[\s.]*Ct[\s.]*Admin[\s.]*R[\s.]*'
        r'|N[\s.]*D[\s.]*Sup[\s.]*Ct[\s.]*Admin[\s.]*R[.\s]*'
        r'(?:Rule\s+)?(\d{1,2})\.(\d{1,2})',
        text, re.IGNORECASE
    )
    if m:
        p1 = m.group(1) or m.group(3)
        p2 = m.group(2) or m.group(4)
        if p1:
            return _court_rule_result(m.group(0), "ndsupctadminr",
                                      [p1, p2], f"N.D. Sup. Ct. Admin. R. {p1}.{p2}")

    # N.D. Sup. Ct. Admin. R. simple
    m = re.search(
        r'(?:Rule\s+)?(\d{1,2})'
        r'(?:(?:\([a-z\d]*\))*|[^.\d])[,\s]*'
        r'N[\s.]*D[\s.]*Sup[\s.]*Ct[\s.]*Admin[\s.]*R[\s.]*'
        r'|N[\s.]*D[\s.]*Sup[\s.]*Ct[\s.]*Admin[\s.]*R[.\s]*'
        r'(?:Rule\s+)?(\d{1,2})(?:(?:\([a-z\d]*\))*|[^.\d])',
        text, re.IGNORECASE
    )
    if m:
        r = m.group(1) or m.group(2)
        if r:
            return _court_rule_result(m.group(0), "ndsupctadminr",
                                      [r], f"N.D. Sup. Ct. Admin. R. {r}")

    # N.D.R.Ev. (Evidence)
    m = re.search(
        r'(?:Rule\s+)?(\d{3,4})'
        r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
        r'N[\s.]*D[\s.]*R[\s.]*Ev(?:id|idence)?[\s.]*'
        r'|N[\s.]*D[\s.]*R[\s.]*Ev(?:id|idence)?[.\s]*'
        r'(?:Rule\s+)?(\d{3,4})',
        text, re.IGNORECASE
    )
    if m:
        r = m.group(1) or m.group(2)
        if r:
            return _court_rule_result(m.group(0), "ndrev",
                                      [r], f"N.D.R.Ev. {r}")

    # N.D.R. Prof. Conduct
    m = re.search(
        r'(?:Rule\s+)?(\d)\.(\d+)'
        r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
        r'N[\s.]*D[\s.]*R[\s.]*Prof(?:essional)?[\s.]*Conduct[\s.]*'
        r'|N[\s.]*D[\s.]*R[\s.]*Prof(?:essional)?[\s.]*Conduct[.\s]*'
        r'(?:Rule\s+)?(\d)\.(\d+)',
        text, re.IGNORECASE
    )
    if m:
        p1 = m.group(1) or m.group(3)
        p2 = m.group(2) or m.group(4)
        if p1:
            return _court_rule_result(m.group(0), "ndrprofconduct",
                                      [p1, p2], f"N.D.R. Prof. Conduct {p1}.{p2}")

    # N.D.R. Lawyer Discipline
    m = re.search(
        r'(?:Rule\s+)?(\d)\.(\d+)'
        r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
        r'N[\s.]*D[\s.]*R[\s.]*Lawyer[\s.]*Discipl(?:ine)?[\s.]*'
        r'|N[\s.]*D[\s.]*R[\s.]*Lawyer[\s.]*Discipl(?:ine)?[.\s]*'
        r'(?:Rule\s+)?(\d)\.(\d+)',
        text, re.IGNORECASE
    )
    if m:
        p1 = m.group(1) or m.group(3)
        p2 = m.group(2) or m.group(4)
        if p1:
            return _court_rule_result(m.group(0), "ndrlawyerdiscipl",
                                      [p1, p2], f"N.D.R. Lawyer Discipl. {p1}.{p2}")

    # N.D. Code Jud. Conduct — Canon:Rule format
    m = re.search(
        r'Canon\s+(\d)\s*:\s*Rule\s+(\d)\.(\d+)'
        r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
        r'N[\s.]*D[\s.]*Code[\s.]*Jud(?:icial)?[\s.]*Conduct[\s.]*'
        r'|N[\s.]*D[\s.]*Code[\s.]*Jud(?:icial)?[\s.]*Conduct[.\s]*'
        r'Canon\s+(\d)\s*:\s*Rule\s+(\d)\.(\d+)',
        text, re.IGNORECASE
    )
    if m:
        canon = m.group(1) or m.group(4)
        if canon:
            return _court_rule_result(m.group(0), "ndcodejudconduct",
                                      [f"canon-{canon}"],
                                      f"N.D. Code Jud. Conduct Canon {canon}")

    # N.D. Code Jud. Conduct — Rule-only format
    m = re.search(
        r'(?:Rule\s+)?(\d)\.(\d+)'
        r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
        r'N[\s.]*D[\s.]*Code[\s.]*Jud(?:icial)?[\s.]*Conduct[\s.]*'
        r'|N[\s.]*D[\s.]*Code[\s.]*Jud(?:icial)?[\s.]*Conduct[.\s]*'
        r'(?:Rule\s+)?(\d)\.(\d+)',
        text, re.IGNORECASE
    )
    if m:
        canon = m.group(1) or m.group(3)
        if canon:
            return _court_rule_result(m.group(0), "ndcodejudconduct",
                                      [f"canon-{canon}"],
                                      f"N.D. Code Jud. Conduct Canon {canon}")

    # Juvenile Procedure — decimal
    m = re.search(
        r'(?:Rule\s+)?(\d{1,2})\.(\d+)'
        r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
        r'(?:North\s+Dakota\s+Rules\s+of\s+Juvenile\s+Procedure'
        r'|N[\s.]*D[\s.]*R[\s.]*Juv(?:enile)?[\s.]*P(?:rocedure)?[\s.]*)'
        r'|(?:North\s+Dakota\s+Rules\s+of\s+Juvenile\s+Procedure'
        r'|N[\s.]*D[\s.]*R[\s.]*Juv(?:enile)?[\s.]*P(?:rocedure)?[.\s]*)'
        r'(?:Rule\s+)?(\d{1,2})\.(\d+)',
        text, re.IGNORECASE
    )
    if m:
        p1 = m.group(1) or m.group(3)
        p2 = m.group(2) or m.group(4)
        if p1:
            return _court_rule_result(m.group(0), "ndrjuvp",
                                      [p1, p2], f"N.D.R. Juv. P. {p1}.{p2}")

    # Procedural rules — simple numbering (Civil, Criminal, Appellate, Juvenile)
    m = re.search(
        r'(?:Rule\s+)?(\d{1,2})'
        r'(?:(?:\([a-z\d]*\))*|[^.\d])[,\s]*'
        r'(?:North\s+Dakota\s+Rules\s+of\s+(Civil|Criminal|Appellate|Juvenile)\s+Procedure'
        r'|N[\s.]*D[\s.]*R[\s.]*(Civ|Crim|App|Juv)(?:il|inal|ellate|enile)?[\s.]*P(?:rocedure)?[\s.]*)'
        r'|(?:North\s+Dakota\s+Rules\s+of\s+(Civil|Criminal|Appellate|Juvenile)\s+Procedure'
        r'|N[\s.]*D[\s.]*R[\s.]*(Civ|Crim|App|Juv)(?:il|inal|ellate|enile)?[\s.]*P(?:rocedure)?[.\s]*)'
        r'(?:Rule\s+)?(\d{1,2})(?:(?:\([a-z\d]*\))*|[^.\d])',
        text, re.IGNORECASE
    )
    if m:
        rule_num = m.group(1) or m.group(6)
        raw_type = next((g for g in [m.group(2), m.group(3), m.group(4), m.group(5)] if g), None)
        if rule_num and raw_type:
            rt = _RULE_TYPES.get(raw_type.lower(), raw_type.lower())
            return _court_rule_result(m.group(0), f"ndr{rt}p",
                                      [rule_num], f"N.D.R.{rt.capitalize()}.P. {rule_num}")

    # N.D.R.App.P. — explicit abbreviation (catch common form not handled above)
    m = re.search(
        r'N[\s.]*D[\s.]*R[\s.]*App[\s.]*P[.\s]*(?:Rule\s+)?(\d{1,2})'
        r'|(?:Rule\s+)?(\d{1,2})[,\s]*N[\s.]*D[\s.]*R[\s.]*App[\s.]*P[\s.]*',
        text, re.IGNORECASE
    )
    if m:
        r = m.group(1) or m.group(2)
        if r:
            return _court_rule_result(m.group(0), "ndrapp p",
                                      [r], f"N.D.R.App.P. {r}")

    # N.D.R.Civ.P. — explicit abbreviation
    m = re.search(
        r'N[\s.]*D[\s.]*R[\s.]*Civ[\s.]*P[.\s]*(?:Rule\s+)?(\d{1,2})'
        r'|(?:Rule\s+)?(\d{1,2})[,\s]*N[\s.]*D[\s.]*R[\s.]*Civ[\s.]*P[\s.]*',
        text, re.IGNORECASE
    )
    if m:
        r = m.group(1) or m.group(2)
        if r:
            return _court_rule_result(m.group(0), "ndrcivp",
                                      [r], f"N.D.R.Civ.P. {r}")

    # N.D.R.Crim.P. — explicit abbreviation
    m = re.search(
        r'N[\s.]*D[\s.]*R[\s.]*Crim[\s.]*P[.\s]*(?:Rule\s+)?(\d{1,2})'
        r'|(?:Rule\s+)?(\d{1,2})[,\s]*N[\s.]*D[\s.]*R[\s.]*Crim[\s.]*P[\s.]*',
        text, re.IGNORECASE
    )
    if m:
        r = m.group(1) or m.group(2)
        if r:
            return _court_rule_result(m.group(0), "ndrcrimp",
                                      [r], f"N.D.R.Crim.P. {r}")

    # N.D.R.Ct. simple (no decimal)
    m = re.search(
        r'N[\s.]*D[\s.]*R[\s.]*Ct[.\s]*(?:Rule\s+)?(\d{1,2})(?:(?:\([a-z\d]*\))*|[^.\d])'
        r'|(?:Rule\s+)?(\d{1,2})(?:(?:\([a-z\d]*\))*|[^.\d])[,\s]*N[\s.]*D[\s.]*R[\s.]*Ct[\s.]*',
        text, re.IGNORECASE
    )
    if m:
        r = m.group(1) or m.group(2)
        if r:
            return _court_rule_result(m.group(0), "ndrct",
                                      [r], f"N.D.R.Ct. {r}")

    # N.D.R. Continuing Legal Ed.
    m = re.search(
        r'(?:Rule\s+)?(\d)'
        r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
        r'N[\s.]*D[\s.]*R[\s.]*Continuing[\s.]*Legal[\s.]*Ed(?:ucation)?[\s.]*'
        r'|N[\s.]*D[\s.]*R[\s.]*Continuing[\s.]*Legal[\s.]*Ed(?:ucation)?[.\s]*'
        r'(?:Rule\s+)?(\d)',
        text, re.IGNORECASE
    )
    if m:
        r = m.group(1) or m.group(2)
        if r:
            return _court_rule_result(m.group(0), "ndrcontinuinglegaled",
                                      [r], f"N.D.R. Continuing Legal Ed. {r}")

    # Admission to Practice — decimal
    m = re.search(
        r'(?:Rule\s+)?(\d{1,2})\.(\d+)'
        r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
        r'N[\s.]*D[\s.]*Admission[\s.]*to[\s.]*Practice[\s.]*R(?:ules)?[\s.]*'
        r'|N[\s.]*D[\s.]*Admission[\s.]*to[\s.]*Practice[\s.]*R(?:ules)?[.\s]*'
        r'(?:Rule\s+)?(\d{1,2})\.(\d+)',
        text, re.IGNORECASE
    )
    if m:
        p1 = m.group(1) or m.group(3)
        p2 = m.group(2) or m.group(4)
        if p1:
            return _court_rule_result(m.group(0), "admissiontopracticer",
                                      [p1, p2],
                                      f"N.D. Admission to Practice R. {p1}.{p2}")

    # Admission to Practice — simple
    m = re.search(
        r'(?:Rule\s+)?(\d{1,2})'
        r'(?:(?:\([a-z\d]*\))*|[^.\d])[,\s]*'
        r'N[\s.]*D[\s.]*Admission[\s.]*to[\s.]*Practice[\s.]*R(?:ules)?[\s.]*'
        r'|N[\s.]*D[\s.]*Admission[\s.]*to[\s.]*Practice[\s.]*R(?:ules)?[.\s]*'
        r'(?:Rule\s+)?(\d{1,2})(?:(?:\([a-z\d]*\))*|[^.\d])',
        text, re.IGNORECASE
    )
    if m:
        r = m.group(1) or m.group(2)
        if r:
            return _court_rule_result(m.group(0), "admissiontopracticer",
                                      [r], f"N.D. Admission to Practice R. {r}")

    # Lawyer Sanctions Standards
    m = re.search(
        r'(?:Standard\s+)?(\d)\.(\d{1,2})'
        r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
        r'N[\s.]*D[\s.]*Stds[\s.]*Imposing[\s.]*Lawyer[\s.]*Sanctions[\s.]*'
        r'|N[\s.]*D[\s.]*Stds[\s.]*Imposing[\s.]*Lawyer[\s.]*Sanctions[.\s]*'
        r'(?:Standard\s+)?(\d)\.(\d{1,2})',
        text, re.IGNORECASE
    )
    if m:
        p1 = m.group(1) or m.group(3)
        if p1:
            return _court_rule_result(m.group(0), "ndstdsimposinglawyersanctions",
                                      [p1, "0"],
                                      f"N.D. Stds. Imposing Lawyer Sanctions {p1}")

    # Local Rules
    m = re.search(r'Local[\s.]*Rule[\s.]*(\d{1,4}(?:-\d+)?)', text, re.IGNORECASE)
    if m:
        return {
            "cite_text": m.group(0).strip(),
            "cite_type": "nd_court_rule",
            "normalized": f"Local Rule {m.group(1)}",
            "parts": {"rule_set": "local", "parts": [m.group(1)]},
            "url": url_nd_local_rule(m.group(1)),
            "search_hint": f"Local Rule {m.group(1)}",
        }

    # N.D.R. Proc. R.
    m = re.search(
        r'(?:Section\s+)?(\d{1,2})'
        r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
        r'N[\s.]*D[\s.]*R[\s.]*Proc[\s.]*R[\s.]*'
        r'|N[\s.]*D[\s.]*R[\s.]*Proc[\s.]*R[.\s]*'
        r'(?:Section\s+)?(\d{1,2})',
        text, re.IGNORECASE
    )
    if m:
        r = m.group(1) or m.group(2)
        if r:
            return _court_rule_result(m.group(0), "ndrprocr",
                                      [r], f"N.D.R. Proc. R. {r}")

    # N.D.R. Local Ct. P.R.
    m = re.search(
        r'(?:Section\s+)?(\d{1,2})'
        r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
        r'N[\s.]*D[\s.]*R[\s.]*Local[\s.]*Ct[\s.]*P[\s.]*R[\s.]*'
        r'|N[\s.]*D[\s.]*R[\s.]*Local[\s.]*Ct[\s.]*P[\s.]*R[.\s]*'
        r'(?:Section\s+)?(\d{1,2})',
        text, re.IGNORECASE
    )
    if m:
        r = m.group(1) or m.group(2)
        if r:
            return _court_rule_result(m.group(0), "ndrlocalctpr",
                                      [r], f"N.D.R. Local Ct. P.R. {r}")

    # Student Practice Rules (Roman numerals)
    m = re.search(
        r'(?:Section\s+)?([IVX]+)'
        r'(?:(?:\([a-z\d]*\))*|\W)[,\s]*'
        r'(?:Limited\s+Practice\s+of\s+Law\s+by\s+Law\s+Students'
        r'|N[\s.]*D[\s.]*Student[\s.]*Practice[\s.]*R[\s.]*)'
        r'|(?:Limited\s+Practice\s+of\s+Law\s+by\s+Law\s+Students'
        r'|N[\s.]*D[\s.]*Student[\s.]*Practice[\s.]*R[.\s]*)'
        r'(?:Section\s+)?([IVX]+)',
        text, re.IGNORECASE
    )
    if m:
        roman = m.group(1) or m.group(2)
        if roman:
            return _court_rule_result(m.group(0), "rltdpracticeoflawbylawstudents",
                                      [roman.upper()],
                                      f"N.D. Student Practice R. \u00a7 {roman.upper()}")

    # Judicial Conduct Commission — decimal
    m = re.search(
        r'(?:Rule\s+)?(\d{1,2})\.(\d+)'
        r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
        r'N[\s.]*D[\s.]*R[\s.]*Jud[\s.]*Conduct[\s.]*Commission[\s.]*'
        r'|N[\s.]*D[\s.]*R[\s.]*Jud[\s.]*Conduct[\s.]*Commission[.\s]*'
        r'(?:Rule\s+)?(\d{1,2})\.(\d+)',
        text, re.IGNORECASE
    )
    if m:
        p1 = m.group(1) or m.group(3)
        p2 = m.group(2) or m.group(4)
        if p1:
            return _court_rule_result(m.group(0), "rjudconductcomm",
                                      [p1, p2],
                                      f"N.D.R. Jud. Conduct Commission {p1}.{p2}")

    # Judicial Conduct Commission — simple
    m = re.search(
        r'(?:Rule\s+)?(\d{1,2})'
        r'(?:(?:\([a-z\d]*\))*|[^.\d])[,\s]*'
        r'N[\s.]*D[\s.]*R[\s.]*Jud[\s.]*Conduct[\s.]*Commission[\s.]*'
        r'|N[\s.]*D[\s.]*R[\s.]*Jud[\s.]*Conduct[\s.]*Commission[.\s]*'
        r'(?:Rule\s+)?(\d{1,2})(?:(?:\([a-z\d]*\))*|[^.\d])',
        text, re.IGNORECASE
    )
    if m:
        r = m.group(1) or m.group(2)
        if r:
            return _court_rule_result(m.group(0), "rjudconductcomm",
                                      [r],
                                      f"N.D.R. Jud. Conduct Commission {r}")

    return None


def _court_rule_result(cite_text, rule_set, parts, description):
    # Fix rule_set with space (typo from "ndrapp p")
    rule_set_clean = rule_set.replace(" ", "")
    return {
        "cite_text": cite_text.strip(),
        "cite_type": "nd_court_rule",
        "normalized": description,
        "parts": {"rule_set": rule_set_clean, "parts": parts},
        "url": url_nd_court_rule(rule_set_clean, parts),
        "search_hint": description,
    }


def match_ndac(text):
    """Match NDAC citations."""
    # "N.D.A.C. § 43-02-05-01" (4-part section)
    m = re.search(
        r'N[\s.]*D[\s.]*A(?:dmin)*[.\s]*(?:Code|C|Rules|R)*[,.\s]*[^\s\d]{0,3}\s*'
        r'(\d{1,2}\.?\d*)[^.\w]{1,2}(\d{2}\.?\d*)[^.\w]{1,2}'
        r'(\d{2}\.?\d*)[^.\w]{1,2}(\d{2}\.?\d*)',
        text, re.IGNORECASE
    )
    if m:
        return {
            "cite_text": m.group(0).strip(),
            "cite_type": "ndac",
            "normalized": f"N.D.A.C. \u00a7 {m.group(1)}-{m.group(2)}-{m.group(3)}-{m.group(4)}",
            "parts": {"p1": m.group(1), "p2": m.group(2), "p3": m.group(3), "p4": m.group(4)},
            "url": url_ndac(m.group(1), m.group(2), m.group(3)),
            "search_hint": f"{m.group(1)}-{m.group(2)}-{m.group(3)}-{m.group(4)}",
        }

    # "N.D.A.C. ch. 43-02-05" (3-part chapter)
    m = re.search(
        r'N[\s.]*D[\s.]*A(?:dmin)*[.\s]*(?:Code|C|Rules|R)*[,.\s]{0,2}'
        r'(?:Ch\.|ch\.|Ch|ch)\s*'
        r'(\d{1,2}\.?\d*)[^.\w]{1,2}(\d{2}\.?\d*)[^.\w]{1,2}(\d{2}\.?\d*)',
        text, re.IGNORECASE
    )
    if m:
        return {
            "cite_text": m.group(0).strip(),
            "cite_type": "ndac",
            "normalized": f"N.D.A.C. ch. {m.group(1)}-{m.group(2)}-{m.group(3)}",
            "parts": {"p1": m.group(1), "p2": m.group(2), "p3": m.group(3)},
            "url": url_ndac(m.group(1), m.group(2), m.group(3)),
            "search_hint": f"{m.group(1)}-{m.group(2)}-{m.group(3)}",
        }

    # Reverse: "43-02-05-01, N.D. Admin Code"
    m = re.search(
        r'(\d{2}\.?\d*)[^.\w]{1,2}(\d{2}\.?\d*)[^.\w]{1,2}'
        r'(\d{2}\.?\d*)[^.\w]{1,2}(\d{2}\.?\d*)'
        r'(?:(?:\([a-z\d]*\))*|\D)(?:,\s{0,3})'
        r'N[\s.]*D[\s.]*A(?:dmin)*[.\s]*(?:Code|C|Rules|R)*',
        text, re.IGNORECASE
    )
    if m:
        return {
            "cite_text": m.group(0).strip(),
            "cite_type": "ndac",
            "normalized": f"N.D.A.C. \u00a7 {m.group(1)}-{m.group(2)}-{m.group(3)}-{m.group(4)}",
            "parts": {"p1": m.group(1), "p2": m.group(2), "p3": m.group(3), "p4": m.group(4)},
            "url": url_ndac(m.group(1), m.group(2), m.group(3)),
            "search_hint": f"{m.group(1)}-{m.group(2)}-{m.group(3)}-{m.group(4)}",
        }

    return None


def match_federal_statutes(text):
    """Match USC, CFR, and U.S. Reports citations.

    Order matters: USC before U.S. Reports to avoid ambiguity.
    """
    # USC: "42 U.S.C. § 1983"
    m = re.search(
        r'(\d+)\s*U[\s.]*S[\s.]*C(?:ode)?[,.\s]*(?:\u00a7|§|[Ss]ec(?:tion)?\.?)\s*(\d+)',
        text, re.IGNORECASE
    )
    if m:
        title, section = m.group(1), m.group(2)
        return {
            "cite_text": m.group(0).strip(),
            "cite_type": "usc",
            "normalized": f"{title} U.S.C. \u00a7 {section}",
            "parts": {"title": title, "section": section},
            "url": url_usc(title, section),
            "search_hint": f"{title} USC {section}",
        }

    # CFR: "29 C.F.R. § 1910.1200"
    m = re.search(
        r'(\d+)\s*C[\s.]*F[\s.]*R(?:eg)?[,.\s]*(?:\u00a7|§|[Ss]ec(?:tion)?\.?)?\s*([.\d]+)',
        text, re.IGNORECASE
    )
    if m:
        title, section = m.group(1), m.group(2)
        return {
            "cite_text": m.group(0).strip(),
            "cite_type": "cfr",
            "normalized": f"{title} C.F.R. \u00a7 {section}",
            "parts": {"title": title, "section": section},
            "url": url_cfr(title, section),
            "search_hint": f"{title} CFR {section}",
        }

    # U.S. Reports: "505 U.S. 377"
    m = re.search(r'(\d+)\s+U\.S\.\s+(\d+)', text)
    if m:
        volume, page = m.group(1), m.group(2)
        return {
            "cite_text": m.group(0).strip(),
            "cite_type": "us_supreme_court",
            "normalized": f"{volume} U.S. {page}",
            "parts": {"volume": volume, "page": page},
            "url": url_us_supreme_court(volume, page),
            "search_hint": f"{volume} US {page}",
        }

    return None


def match_state_cases(text):
    """Match state case citations — ND neutral, other state neutrals, regional/state reporters."""

    # ND neutral: "2024 ND 42"
    m = re.search(r'([12]\d{3})\s+ND\s+(\d{1,3})', text)
    if m:
        year, number = m.group(1), m.group(2)
        return {
            "cite_text": m.group(0),
            "cite_type": "nd_case",
            "normalized": f"{year} ND {number}",
            "parts": {"year": year, "number": number},
            "url": url_nd_case(year, number),
            "search_hint": f"{year}ND{number}",
        }

    # Ohio hyphenated: "2018-Ohio-3237"
    m = re.search(r'(\d{4})-Ohio-(\d+)', text)
    if m:
        return _state_case_result(m, "Ohio", f"{m.group(1)}-Ohio-{m.group(2)}")

    # NM neutral: "2009-NMSC-006"
    m = re.search(r'(\d{4})-(NM(?:SC|CA))-(\d+)', text)
    if m:
        court = m.group(2)
        return _state_case_result(m, court,
                                  f"{m.group(1)}-{court}-{m.group(3)}")

    # Illinois neutral: "2019 IL 123456"
    m = re.search(r'(\d{4})\s+IL\s+(\d+)', text)
    if m:
        return {
            "cite_text": m.group(0).strip(),
            "cite_type": "state_neutral",
            "normalized": f"{m.group(1)} IL {m.group(2)}",
            "parts": {"volume": m.group(1), "page": m.group(2)},
            "url": url_court_listener("IL", m.group(1), m.group(2)),
            "search_hint": f"{m.group(1)} IL {m.group(2)}",
        }

    # Standard state neutrals: "2015 Ark. 520", "2024 CO 42", etc.
    m = re.search(
        r'([12]\d{3})\s+(Ark\.|CO|ME|MT|N\.H\.|OK|S\.D\.|UT|VT|WI|WY|AZ)\s+(\d+)',
        text
    )
    if m:
        reporter = m.group(2)
        return {
            "cite_text": m.group(0).strip(),
            "cite_type": "state_neutral",
            "normalized": f"{m.group(1)} {reporter} {m.group(3)}",
            "parts": {"volume": m.group(1), "page": m.group(3)},
            "url": url_court_listener(reporter, m.group(1), m.group(3)),
            "search_hint": f"{m.group(1)} {reporter} {m.group(3)}",
        }

    # Regional reporters: N.W.2d/3d, A.2d/3d, N.E.2d/3d, S.E.2d, So.2d/3d, S.W.2d/3d, P.2d/3d
    _regional = [
        (r'(\d+)\s+N\.W\.\s?([23]d)\s+(\d+)', lambda m: f"N.W.{m.group(2)}"),
        (r'(\d+)\s+A\.([23]d)\s+(\d+)',        lambda m: f"A.{m.group(2)}"),
        (r'(\d+)\s+N\.E\.\s?([23]d)\s+(\d+)',  lambda m: f"N.E.{m.group(2)}"),
        (r'(\d+)\s+S\.E\.\s?(?:(2d)\s)?(\d+)', lambda m: "S.E.2d" if m.group(2) else "S.E."),
        (r'(\d+)\s+So\.\s?(?:([23]d)\s)?(\d+)',
         lambda m: f"So. {m.group(2)}" if m.group(2) else "So."),
        (r'(\d+)\s+S\.W\.\s?(?:([23]d)\s)?(\d+)',
         lambda m: f"S.W.{m.group(2)}" if m.group(2) else "S.W."),
        (r'(\d+)\s+P\.([23]d)\s+(\d+)',        lambda m: f"P.{m.group(2)}"),
    ]
    for pat, edition_fn in _regional:
        m = re.search(pat, text)
        if m:
            edition = edition_fn(m)
            vol, pg = m.group(1), m.group(3)
            return {
                "cite_text": m.group(0).strip(),
                "cite_type": "state_case",
                "normalized": f"{vol} {edition} {pg}",
                "parts": {"volume": vol, "page": pg, "reporter": edition},
                "url": url_court_listener(edition, vol, pg),
                "search_hint": f"{vol} {edition} {pg}",
            }

    # California reporters
    m = re.search(r'(\d+)\s+Cal\.\s?(?:(2d|3d|4th|5th)\s)?(\d+)', text)
    if m:
        suffix = m.group(2)
        edition = f"Cal. {suffix}" if suffix else "Cal."
        return _vol_reporter_page(m, edition)

    # Cal. Rptr.
    m = re.search(r'(\d+)\s+Cal\.\s?Rptr\.\s?(?:(2d|3d)\s)?(\d+)', text)
    if m:
        suffix = m.group(2)
        edition = f"Cal. Rptr. {suffix}" if suffix else "Cal. Rptr."
        return _vol_reporter_page(m, edition)

    # N.Y. reporters
    m = re.search(r'(\d+)\s+N\.Y\.(?:([23]d)\s)?(\d+)', text)
    if m:
        suffix = m.group(2)
        edition = f"N.Y.{suffix}" if suffix else "N.Y."
        return _vol_reporter_page(m, edition)

    # N.Y.S. reporters
    m = re.search(r'(\d+)\s+N\.Y\.S\.(?:([23]d)\s)?(\d+)', text)
    if m:
        suffix = m.group(2)
        edition = f"N.Y.S.{suffix}" if suffix else "N.Y.S."
        return _vol_reporter_page(m, edition)

    # Ohio St.
    m = re.search(r'(\d+)\s+Ohio\s+St\.\s?(?:([23]d)\s)?(\d+)', text)
    if m:
        suffix = m.group(2)
        edition = f"Ohio St. {suffix}" if suffix else "Ohio St."
        return _vol_reporter_page(m, edition)

    # Wn.2d / Wn. App.
    m = re.search(r'(\d+)\s+Wn\.\s?(2d|App\.)\s+(\d+)', text)
    if m:
        edition = f"Wn. {m.group(2)}"
        return _vol_reporter_page(m, edition)

    # Generic state reporters
    m = re.search(
        r'(\d+)\s+(Conn\.|Ga\.|Haw\.|Kan\.|Mass\.|Md\.|Mich\.|N\.C\.|N\.J\.|Neb\.|Or\.|Pa\.|S\.C\.|Va\.)\s+(\d+)',
        text
    )
    if m:
        return _vol_reporter_page(m, m.group(2))

    # First-series regional: N.W., N.E., A.
    for pat, edition in [
        (r'(\d+)\s+N\.W\.\s+(\d+)', "N.W."),
        (r'(\d+)\s+N\.E\.\s+(\d+)', "N.E."),
        (r'(\d+)\s+A\.\s+(\d+)',     "A."),
    ]:
        m = re.search(pat, text)
        if m:
            vol, pg = m.group(1), m.group(2)
            return {
                "cite_text": m.group(0).strip(),
                "cite_type": "state_case",
                "normalized": f"{vol} {edition} {pg}",
                "parts": {"volume": vol, "page": pg, "reporter": edition},
                "url": url_court_listener(edition, vol, pg),
                "search_hint": f"{vol} {edition} {pg}",
            }

    # Malformed NW2d fallback: "520 NW2d 808", "520 NW.2d 808"
    m = re.search(r'(\d+)\s+(NW\.?\s?2d|N\.W2d)\s+(\d+)', text, re.IGNORECASE)
    if m:
        vol, pg = m.group(1), m.group(3)
        return {
            "cite_text": m.group(0).strip(),
            "cite_type": "state_case",
            "normalized": f"{vol} N.W.2d {pg}",
            "parts": {"volume": vol, "page": pg, "reporter": "N.W.2d"},
            "url": url_court_listener("N.W.2d", vol, pg),
            "search_hint": f"{vol} N.W.2d {pg}",
        }

    return None


def _state_case_result(m, reporter, description):
    """Helper for state neutral citations with year-reporter-number format."""
    return {
        "cite_text": m.group(0).strip(),
        "cite_type": "state_neutral",
        "normalized": description,
        "parts": {"volume": m.group(1), "page": m.group(len(m.groups()))},
        "url": url_court_listener(reporter, m.group(1), m.group(len(m.groups()))),
        "search_hint": description,
    }


def _vol_reporter_page(m, edition):
    """Helper for volume-reporter-page state case citations."""
    vol, pg = m.group(1), m.group(len(m.groups()))
    return {
        "cite_text": m.group(0).strip(),
        "cite_type": "state_case",
        "normalized": f"{vol} {edition} {pg}",
        "parts": {"volume": vol, "page": pg, "reporter": edition},
        "url": url_court_listener(edition, vol, pg),
        "search_hint": f"{vol} {edition} {pg}",
    }


def match_federal_reporters(text):
    """Match federal reporter citations — all resolve to CourtListener."""
    _reporters = [
        # F., F.2d, F.3d, F.4th
        (r'(\d+)\s+F\.\s?(?:(2d|3d|4th)\s)?(\d+)',
         lambda m: f"F.{m.group(2)}" if m.group(2) else "F."),
        # S. Ct.
        (r'(\d+)\s+S\.\s?Ct\.\s+(\d+)',
         lambda m: "S. Ct."),
        # F. Supp., F. Supp. 2d, F. Supp. 3d
        (r'(\d+)\s+F\.\s?Supp\.\s?(?:(2d|3d)\s)?(\d+)',
         lambda m: f"F. Supp. {m.group(2)}" if m.group(2) else "F. Supp."),
        # L. Ed., L. Ed. 2d
        (r'(\d+)\s+L\.\s?Ed\.\s?(?:(2d)\s)?(\d+)',
         lambda m: "L. Ed. 2d" if m.group(2) else "L. Ed."),
        # B.R.
        (r'(\d+)\s+B\.\s?R\.\s+(\d+)', lambda m: "B.R."),
        # F.R.D.
        (r'(\d+)\s+F\.\s?R\.\s?D\.\s+(\d+)', lambda m: "F.R.D."),
        # Fed. Cl.
        (r'(\d+)\s+Fed\.\s?Cl\.\s+(\d+)', lambda m: "Fed. Cl."),
        # M.J.
        (r'(\d+)\s+M\.\s?J\.\s+(\d+)', lambda m: "M.J."),
        # Vet. App.
        (r'(\d+)\s+Vet\.\s?App\.\s+(\d+)', lambda m: "Vet. App."),
        # T.C.
        (r'(\d+)\s+T\.\s?C\.\s+(\d+)', lambda m: "T.C."),
        # F. App'x
        (r"(\d+)\s+F\.\s?App[\u2019']x\s+(\d+)", lambda m: "F. App'x"),
    ]
    for pat, edition_fn in _reporters:
        m = re.search(pat, text)
        if m:
            edition = edition_fn(m)
            vol = m.group(1)
            pg = m.group(len(m.groups()))
            return {
                "cite_text": m.group(0).strip(),
                "cite_type": "federal_reporter",
                "normalized": f"{vol} {edition} {pg}",
                "parts": {"volume": vol, "page": pg, "reporter": edition},
                "url": url_court_listener(edition, vol, pg),
                "search_hint": f"{vol} {edition} {pg}",
            }

    return None


# ---------------------------------------------------------------------------
# Scanner — find all citations in opinion text
# ---------------------------------------------------------------------------

# Matchers in priority order
_MATCHERS = [
    match_us_constitution,
    match_nd_constitution,
    match_ndcc,
    match_ndcc_chapter,
    match_nd_court_rules,
    match_ndac,
    match_federal_statutes,
    match_state_cases,
    match_federal_reporters,
]


_CASE_TYPES = {"nd_case", "state_case", "state_neutral", "us_supreme_court",
                "federal_reporter"}


def scan_opinion(text, refs_dir="~/refs"):
    """Scan opinion text for all citations. Returns deduplicated list."""
    results = []
    seen = set()

    for matcher in _MATCHERS:
        pos = 0
        while pos < len(text):
            chunk = text[pos:]
            result = matcher(chunk)
            if not result:
                break

            normalized = result["normalized"]
            if normalized not in seen:
                seen.add(normalized)

                cite_type = result["cite_type"]
                parts = result.get("parts", {})
                local_path, local_exists = resolve_local(cite_type, parts, refs_dir)

                # Track absolute position in original text for parallel cite detection
                cite_text = result["cite_text"]
                match_start_in_chunk = chunk.find(cite_text)
                abs_start = pos + max(match_start_in_chunk, 0)

                entry = {
                    "cite_text": cite_text,
                    "cite_type": cite_type,
                    "normalized": normalized,
                    "url": result["url"],
                    "search_hint": result["search_hint"],
                    "_abs_pos": abs_start,
                }
                if local_path:
                    entry["local_path"] = local_path
                    entry["local_exists"] = local_exists
                else:
                    entry["local_path"] = None
                    entry["local_exists"] = False

                results.append(entry)

            match_start = chunk.find(result["cite_text"])
            if match_start >= 0:
                pos += match_start + len(result["cite_text"])
            else:
                pos += 1

    # Parallel citation detection: find adjacent case citations separated by ", " or "; "
    case_results = [r for r in results if r["cite_type"] in _CASE_TYPES]
    case_results.sort(key=lambda r: r["_abs_pos"])
    for i in range(len(case_results) - 1):
        a, b = case_results[i], case_results[i + 1]
        a_end = a["_abs_pos"] + len(a["cite_text"])
        gap = text[a_end:b["_abs_pos"]]
        if gap.strip() in (",", ";"):
            a["parallel_cite"] = b["normalized"]
            b["parallel_cite"] = a["normalized"]
            # Mark preferred based on local availability
            a_local = a.get("local_exists", False)
            b_local = b.get("local_exists", False)
            if a_local:
                a["preferred"] = True
            if b_local:
                b["preferred"] = True

    # Strip internal position tracking
    for r in results:
        r.pop("_abs_pos", None)

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Parse legal citations, resolve local files, build URLs."
    )
    parser.add_argument("--file", "-f", help="Scan a file for all citations")
    parser.add_argument("--refs-dir", default="~/refs",
                        help="Override refs directory (default: ~/refs)")
    parser.add_argument("--json", action="store_true", default=True,
                        help="Output as JSON (default)")
    args = parser.parse_args()

    if args.file:
        path = Path(args.file).expanduser()
        if not path.exists():
            print(f"Error: file not found: {path}", file=sys.stderr)
            sys.exit(1)
        text = path.read_text(encoding="utf-8")
        results = scan_opinion(text, refs_dir=args.refs_dir)
    else:
        # stdin mode — one citation per line
        results = []
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            found = scan_opinion(line, refs_dir=args.refs_dir)
            results.extend(found)

    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

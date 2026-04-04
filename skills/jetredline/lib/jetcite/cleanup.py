"""Markdown cleanup functions for cached citation content.

Organized by content type with a dispatcher that routes based on CitationType.
Absorbs cleanup logic from:
  - ~/code/scraper/scraper/markdown_cleanup.py (opinion PDF cleanup)
  - ~/code/code-mirror/scrape_nd_code.py (statute/regulation PDF cleanup)

Each cleanup function takes text and returns cleaned text. All are pure
functions with no side effects.
"""

from __future__ import annotations

import re

from jetcite.models import CitationType

# ── Opinion cleanup (from scraper/markdown_cleanup.py) ────────────


def _identify_page_number_lines(lines: list[str]) -> set[int]:
    """Identify which standalone numbers are PDF page numbers.

    Returns a set of line indices that are page numbers.
    Validates that candidates form a roughly sequential series.
    """
    candidates = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or not re.match(r"^\d{1,3}$", stripped):
            continue
        num = int(stripped)
        if num < 1 or num > 500:
            continue
        prev_blank = i == 0 or lines[i - 1].strip() == ""
        next_blank = (i == len(lines) - 1
                      or (i + 1 < len(lines) and lines[i + 1].strip() == ""))
        if prev_blank and next_blank:
            candidates.append((i, num))

    if not candidates:
        return set()
    if len(candidates) == 1:
        return {candidates[0][0]} if candidates[0][1] <= 30 else set()

    prev_num = 0
    sequential_count = 0
    for _, num in candidates:
        if num > prev_num:
            sequential_count += 1
            prev_num = num

    if sequential_count >= len(candidates) * 0.7:
        return {idx for idx, _ in candidates}
    return set()


def _remove_page_numbers(lines: list[str]) -> list[str]:
    """Remove embedded PDF page numbers and their surrounding blank lines."""
    page_num_lines = _identify_page_number_lines(lines)
    if not page_num_lines:
        return lines
    new_lines = []
    skip_next_blank = False
    for i, line in enumerate(lines):
        if i in page_num_lines:
            skip_next_blank = True
            continue
        if skip_next_blank and line.strip() == "":
            skip_next_blank = False
            continue
        skip_next_blank = False
        new_lines.append(line)
    return new_lines


def _collapse_consecutive_blanks(lines: list[str]) -> list[str]:
    """Collapse runs of multiple blank lines to at most one."""
    new_lines = []
    prev_blank = False
    for line in lines:
        if line.strip() == "":
            if prev_blank:
                continue
            prev_blank = True
        else:
            prev_blank = False
        new_lines.append(line)
    return new_lines


def _reattach_detached_markers(lines: list[str]) -> list[str]:
    """Reattach [paragraph-N] markers that appear alone on a line.

    If the preceding line has content that doesn't end a sentence,
    fold it into this paragraph.
    """
    new_lines = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if re.match(r"^\[\u00b6\d+\]$", stripped):
            j = i + 1
            while j < len(lines) and lines[j].strip() == "":
                j += 1

            prev_text = ""
            if new_lines and new_lines[-1].strip():
                prev = new_lines[-1].strip()
                if (not re.match(r"\[\u00b6\d+\]", prev)
                        and not re.search(r'[.;:!?")}\]]$', prev)):
                    prev_text = prev
                    new_lines.pop()

            if j < len(lines):
                if prev_text:
                    combined = stripped + " " + prev_text + " " + lines[j].strip()
                else:
                    combined = stripped + " " + lines[j].strip()
                new_lines.append(combined)
                i = j + 1
                continue
        new_lines.append(lines[i])
        i += 1
    return new_lines


def _ensure_inter_paragraph_blanks(lines: list[str]) -> list[str]:
    """Ensure a blank line before each [paragraph-N] marker (except the first)."""
    new_lines = []
    first_para_seen = False
    for line in lines:
        stripped = line.strip()
        if re.match(r"\[\u00b6\d+\]", stripped):
            if first_para_seen:
                if new_lines and new_lines[-1].strip() != "":
                    new_lines.append("")
            first_para_seen = True
        new_lines.append(line)
    return new_lines


def _collapse_intra_paragraph_blanks(lines: list[str]) -> list[str]:
    """Collapse blank lines within paragraph blocks, joining text lines.

    A paragraph block runs from [paragraph-N] to the next paragraph marker,
    section header, or end of file.
    """
    new_lines = []
    in_para = False
    para_buffer: list[str] = []

    def flush_para():
        if not para_buffer:
            return
        content_parts = [pl.strip() for pl in para_buffer if pl.strip()]
        if content_parts:
            joined = " ".join(content_parts)
            joined = re.sub(r"  +", " ", joined)
            new_lines.append(joined)
        para_buffer.clear()

    for i, line in enumerate(lines):
        stripped = line.strip()

        if re.match(r"\[\u00b6\d+\]", stripped):
            flush_para()
            in_para = True
            para_buffer.append(line)
            continue

        if in_para:
            is_new_section = (
                re.match(r"^#+\s", stripped)
                or (re.match(r"^[IVX]+\.?\s", stripped) and len(stripped.split()) <= 3)
                or stripped.startswith("---")
            )
            if is_new_section:
                flush_para()
                in_para = False
                new_lines.append(line)
                continue

            if stripped == "":
                j = i + 1
                while j < len(lines) and lines[j].strip() == "":
                    j += 1
                if j >= len(lines):
                    flush_para()
                    in_para = False
                    new_lines.append(line)
                elif re.match(r"\[\u00b6\d+\]", lines[j].strip()):
                    flush_para()
                    in_para = False
                    new_lines.append(line)
                elif re.match(r"^[IVX]+\.?\s*$", lines[j].strip()):
                    flush_para()
                    in_para = False
                    new_lines.append(line)
                continue

            para_buffer.append(line)
            continue

        new_lines.append(line)

    flush_para()
    return new_lines


def _split_concatenated_stamps(lines: list[str]) -> list[str]:
    """Split filing stamps concatenated with following text."""
    new_lines = []
    for line in lines:
        fixed = re.sub(
            r"((?:Supreme Court|Clerk of Supreme Court))([A-Z][a-z])",
            r"\1\n\2",
            line,
        )
        if fixed != line:
            new_lines.extend(fixed.split("\n"))
        else:
            new_lines.append(line)
    return new_lines


def _strip_trailing_page_number(lines: list[str]) -> list[str]:
    """Remove trailing blank lines and final page number at end of file."""
    while lines and lines[-1].strip() == "":
        lines.pop()
    if lines and re.match(r"^\d{1,3}$", lines[-1].strip()):
        lines.pop()
    while lines and lines[-1].strip() == "":
        lines.pop()
    lines.append("")
    return lines


def cleanup_opinion(text: str) -> str:
    """Clean up extracted opinion markdown text.

    Applies the full pipeline: page number removal, blank line collapsing,
    paragraph marker reattachment, intra-paragraph blank removal, stamp
    splitting, and trailing page number stripping.
    """
    if not text or len(text.strip()) < 50:
        return text

    lines = text.split("\n")
    lines = _remove_page_numbers(lines)
    lines = _collapse_consecutive_blanks(lines)
    lines = _reattach_detached_markers(lines)
    lines = _ensure_inter_paragraph_blanks(lines)
    lines = _collapse_intra_paragraph_blanks(lines)
    lines = _split_concatenated_stamps(lines)
    lines = _strip_trailing_page_number(lines)
    return "\n".join(lines)


# ── Statute/regulation cleanup (from code-mirror/scrape_nd_code.py) ──

# Section patterns — require trailing period to distinguish real sections from TOC.
# NDCC: 3+ part numbers e.g. "1-01-01." or "4.1-01-01."
_NDCC_SECTION_RE = re.compile(r"^([\d.]+(?:-[\d.]+){2,})\.\s+(.+)")
# NDAC: 4+ part numbers e.g. "7-20-01-03."
_NDAC_SECTION_RE = re.compile(r"^([\d.]+(?:-[\d.]+){3,})\.\s+(.+)")


def _statute_text_to_markdown(text: str, section_re: re.Pattern) -> list[str]:
    """Convert raw statute/regulation PDF text to markdown lines.

    Strips page headers/footers, TOC entries, and formats section headings
    as level-3 markdown headers.
    """
    lines = text.split("\n")
    md_lines: list[str] = []
    in_section = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_section:
                md_lines.append("")
            continue

        # Skip page headers, footers, and bare page numbers
        if re.match(r"^TITLE\s+\d+", stripped) and len(stripped) < 40:
            continue
        if re.match(r"^CHAPTER\s+[\d.\-]+", stripped) and len(stripped) < 60:
            continue
        if re.match(r"^\d+$", stripped):
            continue
        if re.match(r"^Page No\.\s*\d+", stripped):
            continue
        # Skip all-caps header lines (repeated title/chapter names)
        if stripped.isupper() and len(stripped) < 80 and not re.match(r"^\d", stripped):
            continue
        # Skip TOC entries
        if stripped in ("Chapter", "Section"):
            continue
        if (re.match(r"^[\d.]+(?:-[\d.]+){2,}\s+\S", stripped)
                and not re.match(r"^[\d.]+(?:-[\d.]+){2,}\.\s", stripped)):
            continue
        # Skip "Article X-XX" lines
        if re.match(r"^Article\s+[\d.\-]+", stripped) and len(stripped) < 60:
            continue

        section_m = section_re.match(stripped)
        if section_m:
            sec_num = section_m.group(1).rstrip(".")
            sec_rest = section_m.group(2)
            heading_m = re.match(r"^(.+?\.)\s*(.*)", sec_rest)
            if heading_m:
                heading = heading_m.group(1)
                body = heading_m.group(2)
                md_lines.append(f"### \u00a7 {sec_num}. {heading}")
                md_lines.append("")
                if body:
                    md_lines.append(body)
            else:
                md_lines.append(f"### \u00a7 {sec_num}. {sec_rest}")
                md_lines.append("")
            in_section = True
        else:
            md_lines.append(stripped)
            in_section = True

    return md_lines


def cleanup_statute(text: str, **kwargs) -> str:
    """Clean up extracted NDCC statute text.

    Converts raw PDF text to markdown with section headings formatted
    as ### headers. Strips page headers, footers, and TOC entries.
    """
    lines = _statute_text_to_markdown(text, _NDCC_SECTION_RE)
    lines = _collapse_consecutive_blanks(lines)
    return "\n".join(lines)


def cleanup_regulation(text: str, **kwargs) -> str:
    """Clean up extracted NDAC regulation text.

    Same as statute cleanup but uses the 4-part NDAC section pattern.
    """
    lines = _statute_text_to_markdown(text, _NDAC_SECTION_RE)
    lines = _collapse_consecutive_blanks(lines)
    return "\n".join(lines)


# ── Generic HTML-to-markdown cleanup ──────────────────────────────


def cleanup_html(text: str) -> str:
    """Clean up markdown converted from HTML (via markdownify or extractors).

    Fixes common artifacts: excessive blank lines, trailing whitespace,
    leftover HTML entities, etc.
    """
    if not text:
        return text

    lines = text.split("\n")

    # Strip trailing whitespace from each line
    lines = [line.rstrip() for line in lines]

    # Collapse consecutive blank lines
    lines = _collapse_consecutive_blanks(lines)

    # Remove leading blank lines
    while lines and lines[0].strip() == "":
        lines.pop(0)

    # Ensure trailing newline
    if lines and lines[-1] != "":
        lines.append("")

    return "\n".join(lines)


# ── Dispatcher ────────────────────────────────────────────────────


def cleanup(text: str, cite_type: CitationType, jurisdiction: str = "",
            **kwargs) -> str:
    """Dispatch to the appropriate cleanup function based on citation type.

    Args:
        text: Raw text to clean up.
        cite_type: The citation type (determines which cleanup to apply).
        jurisdiction: Jurisdiction code (e.g., "nd", "us").
        **kwargs: Passed through to the specific cleanup function.

    Returns:
        Cleaned text.
    """
    if cite_type == CitationType.CASE:
        return cleanup_opinion(text)

    if cite_type == CitationType.STATUTE:
        if jurisdiction == "nd":
            return cleanup_statute(text, **kwargs)
        return cleanup_html(text)

    if cite_type == CitationType.REGULATION:
        if jurisdiction == "nd":
            return cleanup_regulation(text, **kwargs)
        return cleanup_html(text)

    # Constitution, court rules, and anything else: generic HTML cleanup
    return cleanup_html(text)

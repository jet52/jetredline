#!/usr/bin/env python3
"""
Readability Metrics — computes per-section readability metrics for legal
documents (opinions and memos).

Usage:
    python3 readability_metrics.py --file opinion.md
    python3 readability_metrics.py --file opinion.md --json

Output: JSON with overall metrics, per-section breakdown, and flags for
sentences/sections exceeding thresholds.
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import textstat
except ImportError:
    # Point the hint at whatever interpreter ran us — the workflow always
    # invokes this script with $VENV_PYTHON, so that's the venv to repair.
    print(f"Error: textstat not installed. Run: uv pip install textstat "
          f'--python "{sys.executable}"',
          file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Sentence splitting
# ---------------------------------------------------------------------------

# Abbreviations that end with a period but don't end a sentence
_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "ave", "blvd",
    "inc", "ltd", "corp", "co", "dept", "div", "est", "govt",
    "hon", "gen", "sgt", "cpl", "pvt", "capt", "maj", "col", "lt",
    "no", "nos", "vol", "rev", "ed", "jan", "feb", "mar", "apr",
    "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    "v", "vs",  # case names
    "e.g", "i.e", "et al", "etc",
    "u.s", "s.ct", "l.ed", "f.2d", "f.3d", "f.4th",
    "n.d", "s.d", "e.d", "w.d", "d.n.d",
    "n.w", "n.w.2d", "n.e", "n.e.2d", "s.w", "s.w.2d", "s.e", "s.e.2d",
    "so", "so.2d", "so.3d",
    "a.2d", "a.3d", "p.2d", "p.3d",
    "n.d.c.c", "n.d.r.civ.p", "n.d.r.crim.p", "n.d.r.app.p",
    "n.d.r.ev", "n.d.r.ct", "n.d.a.c",
    "app", "civ", "crim", "ev", "ct", "const", "art", "sec",
    "supp", "dist", "cir", "cl", "op",
    "id", "cf",
}

# Precompile a set of lowercase abbreviations without trailing periods
_ABBREV_SET = set()
for a in _ABBREVIATIONS:
    _ABBREV_SET.add(a.replace(".", "").lower())
    _ABBREV_SET.add(a.lower())


_FK_FALLBACK_NOTED = False


def _estimate_syllables(word: str) -> int:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    groups = len(re.findall(r"[aeiouy]+", w))
    if w.endswith("e") and not w.endswith(("le", "ee")) and groups > 1:
        groups -= 1
    return max(1, groups)


def fk_grade(text: str) -> float:
    """Flesch-Kincaid grade via textstat, degrading to a vowel-group
    syllable estimate when textstat's pronouncing dictionary (NLTK cmudict
    in some textstat builds) is not installed. A fresh venv in an offline
    sandbox otherwise dies here with an unhandled LookupError."""
    global _FK_FALLBACK_NOTED
    try:
        return textstat.flesch_kincaid_grade(text)
    except LookupError:
        if not _FK_FALLBACK_NOTED:
            print("Note: textstat's pronouncing dictionary is unavailable "
                  "(NLTK cmudict not installed); Flesch-Kincaid uses a "
                  "syllable estimate.", file=sys.stderr)
            _FK_FALLBACK_NOTED = True
    words = re.findall(r"[A-Za-z']+", text)
    sents = max(1, len(re.findall(r"[.!?]+(?:\s|$)", text)))
    if not words:
        return 0.0
    syl = sum(_estimate_syllables(w) for w in words)
    return 0.39 * len(words) / sents + 11.8 * syl / len(words) - 15.59


def _is_abbreviation(word: str) -> bool:
    """Check if a word (without trailing period) is a known abbreviation."""
    clean = word.rstrip(".").lower()
    return clean in _ABBREV_SET


def split_sentences(text: str) -> list[str]:
    """Split text into sentences, handling legal abbreviations and citations."""
    # Remove footnote markers and paragraph markers
    text = re.sub(r'\[\*+\d*\]', '', text)

    # Split on sentence-ending punctuation followed by space + capital letter
    # or end of string, but be careful with abbreviations
    sentences = []
    current = []
    words = text.split()

    for i, word in enumerate(words):
        current.append(word)

        # Check if this word ends a sentence
        if not word:
            continue

        ends_with_period = word.endswith('.') and not word.endswith('..')
        ends_with_terminal = word.endswith(('?', '!'))
        ends_with_quote_terminal = word.endswith(('."', '?"', '!"',
                                                   ".'", "?'", "!'",
                                                   '.)', '?)', '!)'))

        if ends_with_terminal or ends_with_quote_terminal or ends_with_period:
            # Check if next word starts with a capital letter (new sentence)
            if i + 1 < len(words):
                next_word = words[i + 1]
                # Strip leading punctuation like quotes or parentheses
                next_clean = next_word.lstrip('"\'(["')
                next_starts_upper = next_clean and next_clean[0].isupper()

                if ends_with_terminal or ends_with_quote_terminal:
                    if next_starts_upper:
                        sentences.append(' '.join(current))
                        current = []
                elif ends_with_period:
                    # Check for abbreviation
                    bare_word = word.rstrip('."\')')
                    if not _is_abbreviation(bare_word) and next_starts_upper:
                        # Also skip if the word looks like a citation reporter
                        # (e.g., "2d", "3d", "4th" preceded by a number)
                        if not re.match(r'^\d', next_clean):
                            sentences.append(' '.join(current))
                            current = []
            elif i + 1 == len(words):
                # Last word — end of text is end of sentence
                sentences.append(' '.join(current))
                current = []

    if current:
        sentences.append(' '.join(current))

    # Filter out very short fragments (< 3 words) that are likely headings
    # or citation-only lines, unless they're the only content
    if len(sentences) > 1:
        sentences = [s for s in sentences if len(s.split()) >= 3 or s.strip()]

    return [s.strip() for s in sentences if s.strip()]


# ---------------------------------------------------------------------------
# Passive voice detection
# ---------------------------------------------------------------------------

_BE_FORMS = {'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being'}

# Common past participles (irregular verbs) — not exhaustive but covers
# the most common ones in legal writing
_IRREGULAR_PP = {
    'been', 'born', 'borne', 'bound', 'brought', 'built', 'caught',
    'chosen', 'come', 'done', 'drawn', 'driven', 'eaten', 'fallen',
    'felt', 'found', 'given', 'gone', 'grown', 'heard', 'held',
    'hidden', 'hit', 'known', 'laid', 'led', 'left', 'lent', 'lost',
    'made', 'meant', 'met', 'paid', 'put', 'read', 'run', 'said',
    'seen', 'sent', 'set', 'shown', 'shut', 'sought', 'sold', 'spent',
    'spoken', 'stood', 'struck', 'taken', 'taught', 'thought', 'told',
    'understood', 'won', 'worn', 'written',
}

# Regex for regular past participles: words ending in -ed (but not common
# adjectives that aren't really passive)
_NOT_PASSIVE = {
    'alleged', 'concerned', 'supposed', 'required', 'needed', 'united',
    'continued', 'undisputed', 'above-referenced',
}


def _is_past_participle(word: str) -> bool:
    """Heuristic: is this word likely a past participle?"""
    w = word.lower().rstrip('.,;:!?"\')]')
    if w in _IRREGULAR_PP:
        return True
    if w in _NOT_PASSIVE:
        return False
    if w.endswith('ed') and len(w) > 3:
        return True
    return False


def count_passive(sentences: list[str]) -> tuple[int, int]:
    """Count sentences with passive voice constructions.

    Returns (passive_count, total_count).
    """
    passive_count = 0

    for sentence in sentences:
        words = sentence.lower().split()
        for i, word in enumerate(words):
            clean = word.rstrip('.,;:!?"\')]')
            if clean in _BE_FORMS and i + 1 < len(words):
                # Check if next word (or word after adverb) is past participle
                for offset in (1, 2):
                    if i + offset < len(words):
                        next_w = words[i + offset]
                        if _is_past_participle(next_w):
                            passive_count += 1
                            break
                        # Allow one adverb between be-verb and participle
                        if offset == 1 and next_w.endswith('ly'):
                            continue
                        break
                break  # Only check first be-verb per sentence

    return passive_count, len(sentences)


# ---------------------------------------------------------------------------
# Nominalization detection
# ---------------------------------------------------------------------------

_NOM_SUFFIXES = ('tion', 'sion', 'ment', 'ness', 'ity', 'ence', 'ance')

# Common words with these suffixes that aren't really nominalizations
# (they're the primary/natural form, not derived from a verb)
_NOM_EXCLUSIONS = {
    'court', 'constitution', 'portion', 'position', 'condition', 'mention',
    'attention', 'question', 'section', 'station', 'nation', 'caution',
    'function', 'action', 'election', 'fashion', 'opinion', 'occasion',
    'person', 'reason', 'season', 'prison', 'lesson', 'mission', 'tension',
    'passion', 'session', 'version', 'pension', 'mansion', 'vision',
    'department', 'government', 'moment', 'comment', 'element', 'statement',
    'document', 'argument', 'apartment', 'instrument', 'amendment',
    'judgment', 'supplement', 'environment', 'tournament', 'parliament',
    'treatment', 'management', 'agreement', 'sentiment', 'appointment',
    'arrangement', 'assessment', 'employment',
    'witness', 'business', 'process', 'illness', 'fitness', 'awareness',
    'darkness', 'kindness', 'madness', 'sadness', 'weakness', 'goodness',
    'happiness', 'consciousness',
    'ability', 'activity', 'authority', 'capacity', 'city', 'community',
    'county', 'dignity', 'entity', 'facility', 'identity', 'liability',
    'majority', 'minority', 'opportunity', 'party', 'penalty', 'priority',
    'property', 'quality', 'quantity', 'reality', 'responsibility',
    'security', 'society', 'university', 'utility', 'vicinity', 'custody',
    'equity', 'felicity', 'integrity', 'liberty', 'maturity', 'necessity',
    'notoriety', 'parity', 'publicity', 'severity', 'stability',
    'evidence', 'experience', 'absence', 'audience', 'conference',
    'confidence', 'conscience', 'consequence', 'difference', 'existence',
    'fence', 'hence', 'independence', 'incidence', 'influence', 'innocence',
    'intelligence', 'interference', 'licence', 'negligence', 'offence',
    'patience', 'precedence', 'presence', 'prudence', 'reference',
    'residence', 'science', 'sentence', 'sequence', 'silence', 'violence',
    'circumstance', 'distance', 'entrance', 'finance', 'glance',
    'ignorance', 'importance', 'instance', 'insurance', 'performance',
    'substance', 'tolerance', 'relevance', 'assistance', 'compliance',
    'grievance', 'inheritance', 'maintenance', 'ordinance', 'resemblance',
    'resistance', 'significance', 'surveillance', 'temperance',
    'abundance', 'acceptance', 'accordance', 'allegiance', 'alliance',
    'allowance', 'appearance', 'appliance', 'assurance', 'attendance',
    'avoidance', 'balance', 'brilliance', 'clearance', 'dance',
    'defiance', 'dominance', 'endurance', 'fragrance', 'governance',
    'guidance', 'hindrance', 'impedance',
}


def count_nominalizations(text: str) -> tuple[int, int]:
    """Count nominalizations in text.

    Returns (nominalization_count, word_count).
    """
    words = re.findall(r"[a-zA-Z]+(?:'[a-zA-Z]+)?", text)
    word_count = len(words)
    nom_count = 0

    for word in words:
        w = word.lower()
        if len(w) < 5:
            continue
        if w in _NOM_EXCLUSIONS:
            continue
        if any(w.endswith(suffix) for suffix in _NOM_SUFFIXES):
            nom_count += 1

    return nom_count, word_count


# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------

_KNOWN_HEADINGS = {
    'FACTS', 'BACKGROUND', 'FACTUAL BACKGROUND', 'PROCEDURAL BACKGROUND',
    'FACTUAL AND PROCEDURAL BACKGROUND', 'PROCEDURAL HISTORY',
    'STANDARD OF REVIEW', 'STANDARDS OF REVIEW',
    'ANALYSIS', 'DISCUSSION', 'LAW AND ANALYSIS',
    'DISPOSITION', 'CONCLUSION', 'RELIEF',
    'ISSUES PRESENTED', 'ISSUES', 'QUESTIONS PRESENTED',
    'RECOMMENDATION', 'RECOMMENDATIONS',
    'SUMMARY', 'INTRODUCTION', 'OVERVIEW',
    'ARGUMENT', 'ARGUMENTS',
    'CONCURRENCE', 'DISSENT', 'DISSENTING OPINION', 'CONCURRING OPINION',
}

# Section headings in an opinion are bare roman numerals as often as they are
# numerals with a period, and the old pattern required the period. `I`, `II`,
# and `IV` then fell through to the ALL-CAPS branch below, which requires three
# characters -- so on a four-section opinion exactly one heading resolved, and
# it was `III`. Longest-first so `XIV` is not read as `X`.
_ROMAN_NUMERALS = ("XX XIX XVIII XVII XVI XV XIV XIII XII XI X "
                   "IX VIII VII VI V IV III II I").split()
_ROMAN_PATTERN = re.compile(
    r'^(?:' + '|'.join(_ROMAN_NUMERALS) + r'|[A-Z])\.?(?:\s+.*)?$'
)


def detect_sections(text: str) -> list[dict]:
    """Detect document sections and their paragraph ranges.

    Returns a list of dicts: {name, start_line, text, para_start, para_end}
    """
    lines = text.split('\n')

    # First, find all paragraph markers to build a line->para map
    para_map = {}     # line_index -> the paragraph that line belongs to
    marker_lines = {}  # line_index -> paragraph, only where the marker appears
    current_para = None
    for i, line in enumerate(lines):
        m = re.match(r'\[?\u00b6\s*(\d+)\]?', line)
        if not m:
            m = re.match(r'\[¶\s*(\d+)\]', line)
        if m:
            current_para = int(m.group(1))
            marker_lines[i] = current_para
        if current_para is not None:
            para_map[i] = current_para

    # Find section boundaries
    section_starts = []  # (line_index, name)

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        # Check for known heading names (ALL CAPS or title case)
        upper = stripped.upper().rstrip(':').strip()
        if upper in _KNOWN_HEADINGS:
            section_starts.append((i, stripped.rstrip(':')))
            continue

        # ALL CAPS line (at least 3 chars, not a citation or paragraph marker)
        if (len(stripped) >= 3
                and stripped == stripped.upper()
                and re.match(r'^[A-Z][A-Z\s,&\-]+$', stripped)
                and not stripped.startswith('[')
                and len(stripped.split()) <= 8):
            section_starts.append((i, stripped.rstrip(':')))
            continue

        # Roman numeral or letter heading: "I.", "II.", "A."
        if _ROMAN_PATTERN.match(stripped) and len(stripped.split()) <= 10:
            section_starts.append((i, stripped.rstrip(':')))
            continue

        # Line ending with colon preceded by blank line
        if (stripped.endswith(':')
                and i > 0
                and not lines[i - 1].strip()
                and len(stripped.split()) <= 8):
            section_starts.append((i, stripped.rstrip(':')))
            continue

    # Build sections
    sections = []
    for idx, (start_line, name) in enumerate(section_starts):
        end_line = (section_starts[idx + 1][0]
                    if idx + 1 < len(section_starts) else len(lines))
        section_text = '\n'.join(lines[start_line:end_line])

        # Determine paragraph range from the markers that actually open
        # inside the section. Using para_map here counted the heading line
        # itself, which inherits the *previous* paragraph's number, so every
        # section reported starting one paragraph early. Fall back to the
        # inherited numbering for a section that contains no marker at all.
        paras_in_section = [
            marker_lines[j] for j in range(start_line, end_line)
            if j in marker_lines
        ] or [
            para_map[j] for j in range(start_line, end_line) if j in para_map
        ]
        para_start = min(paras_in_section) if paras_in_section else None
        para_end = max(paras_in_section) if paras_in_section else None

        sections.append({
            'name': name,
            'start_line': start_line,
            'text': section_text,
            'para_start': para_start,
            'para_end': para_end,
        })

    # If no sections detected, treat entire document as one section
    if not sections:
        all_paras = list(para_map.values())
        sections = [{
            'name': 'Full Document',
            'start_line': 0,
            'text': text,
            'para_start': min(all_paras) if all_paras else None,
            'para_end': max(all_paras) if all_paras else None,
        }]

    return sections


# ---------------------------------------------------------------------------
# Per-section analysis
# ---------------------------------------------------------------------------

def analyze_section(name: str, text: str, para_range: tuple) -> dict:
    """Analyze a single section and return metrics."""
    sentences = split_sentences(text)
    if not sentences:
        return {
            'name': name,
            'para_range': _format_range(para_range),
            'word_count': 0,
            'fk_grade': 0,
            'avg_sentence_length': 0,
            'longest_sentence': 0,
            'passive_pct': 0,
            'nominalization_density': 0,
        }

    # Word count and sentence lengths
    sentence_lengths = [len(s.split()) for s in sentences]
    word_count = sum(sentence_lengths)
    avg_sentence_length = round(word_count / len(sentences), 1) if sentences else 0
    longest_sentence = max(sentence_lengths) if sentence_lengths else 0

    # Flesch-Kincaid. Named `grade`, not `fk_grade`: assigning to the
    # function's own name makes it local for the whole function body, so the
    # call on the right raised UnboundLocalError and every section with text
    # in it failed. Introduced in 4.21.0 when fk_grade became module-level.
    grade = round(fk_grade(text), 1)

    # Passive voice
    passive_count, total_sents = count_passive(sentences)
    passive_pct = round(100 * passive_count / total_sents, 1) if total_sents else 0

    # Nominalizations
    nom_count, wc = count_nominalizations(text)
    nom_density = round(100 * nom_count / wc, 1) if wc else 0

    return {
        'name': name,
        'para_range': _format_range(para_range),
        'word_count': word_count,
        'fk_grade': grade,
        'avg_sentence_length': avg_sentence_length,
        'longest_sentence': longest_sentence,
        'passive_pct': passive_pct,
        'nominalization_density': nom_density,
    }


def _format_range(para_range: tuple) -> str:
    """Format a (start, end) paragraph range as a string."""
    start, end = para_range
    if start is None:
        return "—"
    if start == end:
        return str(start)
    return f"{start}\u2013{end}"


# ---------------------------------------------------------------------------
# Document-level analysis
# ---------------------------------------------------------------------------

_PARA_MARKER_RE = re.compile(r'\[?[¶\u00b6]\s*(\d+)\]?')


def paragraph_blocks(text: str) -> list[tuple[int | None, str]]:
    """(paragraph number, block text) for each ``[¶N]``-marked block, in order.

    Flags are keyed by walking these rather than by searching the document for
    a sentence's own opening words. A phrase that recurs -- and in an opinion
    "The district court found that" recurs constantly -- resolves to its first
    occurrence, so a flag belonging to ¶ 30 was reported at ¶ 4. Any text
    before the first marker is yielded under None.
    """
    marks = list(_PARA_MARKER_RE.finditer(text))
    if not marks:
        return [(None, text)]
    blocks: list[tuple[int | None, str]] = []
    head = text[:marks[0].start()]
    if head.strip():
        blocks.append((None, head))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        blocks.append((int(m.group(1)), text[m.start():end]))
    return blocks


def _find_para_for_line(text: str, char_offset: int) -> int | None:
    """Find the paragraph number for a character offset in the text."""
    prefix = text[:char_offset]
    # Find the last paragraph marker before this offset
    matches = list(re.finditer(r'\[?[¶\u00b6]\s*(\d+)\]?', prefix))
    if matches:
        return int(matches[-1].group(1))
    return None


def analyze_document(text: str) -> dict:
    """Analyze the full document and return metrics + flags."""
    sections = detect_sections(text)

    # Overall metrics
    all_sentences = split_sentences(text)
    all_lengths = [len(s.split()) for s in all_sentences]
    total_words = sum(all_lengths)
    total_sents = len(all_sentences)

    overall_fk = round(fk_grade(text), 1)
    avg_sent_len = round(total_words / total_sents, 1) if total_sents else 0

    passive_count, _ = count_passive(all_sentences)
    passive_pct = round(100 * passive_count / total_sents, 1) if total_sents else 0

    nom_count, wc = count_nominalizations(text)
    nom_density = round(100 * nom_count / wc, 1) if wc else 0

    overall = {
        'word_count': total_words,
        'sentence_count': total_sents,
        'avg_sentence_length': avg_sent_len,
        'fk_grade': overall_fk,
        'passive_pct': passive_pct,
        'nominalization_density': nom_density,
    }

    # Per-section metrics
    section_results = []
    for sec in sections:
        para_range = (sec['para_start'], sec['para_end'])
        result = analyze_section(sec['name'], sec['text'], para_range)
        section_results.append(result)

    # Generate flags
    flags = []

    # Flag long sentences (> 40 words)
    for para, block in paragraph_blocks(text):
        for sentence in split_sentences(block):
            words = sentence.split()
            if len(words) <= 40:
                continue
            preview = ' '.join(words[:10]) + '...'
            flags.append({
                'para': para,
                'type': 'long_sentence',
                'value': len(words),
                'text': preview,
            })

    # Flag high passive and high FK grade per section
    for sec_result in section_results:
        if sec_result['passive_pct'] > 25 and sec_result['word_count'] > 50:
            flags.append({
                'para': None,
                'type': 'high_passive',
                'section': sec_result['name'],
                'value': sec_result['passive_pct'],
            })
        if sec_result['fk_grade'] > 16 and sec_result['word_count'] > 50:
            flags.append({
                'para': None,
                'type': 'high_fk_grade',
                'section': sec_result['name'],
                'value': sec_result['fk_grade'],
            })

    return {
        'overall': overall,
        'sections': section_results,
        'flags': flags,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Compute readability metrics for legal documents."
    )
    parser.add_argument("--file", "-f", required=True,
                        help="Path to the document file (markdown or text)")
    parser.add_argument("--json", action="store_true",
                        help="Pretty-print JSON output (default is compact)")
    args = parser.parse_args()

    path = Path(args.file).expanduser()
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    text = path.read_text(encoding="utf-8")
    result = analyze_document(text)

    # ensure_ascii=False emits real en dashes in para_range; on a cp1252
    # console that reaches the file as mojibake ("17?32"). Reported from a
    # Windows run.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    indent = 2 if args.json else None
    print(json.dumps(result, indent=indent, ensure_ascii=False))


if __name__ == "__main__":
    main()

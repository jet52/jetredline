"""Tests for voice_search.py — runs a voice file's Search: patterns on a draft."""

import json

import voice_search

VOICE = """# Writing in my voice

## Avoid
- Sentence-initial "However,".

## Flag in any draft I review
- **"Case law."** Name the source instead.
  Search: `\\bcase[ -]?law\\b`
- **Rebuttable "conclusive" presumptions.** Flag them.
  Search: `\\bconclusive(?:ly)?\\b(?:(?!\\n\\s*\\n).){0,300}?\\b(?:unless|absent)\\b`
"""

DRAFT = """[¶1] Smith appeals. We affirm.

[¶2] Our case law says so. See Doe v. Roe, 2020 ND 1, ¶ 4.

[¶3] A statute carries a presumption of constitutionality, which is
conclusive unless the challenger clearly demonstrates otherwise.

[¶4] The presumption is conclusive.

Absent a showing, we affirm.
"""


def run(tmp_path, capsys, *extra, voice=VOICE, draft=DRAFT):
    v = tmp_path / "voice.md"
    d = tmp_path / "draft.md"
    v.write_text(voice, encoding="utf-8")
    d.write_text(draft, encoding="utf-8")
    code = voice_search.main([*extra, str(v), str(d)])
    return code, capsys.readouterr().out


def test_labels_come_from_bold_text():
    pats = voice_search.load_patterns(VOICE)
    assert [label for label, _ in pats] == [
        '"Case law."', 'Rebuttable "conclusive" presumptions.']


def test_hits_report_paragraph_marker_not_pincite(tmp_path, capsys):
    code, out = run(tmp_path, capsys, "--json")
    hits = json.loads(out)
    assert code == 0
    assert [(h["rule"], h["para"]) for h in hits] == [
        ('"Case law."', "2"),
        ('Rebuttable "conclusive" presumptions.', "3"),
    ]


def test_match_does_not_cross_a_blank_line(tmp_path, capsys):
    # ¶4's "conclusive" is followed by "Absent" only after a blank line.
    _, out = run(tmp_path, capsys)
    assert "¶4" not in out


def test_no_hits_exits_1(tmp_path, capsys):
    code, out = run(tmp_path, capsys, draft="[¶1] We affirm.\n")
    assert code == 1 and out == ""


def test_voice_file_without_patterns_exits_1(tmp_path, capsys):
    code, _ = run(tmp_path, capsys, voice="# Voice\n- Be brief.\n")
    assert code == 1


def test_invalid_pattern_exits_2(tmp_path, capsys):
    code, _ = run(tmp_path, capsys, voice="- **Bad.**\n  Search: `(`\n")
    assert code == 2


def test_missing_file_exits_2(tmp_path, capsys):
    code = voice_search.main([str(tmp_path / "nope.md"), str(tmp_path / "x.md")])
    assert code == 2

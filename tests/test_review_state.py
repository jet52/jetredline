"""Tests for review_state.py — cite-review marks round-trip."""

import json

import pytest

from review_state import (
    FILENAME_GLOB,
    SCHEMA,
    SCHEMA_VERSION,
    StateFileError,
    build_restore,
    content_key,
    counts,
    find_latest,
    load,
    safe_case_id,
    state_key,
)


def payload(entries, **kw):
    p = {"schema": SCHEMA, "schema_version": SCHEMA_VERSION,
         "case_id": "20990001", "title": "t", "entries": entries}
    p.update(kw)
    return p


def cite(text, para, occ=0, status="verified", notes=""):
    return {"kind": "cite", "cite_text": text, "para_num": para,
            "occurrence": occ, "status": status, "notes": notes}


def datum(text, para, occ=0, position=None, kind="cite"):
    d = {"kind": kind, "para_num": para, "occurrence": occ, "position": position}
    if kind == "fact":
        d["claim"] = text
    else:
        d["cite_text"] = text
    return d


# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------

class TestKeys:
    def test_state_key_matches_the_page_convention(self):
        assert state_key("cite", 1234, 0) == "p1234"
        assert state_key("fact", 1234, 0) == "fp1234"
        assert state_key("cite", None, 7) == "i7"
        assert state_key("fact", None, 7) == "fi7"

    def test_content_key_normalizes_whitespace(self):
        assert content_key("cite", "2020  ND\n30", 1, 0) == \
               content_key("cite", "2020 ND 30", 1, 0)

    def test_facts_and_cites_never_collide(self):
        assert content_key("fact", "x", 1, 0) != content_key("cite", "x", 1, 0)

    def test_safe_case_id_strips_path_characters(self):
        assert safe_case_id("20990001 State v. Baker/OP1") == \
               "20990001-State-v.-Baker-OP1"
        assert safe_case_id("") == "review"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

class TestLoad:
    def test_round_trips_a_valid_file(self, tmp_path):
        f = tmp_path / "s.json"
        f.write_text(json.dumps(payload([cite("2020 ND 30", 1)])), encoding="utf-8")
        assert load(f)["case_id"] == "20990001"

    def test_rejects_foreign_json(self, tmp_path):
        f = tmp_path / "s.json"
        f.write_text('{"hello": "world"}', encoding="utf-8")
        with pytest.raises(StateFileError, match="not a cite-review state file"):
            load(f)

    def test_rejects_a_future_schema_version(self, tmp_path):
        f = tmp_path / "s.json"
        f.write_text(json.dumps(payload([], schema_version=99)), encoding="utf-8")
        with pytest.raises(StateFileError, match="schema version"):
            load(f)

    def test_rejects_malformed_json(self, tmp_path):
        f = tmp_path / "s.json"
        f.write_text("{not json", encoding="utf-8")
        with pytest.raises(StateFileError, match="not valid JSON"):
            load(f)

    def test_rejects_missing_entries(self, tmp_path):
        f = tmp_path / "s.json"
        f.write_text(json.dumps({"schema": SCHEMA,
                                 "schema_version": SCHEMA_VERSION}), encoding="utf-8")
        with pytest.raises(StateFileError, match="entries"):
            load(f)


# ---------------------------------------------------------------------------
# Finding the newest export
# ---------------------------------------------------------------------------

class TestFindLatest:
    def _mk(self, d, name):
        (d / name).write_text("{}", encoding="utf-8")

    def test_picks_the_newest_by_embedded_stamp(self, tmp_path):
        self._mk(tmp_path, "cite-review-state__abc__20991231-090000.json")
        self._mk(tmp_path, "cite-review-state__abc__20991231-170000.json")
        self._mk(tmp_path, "cite-review-state__abc__20260101-090000.json")
        assert find_latest(tmp_path).name.endswith("20991231-170000.json")

    def test_filters_by_case_id(self, tmp_path):
        self._mk(tmp_path, "cite-review-state__abc__20991231-090000.json")
        self._mk(tmp_path, "cite-review-state__xyz__20991231-170000.json")
        got = find_latest(tmp_path, "abc")
        assert got is not None and "__abc__" in got.name

    def test_ignores_unrelated_json(self, tmp_path):
        self._mk(tmp_path, "manifest.json")
        self._mk(tmp_path, "cite-review-state.json")   # old flat name
        assert find_latest(tmp_path) is None

    def test_missing_directory_is_not_an_error(self, tmp_path):
        assert find_latest(tmp_path / "nope") is None

    def test_glob_constant_matches_the_naming(self, tmp_path):
        self._mk(tmp_path, "cite-review-state__abc__20991231-090000.json")
        assert list(tmp_path.glob(FILENAME_GLOB))


# ---------------------------------------------------------------------------
# Restoring
# ---------------------------------------------------------------------------

class TestRestore:
    def test_exact_match_restores_to_the_new_offset(self):
        p = payload([cite("2020 ND 30", 1, status="verified", notes="ok")])
        data = [datum("2020 ND 30", 1, position=500)]
        r = build_restore(p, data)
        assert r.restored == 1
        assert r.state == {"p500": {"status": "verified", "notes": "ok"}}

    def test_offsets_moving_does_not_break_the_match(self):
        # The whole point: the mark follows the citation, not the offset.
        p = payload([cite("2020 ND 30", 1)])
        r = build_restore(p, [datum("2020 ND 30", 1, position=9999)])
        assert r.state == {"p9999": {"status": "verified", "notes": ""}}

    def test_occurrence_distinguishes_repeats_in_one_paragraph(self):
        p = payload([cite("Id.", 3, occ=0, status="verified"),
                     cite("Id.", 3, occ=1, status="flagged")])
        data = [datum("Id.", 3, occ=0, position=10),
                datum("Id.", 3, occ=1, position=20)]
        r = build_restore(p, data)
        assert r.state["p10"]["status"] == "verified"
        assert r.state["p20"]["status"] == "flagged"

    def test_vanished_citation_is_dropped_not_guessed(self):
        p = payload([cite("2020 ND 30", 1), cite("445 U.S. 684", 2)])
        r = build_restore(p, [datum("2020 ND 30", 1, position=5)])
        assert r.restored == 1
        assert len(r.dropped) == 1 and "445 U.S. 684" in r.dropped[0]

    def test_renumbering_rematches_a_unique_citation(self):
        # A paragraph inserted above renumbers everything below it.
        p = payload([cite("445 U.S. 684", 2, status="flagged", notes="n")])
        r = build_restore(p, [datum("445 U.S. 684", 7, position=800)])
        assert r.restored == 1
        assert r.rematched == ["445 U.S. 684"]
        assert r.state["p800"] == {"status": "flagged", "notes": "n"}

    def test_ambiguous_label_is_never_rematched(self):
        # "Id." appears twice on the new side: no unique answer, so the mark
        # is dropped rather than attached to the wrong one.
        p = payload([cite("Id.", 3, occ=0)])
        data = [datum("Id.", 9, occ=0, position=10),
                datum("Id.", 9, occ=1, position=20)]
        r = build_restore(p, data)
        assert r.restored == 0
        assert r.state == {}
        assert r.dropped

    def test_ambiguous_on_the_export_side_is_also_refused(self):
        p = payload([cite("Id.", 3, occ=0), cite("Id.", 4, occ=0)])
        r = build_restore(p, [datum("Id.", 9, occ=0, position=10)])
        assert r.restored == 0

    def test_unreviewed_entries_carry_nothing(self):
        p = payload([cite("2020 ND 30", 1, status=None, notes="")])
        r = build_restore(p, [datum("2020 ND 30", 1, position=5)])
        assert r.marks_in_file == 0 and r.state == {}

    def test_a_note_without_a_status_still_carries(self):
        p = payload([cite("2020 ND 30", 1, status=None, notes="check vol.")])
        r = build_restore(p, [datum("2020 ND 30", 1, position=5)])
        assert r.state["p5"] == {"status": None, "notes": "check vol."}

    def test_facts_restore_under_the_fact_prefix(self):
        p = payload([{"kind": "fact", "claim": "The car was red",
                      "para_num": 4, "occurrence": 0,
                      "status": "flagged", "notes": ""}])
        r = build_restore(p, [datum("The car was red", 4, position=77, kind="fact")])
        assert r.state == {"fp77": {"status": "flagged", "notes": ""}}

    def test_draft_change_is_reported(self):
        p = payload([cite("2020 ND 30", 1)], draft_sha256="aaa")
        r = build_restore(p, [datum("2020 ND 30", 1, position=5)], draft_sha="bbb")
        assert r.draft_changed
        assert "draft has changed" in r.summary()

    def test_same_draft_is_not_reported_as_changed(self):
        p = payload([cite("2020 ND 30", 1)], draft_sha256="aaa")
        r = build_restore(p, [datum("2020 ND 30", 1, position=5)], draft_sha="aaa")
        assert not r.draft_changed

    def test_summary_counts_marks_not_entries(self):
        p = payload([cite("2020 ND 30", 1), cite("445 U.S. 684", 2, status=None)])
        r = build_restore(p, [datum("2020 ND 30", 1, position=5)])
        assert r.marks_in_file == 1
        assert "restored 1 of 1" in r.summary()


class TestCounts:
    def test_tallies_by_status(self):
        p = payload([cite("a", 1, status="verified"),
                     cite("b", 1, status="flagged"),
                     cite("c", 1, status="skipped"),
                     cite("d", 1, status=None)])
        assert counts(p) == {"total": 4, "verified": 1, "flagged": 1,
                             "skipped": 1, "unreviewed": 1}

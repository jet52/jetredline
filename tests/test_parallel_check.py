"""Tests for parallel_check.py — parallel-citation consistency."""

import pytest

from parallel_check import (
    CONSISTENT,
    MISMATCH,
    NOT_FOUND,
    UNVERIFIED,
    Resolver,
    build_groups,
    check_citations,
    check_group,
    fold,
)


def ent(norm, parallel=None, **kw):
    d = {"normalized": norm, "cite_type": kw.pop("cite_type", "case")}
    if parallel:
        d["parallel_cite"] = parallel
    d.update(kw)
    return d


class FakeResolver(Resolver):
    """Table-driven resolver. ``claimed`` is the authority boundary."""

    def __init__(self, name, claimed, table):
        self.name = name
        self._claimed = {fold(c) for c in claimed}
        self._table = {fold(k): v for k, v in table.items()}
        self.calls = []

    def claims(self, cite):
        return fold(cite) in self._claimed

    def lookup(self, cite):
        self.calls.append(cite)
        return self._table.get(fold(cite))


WHALEN = {"case_name": "Whalen v. United States",
          "citations": ["445 U.S. 684", "100 S. Ct. 1432", "63 L. Ed. 2d 715"]}
PAYTON = {"case_name": "Payton v. New York",
          "citations": ["445 U.S. 573", "100 S. Ct. 1371", "63 L. Ed. 2d 639"]}


# ---------------------------------------------------------------------------
# fold / grouping
# ---------------------------------------------------------------------------

class TestFold:
    def test_spacing_and_case_ignored(self):
        assert fold("100 S. Ct. 1432") == fold("100 S.Ct. 1432") == fold("100 s ct 1432")

    def test_distinct_cites_differ(self):
        assert fold("100 S. Ct. 1432") != fold("100 S. Ct. 1371")


class TestBuildGroups:
    def test_transitive_closure_over_pairwise_links(self):
        # jetcite records only parallel_cites[0], so a trio arrives as a chain
        ents = [ent("445 U.S. 684", "100 S. Ct. 1371"),
                ent("100 S. Ct. 1371", "445 U.S. 684"),
                ent("63 L. Ed. 2d 639", "100 S. Ct. 1371")]
        groups = build_groups(ents)
        assert len(groups) == 1
        assert set(groups[0]) == {"445 U.S. 684", "100 S. Ct. 1371",
                                  "63 L. Ed. 2d 639"}

    def test_singletons_are_not_groups(self):
        assert build_groups([ent("543 N.W.2d 491")]) == []

    def test_repeats_and_pins_excluded(self):
        ents = [ent("2024 ND 156", "10 N.W.3d 500"),
                ent("10 N.W.3d 500", "2024 ND 156"),
                ent("2024 ND 156", "10 N.W.3d 500", is_repeat=True),
                ent("2024 ND 156", "10 N.W.3d 500", cite_type="pin_cite")]
        groups = build_groups(ents)
        assert len(groups) == 1
        assert sorted(groups[0]) == ["10 N.W.3d 500", "2024 ND 156"]

    def test_two_independent_groups(self):
        ents = [ent("445 U.S. 684", "100 S. Ct. 1432"),
                ent("100 S. Ct. 1432", "445 U.S. 684"),
                ent("2020 ND 30", "938 N.W.2d 897"),
                ent("938 N.W.2d 897", "2020 ND 30")]
        assert len(build_groups(ents)) == 2


# ---------------------------------------------------------------------------
# verdicts
# ---------------------------------------------------------------------------

class TestCheckGroup:
    def _fed(self, table):
        return FakeResolver("CourtListener",
                            ["445 U.S. 684", "100 S. Ct. 1432", "100 S. Ct. 1371",
                             "63 L. Ed. 2d 715", "63 L. Ed. 2d 639",
                             "100 S. Ct. 999999"],
                            table)

    def test_consistent_group_collapses(self):
        r = self._fed({"445 U.S. 684": WHALEN, "100 S. Ct. 1432": WHALEN})
        v = check_group(["445 U.S. 684", "100 S. Ct. 1432"], [r])
        assert v.status == CONSISTENT
        assert not v.blocks_collapse
        assert v.case_name == "Whalen v. United States"

    def test_wrong_parallel_is_mismatch_and_blocks(self):
        r = self._fed({"445 U.S. 684": WHALEN, "100 S. Ct. 1371": PAYTON})
        v = check_group(["445 U.S. 684", "100 S. Ct. 1371"], [r])
        assert v.status == MISMATCH
        assert v.blocks_collapse
        assert "Payton" in v.detail and "Whalen" in v.detail

    def test_bogus_page_conflicts_with_recorded_cite_of_same_series(self):
        # 999999 resolves to nothing, but Whalen's record carries a S. Ct.
        # cite — so the source does speak to this series, and it differs.
        r = self._fed({"445 U.S. 684": WHALEN})
        v = check_group(["445 U.S. 684", "100 S. Ct. 999999"], [r])
        assert v.status == MISMATCH
        assert v.blocks_collapse
        assert "100 S. Ct. 1432" in v.detail   # names the correct cite

    def test_no_resolver_is_unverified_and_collapses(self):
        v = check_group(["2020 ND 30", "938 N.W.2d 897"], [])
        assert v.status == UNVERIFIED
        assert not v.blocks_collapse

    def test_member_only_in_anchor_set_is_confirmed_without_lookup(self):
        # 63 L. Ed. 2d 715 is in Whalen's citation set, so it needs no call
        r = self._fed({"445 U.S. 684": WHALEN})
        v = check_group(["445 U.S. 684", "63 L. Ed. 2d 715"], [r])
        assert v.status == CONSISTENT
        assert "63 L. Ed. 2d 715" not in r.calls

    def test_anchor_falls_through_to_a_resolvable_member(self):
        # first member unresolvable, second anchors the group
        r = self._fed({"100 S. Ct. 1432": WHALEN})
        v = check_group(["445 U.S. 684", "100 S. Ct. 1432"], [r])
        assert v.status == CONSISTENT


class TestAuthorityBoundary:
    """A source may only produce a negative for reporters it claims."""

    def test_non_claiming_source_silence_is_unverified_not_mismatch(self):
        # CourtListener does not claim ND reporters. Its silence about
        # 938 N.W.2d 897 must never read as "wrong".
        cl = FakeResolver("CourtListener", ["445 U.S. 684"], {})
        v = check_group(["2020 ND 30", "938 N.W.2d 897"], [cl])
        assert v.status == UNVERIFIED
        assert not v.blocks_collapse

    def test_recorded_rival_in_same_series_is_a_conflict(self):
        # The corpus records 938 N.W.2d 897 for this case; the draft says 879.
        nd = FakeResolver("the ND corpus", ["2020 ND 30", "938 N.W.2d 879"],
                          {"2020 ND 30": {"case_name": "State v. Thomas",
                                          "citations": ["2020 ND 30",
                                                        "938 N.W.2d 897"]}})
        v = check_group(["2020 ND 30", "938 N.W.2d 879"], [nd])
        assert v.status == MISMATCH
        assert v.blocks_collapse
        assert "938 N.W.2d 897" in v.detail

    def test_corpus_gap_in_a_series_is_not_a_finding(self):
        # Regression: a recent ND opinion whose N.W.3d assignment the corpus
        # has not recorded. Absence of the series is a gap, not evidence that
        # the draft's parallel is wrong.
        nd = FakeResolver("the ND corpus", ["2024 ND 156", "10 N.W.3d 500"],
                          {"2024 ND 156": {"case_name": "Fiebiger v. Anderson",
                                           "citations": ["2024 ND 156"]}})
        v = check_group(["2024 ND 156", "10 N.W.3d 500"], [nd])
        assert v.status == UNVERIFIED
        assert not v.blocks_collapse
        assert "no nw cite recorded" in v.detail

    def test_group_with_no_resolvable_member_but_claiming_source(self):
        nd = FakeResolver("the ND corpus", ["2099 ND 1", "999 N.W.3d 1"], {})
        v = check_group(["2099 ND 1", "999 N.W.3d 1"], [nd])
        assert v.status == NOT_FOUND
        assert v.blocks_collapse

    def test_nd_group_uses_nd_resolver_not_courtlistener(self):
        nd = FakeResolver("the ND corpus", ["2020 ND 30", "938 N.W.2d 897"],
                          {"2020 ND 30": {"case_name": "State v. Thomas",
                                          "citations": ["2020 ND 30",
                                                        "938 N.W.2d 897"]}})
        cl = FakeResolver("CourtListener", ["2020 ND 30"],
                          {"2020 ND 30": {"case_name": "State v. Thomas",
                                          "citations": ["2020 ND 30"]}})
        v = check_group(["2020 ND 30", "938 N.W.2d 897"], [nd, cl])
        assert v.status == CONSISTENT
        assert cl.calls == []          # ND resolver claimed it first


class TestCheckCitations:
    def test_every_member_maps_to_its_group_verdict(self):
        r = FakeResolver("CourtListener",
                         ["445 U.S. 684", "100 S. Ct. 1371"],
                         {"445 U.S. 684": WHALEN, "100 S. Ct. 1371": PAYTON})
        ents = [ent("445 U.S. 684", "100 S. Ct. 1371"),
                ent("100 S. Ct. 1371", "445 U.S. 684")]
        verdicts = check_citations(ents, [r])
        assert verdicts[fold("445 U.S. 684")].status == MISMATCH
        assert verdicts[fold("100 S. Ct. 1371")] is verdicts[fold("445 U.S. 684")]

    def test_lookups_are_cached_across_groups(self):
        r = FakeResolver("CourtListener",
                         ["445 U.S. 684", "100 S. Ct. 1432"],
                         {"445 U.S. 684": WHALEN, "100 S. Ct. 1432": WHALEN})
        ents = [ent("445 U.S. 684", "100 S. Ct. 1432"),
                ent("100 S. Ct. 1432", "445 U.S. 684")]
        check_citations(ents, [r])
        assert r.calls.count("445 U.S. 684") == 1


# ---------------------------------------------------------------------------
# Regression: parallel cycle in the collapse (pre-existing hang)
# ---------------------------------------------------------------------------

class TestAliasCycle:
    """A S. Ct./L. Ed. pair naming each other looped forever in
    _dedup_parallel_citations, and would have dropped both — deleting the
    authority from review. Reproduced by a pin page breaking the U.S. link:
    "445 U.S. 684, 691, 100 S. Ct. 1371, 63 L. Ed. 2d 715".
    """

    CYCLE = [
        {"normalized": "100 S. Ct. 1371", "cite_type": "federal_reporter",
         "cite_text": "100 S. Ct. 1371", "parallel_cite": "63 L. Ed. 2d 715"},
        {"normalized": "63 L. Ed. 2d 715", "cite_type": "federal_reporter",
         "cite_text": "63 L. Ed. 2d 715", "parallel_cite": "100 S. Ct. 1371"},
    ]

    def test_terminates(self):
        from cite_review import _dedup_parallel_citations
        kept, alias = _dedup_parallel_citations([dict(c) for c in self.CYCLE])
        assert isinstance(kept, list)   # reaching here at all is the assertion

    def test_authority_survives_the_collapse(self):
        from cite_review import _dedup_parallel_citations
        kept, alias = _dedup_parallel_citations([dict(c) for c in self.CYCLE])
        assert len(kept) == 1, "collapsing a cycle must not delete the authority"
        assert kept[0]["normalized"] == "100 S. Ct. 1371"   # first in document order

    def test_dropped_member_aliases_to_the_elected_lead(self):
        from cite_review import _dedup_parallel_citations
        _kept, alias = _dedup_parallel_citations([dict(c) for c in self.CYCLE])
        assert alias.get("63 L. Ed. 2d 715") == "100 S. Ct. 1371"
        assert "100 S. Ct. 1371" not in alias   # the lead aliases to nothing

    def test_flagged_cycle_keeps_both_rows(self):
        from cite_review import _dedup_parallel_citations
        from parallel_check import MISMATCH, Verdict
        v = Verdict(MISMATCH, ["100 S. Ct. 1371", "63 L. Ed. 2d 715"],
                    detail="different cases")
        verdicts = {fold(m): v for m in v.members}
        kept, _alias = _dedup_parallel_citations(
            [dict(c) for c in self.CYCLE], verdicts)
        assert len(kept) == 2
        assert all(c["parallel_status"] == MISMATCH for c in kept)

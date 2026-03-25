"""Shared fixtures for jetredline tests."""

import sys
from pathlib import Path

import pytest

# Add the skill directory to sys.path so we can import modules directly
SKILL_DIR = Path(__file__).resolve().parent.parent / "skills" / "jetredline"
sys.path.insert(0, str(SKILL_DIR))


@pytest.fixture
def refs_dir(tmp_path):
    """Create a minimal refs directory with sample opinion files."""
    opin_dir = tmp_path / "opin" / "markdown" / "2023"
    opin_dir.mkdir(parents=True)

    # Tracey v. Tracey — the case from the TODO example
    (opin_dir / "2023ND219.md").write_text(
        "IN THE SUPREME COURT\n"
        "STATE OF NORTH DAKOTA\n\n"
        "2023 ND 219\n\n"
        "Monica Tracey,\n\n"
        "v.\n\n"
        "David Tracey,\n\n"
        "Petitioner\n\n"
        "Respondent and Appellant\n\n"
        "[¶1] This is the opinion text for Tracey v. Tracey.\n\n"
        "[¶2] The district court found that Tracey had not met the burden.\n",
        encoding="utf-8",
    )

    # A short opinion for testing
    opin_2024 = tmp_path / "opin" / "markdown" / "2024"
    opin_2024.mkdir(parents=True)
    (opin_2024 / "2024ND42.md").write_text(
        "IN THE SUPREME COURT\n"
        "STATE OF NORTH DAKOTA\n\n"
        "2024 ND 42\n\n"
        "State of North Dakota,\n\n"
        "v.\n\n"
        "John Henderson,\n\n"
        "Plaintiff and Appellee\n\n"
        "Defendant and Appellant\n\n"
        "[¶1] Henderson appeals from a criminal judgment.\n\n"
        "[¶2] We affirm.\n",
        encoding="utf-8",
    )

    return tmp_path


@pytest.fixture
def sample_opinion():
    """Return sample opinion markdown text with ¶ markers and citations."""
    return (
        "[¶1] This appeal arises from a divorce proceeding. "
        "In Tracey v. Tracey, 2023 ND 219, ¶ 5, we held that the "
        "district court did not abuse its discretion.\n\n"
        "[¶2] The relevant statute is N.D.C.C. § 14-05-24. "
        'Under the "clearly erroneous" standard, we defer to the '
        "district court's factual findings. Tracy v. Tracy, 2024 ND 195, ¶ 10.\n\n"
        "[¶3] Henderson argues that the court erred. "
        "State v. Henderson, 2024 ND 42, ¶ 8. We disagree.\n\n"
        "[¶4] We also considered Hogen v. Hogen, 226 N.W.2d 640 (N.D. 1975), "
        "which established the framework.\n"
    )

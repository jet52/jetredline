"""Tests for bootstrap_env.py — venv/node bootstrap tier selection."""

import sys
import venv
from pathlib import Path

import pytest

import bootstrap_env


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def test_import_names_maps_extras_and_dashes(tmp_path):
    req = tmp_path / "requirements.txt"
    req.write_text(
        "defusedxml\nhttpx[socks]>=0.27\n# comment\n\nPy-Pdf>=3\nPyMuPDF>=1.24.0\n")
    assert bootstrap_env.import_names(req) == [
        "defusedxml", "httpx", "socksio", "py_pdf", "fitz",
    ]


def test_import_names_missing_file(tmp_path):
    assert bootstrap_env.import_names(tmp_path / "nope.txt") == []


def test_read_version(tmp_path):
    (tmp_path / "VERSION").write_text("4.11.0\n")
    assert bootstrap_env.read_version(tmp_path) == "4.11.0"
    assert bootstrap_env.read_version(tmp_path / "nowhere") == "dev"


def test_read_version_json_and_frontmatter_fallbacks(tmp_path):
    (tmp_path / "version.json").write_text('{"version": "1.2.3"}')
    assert bootstrap_env.read_version(tmp_path) == "1.2.3"
    fm = tmp_path / "fm"
    fm.mkdir()
    (fm / "SKILL.md").write_text("---\nname: foo\nversion: 7.8.9\n---\nbody\n")
    assert bootstrap_env.read_version(fm) == "7.8.9"


def test_skill_name_from_frontmatter_else_dirname(tmp_path):
    d = tmp_path / "skill"
    d.mkdir()
    assert bootstrap_env.skill_name(d) == "skill"
    (d / "SKILL.md").write_text('---\nname: jetfoo\ndescription: "a: b"\n---\n')
    assert bootstrap_env.skill_name(d) == "jetfoo"


def test_venv_python_selects_posix_and_windows_layouts(tmp_path):
    assert bootstrap_env.venv_python(tmp_path) is None
    posix = tmp_path / "bin" / "python"
    posix.parent.mkdir()
    posix.touch()
    assert bootstrap_env.venv_python(tmp_path) == posix
    win = tmp_path / "Scripts" / "python.exe"
    win.parent.mkdir()
    win.touch()
    # POSIX layout wins when both exist (never true in practice)
    assert bootstrap_env.venv_python(tmp_path) == posix


# ---------------------------------------------------------------------------
# Tier selection (real venvs, empty requirements — fast, no network)
# ---------------------------------------------------------------------------

@pytest.fixture
def skill_dir(tmp_path):
    d = tmp_path / "skill"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: jetredline\n---\n")
    (d / "VERSION").write_text("9.9.9")
    (d / "requirements.txt").write_text("")  # no deps -> no pip, no network
    return d


def test_tier1_prebuilt_venv_wins(skill_dir, tmp_path):
    venv.create(skill_dir / ".venv", with_pip=False)
    python = bootstrap_env.ensure_venv(
        skill_dir, tmp_path / "cache", tmp_path / "tmp")
    assert python is not None
    assert (skill_dir / ".venv") in python.parents
    assert not (tmp_path / "cache").exists()


def test_tier2_builds_version_keyed_cache(skill_dir, tmp_path):
    python = bootstrap_env.ensure_venv(
        skill_dir, tmp_path / "cache", tmp_path / "tmp")
    assert python is not None
    expected = tmp_path / "cache" / "jetredline" / "9.9.9" / "venv"
    assert expected in python.parents
    assert python.exists()


def test_tier2_reuses_existing_cache(skill_dir, tmp_path):
    first = bootstrap_env.ensure_venv(
        skill_dir, tmp_path / "cache", tmp_path / "tmp")
    mtime = first.stat().st_mtime
    second = bootstrap_env.ensure_venv(
        skill_dir, tmp_path / "cache", tmp_path / "tmp")
    assert second == first
    assert second.stat().st_mtime == mtime  # not rebuilt


def test_tier3_tmp_when_cache_unwritable(skill_dir, tmp_path, monkeypatch):
    def deny_cache(venv_dir, requirements):
        if "unwritable-cache" in str(venv_dir):
            return None
        return real_build(venv_dir, requirements)

    real_build = bootstrap_env.build_venv
    monkeypatch.setattr(bootstrap_env, "build_venv", deny_cache)
    python = bootstrap_env.ensure_venv(
        skill_dir, tmp_path / "unwritable-cache", tmp_path / "tmp")
    assert python is not None
    assert (tmp_path / "tmp" / "jetredline-venv") in python.parents


def test_corrupt_cache_venv_is_rebuilt(skill_dir, tmp_path):
    # A venv dir whose python exists but cannot run -> rmtree + rebuild.
    stub = tmp_path / "cache" / "jetredline" / "9.9.9" / "venv" / "bin"
    stub.mkdir(parents=True)
    (stub / "python").touch()
    (skill_dir / "requirements.txt").write_text("defusedxml\n")
    python = bootstrap_env.ensure_venv(
        skill_dir, tmp_path / "cache", tmp_path / "tmp")
    assert python is not None
    r = __import__("subprocess").run(
        [str(python), "-c", "import defusedxml"], capture_output=True)
    assert r.returncode == 0


# ---------------------------------------------------------------------------
# Node path resolution (no npm invocation)
# ---------------------------------------------------------------------------

def test_node_prefers_bundled_modules(skill_dir, tmp_path):
    (skill_dir / "node_modules" / "docx").mkdir(parents=True)
    got = bootstrap_env.ensure_node(skill_dir, tmp_path / "cache")
    assert got == skill_dir / "node_modules"


def test_node_reuses_cache(skill_dir, tmp_path):
    cached = tmp_path / "cache" / "jetredline" / "9.9.9" / "node" / "node_modules"
    (cached / "docx").mkdir(parents=True)
    got = bootstrap_env.ensure_node(skill_dir, tmp_path / "cache")
    assert got == cached


def test_node_none_without_npm(skill_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap_env.shutil, "which", lambda _: None)
    assert bootstrap_env.ensure_node(skill_dir, tmp_path / "cache") is None


# ---------------------------------------------------------------------------
# CLI output contract
# ---------------------------------------------------------------------------

def test_main_prints_venv_python_line(tmp_path, monkeypatch, capsys):
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "requirements.txt").write_text("")
    fake_python = tmp_path / "venv" / "bin" / "python"
    monkeypatch.setattr(bootstrap_env, "ensure_venv",
                        lambda *a, **k: fake_python)
    monkeypatch.setattr(bootstrap_env, "ensure_node", lambda *a, **k: None)
    rc = bootstrap_env.main(["--node", "--cache-root", str(tmp_path / "c")])
    out = capsys.readouterr().out.splitlines()
    assert rc == 0
    assert out[0] == f"VENV_PYTHON={fake_python}"
    assert out[1] == "NODE_PATH=NONE"


def test_main_exit_1_when_no_venv(monkeypatch, capsys):
    monkeypatch.setattr(bootstrap_env, "ensure_venv", lambda *a, **k: None)
    assert bootstrap_env.main([]) == 1


# ---------------------------------------------------------------------------
# stable_path: print the spelling the caller used, not the resolved one
#
# The skill directory is normally a symlink to a dev checkout, so a resolved
# path is one nobody types and no permission rule is written against. Printing
# it made every downstream command miss its allowlist entry and prompt.
# ---------------------------------------------------------------------------

def _fake_skill(tmp_path, name="skills/jetredline"):
    """A skill dir with a .venv, plus a symlink to it — the real layout."""
    real = tmp_path / name
    (real / ".venv" / "bin").mkdir(parents=True)
    python = real / ".venv" / "bin" / "python"
    python.write_text("#!/bin/sh\n")
    link = tmp_path / "linked-skill"
    link.symlink_to(real)
    return real, link, python


def test_stable_path_prefers_the_symlinked_spelling(tmp_path, monkeypatch):
    real, link, python = _fake_skill(tmp_path)
    monkeypatch.setattr(bootstrap_env, "__file__", str(real / "bootstrap_env.py"))
    monkeypatch.setenv("CLAUDE_SKILL_DIR", str(link))
    assert bootstrap_env.stable_path(python) == link / ".venv" / "bin" / "python"


def test_stable_path_result_is_the_same_interpreter(tmp_path, monkeypatch):
    """The whole point is a different spelling, never a different file."""
    real, link, python = _fake_skill(tmp_path)
    monkeypatch.setattr(bootstrap_env, "__file__", str(real / "bootstrap_env.py"))
    monkeypatch.setenv("CLAUDE_SKILL_DIR", str(link))
    assert bootstrap_env.stable_path(python).samefile(python)


def test_stable_path_rejects_a_lookalike_that_is_a_different_file(tmp_path, monkeypatch):
    """A directory that merely *looks* like the skill dir must not be trusted."""
    real, _, python = _fake_skill(tmp_path)
    impostor = tmp_path / "impostor"
    (impostor / ".venv" / "bin").mkdir(parents=True)
    (impostor / ".venv" / "bin" / "python").write_text("#!/bin/sh\n# a different python\n")
    monkeypatch.setattr(bootstrap_env, "__file__", str(real / "bootstrap_env.py"))
    monkeypatch.setenv("CLAUDE_SKILL_DIR", str(impostor))
    assert bootstrap_env.stable_path(python) == python


def test_stable_path_passes_through_a_real_directory(tmp_path, monkeypatch):
    """Cowork mounts the skill at a real path — no alternate spelling exists."""
    real, _, python = _fake_skill(tmp_path)
    monkeypatch.setattr(bootstrap_env, "__file__", str(real / "bootstrap_env.py"))
    monkeypatch.setenv("CLAUDE_SKILL_DIR", str(real))
    assert bootstrap_env.stable_path(python) == python


def test_stable_path_passes_through_a_cache_built_venv(tmp_path, monkeypatch):
    """A venv outside the skill dir has no in-skill counterpart to prefer."""
    real, link, _ = _fake_skill(tmp_path)
    cached = tmp_path / "cache" / "venv" / "bin" / "python"
    cached.parent.mkdir(parents=True)
    cached.write_text("#!/bin/sh\n")
    monkeypatch.setattr(bootstrap_env, "__file__", str(real / "bootstrap_env.py"))
    monkeypatch.setenv("CLAUDE_SKILL_DIR", str(link))
    assert bootstrap_env.stable_path(cached) == cached


def test_stable_path_without_the_env_var(tmp_path, monkeypatch):
    """Falls back to this file's own uninterpreted parent."""
    real, _, python = _fake_skill(tmp_path)
    monkeypatch.setattr(bootstrap_env, "__file__", str(real / "bootstrap_env.py"))
    monkeypatch.delenv("CLAUDE_SKILL_DIR", raising=False)
    assert bootstrap_env.stable_path(python) == python


def test_stable_path_ignores_an_env_var_pointing_nowhere(tmp_path, monkeypatch):
    real, _, python = _fake_skill(tmp_path)
    monkeypatch.setattr(bootstrap_env, "__file__", str(real / "bootstrap_env.py"))
    monkeypatch.setenv("CLAUDE_SKILL_DIR", str(tmp_path / "does-not-exist"))
    assert bootstrap_env.stable_path(python) == python

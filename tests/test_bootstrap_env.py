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
    req.write_text("defusedxml\nhttpx[socks]\n# comment\n\npy-pdf>=3\n")
    assert bootstrap_env.import_names(req) == [
        "defusedxml", "httpx", "socksio", "py_pdf",
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

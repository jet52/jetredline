#!/usr/bin/env python3
"""
Bootstrap a jet skill's runtime environment (venv, optionally node_modules).

Canonical copy: identical across the jet skills that need a venv; the skill's
name and version are read from the directory this file sits in, so the file
itself carries no per-skill edits.

Works in every install layout: dev symlink / standalone install (prebuilt
.venv inside the skill dir), plugin-cache or zip install (no bundled
artifacts — builds into a version-keyed user cache), and Cowork (read-only
skill dir, possibly read-only home — falls back to the system temp dir).

Selection ladder for the venv:
  1. <skill_dir>/.venv            — prebuilt; repaired in place if writable
  2. ~/.cache/jet-skills/<name>/<version>/venv
  3. <tmpdir>/<name>-venv

Prints machine-readable lines on stdout:
  VENV_PYTHON=<absolute path>
  NODE_PATH=<absolute path>|NONE     (only with --node)
Diagnostics go to stderr. Exit 1 only if no venv could be produced.

Usage:
    python3 bootstrap_env.py [--node] [--cache-root DIR]
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# requirements.txt names -> import names to verify, keyed on the requirement
# with version specifiers stripped. Extras matter: httpx[socks] is satisfied
# for import purposes without socksio, but Cowork's SOCKS proxy needs it, so
# verify the extra explicitly. PyMuPDF's import name is fitz;
# beautifulsoup4's is bs4.
_IMPORT_OVERRIDES = {
    "beautifulsoup4": ["bs4"],
    "httpx[socks]": ["httpx", "socksio"],
    "PyMuPDF": ["fitz"],
}


def _frontmatter(skill_dir: Path) -> dict:
    """Best-effort parse of SKILL.md YAML frontmatter scalar fields."""
    out: dict = {}
    try:
        text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    except OSError:
        return out
    if not text.startswith("---"):
        return out
    for line in text.split("\n---", 1)[0].splitlines()[1:]:
        key, sep, value = line.partition(":")
        if sep and " " not in key.strip():
            out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def skill_name(skill_dir: Path) -> str:
    return _frontmatter(skill_dir).get("name") or skill_dir.name


def read_version(skill_dir: Path) -> str:
    try:
        v = (skill_dir / "VERSION").read_text(encoding="utf-8").strip()
        if v:
            return v
    except OSError:
        pass
    try:
        v = json.loads((skill_dir / "version.json").read_text(encoding="utf-8")).get("version")
        if v:
            return str(v)
    except (OSError, ValueError):
        pass
    return _frontmatter(skill_dir).get("version") or "dev"


def import_names(requirements: Path) -> list[str]:
    names: list[str] = []
    try:
        lines = requirements.read_text(encoding="utf-8").splitlines()
    except OSError:
        return names
    for line in lines:
        req = line.strip()
        if not req or req.startswith("#"):
            continue
        base = req.split(">")[0].split("<")[0].split("=")[0].split("~")[0].strip()
        if base in _IMPORT_OVERRIDES:
            names.extend(_IMPORT_OVERRIDES[base])
        else:
            names.append(base.split("[")[0].replace("-", "_").lower())
    return names


def venv_python(venv_dir: Path) -> Path | None:
    for rel in ("bin/python", "Scripts/python.exe"):
        p = venv_dir / rel
        if p.exists():
            return p
    return None


def check_imports(python: Path, modules: list[str]) -> bool:
    if not modules:
        return True
    try:
        r = subprocess.run([str(python), "-c",
                            "import " + ", ".join(modules)],
                           capture_output=True)
    except OSError:
        return False
    return r.returncode == 0


def pip_install(python: Path, requirements: Path) -> bool:
    try:
        r = subprocess.run([str(python), "-m", "pip", "install", "-q",
                            "--disable-pip-version-check", "-r",
                            str(requirements)],
                           capture_output=True)
        if r.returncode == 0:
            return True
    except OSError:
        r = None
    # uv-built venvs ship without pip; use uv itself when available.
    uv = shutil.which("uv")
    if uv is not None:
        try:
            r2 = subprocess.run([uv, "pip", "install", "-q", "-r",
                                 str(requirements), "--python", str(python)])
            return r2.returncode == 0
        except OSError:
            return False
    if r is not None:
        sys.stderr.buffer.write(r.stderr)
    return False


def _base_python() -> str:
    """The interpreter to create venvs from — never a venv python itself.

    A venv created from another venv's python can inherit dangling shared-lib
    paths (observed with uv-managed CPython); the base interpreter is safe.
    """
    if sys.prefix != sys.base_prefix:
        base = getattr(sys, "_base_executable", None)
        if base and Path(base).exists():
            return base
    return sys.executable


def build_venv(venv_dir: Path, requirements: Path) -> Path | None:
    try:
        venv_dir.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([_base_python(), "-m", "venv", str(venv_dir)],
                           capture_output=True)
        if r.returncode != 0:
            # ensurepip can abort under some interpreters; build without pip
            # and let pip_install()'s uv fallback do the installing.
            shutil.rmtree(venv_dir, ignore_errors=True)
            r = subprocess.run([_base_python(), "-m", "venv", "--without-pip",
                                str(venv_dir)], capture_output=True)
            if r.returncode != 0:
                sys.stderr.buffer.write(r.stderr)
                return None
    except OSError:
        return None
    python = venv_python(venv_dir)
    if python is None:
        return None
    needs_install = False
    try:
        needs_install = bool(requirements.read_text(encoding="utf-8").strip())
    except OSError:
        pass
    if needs_install and not pip_install(python, requirements):
        return None
    warm_textstat(python)
    return python


def warm_textstat(python: Path) -> None:
    """Best-effort: some textstat builds look up syllables through NLTK's
    cmudict corpus, which pip does not install. Probe once at build time and
    fetch the corpus if the probe raises LookupError. Never fatal --
    readability_metrics.py falls back to a syllable estimate without it."""
    probe = (
        "import sys\n"
        "try:\n"
        "    import textstat\n"
        "except ImportError:\n"
        "    sys.exit(0)\n"
        "try:\n"
        "    textstat.flesch_kincaid_grade('The cat sat on the mat.')\n"
        "except LookupError:\n"
        "    try:\n"
        "        import nltk\n"
        "        for c in ('cmudict', 'punkt', 'punkt_tab'):\n"
        "            nltk.download(c, quiet=True)\n"
        "    except Exception as e:\n"
        "        print('textstat corpus download skipped: %s' % e,\n"
        "              file=sys.stderr)\n"
    )
    try:
        subprocess.run([str(python), "-c", probe], capture_output=True,
                       timeout=120)
    except (OSError, subprocess.SubprocessError):
        pass


def ensure_venv(skill_dir: Path, cache_root: Path, tmp_root: Path) -> Path | None:
    requirements = skill_dir / "requirements.txt"
    modules = import_names(requirements)

    # Tier 1: prebuilt venv inside the skill dir (dev / standalone install).
    prebuilt = venv_python(skill_dir / ".venv")
    if prebuilt is not None:
        if check_imports(prebuilt, modules):
            print(f"venv: using prebuilt {skill_dir / '.venv'}", file=sys.stderr)
            return prebuilt
        if requirements.exists() and pip_install(prebuilt, requirements) \
                and check_imports(prebuilt, modules):
            print(f"venv: repaired prebuilt {skill_dir / '.venv'}", file=sys.stderr)
            return prebuilt
        print("venv: prebuilt .venv unusable, falling through", file=sys.stderr)

    # Tiers 2 and 3: version-keyed user cache, then the system temp dir.
    name = skill_name(skill_dir)
    candidates = [
        cache_root / name / read_version(skill_dir) / "venv",
        tmp_root / f"{name}-venv",
    ]
    for venv_dir in candidates:
        existing = venv_python(venv_dir)
        if existing is not None:
            if check_imports(existing, modules):
                print(f"venv: reusing {venv_dir}", file=sys.stderr)
                return existing
            if requirements.exists() and pip_install(existing, requirements) \
                    and check_imports(existing, modules):
                print(f"venv: repaired {venv_dir}", file=sys.stderr)
                return existing
            shutil.rmtree(venv_dir, ignore_errors=True)  # corrupt — rebuild
        python = build_venv(venv_dir, requirements)
        if python is not None and check_imports(python, modules):
            print(f"venv: built {venv_dir}", file=sys.stderr)
            return python
        shutil.rmtree(venv_dir, ignore_errors=True)
    return None


def ensure_node(skill_dir: Path, cache_root: Path) -> Path | None:
    """Return a NODE_PATH directory containing the docx package, or None."""
    local = skill_dir / "node_modules"
    if (local / "docx").is_dir():
        print(f"node: using bundled {local}", file=sys.stderr)
        return local

    prefix = cache_root / skill_name(skill_dir) / read_version(skill_dir) / "node"
    cached = prefix / "node_modules"
    if (cached / "docx").is_dir():
        print(f"node: reusing {cached}", file=sys.stderr)
        return cached

    npm = shutil.which("npm")
    if npm is None:
        print("node: npm not found; new-.docx creation path unavailable",
              file=sys.stderr)
        return None
    try:
        spec = json.loads((skill_dir / "package.json").read_text(encoding="utf-8"))
        docx_spec = "docx@" + spec["dependencies"]["docx"]
    except (OSError, KeyError, ValueError):
        docx_spec = "docx"
    try:
        prefix.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([npm, "install", "--prefix", str(prefix), docx_spec,
                            "--no-audit", "--no-fund", "--loglevel=error"])
    except OSError:
        return None
    if r.returncode == 0 and (cached / "docx").is_dir():
        print(f"node: installed into {cached}", file=sys.stderr)
        return cached
    return None


def stable_path(python: Path) -> Path:
    """Prefer the spelling the caller *invoked* us by, over the resolved one.

    The skill directory is commonly a symlink to a dev checkout, so
    Path(__file__).resolve() yields a path nobody types and no permission rule
    is written against -- e.g. ~/.claude/skills/jetredline resolves to
    ~/code/jetredline/skills/jetredline. Printing the resolved form makes every
    downstream command miss its allowlist entry and prompt.

    So: if the unresolved skill directory (CLAUDE_SKILL_DIR, else this file's
    own uninterpreted parent) contains an equivalent interpreter, print that
    instead. Equivalence is checked with samefile() so a wrong guess can never
    hand back an interpreter that isn't the one we just built.

    Portable by construction: in Cowork the skill is a real directory under
    /mnt/.skills (no symlink, so the candidate equals the resolved path), and a
    cache- or temp-built venv lives outside the skill dir entirely (so no
    candidate matches). Both fall through to `python` unchanged.
    """
    candidates = []
    env_dir = os.environ.get("CLAUDE_SKILL_DIR")
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.append(Path(__file__).parent)

    for skill_dir in candidates:
        try:
            candidate = skill_dir / ".venv" / python.relative_to(
                Path(__file__).resolve().parent / ".venv")
        except ValueError:
            continue  # venv lives outside the skill dir (cache/temp build)
        try:
            if candidate.exists() and candidate.samefile(python):
                return candidate
        except OSError:
            continue
    return python


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", action="store_true",
                        help="also ensure the docx npm package and print NODE_PATH")
    parser.add_argument("--cache-root", type=Path,
                        default=Path.home() / ".cache" / "jet-skills",
                        help="base directory for built environments")
    args = parser.parse_args(argv)

    skill_dir = Path(__file__).resolve().parent
    python = ensure_venv(skill_dir, args.cache_root,
                         Path(tempfile.gettempdir()))
    if python is None:
        print("ERROR: could not create a usable venv in any location",
              file=sys.stderr)
        return 1
    print(f"VENV_PYTHON={stable_path(python)}")

    if args.node:
        node_path = ensure_node(skill_dir, args.cache_root)
        print(f"NODE_PATH={node_path if node_path else 'NONE'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

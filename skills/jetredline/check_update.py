#!/usr/bin/env python3
"""Check for skill/plugin updates against the latest GitHub release.

Shared across jet52 projects: jetmemo-skill, jetredline, jetbriefcheck, jetcite.
Uses a weekly cache to avoid hitting the GitHub API on every invocation.
Fails open — never blocks the user's work.
"""

import json
import sys
import time
import urllib.request
from pathlib import Path

REPO = "jet52/jetredline"
SKILL_NAME = "jetredline"

GITHUB_API = f"https://api.github.com/repos/{REPO}/releases/latest"
CACHE_DIR = Path.home() / ".cache" / SKILL_NAME
CACHE_FILE = CACHE_DIR / "update_check.json"
CHECK_INTERVAL = 7 * 86400  # 1 week in seconds
TIMEOUT = 3.0


def _read_local_version() -> str | None:
    """Read the locally installed version from VERSION file."""
    # Installed location
    version_file = Path.home() / ".claude" / "skills" / SKILL_NAME / "VERSION"
    if version_file.exists():
        return version_file.read_text().strip()
    # Repo location (same directory as this script)
    version_file = Path(__file__).resolve().parent / "VERSION"
    if version_file.exists():
        return version_file.read_text().strip()
    return None


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse a semver string into a comparable tuple."""
    return tuple(int(x) for x in v.split("."))


def _read_cache() -> dict | None:
    """Read the cached update check result."""
    try:
        data = json.loads(CACHE_FILE.read_text())
        if time.time() - data.get("checked", 0) < CHECK_INTERVAL:
            return data
    except Exception:
        pass
    return None


def _write_cache(remote_version: str) -> None:
    """Write the update check result to cache."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps({
            "checked": time.time(),
            "remote_version": remote_version,
        }))
    except Exception:
        pass


def _fetch_latest() -> str | None:
    """Fetch the latest release tag from GitHub."""
    req = urllib.request.Request(
        GITHUB_API, headers={"Accept": "application/vnd.github+json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read())
            return data.get("tag_name", "").lstrip("v")
    except Exception:
        return None


def check_for_update() -> str | None:
    """Check for updates. Returns an advisory string if one is available, None otherwise."""
    local = _read_local_version()
    if not local:
        return None

    # Try cache first
    cache = _read_cache()
    if cache:
        remote = cache.get("remote_version")
    else:
        remote = _fetch_latest()
        if remote:
            _write_cache(remote)

    if not remote:
        return None

    try:
        if _parse_version(remote) > _parse_version(local):
            return (
                f"{SKILL_NAME} v{local} -> v{remote} available: "
                f"https://github.com/{REPO}/releases/latest"
            )
    except (ValueError, TypeError):
        pass

    return None


def main():
    msg = check_for_update()
    if msg:
        print(msg)
    else:
        local = _read_local_version() or "unknown"
        print(f"{SKILL_NAME} v{local} (up to date)")


if __name__ == "__main__":
    main()

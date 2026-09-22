#!/usr/bin/env python3
"""Probe the network sources a jetredline run depends on, before any pass.

A sandboxed session (Claude Cowork, the Claude Code sandbox) sends all egress
through a filtering proxy with a domain allowlist. A host missing from that
list does not fail loudly: the scripts degrade to a weaker source -- ndlaw
text scribed through the model, an ND opinion left on its search URL, a
statute with no text -- and nothing says so until the end of the run, if
then. This script finds that out up front, so the run announcement and the
analysis document can say which sources were out of reach.

Probes:
  ndlaw.org          MCP initialize handshake against the public server
                     (the default ndlaw_export.py backend).
  jetcite's hosts    One HEAD request per entry in jetcite's egress registry
                     (lib/jetcite/_egress.py -- read directly, so the list
                     here cannot drift from the code that fetches).
                     Out-of-state hosts are skipped unless --all.

Any HTTP response counts as reachable: the question is egress, not whether a
particular page exists. Failures are classified -- `blocked` (the proxy
refused CONNECT: an allowlist gap), `dns`, `timeout`, `tls`, `network`, and
for ndlaw only `auth` -- and each warning names the fix.

Output, one line per probe, then a summary:
    PREFLIGHT ok ndlaw.org
    PREFLIGHT warn www.ndcourts.gov blocked -- <what is lost>. <fix>
    PREFLIGHT_SUMMARY warnings=1

Stdlib only; runs on system python3 before the bootstrap. Always exits 0 --
a warning never stops a run.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import socket
import ssl
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
EGRESS_FILE = SKILL_DIR / "lib" / "jetcite" / "_egress.py"

NDLAW_URL = "https://ndlaw.org/mcp"
NDLAW_ENTRIES = "`ndlaw.org` and `*.ndlaw.org`"
NDLAW_LOSS = ("ND opinion text for the citation-review page will be scribed "
              "through the model instead (about 15k tokens and 2 minutes per "
              "opinion), or left to cached copies")

# Registry entries that serve only out-of-state citations. Probed with --all;
# otherwise a Cowork allowlist built for ND work would warn on every run.
OUT_OF_STATE = frozenset({
    "www.azleg.gov", "apps.azsos.gov", "www.azcourts.gov",
    "www.legis.iowa.gov",
})

USER_AGENT = "jetredline-preflight (+https://github.com/jet52/jetredline)"


def classify_error(exc: BaseException) -> str:
    """Name the failure: blocked | auth | http | dns | timeout | tls | network.

    `blocked` is the signature of an egress allowlist: the proxy answers the
    CONNECT with 403 and urllib reports "Tunnel connection failed". An HTTP
    error from the host itself means egress worked.
    """
    if isinstance(exc, urllib.error.HTTPError):
        return "auth" if exc.code in (401, 403) else "http"
    reason = getattr(exc, "reason", exc)
    text = f"{exc} {reason}"
    if "Tunnel connection failed" in text or "CONNECT" in text:
        return "blocked"
    if isinstance(reason, socket.gaierror):
        return "dns"
    if isinstance(reason, (socket.timeout, TimeoutError)) or \
            isinstance(exc, (socket.timeout, TimeoutError)):
        return "timeout"
    if isinstance(reason, ssl.SSLError) or isinstance(exc, ssl.SSLError):
        return "tls"
    return "network"


def fix_hint(kind: str, entry: str) -> str:
    """One sentence on how to fix a failure of this kind."""
    if kind == "blocked":
        return (f"The network policy blocks it: add {entry} to the egress "
                "allowlist (Cowork: Additional allowed domains; Claude Code: "
                "sandbox.network.allowedDomains), then start a new session.")
    if kind == "auth":
        return "The server demanded credentials; set NDLAW_URL/NDLAW_AUTH."
    if kind in ("dns", "timeout", "network"):
        return "Check the machine's network connection."
    if kind == "tls":
        return ("TLS failed -- often an intercepting proxy whose certificate "
                "the Python install does not trust.")
    return ""


def _open(req: urllib.request.Request, timeout: float):
    return urllib.request.urlopen(req, timeout=timeout)


def probe_ndlaw(timeout: float) -> str | None:
    """None when the public ndlaw MCP server completes an initialize."""
    body = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                   "clientInfo": {"name": "jetredline-preflight",
                                  "version": "1.0"}}}).encode()
    req = urllib.request.Request(NDLAW_URL, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": USER_AGENT})
    try:
        with _open(req, timeout) as resp:
            text = resp.read(65536).decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 -- classified, never raised
        return classify_error(exc)
    return None if '"result"' in text else "http"


def probe_host(host: str, timeout: float) -> str | None:
    """None when the host answers HTTP at all."""
    req = urllib.request.Request(f"https://{host}/", method="HEAD",
                                 headers={"User-Agent": USER_AGENT})
    try:
        with _open(req, timeout):
            pass
    except urllib.error.HTTPError:
        return None  # the host answered; egress is fine
    except Exception as exc:  # noqa: BLE001
        return classify_error(exc)
    return None


def load_registry() -> dict[str, str]:
    """jetcite's EGRESS_ALLOWLIST, loaded from the file without importing
    the package (whose __init__ pulls in third-party modules)."""
    spec = importlib.util.spec_from_file_location("_jetcite_egress",
                                                  EGRESS_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return dict(mod.EGRESS_ALLOWLIST)


def probe_host_for(entry: str) -> str:
    """The host to probe for an allowlist entry (`*.x.gov` -> `www.x.gov`)."""
    return "www." + entry[2:] if entry.startswith("*.") else entry


def run(timeout: float = 8.0, include_all: bool = False,
        registry: dict[str, str] | None = None) -> list[dict]:
    """Probe everything in parallel; one result dict per probe, in order."""
    registry = load_registry() if registry is None else registry
    checks = [("ndlaw.org", NDLAW_ENTRIES, NDLAW_LOSS,
               lambda: probe_ndlaw(timeout))]
    for entry, enables in registry.items():
        host = probe_host_for(entry)
        if host in OUT_OF_STATE and not include_all:
            continue
        checks.append((host, f"`{entry}`", f"loses {enables}",
                       lambda h=host: probe_host(h, timeout)))
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fn) for *_, fn in checks]
        kinds = [f.result() for f in futures]
    results = []
    for (host, entry, loss, _), kind in zip(checks, kinds):
        results.append({"host": host, "ok": kind is None, "kind": kind,
                        "loss": loss, "fix": fix_hint(kind, entry)
                        if kind else ""})
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--timeout", type=float, default=8.0,
                    help="Seconds per probe (default 8; probes run in "
                         "parallel)")
    ap.add_argument("--all", action="store_true",
                    help="Also probe out-of-state sources (Arizona, Iowa)")
    args = ap.parse_args(argv)

    try:
        results = run(args.timeout, args.all)
    except Exception as exc:  # noqa: BLE001 -- a broken probe never blocks
        print(f"PREFLIGHT_SUMMARY error={exc}")
        return 0
    warnings = 0
    for r in results:
        if r["ok"]:
            print(f"PREFLIGHT ok {r['host']}")
            continue
        warnings += 1
        # A 404/405 from a live host is "http" and already counted ok in
        # probe_host; for ndlaw it means the server answered but not as MCP.
        print(f"PREFLIGHT warn {r['host']} {r['kind']} -- "
              f"{r['loss']}. {r['fix']}".rstrip())
    print(f"PREFLIGHT_SUMMARY warnings={warnings}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

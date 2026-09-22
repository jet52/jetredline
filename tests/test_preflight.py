"""Tests for preflight.py and ndlaw_export.py's public-server default.

A Cowork run's ndlaw export failed with exit 2 and fell back to scribing
opinion text through the model, and nothing told the user until the end.
The export now defaults to the public server, and the preflight names any
blocked host -- and the allowlist entry that fixes it -- before a pass runs.
"""

import socket
import ssl
import urllib.error
from types import SimpleNamespace

import pytest

import ndlaw_export
import preflight as P


# --- classification ---------------------------------------------------------


@pytest.mark.parametrize("exc, kind", [
    (urllib.error.URLError(OSError("Tunnel connection failed: 403 Forbidden")),
     "blocked"),
    (urllib.error.URLError(socket.gaierror(8, "nodename nor servname")), "dns"),
    (urllib.error.URLError(socket.timeout("timed out")), "timeout"),
    (TimeoutError("timed out"), "timeout"),
    (urllib.error.URLError(ssl.SSLError("CERTIFICATE_VERIFY_FAILED")), "tls"),
    (urllib.error.HTTPError("u", 401, "Unauthorized", {}, None), "auth"),
    (urllib.error.HTTPError("u", 500, "Server Error", {}, None), "http"),
    (urllib.error.URLError(ConnectionRefusedError(61, "refused")), "network"),
])
def test_classify_error(exc, kind):
    assert P.classify_error(exc) == kind


def test_blocked_hint_names_the_entry_and_a_new_session():
    hint = P.fix_hint("blocked", P.NDLAW_ENTRIES)
    assert "`ndlaw.org` and `*.ndlaw.org`" in hint
    assert "new session" in hint


def test_probe_host_counts_any_http_answer_as_reachable(monkeypatch):
    def four_oh_five(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 405, "Method Not Allowed",
                                     {}, None)
    monkeypatch.setattr(P, "_open", four_oh_five)
    assert P.probe_host("www.ecfr.gov", 1) is None


# --- registry and run -------------------------------------------------------


def test_registry_is_read_from_vendored_jetcite():
    reg = P.load_registry()
    assert "*.ndcourts.gov" in reg and "www.courtlistener.com" in reg


def test_wildcard_entries_probe_the_www_host():
    assert P.probe_host_for("*.ndcourts.gov") == "www.ndcourts.gov"
    assert P.probe_host_for("ndlegis.gov") == "ndlegis.gov"


def fake_probes(monkeypatch, blocked):
    monkeypatch.setattr(P, "probe_ndlaw",
                        lambda t: "blocked" if "ndlaw.org" in blocked else None)
    monkeypatch.setattr(P, "probe_host",
                        lambda h, t: "blocked" if h in blocked else None)


REG = {"*.ndcourts.gov": "ND opinions", "www.azleg.gov": "Arizona statutes"}


def test_out_of_state_hosts_skipped_unless_all(monkeypatch):
    fake_probes(monkeypatch, set())
    hosts = [r["host"] for r in P.run(registry=REG)]
    assert hosts == ["ndlaw.org", "www.ndcourts.gov"]
    hosts = [r["host"] for r in P.run(registry=REG, include_all=True)]
    assert "www.azleg.gov" in hosts


def test_main_reports_each_warning_and_exits_zero(monkeypatch, capsys):
    fake_probes(monkeypatch, {"ndlaw.org", "www.ndcourts.gov"})
    monkeypatch.setattr(P, "load_registry", lambda: REG)
    assert P.main([]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("PREFLIGHT warn ndlaw.org blocked -- ")
    assert "*.ndcourts.gov" in out[1]
    assert out[-1] == "PREFLIGHT_SUMMARY warnings=2"


def test_main_never_raises(monkeypatch, capsys):
    def boom():
        raise FileNotFoundError("no registry")
    monkeypatch.setattr(P, "load_registry", boom)
    assert P.main([]) == 0
    assert "PREFLIGHT_SUMMARY error=" in capsys.readouterr().out


# --- ndlaw_export backend selection -----------------------------------------


def args(**kw):
    base = dict(db="/nonexistent/opinions.db", url=None, auth=None,
                no_public=False)
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture
def no_env(monkeypatch):
    for var in ("NDLAW_DB", "NDLAW_URL", "NDLAW_AUTH"):
        monkeypatch.delenv(var, raising=False)


def test_export_defaults_to_public_server(monkeypatch, no_env):
    seen = []
    monkeypatch.setattr(ndlaw_export, "McpBackend",
                        lambda url, auth: seen.append((url, auth)) or "B")
    backend, label = ndlaw_export._pick_backend(args())
    assert backend == "B"
    assert seen == [("https://ndlaw.org/mcp", None)]
    assert "(public)" in label


def test_explicit_url_wins_over_public(monkeypatch, no_env):
    seen = []
    monkeypatch.setattr(ndlaw_export, "McpBackend",
                        lambda url, auth: seen.append(url) or "B")
    ndlaw_export._pick_backend(args(url="https://example.test/mcp"))
    assert seen == ["https://example.test/mcp"]


def test_no_public_opts_out(monkeypatch, no_env):
    monkeypatch.setattr(ndlaw_export, "McpBackend",
                        lambda *a: pytest.fail("contacted a server"))
    assert ndlaw_export._pick_backend(args(no_public=True)) == (None, None)


def test_blocked_public_server_names_the_fix(monkeypatch, no_env):
    def blocked(url, auth):
        raise urllib.error.URLError(
            OSError("Tunnel connection failed: 403 Forbidden"))
    monkeypatch.setattr(ndlaw_export, "McpBackend", blocked)
    with pytest.raises(RuntimeError) as ei:
        ndlaw_export._pick_backend(args())
    msg = str(ei.value)
    assert "blocked" in msg and "`*.ndlaw.org`" in msg

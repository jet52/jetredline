#!/usr/bin/env python3
"""Export ND opinion text and direct URLs from the ndlaw corpus.

Writes each cited ND opinion's corpus text into this run's sources
directory (normally <TMPDIR>/sources) so the citation-review HTML embeds
corpus text and the court's direct opinion URL. Nothing is written
outside that directory. Runs with zero model-context cost via one of two backends:

  sqlite  — a local ndlaw opinions.db (--db, NDLAW_DB env, or the
            default development path), read-only.
  mcp     — a deployed ndlaw instance over Streamable HTTP with
            Basic Auth (--url/NDLAW_URL, --auth/NDLAW_AUTH). The script
            speaks JSON-RPC directly; no LLM tokens are spent.
  public  — with neither of the above, the public server at
            https://ndlaw.org/mcp (no auth). --no-public disables it.

Usage:
    ndlaw_export.py --opinion draft.md --sources-dir <TMPDIR>/sources \
        --meta-out sources.json
    ndlaw_export.py --cite-json cites.json --sources-dir <TMPDIR>/sources \
        --meta-out sources.json
    ndlaw_export.py --cites "2024 ND 156" "2023 ND 44" ...

Exit codes: 0 = exported (possibly with misses); 2 = no backend
reachable (callers should fall through to the MCP tools / link-only). When the
public server is the one that failed, stderr says why -- an egress allowlist
refusal, a network failure, or an HTTP error -- and what to allowlist.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

SKILL_DIR = Path(__file__).parent
sys.path.insert(0, str(SKILL_DIR / "lib"))

DEFAULT_DB = "~/code/ndlaw-mcp/opinions.db"
# Public ndlaw server: serves the same corpus without authentication. The
# apex host needs its own allowlist entry -- `*.ndlaw.org` does not cover it.
PUBLIC_URL = "https://ndlaw.org/mcp"
COURTLISTENER_BASE = "https://www.courtlistener.com"

# Citations the ndlaw corpus can resolve: ND neutral cites and the
# North Western reporter (which carries ND cases, incl. pre-1997).
_ND_NEUTRAL_RE = re.compile(r"^[12]\d{3} ND \d{1,3}$")
_NW_RE = re.compile(r"^\d+ N\.W\.(?:2d|3d)? \d+$")


def _corpus_eligible(normalized: str) -> bool:
    return bool(_ND_NEUTRAL_RE.match(normalized) or _NW_RE.match(normalized))


def _collect_cites(args) -> list[str]:
    """Gather unique corpus-eligible citation strings, first-seen order."""
    cites: list[str] = []
    seen: set[str] = set()

    def add(norm: str):
        norm = " ".join(norm.split())
        if norm and norm not in seen and _corpus_eligible(norm):
            seen.add(norm)
            cites.append(norm)

    if args.cite_json:
        entries = json.loads(Path(args.cite_json).expanduser().read_text(encoding="utf-8"))
        for e in entries:
            if e.get("cite_type") == "pin_cite" or e.get("is_repeat"):
                continue  # short forms resolve through their parent
            add(e.get("normalized", ""))
    if args.opinion:
        from cite_check import scan_opinion
        text = Path(args.opinion).expanduser().read_text(encoding="utf-8")
        # Offline scan: no URL resolution, no fetching
        import jetcite.scanner as _scanner
        saved = _scanner.resolve_nd_opinion_urls
        _scanner.resolve_nd_opinion_urls = lambda cites: None
        try:
            entries = scan_opinion(text)
        finally:
            _scanner.resolve_nd_opinion_urls = saved
        for e in entries:
            if e.get("cite_type") == "pin_cite" or e.get("is_repeat"):
                continue
            add(e.get("normalized", ""))
    for c in args.cites or []:
        add(c)
    return cites


# ---------------------------------------------------------------------------
# Backends — both return, per citation:
#   {"case_name": str, "url": str|None, "url_source": str|None,
#    "date_filed": str|None, "citations": [str, ...], "text": str}
# or None when the corpus has no match.
# ---------------------------------------------------------------------------

class SqliteBackend:
    def __init__(self, db_path: str):
        import sqlite3
        self._sqlite3 = sqlite3
        self.conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        self.conn.row_factory = sqlite3.Row

    def lookup_meta(self, citation: str) -> dict | None:
        """Metadata only — same shape as lookup() but without the text.

        The parallel-cite check needs only ``citations``; pulling the full
        opinion body for it would be pure waste (and, over MCP, a paged
        round trip per authority).
        """
        row = self.conn.execute(
            """SELECT o.id, o.case_name, o.date_filed
               FROM opinions o JOIN citations c ON c.opinion_id = o.id
               WHERE c.citation = ?""",
            (citation,),
        ).fetchone()
        if row is None:
            return None
        all_cites = [
            r["citation"] for r in self.conn.execute(
                "SELECT citation FROM citations WHERE opinion_id = ? "
                "ORDER BY is_primary DESC", (row["id"],))
        ]
        return {
            "case_name": row["case_name"],
            "date_filed": row["date_filed"],
            "citations": all_cites,
        }

    def lookup(self, citation: str) -> dict | None:
        row = self.conn.execute(
            """SELECT o.id, o.case_name, o.date_filed, o.opinion_url,
                      o.absolute_url, o.text_content
               FROM opinions o JOIN citations c ON c.opinion_id = o.id
               WHERE c.citation = ?""",
            (citation,),
        ).fetchone()
        if row is None:
            return None
        url, url_source = None, None
        if row["opinion_url"]:
            url, url_source = row["opinion_url"], "ndcourts.gov"
        elif row["absolute_url"]:
            cl = row["absolute_url"]
            url = cl if cl.startswith("http") else COURTLISTENER_BASE + cl
            url_source = "courtlistener"
        all_cites = [
            r["citation"] for r in self.conn.execute(
                "SELECT citation FROM citations WHERE opinion_id = ? "
                "ORDER BY is_primary DESC", (row["id"],))
        ]
        return {
            "case_name": row["case_name"],
            "url": url,
            "url_source": url_source,
            "date_filed": row["date_filed"],
            "citations": all_cites,
            "text": row["text_content"],
        }

    def close(self):
        self.conn.close()


class McpBackend:
    """Minimal Streamable HTTP MCP client (JSON-RPC over POST + SSE)."""

    def __init__(self, url: str, auth: str | None, timeout: float = 30.0):
        self.url = url
        self.timeout = timeout
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if auth:
            # Accept "user:pass" (encode it) or a pre-encoded base64 token.
            token = (base64.b64encode(auth.encode()).decode()
                     if ":" in auth else auth)
            self.headers["Authorization"] = f"Basic {token}"
        self._id = 0
        self._initialize()

    def _post(self, payload: dict | None, extra: dict | None = None) -> tuple[dict | None, dict]:
        req = urllib.request.Request(
            self.url, data=json.dumps(payload).encode(),
            headers={**self.headers, **(extra or {})}, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            resp_headers = dict(resp.headers)
            ctype = resp.headers.get("Content-Type", "")
            body = resp.read().decode("utf-8", errors="replace")
        if not body.strip():
            return None, resp_headers
        if "text/event-stream" in ctype:
            # Take the last data: event carrying a JSON-RPC response
            result = None
            for line in body.splitlines():
                if line.startswith("data:"):
                    try:
                        msg = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    if isinstance(msg, dict) and ("result" in msg or "error" in msg):
                        result = msg
            return result, resp_headers
        return json.loads(body), resp_headers

    def _rpc(self, method: str, params: dict) -> dict:
        self._id += 1
        msg, _ = self._post({"jsonrpc": "2.0", "id": self._id,
                             "method": method, "params": params})
        if msg is None:
            raise RuntimeError(f"no response to {method}")
        if "error" in msg:
            raise RuntimeError(f"{method}: {msg['error']}")
        return msg["result"]

    def _initialize(self):
        self._id += 1
        msg, headers = self._post({
            "jsonrpc": "2.0", "id": self._id, "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "jetredline-ndlaw-export",
                               "version": "1.0"},
            }})
        if msg is None or "error" in msg:
            raise RuntimeError(f"MCP initialize failed: {msg}")
        session = headers.get("mcp-session-id") or headers.get("Mcp-Session-Id")
        if session:
            self.headers["mcp-session-id"] = session
        proto = msg["result"].get("protocolVersion")
        if proto:
            self.headers["MCP-Protocol-Version"] = proto
        # initialized notification (no id, no response expected)
        try:
            self._post({"jsonrpc": "2.0",
                        "method": "notifications/initialized", "params": {}})
        except urllib.error.HTTPError:
            pass  # some servers 202/4xx a bare notification; not fatal

    def _call_tool(self, name: str, arguments: dict) -> dict:
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            raise RuntimeError(f"{name}: {result}")
        structured = result.get("structuredContent")
        if structured is not None:
            # FastMCP wraps non-object returns as {"result": ...}
            return structured.get("result", structured)
        for item in result.get("content", []):
            if item.get("type") == "text":
                return json.loads(item["text"])
        raise RuntimeError(f"{name}: no parseable content")

    def lookup_meta(self, citation: str) -> dict | None:
        """Metadata only — skips the paged get_opinion_text loop."""
        meta = self._call_tool("lookup_opinion", {"citation": citation})
        if not isinstance(meta, dict) or meta.get("error"):
            return None
        return {
            "case_name": meta.get("case_name"),
            "date_filed": meta.get("date_filed"),
            "citations": meta.get("citations") or [citation],
        }

    def lookup(self, citation: str) -> dict | None:
        meta = self._call_tool("lookup_opinion", {"citation": citation})
        if not isinstance(meta, dict) or meta.get("error"):
            return None
        chunks: list[str] = []
        offset = 0
        while True:
            page = self._call_tool("get_opinion_text", {
                "citation": citation, "offset": offset, "limit": 50000})
            if not isinstance(page, dict) or page.get("error"):
                break
            chunks.append(page.get("text", ""))
            if not page.get("has_more"):
                break
            offset += page.get("chunk_length") or 50000
        return {
            "case_name": meta.get("case_name"),
            "url": meta.get("url"),
            "url_source": meta.get("url_source"),
            "date_filed": meta.get("date_filed"),
            "citations": meta.get("citations") or [citation],
            "text": "".join(chunks),
        }

    def close(self):
        pass


def _pick_backend(args):
    db = args.db or os.environ.get("NDLAW_DB") or DEFAULT_DB
    if Path(db).expanduser().is_file():
        return SqliteBackend(str(Path(db).expanduser())), f"sqlite:{db}"
    url = args.url or os.environ.get("NDLAW_URL")
    if url:
        auth = args.auth or os.environ.get("NDLAW_AUTH")
        return McpBackend(url, auth), f"mcp:{url}"
    if getattr(args, "no_public", False):
        return None, None
    try:
        return McpBackend(PUBLIC_URL, None), f"mcp:{PUBLIC_URL} (public)"
    except Exception as exc:
        from preflight import NDLAW_ENTRIES, classify_error, fix_hint
        kind = classify_error(exc)
        raise RuntimeError(
            f"public ndlaw server {PUBLIC_URL} unreachable ({kind}: {exc}). "
            f"{fix_hint(kind, NDLAW_ENTRIES)}") from exc


# ---------------------------------------------------------------------------
# Writing into the run's sources directory
# ---------------------------------------------------------------------------

def _write_source(sources_dir: Path, record: dict, queried: str) -> Path:
    from cite_check import source_path, write_source
    path = source_path(queried, sources_dir)
    write_source(path, record["text"], {
        "citation": queried,
        "case_name": record.get("case_name"),
        "source_url": record.get("url"),
        "content_type": "text/markdown",
        "origin": "ndlaw-corpus",
    })
    return path


def main():
    ap = argparse.ArgumentParser(
        description="Write ND opinion text + direct URLs from the ndlaw "
                    "corpus (local sqlite or deployed MCP) into this run's "
                    "sources directory.")
    src = ap.add_argument_group("citation sources (any combination)")
    src.add_argument("--opinion", help="Draft to scan for ND case cites")
    src.add_argument("--cite-json", help="cite_check.py JSON output")
    src.add_argument("--cites", nargs="*", help="Explicit citation strings")
    ap.add_argument("--sources-dir",
                    help="This run's sources directory to write opinion text "
                         "into (e.g. <TMPDIR>/sources). Omit to write "
                         "metadata only.")
    ap.add_argument("--meta-out",
                    help="Write sources metadata JSON (normalized cite → "
                         "case_name/url/url_source/via) to this path")
    ap.add_argument("--db", help=f"ndlaw opinions.db path "
                                 f"(or NDLAW_DB env; default {DEFAULT_DB})")
    ap.add_argument("--url", help="Deployed ndlaw Streamable HTTP URL "
                                  "(or NDLAW_URL env)")
    ap.add_argument("--auth", help="Basic auth as user:pass or base64 token "
                                   "(or NDLAW_AUTH env)")
    ap.add_argument("--no-public", action="store_true",
                    help=f"Do not fall back to the public server "
                         f"({PUBLIC_URL}) when no --db or --url is available")
    args = ap.parse_args()

    if not (args.opinion or args.cite_json or args.cites):
        ap.error("provide --opinion, --cite-json, or --cites")

    cites = _collect_cites(args)
    if not cites:
        print("No corpus-eligible ND citations found.", file=sys.stderr)
        if args.meta_out:
            Path(args.meta_out).expanduser().write_text("{}", encoding="utf-8")
        return 0

    try:
        backend, label = _pick_backend(args)
    except Exception as exc:
        print(f"Backend unavailable: {exc}", file=sys.stderr)
        return 2
    if backend is None:
        print("No ndlaw backend: no opinions.db found, no server URL given, "
              "and --no-public set. Pass --url https://<server>/mcp "
              "(plus --auth user:pass if the server requires it), or set "
              "NDLAW_URL/NDLAW_AUTH.",
              file=sys.stderr)
        return 2

    sources_dir = (Path(args.sources_dir).expanduser().resolve()
                   if args.sources_dir else None)
    meta_map: dict[str, dict] = {}
    exported = missed = 0
    try:
        for cite in cites:
            try:
                record = backend.lookup(cite)
            except Exception as exc:
                print(f"  {cite}: lookup failed ({exc})", file=sys.stderr)
                record = None
            if record is None or not record.get("text"):
                print(f"  {cite}: not in corpus", file=sys.stderr)
                missed += 1
                continue

            entry = {
                "case_name": record.get("case_name"),
                "url": record.get("url"),
                "url_source": record.get("url_source"),
                "date_filed": record.get("date_filed"),
                "via": "ndlaw",
            }
            # Key the metadata under every citation form of this opinion so
            # parallel cites (N.W.2d/3d) resolve to the same record.
            for alias in record.get("citations") or [cite]:
                meta_map.setdefault(" ".join(alias.split()), entry)

            if sources_dir is None:
                continue
            path = _write_source(sources_dir, record, cite)
            exported += 1
            print(f"  {cite}: {path}", file=sys.stderr)
    finally:
        backend.close()

    if args.meta_out:
        Path(args.meta_out).expanduser().write_text(
            json.dumps(meta_map, indent=2, ensure_ascii=False),
            encoding="utf-8")

    print(f"ndlaw export via {label}: {exported} written, "
          f"{missed} not in corpus, {len(meta_map)} cite keys in metadata.",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

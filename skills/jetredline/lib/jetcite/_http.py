"""Shared HTTP constants for network-backed source fetching.

httpx — and its SOCKS proxy support, which requires the ``socksio`` extra —
may be missing in sandboxed environments (e.g. Claude Cowork, where outbound
traffic is routed through a SOCKS proxy). Each source module imports httpx
under a ``try/except ImportError`` guard (binding ``httpx = None`` when it is
unavailable) so jetcite can be imported and used for local-only citation
scanning without httpx installed. Network functions short-circuit when
``httpx is None`` and include ``ImportError`` in their ``except`` clauses so a
missing ``socksio`` extra — which httpx raises at request time when a SOCKS
proxy is configured — fails soft instead of crashing the scan.
"""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
import warnings

from jetcite._version import __version__

try:
    import httpx
except ImportError:  # pragma: no cover - exercised in sandboxes without httpx
    httpx = None

USER_AGENT = (
    f"jetcite/{__version__} (legal-research-tool; "
    "https://github.com/jet52/jetcite)"
)


class EgressBlockedWarning(UserWarning):
    """A request was refused by a sandbox network-egress proxy.

    Signals that a host jetcite needs is not on the environment's egress
    allowlist (Claude Cowork / Claude Code sandbox), so some citation URLs
    could not be resolved or verified against their official source and
    jetcite fell back to a less specific link. See ``jetcite/NETWORK.md`` for
    the domains to allowlist.
    """


# Distinctive substrings of *proxy-level* egress denials: an HTTP CONNECT 403
# ("Tunnel connection failed: 403 Forbidden") and a SOCKS5 reply-code-2
# ("connection not allowed by ruleset"). A site's own 403 arrives as a normal
# HttpResponse, not an exception, so it is never matched here.
_EGRESS_BLOCK_MARKERS = (
    "tunnel connection failed",
    "from proxy after connect",
    "connection not allowed by ruleset",
)

_blocked_hosts: set[str] = set()


def egress_blocked_hosts() -> frozenset[str]:
    """Hosts refused by an egress proxy so far this process (deduplicated)."""
    return frozenset(_blocked_hosts)


def reset_egress_blocked_hosts() -> None:
    """Clear the recorded egress-block hosts (primarily for tests)."""
    _blocked_hosts.clear()


def _is_egress_block(exc: Exception) -> bool:
    if httpx is not None and isinstance(exc, httpx.ProxyError):
        return True
    text = str(exc).lower()
    return any(marker in text for marker in _EGRESS_BLOCK_MARKERS)


def _note_egress_block(url: str, exc: Exception) -> None:
    """Record a blocked host and warn once per host."""
    host = urllib.parse.urlsplit(url).hostname or url
    if host in _blocked_hosts:
        return
    _blocked_hosts.add(host)
    warnings.warn(
        f"Network egress to {host} was refused by the sandbox proxy, so some "
        f"jetcite citation URLs could not be resolved to their official "
        f"source (it fell back to a less specific link). This host is not on "
        f"the environment's egress allowlist — add the domains listed in "
        f"jetcite/NETWORK.md to the allowlist and start a new session.",
        EgressBlockedWarning,
        stacklevel=3,
    )


class HttpResponse:
    """Minimal normalized HTTP response.

    Exposes the httpx subset that jetcite's source modules rely on, so the
    same calling code works whether the body was fetched via httpx or the
    standard-library urllib fallback.
    """

    __slots__ = ("status_code", "content", "content_type")

    def __init__(self, status_code: int, content: bytes, content_type: str):
        self.status_code = status_code
        self.content = content
        #: Bare media type, without parameters (e.g. ``"text/html"``).
        self.content_type = content_type

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", "replace")


def http_get(url: str, timeout: float = 15.0) -> HttpResponse | None:
    """GET ``url`` following redirects, preferring httpx with a urllib fallback.

    httpx is used when available. The standard-library ``urllib`` is used when
    httpx is missing (e.g. dependency-free skill sandboxes) or when httpx
    fails at request time (e.g. a missing ``socksio`` extra raised under a
    SOCKS proxy). Returns an :class:`HttpResponse`, or ``None`` if every path
    failed to produce a response. HTTP error statuses (>= 400) are returned,
    not swallowed, so callers can distinguish them from transport failures.

    Note: urllib does not traverse SOCKS proxies, so the fallback only reaches
    hosts available over a direct or HTTP-proxied connection.
    """
    if httpx is not None:
        try:
            resp = httpx.get(
                url,
                follow_redirects=True,
                timeout=timeout,
                headers={"User-Agent": USER_AGENT},
            )
            content_type = (
                resp.headers.get("content-type", "").split(";")[0].strip()
            )
            return HttpResponse(resp.status_code, resp.content, content_type)
        except (httpx.HTTPError, ImportError) as exc:
            # A proxy-level egress denial will also block urllib (same proxy),
            # so warn and stop. Other failures (incl. a missing socksio
            # ImportError) fall through to the urllib path.
            if _is_egress_block(exc):
                _note_egress_block(url, exc)
                return None

    return _urllib_get(url, timeout)


def _urllib_get(url: str, timeout: float) -> HttpResponse | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return HttpResponse(
                getattr(resp, "status", 200) or 200,
                resp.read(),
                resp.headers.get_content_type(),
            )
    except urllib.error.HTTPError as exc:  # >= 400; preserve the status code
        return HttpResponse(exc.code, b"", "")
    except (urllib.error.URLError, OSError) as exc:
        if _is_egress_block(exc):
            _note_egress_block(url, exc)
        return None

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

from jetcite._version import __version__

USER_AGENT = (
    f"jetcite/{__version__} (legal-research-tool; "
    "https://github.com/jet52/jetcite)"
)

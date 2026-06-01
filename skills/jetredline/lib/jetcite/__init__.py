"""jetcite - American legal citation parser and linker."""

from jetcite._egress import EGRESS_ALLOWLIST
from jetcite._http import EgressBlockedWarning, egress_blocked_hosts
from jetcite._version import __version__
from jetcite.cache import citation_path
from jetcite.casename import extract_antecedent_name
from jetcite.models import Citation, CitationType, Source
from jetcite.scanner import lookup, scan_text

__all__ = [
    "Citation", "CitationType", "Source",
    "citation_path", "extract_antecedent_name", "lookup", "scan_text",
    "EGRESS_ALLOWLIST", "EgressBlockedWarning", "egress_blocked_hosts",
    "__version__",
]

# jetcite.legacy is importable but not star-exported — consumers import explicitly:
#   from jetcite.legacy import to_legacy_dict, legacy_cite_type, CASE_TYPES

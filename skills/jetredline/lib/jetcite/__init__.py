"""jetcite - American legal citation parser and linker."""

from jetcite.cache import citation_path
from jetcite.models import Citation, CitationType, Source
from jetcite.scanner import lookup, scan_text

__all__ = ["Citation", "CitationType", "Source", "citation_path", "lookup", "scan_text"]

# jetcite.legacy is importable but not star-exported — consumers import explicitly:
#   from jetcite.legacy import to_legacy_dict, legacy_cite_type, CASE_TYPES

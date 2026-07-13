"""azcourts.gov URL generation for Arizona court rules.

Arizona publishes its court rules only through an opaque DotNetNuke viewer with
non-derivable numeric ids (portalid/moduleid/attachmentid), so there is no
per-rule or per-rule-set deep link that can be built from a citation. The best
official, stable target is the Rules index page; a recognized rule citation
lands the reader there to navigate to the specific rule set.
"""

from __future__ import annotations

#: Official Arizona Supreme Court rules index (document-level entry point).
AZ_COURT_RULES_URL = "https://www.azcourts.gov/rules"


def az_court_rule_url() -> str:
    """Return the official Arizona court rules index URL."""
    return AZ_COURT_RULES_URL

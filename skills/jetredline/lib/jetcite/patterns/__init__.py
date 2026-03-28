"""Pattern registry for citation matchers."""

from jetcite.patterns.base import BaseMatcher

_registry: list[tuple[int, BaseMatcher]] = []


def register(priority: int, matcher: BaseMatcher):
    """Register a matcher at a given priority level (lower = higher priority)."""
    _registry.append((priority, matcher))
    _registry.sort(key=lambda x: x[0])


def get_matchers() -> list[BaseMatcher]:
    """Return all registered matchers in priority order."""
    return [m for _, m in _registry]


def _auto_register():
    """Import all pattern modules to trigger registration."""
    from jetcite.patterns import (  # noqa: F401
        constitutions,
        federal_cases,
        federal_rules,
        federal_statutes,
        neutral,
        regional,
    )
    from jetcite.patterns.states import nd  # noqa: F401


_auto_register()

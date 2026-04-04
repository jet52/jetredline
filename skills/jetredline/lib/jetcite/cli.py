"""CLI entry point for jetcite."""

from __future__ import annotations

import json
import platform
import subprocess
import sys
import webbrowser
from importlib.metadata import version
from pathlib import Path

import click

from jetcite.models import Citation
from jetcite.resolver import verify_citations_sync
from jetcite.scanner import lookup, scan_text


def _format_url(cite: Citation) -> str:
    """Return the primary URL for a citation."""
    if cite.sources:
        return cite.sources[0].url
    return "(no URL)"


def _format_table(citations: list[Citation], all_sources: bool = False) -> str:
    """Format citations as a human-readable table."""
    if not citations:
        return "No citations found."

    lines = []
    lines.append(f"  {'#':>3}  {'Citation':<30} {'Type':<14} URL")
    lines.append(f"  {'─' * 3}  {'─' * 30} {'─' * 14} {'─' * 50}")

    for i, cite in enumerate(citations, 1):
        url = _format_url(cite)
        verified = ""
        if cite.sources and cite.sources[0].verified is not None:
            verified = " ✓" if cite.sources[0].verified else " ✗"
        lines.append(f"  {i:>3}  {cite.normalized:<30} {cite.cite_type.value:<14} {url}{verified}")

        if cite.parallel_cites:
            lines.append(f"       {'':30} {'= ' + ', '.join(cite.parallel_cites)}")

        if all_sources and len(cite.sources) > 1:
            for src in cite.sources[1:]:
                v = ""
                if src.verified is not None:
                    v = " ✓" if src.verified else " ✗"
                lines.append(f"       {'':30} {'':14} {src.url}{v}")

    return "\n".join(lines)


def _format_json(citations: list[Citation]) -> str:
    """Format citations as JSON."""
    return json.dumps([c.to_dict() for c in citations], indent=2)


class DefaultGroup(click.Group):
    """A click Group that falls through to a default command when no subcommand matches."""

    def __init__(self, *args, default_cmd_name: str = "cite", **kwargs):
        super().__init__(*args, **kwargs)
        self.default_cmd_name = default_cmd_name

    def parse_args(self, ctx, args):
        # If the first arg isn't a known subcommand, insert the default command name
        if args and args[0] not in self.commands and not args[0].startswith("-"):
            args = [self.default_cmd_name] + args
        elif not args or (args[0].startswith("-") and args[0] not in ("--help", "--version")):
            args = [self.default_cmd_name] + args
        return super().parse_args(ctx, args)


@click.group(cls=DefaultGroup, invoke_without_command=True)
@click.version_option(version=version("jetcite"), prog_name="jetcite")
@click.pass_context
def main(ctx):
    """Parse legal citations and generate URLs to official sources."""
    pass


@main.command(name="cite", hidden=True)
@click.argument("citation", required=False)
@click.option("--scan", "scan_file", type=str,
              help="Scan a document file for citations (use '-' for stdin).")
@click.option("--format", "fmt", type=click.Choice(["url", "json", "table"]),
              default=None, help="Output format.")
@click.option("--verify", is_flag=True, help="HTTP-verify each URL.")
@click.option("--open", "open_url", is_flag=True, help="Open the first URL in browser.")
@click.option("--from-clipboard", is_flag=True, help="Read citation from clipboard.")
@click.option("--all-sources", is_flag=True, help="Show all available URLs.")
@click.option("--refs-dir", type=click.Path(exists=False), default=None,
              help="Check local reference cache at this directory.")
@click.option("--fetch", "do_fetch", is_flag=True,
              help="Fetch citation content from web and cache locally (requires --refs-dir).")
def cite_cmd(
    citation: str | None,
    scan_file: str | None,
    fmt: str | None,
    verify: bool,
    open_url: bool,
    from_clipboard: bool,
    all_sources: bool,
    refs_dir: str | None,
    do_fetch: bool,
):
    """Parse legal citations and generate URLs to official sources."""
    refs_path = Path(refs_dir).expanduser() if refs_dir else None

    if do_fetch and refs_path is None:
        click.echo("Error: --fetch requires --refs-dir", err=True)
        sys.exit(1)

    # Determine input
    if scan_file:
        if scan_file == "-":
            text = sys.stdin.read()
        else:
            with open(scan_file) as f:
                text = f.read()
        citations = scan_text(text, refs_dir=refs_path)
        if fmt is None:
            fmt = "table"
    elif from_clipboard:
        try:
            system = platform.system()
            if system == "Darwin":
                result = subprocess.run(["pbpaste"], capture_output=True, text=True, check=True)
            elif system == "Linux":
                result = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-o"],
                    capture_output=True, text=True, check=True,
                )
            elif system == "Windows":
                result = subprocess.run(
                    ["powershell", "-command", "Get-Clipboard"],
                    capture_output=True, text=True, check=True,
                )
            else:
                click.echo(f"Error: clipboard not supported on {system}", err=True)
                sys.exit(1)
            citation = result.stdout.strip()
        except FileNotFoundError:
            click.echo("Error: clipboard command not found (pbpaste/xclip/powershell)", err=True)
            sys.exit(1)
        except subprocess.CalledProcessError as e:
            click.echo(f"Error: could not read from clipboard: {e}", err=True)
            sys.exit(1)

    if not scan_file:
        if citation is None and not from_clipboard:
            # Try reading from stdin if piped
            if not sys.stdin.isatty():
                citation = sys.stdin.read().strip()
            else:
                click.echo("Usage: jetcite <citation> or jetcite --scan <file>", err=True)
                sys.exit(1)

        if citation:
            result = lookup(citation, refs_dir=refs_path)
            if result:
                citations = [result]
            else:
                click.echo(f"No citation pattern matched: {citation}", err=True)
                sys.exit(1)
        else:
            click.echo("No citation provided.", err=True)
            sys.exit(1)

        if fmt is None:
            fmt = "url"

    # Verify if requested
    if verify:
        verify_citations_sync(citations, rate_limit=1.0)

    # Fetch and cache if requested
    if do_fetch and refs_path:
        from jetcite.cache import fetch_and_cache
        for cite in citations:
            cached = fetch_and_cache(cite, refs_dir=refs_path)
            if cached:
                click.echo(f"Cached: {cite.normalized} -> {cached}", err=True)

    # Open URL
    if open_url and citations and citations[0].sources:
        webbrowser.open(citations[0].sources[0].url)

    # Output
    if fmt == "json":
        click.echo(_format_json(citations))
    elif fmt == "table":
        click.echo(_format_table(citations, all_sources=all_sources))
    else:  # url
        for cite in citations:
            click.echo(_format_url(cite))


@main.command()
@click.argument("citation", required=False)
@click.option("--file", "cache_file", type=str,
              help="Scan a document and cache all citations.")
@click.option("--refs-dir", type=click.Path(exists=False), default="~/refs",
              help="Reference cache directory (default: ~/refs).")
@click.option("--dry-run", is_flag=True,
              help="Show what would be fetched without actually fetching.")
@click.option("--status", is_flag=True,
              help="Report cache status for each citation.")
@click.option("--force", is_flag=True,
              help="Re-fetch even if already cached.")
@click.option("--refresh-stale", is_flag=True,
              help="Re-fetch only stale mutable content (statutes, regs, rules).")
@click.option("--parallel", type=int, default=None,
              help="Max concurrent fetches (default: 5). Use 1 for sequential.")
def cache(
    citation: str | None,
    cache_file: str | None,
    refs_dir: str,
    dry_run: bool,
    status: bool,
    force: bool,
    refresh_stale: bool,
    parallel: int | None,
):
    """Fetch citation content and cache locally.

    Scan a document or look up a single citation, then fetch content
    from the best available online source and cache it as markdown.

    \b
    Examples:
      jetcite cache "585 N.W.2d 123"
      jetcite cache --file opinion.md
      jetcite cache --file opinion.md --dry-run
      jetcite cache --file opinion.md --status
    """
    from jetcite.cache import (
        fetch_and_cache,
        is_stale,
        read_meta,
        resolve_local,
    )

    refs_path = Path(refs_dir).expanduser()

    # Gather citations
    if cache_file:
        if cache_file == "-":
            text = sys.stdin.read()
        else:
            with open(cache_file) as f:
                text = f.read()
        citations = scan_text(text, refs_dir=refs_path)
    elif citation:
        result = lookup(citation, refs_dir=refs_path)
        if result:
            citations = [result]
        else:
            click.echo(f"No citation pattern matched: {citation}", err=True)
            sys.exit(1)
    else:
        # Try stdin
        if not sys.stdin.isatty():
            text = sys.stdin.read()
            citations = scan_text(text, refs_dir=refs_path)
        else:
            click.echo("Usage: jetcite cache <citation> or jetcite cache --file <file>", err=True)
            sys.exit(1)

    if not citations:
        click.echo("No citations found.")
        return

    # Status mode: report cache state
    if status:
        _print_cache_status(citations, refs_path, resolve_local, read_meta, is_stale)
        return

    # Dry-run mode
    if dry_run:
        for cite in citations:
            local = resolve_local(cite, refs_path)
            if local and not force and not is_stale(cite, local):
                click.echo(f"  skip  {cite.normalized:<30} (cached)")
            else:
                url = "(no URL)"
                for s in cite.sources:
                    if s.name != "local":
                        url = s.url
                        break
                click.echo(f"  fetch {cite.normalized:<30} <- {url}")
        return

    # Fetch mode — use batch for multiple citations
    from jetcite.cache import fetch_and_cache_batch_sync

    fetched = 0
    failed = 0

    def _on_complete(cite, path):
        nonlocal fetched, failed
        if path:
            fetched += 1
            click.echo(f"  ok    {cite.normalized:<30} -> {path}", err=True)
        else:
            failed += 1
            click.echo(f"  FAIL  {cite.normalized}", err=True)

    max_concurrent = parallel if parallel is not None else 5
    results = fetch_and_cache_batch_sync(
        citations, refs_dir=refs_path, max_concurrent=max_concurrent,
        force=force, refresh_stale=refresh_stale, on_complete=_on_complete,
    )

    skipped = sum(1 for _, path in results if path and path.suffix == ".md") - fetched
    # Recalculate: batch returns all results, including already-cached
    cached_total = sum(1 for _, p in results if p is not None)
    click.echo(
        f"\n{fetched} fetched, {cached_total - fetched} already cached, {failed} failed "
        f"({len(citations)} total)",
        err=True,
    )


def _print_cache_status(citations, refs_path, resolve_local, read_meta, is_stale):
    """Print cache status table for citations."""
    lines = []
    lines.append(f"  {'#':>3}  {'Citation':<30} {'Status':<10} {'Age':>6}  Source")
    lines.append(f"  {'─' * 3}  {'─' * 30} {'─' * 10} {'─' * 6}  {'─' * 40}")

    for i, cite in enumerate(citations, 1):
        local = resolve_local(cite, refs_path)
        if local:
            meta = read_meta(local)
            stale = is_stale(cite, local)
            if meta and "fetched" in meta:
                from datetime import datetime, timezone
                fetched = datetime.fromisoformat(meta["fetched"])
                age_days = (datetime.now(timezone.utc) - fetched).days
                age_str = f"{age_days}d"
            else:
                age_str = "?"
            status_str = "stale" if stale else "cached"
            source = meta.get("source_url", "") if meta else ""
        else:
            status_str = "missing"
            age_str = ""
            source = ""
            for s in cite.sources:
                if s.name != "local":
                    source = s.url
                    break

        lines.append(
            f"  {i:>3}  {cite.normalized:<30} {status_str:<10} {age_str:>6}  {source}"
        )

    click.echo("\n".join(lines))


if __name__ == "__main__":
    main()

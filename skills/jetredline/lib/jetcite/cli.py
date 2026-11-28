"""CLI entry point for jetcite."""

from __future__ import annotations

import json
import platform
import subprocess
import sys
import webbrowser
from importlib.metadata import version

import click

from jetcite.models import Citation
from jetcite.resolver import verify_citations_sync
from jetcite.scanner import lookup, scan_text


def _format_url(cite: Citation) -> str:
    """Return the reader-facing URL for a citation: link_url (which the
    --prefer choice sets), else the primary URL."""
    if cite.link_url:
        return cite.link_url
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

        if cite.is_pin_cite:
            if cite.parent_normalized:
                lines.append(f"       {'':30} ↪ pin of {cite.parent_normalized}")
            else:
                lines.append(f"       {'':30} ↪ UNRESOLVED short form")
        elif cite.is_repeat:
            lines.append(f"       {'':30} ↪ repeat of {cite.parent_normalized}")

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
@click.option("--fetch", "do_fetch", is_flag=True,
              help="Fetch the text of the cited authority from its online source and print it.")
@click.option("--pin-cites", "pin_cites", is_flag=True,
              help="Include Bluebook pin-cite short forms (e.g. '491 F.3d at 363', 'Id. ¶ 14') linked to their parent cites (scan mode only).")
@click.option("--occurrences", "occurrences", is_flag=True,
              help="Include repeat full-form case cites (second and later appearances) linked to their first occurrence (scan mode only).")
@click.option("--prefer", "prefer", type=click.Choice(["official", "ndlaw"]),
              default=None,
              help="Which link to print for ND opinions, rules, N.D.C.C., and N.D.A.C.: the official site (default) or ndlaw.org. Defaults to $JETCITE_PREFER.")
def cite_cmd(
    citation: str | None,
    scan_file: str | None,
    fmt: str | None,
    verify: bool,
    open_url: bool,
    from_clipboard: bool,
    all_sources: bool,
    do_fetch: bool,
    pin_cites: bool,
    occurrences: bool,
    prefer: str | None,
):
    """Parse legal citations and generate URLs to official sources."""
    # Determine input
    if scan_file:
        if scan_file == "-":
            text = sys.stdin.read()
        else:
            with open(scan_file) as f:
                text = f.read()
        citations = scan_text(text, include_pin_cites=pin_cites,
                              include_occurrences=occurrences, prefer=prefer)
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
            result = lookup(citation, prefer=prefer)
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

    # Fetch the text if requested: print it in place of the usual output
    if do_fetch:
        from jetcite.fetch import fetch_text
        failed = 0
        for cite in citations:
            got = fetch_text(cite)
            if got is None:
                failed += 1
                click.echo(f"No text fetched: {cite.normalized}", err=True)
                continue
            click.echo(f"# {cite.normalized}  <{got.source_url}>\n", err=True)
            click.echo(got.text)
        sys.exit(1 if failed else 0)

    # Open URL
    if open_url and citations and (citations[0].link_url or citations[0].sources):
        webbrowser.open(_format_url(citations[0]))

    # Output
    if fmt == "json":
        click.echo(_format_json(citations))
    elif fmt == "table":
        click.echo(_format_table(citations, all_sources=all_sources))
    else:  # url
        for cite in citations:
            click.echo(_format_url(cite))


if __name__ == "__main__":
    main()

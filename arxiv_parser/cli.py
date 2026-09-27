"""Command-line entry point and interactive picker."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__, display, taxonomy
from .fetchers import ANNOUNCE_TYPES, FetchError, fetch_recent, fetch_today, filter_types, parse_file


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="arxiv_parser",
        description="Fetch and display new arXiv papers for a domain (e.g. cs) or subdomain (e.g. cs.CV).",
    )
    p.add_argument("-c", "--cats", nargs="+", metavar="CODE",
                   help="domain(s) or subdomain(s), e.g. cs.CV cs.LG or cs. Omit for the interactive picker.")
    p.add_argument("--mode", choices=("today", "recent"), default="today",
                   help="today = today's announcement (RSS, default); recent = submitted in the last N days (API)")
    p.add_argument("--days", type=int, default=3, help="window for --mode recent (default 3)")
    p.add_argument("--max", type=int, default=500, dest="max_results",
                   help="cap on papers for --mode recent (default 500)")
    p.add_argument("--type", nargs="+", choices=ANNOUNCE_TYPES, dest="types",
                   help="keep only these announce types (today mode), e.g. --type new cross")
    p.add_argument("--short", action="store_true", help="trim abstracts")
    p.add_argument("--json", metavar="FILE", help="also save results as JSON")
    p.add_argument("--md", metavar="FILE", help="also save results as Markdown")
    p.add_argument("--from-file", metavar="XML", help="parse a saved RSS/API XML file instead of fetching")
    p.add_argument("--list", action="store_true", help="show known domains and subdomains, then exit")
    p.add_argument("--no-color", action="store_true", help="disable colour output")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    display.setup_output(color=False if args.no_color else None)

    if args.list:
        print(taxonomy.format_listing())
        return 0

    try:
        if args.from_file:
            papers, meta = parse_file(Path(args.from_file).read_bytes())
            cats = args.cats or sorted({p.primary_category for p in papers if p.primary_category})
            mode = "today" if "pub_date" in meta else "file"
        else:
            cats, mode, days = _resolve_target(args)
            bad = [cat for cat in cats if not taxonomy.is_valid_code(cat)]
            if bad:
                print(f"Not a valid arXiv code: {', '.join(bad)} (try --list)", file=sys.stderr)
                return 2
            if mode == "today":
                print(f"Fetching today's announcement for {' + '.join(cats)} …", file=sys.stderr)
                papers, meta = fetch_today(cats)
            else:
                if args.days < 1:
                    print("--days must be at least 1", file=sys.stderr)
                    return 2
                print(f"Querying the arXiv API for {' + '.join(cats)}, last {days} day(s) …", file=sys.stderr)
                papers, meta = fetch_recent(cats, days=days, max_results=args.max_results)
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.", file=sys.stderr)
        return 130
    except (FetchError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.types:
        papers = filter_types(papers, set(args.types))

    display.print_header(cats, mode, meta, papers)
    if not papers:
        if mode == "today":
            print("No papers in this feed. arXiv does not announce on Friday/Saturday nights (US Eastern),\n"
                  "so weekend feeds are empty; try --mode recent --days 3.")
        else:
            print("No papers found.")
        return 0
    display.print_papers(papers, short=args.short)

    title = f"arXiv {' + '.join(cats)} — {meta.get('pub_date') or meta.get('end', '')[:10] or mode}"
    if args.json:
        display.export_json(papers, args.json, meta={**meta, "categories": cats, "mode": mode})
        print(f"Saved JSON → {args.json}", file=sys.stderr)
    if args.md:
        display.export_markdown(papers, args.md, title=title)
        print(f"Saved Markdown → {args.md}", file=sys.stderr)
    return 0


def _resolve_target(args: argparse.Namespace):
    if args.cats:
        return args.cats, args.mode, args.days
    cats = taxonomy.pick_categories()
    mode, days = taxonomy.pick_mode()
    print()
    return cats, mode, days

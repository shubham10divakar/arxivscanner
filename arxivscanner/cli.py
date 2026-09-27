"""Command-line entry point and interactive picker."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__, display, taxonomy
from .commands import COMMANDS
from .fetchers import ANNOUNCE_TYPES, FetchError, fetch_recent, fetch_today, filter_types, parse_file
from .filters import filter_keywords, keyword_pattern
from .library import LibraryError, remember_list


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="arxivscanner",
        description="Fetch and display new arXiv papers for a domain (e.g. cs) or subdomain (e.g. cs.CV).",
        epilog="reading list:  arxivscanner save 3 7 --tag important  |  arxivscanner saved  |  "
               "arxivscanner unsave 3   (add -h to any of these for help)",
    )
    p.add_argument("-c", "--cats", nargs="+", metavar="CODE",
                   help="domain(s) or subdomain(s), e.g. cs.CV cs.LG or cs. Omit for the interactive picker.")
    p.add_argument("--mode", choices=("today", "recent"), default="today",
                   help="today = today's announcement feed (default); "
                        "recent = the last N announcements, like arXiv's 'recent' page")
    p.add_argument("--days", type=int, default=3,
                   help="number of announcement days for --mode recent (default 3)")
    p.add_argument("--max", type=int, default=None, dest="max_results",
                   help="cap on papers for --mode recent (default: no cap)")
    p.add_argument("--type", nargs="+", choices=ANNOUNCE_TYPES, dest="types",
                   help="keep only these announce types, e.g. --type new "
                        "(recent mode has new and cross; today mode also has replace, replace-cross)")
    p.add_argument("-k", "--keyword", nargs="+", metavar="WORD", dest="keywords",
                   help='keep papers whose title or abstract mentions any of these words, '
                        'e.g. -k attention "vision transformer" (case-insensitive, matches from the start of a word)')
    p.add_argument("--short", action="store_true", help="trim abstracts")
    p.add_argument("--json", metavar="FILE", help="also save results as JSON")
    p.add_argument("--md", metavar="FILE", help="also save results as Markdown")
    p.add_argument("--from-file", metavar="XML", help="parse a saved RSS, API or OAI-PMH XML file instead of fetching")
    p.add_argument("--list", action="store_true", help="show known domains and subdomains, then exit")
    p.add_argument("--no-color", action="store_true", help="disable colour output")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in COMMANDS:
        try:
            return COMMANDS[argv[0]](argv[1:])
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.", file=sys.stderr)
            return 130
        except (LibraryError, FetchError, OSError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    args = build_parser().parse_args(argv)
    display.setup_output(color=False if args.no_color else None)

    if args.list:
        print(taxonomy.format_listing())
        return 0

    try:
        keywords = args.keywords or []
        if args.from_file:
            papers, meta = parse_file(Path(args.from_file).read_bytes())
            cats = args.cats or sorted({p.primary_category for p in papers if p.primary_category})
            mode = "today" if "pub_date" in meta else "file"
        else:
            cats, mode, days, keywords = _resolve_target(args)
            bad = [cat for cat in cats if not taxonomy.is_valid_code(cat)]
            if bad:
                print(f"Not a valid arXiv code: {', '.join(bad)} (try --list)", file=sys.stderr)
                return 2
            if mode == "today":
                print(f"Fetching today's announcement for {' + '.join(cats)} …", file=sys.stderr)
                papers, meta = fetch_today(cats)
            else:
                if days < 1:
                    print("--days must be at least 1", file=sys.stderr)
                    return 2
                print(f"Fetching the last {days} announcement(s) for {' + '.join(cats)} from arXiv OAI-PMH …",
                      file=sys.stderr)
                papers, meta = fetch_recent(cats, days=days, max_results=args.max_results)
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.", file=sys.stderr)
        return 130
    except (FetchError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.types:
        papers = filter_types(papers, set(args.types))
    searched = len(papers)
    pattern = keyword_pattern(keywords)
    if pattern:
        papers = filter_keywords(papers, pattern)
    else:
        keywords = []

    display.print_header(cats, mode, meta, papers, keywords=keywords, searched=searched)
    if not papers:
        if keywords and searched:
            print(f"None of the {searched} papers mention {display._quoted(keywords)}. "
                  "Try other keywords or a larger --days.")
        elif mode == "today":
            print("No papers in this feed. arXiv does not announce on Friday/Saturday nights (US Eastern),\n"
                  "so weekend feeds are empty; try --mode recent --days 1 for the latest announcement.")
        else:
            print("No papers in these announcements. Try a larger --days, or check the category code (--list).")
        return 0
    display.print_papers(papers, short=args.short, highlight=pattern)
    try:
        remember_list(papers)
        print(display.c("Save papers from this list with: arxivscanner save <numbers> [--tag important]", "dim"),
              file=sys.stderr)
    except (LibraryError, OSError) as e:
        print(f"  ! Could not remember this list for `arxivscanner save`: {e}", file=sys.stderr)

    title = f"arXiv {' + '.join(cats)} — {meta.get('pub_date') or meta.get('end', '')[:10] or mode}"
    if keywords:
        title += f" — {display._quoted(keywords)}"
    if args.json:
        display.export_json(papers, args.json,
                            meta={**meta, "categories": cats, "mode": mode, "keywords": keywords})
        print(f"Saved JSON → {args.json}", file=sys.stderr)
    if args.md:
        display.export_markdown(papers, args.md, title=title, highlight=pattern)
        print(f"Saved Markdown → {args.md}", file=sys.stderr)
    return 0


def _resolve_target(args: argparse.Namespace):
    if args.cats:
        return args.cats, args.mode, args.days, args.keywords or []
    cats = taxonomy.pick_categories()
    mode, days = taxonomy.pick_mode()
    keywords = args.keywords if args.keywords is not None else taxonomy.pick_keywords()
    print()
    return cats, mode, days, keywords

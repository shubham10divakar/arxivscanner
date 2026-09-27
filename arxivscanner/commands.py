"""Reading-list commands: save, saved, unsave."""
from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Sequence, Tuple

from . import display
from .fetchers import fetch_papers
from .filters import filter_keywords, keyword_pattern
from .library import Library, last_list, paper_from_dict, remember_list, resolve_library
from .models import Paper, split_id

_ID_RE = re.compile(r"\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7}")


def _library_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--library", metavar="FOLDER",
                        help="use this library folder for this command only")


def _short_title(title: str, width: int = 60) -> str:
    return textwrap.shorten(title, width, placeholder="…")


def resolve_refs(refs: Sequence[str], shown: Sequence[Paper]) -> Tuple[List[Tuple[str, Paper]], List[str], List[str]]:
    """Turn list numbers and arXiv ids/links into papers.

    Returns (label and paper for each one found, ids to look up on arXiv, error messages).
    """
    by_id = {p.arxiv_id: p for p in shown}
    found: List[Tuple[str, Paper]] = []
    lookup: List[str] = []
    errors: List[str] = []
    for ref in refs:
        if re.fullmatch(r"\d+", ref):
            n = int(ref)
            if not shown:
                errors.append(f"#{n}: there's no list to pick from yet; show some papers first")
            elif 1 <= n <= len(shown):
                found.append((f"#{n}", shown[n - 1]))
            else:
                errors.append(f"#{n}: the last list had {len(shown)} papers")
            continue
        arxiv_id, _ = split_id(ref)
        if arxiv_id in by_id:
            found.append((arxiv_id, by_id[arxiv_id]))
        elif _ID_RE.fullmatch(arxiv_id):
            if arxiv_id not in lookup:
                lookup.append(arxiv_id)
        else:
            errors.append(f"{ref}: not a list number or an arXiv id")
    return found, lookup, errors


def _report_errors(errors: Sequence[str]) -> None:
    for e in errors:
        print(f"  ! {e}", file=sys.stderr)


# ---------------------------------------------------------------- save

def cmd_save(argv: Sequence[str]) -> int:
    p = argparse.ArgumentParser(
        prog="arxivscanner save",
        description="Save papers to your library. Use the numbers from the last list shown, "
                    "or arXiv ids or links.",
        epilog="examples:  arxivscanner save 3 7 12 --tag important   |   arxivscanner save 2609.30264")
    p.add_argument("refs", nargs="+", metavar="N_OR_ID", help="list numbers (3 7 12) or arXiv ids/links")
    p.add_argument("--tag", nargs="+", default=[], metavar="TAG", help="tags to add, e.g. --tag important")
    _library_arg(p)
    args = p.parse_args(argv)
    display.setup_output()

    folder, _ = resolve_library(args.library)
    library = Library(folder)
    found, lookup, errors = resolve_refs(args.refs, last_list())
    if lookup:
        print(f"Looking up {len(lookup)} paper(s) on arXiv …", file=sys.stderr)
        papers, missing = fetch_papers(lookup)
        found += [(p.arxiv_id, p) for p in papers]
        errors += [f"{m}: not found on arXiv" for m in missing]

    if found:
        print(f"Saved to {folder}")
        for label, paper in found:
            new = library.add(paper, args.tag)
            tags = library.get(paper.arxiv_id)["tags"]
            note = "" if new else "  (already saved" + ("; tags updated)" if args.tag else ")")
            label = f"{label:>6}  " if label.startswith("#") else "        "
            print(f"{label}{paper.arxiv_id:<11} {_short_title(paper.title)}"
                  + (f"  [{', '.join(tags)}]" if tags else "") + note)
        library.save()
        print(display.c(f"{len(library)} papers in your library. See them with: arxivscanner saved", "dim"))
    _report_errors(errors)
    return 1 if errors else 0


# ---------------------------------------------------------------- saved

def _saved_line(entry: dict) -> str:
    parts = []
    saved_at = entry.get("saved_at", "")
    if saved_at:
        parts.append("Saved " + datetime.fromisoformat(saved_at).strftime("%d %b %Y"))
    if entry.get("tags"):
        parts.append("tags: " + ", ".join(entry["tags"]))
    return "★ " + " · ".join(parts)


def cmd_saved(argv: Sequence[str]) -> int:
    p = argparse.ArgumentParser(prog="arxivscanner saved", description="Show the papers in your library.",
                                epilog="examples:  arxivscanner saved --tag important   |   "
                                       "arxivscanner saved -k diffusion --md reading-list.md")
    p.add_argument("--tag", nargs="+", default=[], metavar="TAG", help="only papers with any of these tags")
    p.add_argument("-k", "--keyword", nargs="+", metavar="WORD", dest="keywords",
                   help="only papers whose title or abstract mentions any of these words")
    p.add_argument("--short", action="store_true", help="trim abstracts")
    p.add_argument("--json", metavar="FILE", help="also save the list as JSON")
    p.add_argument("--md", metavar="FILE", help="also save the list as Markdown")
    p.add_argument("--no-color", action="store_true", help="disable colour output")
    _library_arg(p)
    args = p.parse_args(argv)
    display.setup_output(color=False if args.no_color else None)

    folder, _ = resolve_library(args.library)
    library = Library(folder)
    entries = library.entries(args.tag)
    pattern = keyword_pattern(args.keywords or [])
    if pattern:
        entries = [e for e in entries if filter_keywords([paper_from_dict(e)], pattern)]
    papers = [paper_from_dict(e) for e in entries]

    display.print_library_header(folder, len(library), library.tag_counts(), len(papers),
                                 tags=args.tag, keywords=args.keywords or [] if pattern else [])
    if not papers:
        if not len(library):
            print("Your library is empty. Save papers from a list with: arxivscanner save 3 7 --tag important")
        else:
            print("No saved papers match.")
        return 0
    extra = {e["arxiv_id"]: [_saved_line(e)] for e in entries}
    display.print_papers(papers, short=args.short, highlight=pattern, extra=extra)
    remember_list(papers)

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"meta": {"library": str(folder), "tags": args.tag, "keywords": args.keywords or []},
             "count": len(entries), "papers": entries}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved JSON → {args.json}", file=sys.stderr)
    if args.md:
        display.export_markdown(papers, args.md, title="Saved papers", highlight=pattern, extra=extra)
        print(f"Saved Markdown → {args.md}", file=sys.stderr)
    return 0


# ---------------------------------------------------------------- unsave

def cmd_unsave(argv: Sequence[str]) -> int:
    p = argparse.ArgumentParser(
        prog="arxivscanner unsave",
        description="Remove papers from your library, or with --tag only remove those tags.",
        epilog="examples:  arxivscanner unsave 2609.30264   |   arxivscanner unsave 3 --tag to-read")
    p.add_argument("refs", nargs="+", metavar="N_OR_ID", help="list numbers (from the last list shown) or arXiv ids")
    p.add_argument("--tag", nargs="+", default=[], metavar="TAG", help="remove only these tags, keep the papers")
    _library_arg(p)
    args = p.parse_args(argv)
    display.setup_output()

    folder, _ = resolve_library(args.library)
    library = Library(folder)
    found, lookup, errors = resolve_refs(args.refs, last_list())
    targets = [(label, paper.arxiv_id) for label, paper in found] + [(i, i) for i in lookup]
    changed = False
    for label, arxiv_id in targets:
        entry = library.get(arxiv_id)
        if entry is None:
            errors.append(f"{label}: {arxiv_id} isn't in your library")
            continue
        if args.tag:
            library.untag(arxiv_id, args.tag)
            print(f"Removed tag(s) {', '.join(args.tag)} from {arxiv_id} {_short_title(entry.get('title', ''))}")
        else:
            library.remove(arxiv_id)
            print(f"Removed {arxiv_id} {_short_title(entry.get('title', ''))}")
        changed = True
    if changed:
        library.save()
        print(display.c(f"{len(library)} papers left in {folder}", "dim"))
    _report_errors(errors)
    return 1 if errors else 0


COMMANDS: Dict[str, Callable[[Sequence[str]], int]] = {
    "save": cmd_save,
    "saved": cmd_saved,
    "unsave": cmd_unsave,
}

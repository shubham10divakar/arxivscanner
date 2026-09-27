"""Reading-list commands: save, saved, unsave, config."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Sequence, Tuple

from . import display, fetchers
from . import library as _library
from .fetchers import FetchError, fetch_papers
from .filters import filter_keywords, keyword_pattern
from .library import (ENV_LIBRARY, Library, folder_stats, human_size, last_list, load_config, move_library,
                      move_pdfs, paper_from_dict, pdf_filename, pdf_folder, remember_list, resolve_library,
                      save_config, write_file_atomic)
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


def download_pdfs(library: Library, ids: Sequence[str]) -> List[str]:
    """Download the PDFs of these saved papers that don't have one yet. Returns error messages."""
    folder = pdf_folder(library.folder)
    todo = []
    for arxiv_id in ids:
        existing = library.pdf_path(arxiv_id)
        if not (existing and existing.is_file()):
            todo.append(arxiv_id)
    errors = []
    for n, arxiv_id in enumerate(todo, 1):
        target = folder / pdf_filename(paper_from_dict(library.get(arxiv_id)), folder)
        try:
            if target.is_file():
                note = "already in the folder"
            else:
                if n > 1:
                    fetchers.time.sleep(fetchers.API_DELAY)   # one at a time, as arXiv asks
                data = fetchers.fetch_pdf(arxiv_id)
                write_file_atomic(target, data)
                note = human_size(len(data))
            library.set_pdf(arxiv_id, target)
            print(f"  PDF {n}/{len(todo)}  {target.name}  ({note})")
        except FetchError as e:
            errors.append(f"{arxiv_id}: {e}")
    if todo:
        print(display.c(f"  PDFs are in {folder}", "dim"))
    return errors


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
    p.add_argument("--pdf", action="store_true",
                   help="also download the PDFs (always on with `arxivscanner config --auto-pdf on`)")
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
        if args.pdf or load_config().get("auto_pdf"):
            errors += download_pdfs(library, [paper.arxiv_id for _, paper in found])
            library.save()
        print(display.c(f"{len(library)} papers in your library. See them with: arxivscanner saved", "dim"))
    _report_errors(errors)
    return 1 if errors else 0


# ---------------------------------------------------------------- saved

def _saved_lines(library: Library, entry: dict) -> List[str]:
    parts = []
    saved_at = entry.get("saved_at", "")
    if saved_at:
        parts.append("Saved " + datetime.fromisoformat(saved_at).strftime("%d %b %Y"))
    if entry.get("tags"):
        parts.append("tags: " + ", ".join(entry["tags"]))
    lines = ["★ " + " · ".join(parts)]
    pdf = library.pdf_path(entry["arxiv_id"])
    if pdf:
        lines.append(f"PDF: {pdf}" if pdf.is_file() else f"PDF missing (was {pdf}); get it again with --download")
    return lines


def cmd_saved(argv: Sequence[str]) -> int:
    p = argparse.ArgumentParser(prog="arxivscanner saved", description="Show the papers in your library.",
                                epilog="examples:  arxivscanner saved --tag important   |   "
                                       "arxivscanner saved -k diffusion --md reading-list.md")
    p.add_argument("--tag", nargs="+", default=[], metavar="TAG", help="only papers with any of these tags")
    p.add_argument("-k", "--keyword", nargs="+", metavar="WORD", dest="keywords",
                   help="only papers whose title or abstract mentions any of these words")
    p.add_argument("--download", action="store_true", help="download the PDFs these papers don't have yet")
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
    errors: List[str] = []
    if args.download and entries:
        print(f"Downloading PDFs for {len(entries)} saved paper(s) that need one …", file=sys.stderr)
        errors = download_pdfs(library, [e["arxiv_id"] for e in entries])
        library.save()
        entries = [library.get(e["arxiv_id"]) for e in entries]
        print()
    papers = [paper_from_dict(e) for e in entries]

    display.print_library_header(folder, len(library), library.tag_counts(), len(papers),
                                 tags=args.tag, keywords=args.keywords or [] if pattern else [])
    if not papers:
        if not len(library):
            print("Your library is empty. Save papers from a list with: arxivscanner save 3 7 --tag important")
        else:
            print("No saved papers match.")
        return 0
    extra = {e["arxiv_id"]: _saved_lines(library, e) for e in entries}
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
    _report_errors(errors)
    return 1 if errors else 0


# ---------------------------------------------------------------- unsave

def cmd_unsave(argv: Sequence[str]) -> int:
    p = argparse.ArgumentParser(
        prog="arxivscanner unsave",
        description="Remove papers from your library, or with --tag only remove those tags.",
        epilog="examples:  arxivscanner unsave 2609.30264   |   arxivscanner unsave 3 --tag to-read")
    p.add_argument("refs", nargs="+", metavar="N_OR_ID", help="list numbers (from the last list shown) or arXiv ids")
    p.add_argument("--tag", nargs="+", default=[], metavar="TAG", help="remove only these tags, keep the papers")
    p.add_argument("--delete-pdf", action="store_true", help="also delete the downloaded PDF files")
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
            pdf = library.pdf_path(arxiv_id)
            library.remove(arxiv_id)
            print(f"Removed {arxiv_id} {_short_title(entry.get('title', ''))}")
            if pdf and pdf.is_file():
                if args.delete_pdf:
                    pdf.unlink()
                    print(f"  deleted {pdf}")
                else:
                    print(display.c(f"  PDF kept: {pdf} (add --delete-pdf to delete it)", "dim"))
        changed = True
    if changed:
        library.save()
        print(display.c(f"{len(library)} papers left in {folder}", "dim"))
    _report_errors(errors)
    return 1 if errors else 0


# ---------------------------------------------------------------- config

def _show_config() -> None:
    folder, source = resolve_library()
    papers, n_pdfs, size = folder_stats(folder)
    config = load_config()
    print(f"Library:   {folder}   (set by: {source})")
    print(f"PDFs:      {pdf_folder(folder)}" + ("" if config.get("pdfs") else "   (inside the library)"))
    print(f"Auto-PDF:  {'on' if config.get('auto_pdf') else 'off'}")
    print(f"Settings:  {_library.settings_dir() / 'config.json'}")
    print(f"Saved papers: {papers}   PDFs: {n_pdfs} ({human_size(size)})")


def _ask_move(what: str, old: Path, new: Path) -> str:
    """'move', 'fresh' or 'cancel'. Without a terminal to ask in, don't move."""
    if not sys.stdin.isatty():
        print(f"You have {what} in {old}. They stay there; run the same command with --move to move them.")
        return "fresh"
    while True:
        answer = input(f"You have {what} in {old}.\n"
                       f"Move them to {new}?  [Y]es / [n]o, start fresh there / [c]ancel: ").strip().lower()
        if answer in ("", "y", "yes"):
            return "move"
        if answer in ("n", "no"):
            return "fresh"
        if answer in ("c", "cancel"):
            return "cancel"


def cmd_config(argv: Sequence[str]) -> int:
    p = argparse.ArgumentParser(
        prog="arxivscanner config",
        description="Show or change where your saved papers and PDFs are kept. With no options, show the settings.",
        epilog='examples:  arxivscanner config --library "D:/Research/arxiv"   |   '
               'arxivscanner config --pdfs "E:/papers"   |   arxivscanner config --library default')
    p.add_argument("--library", metavar="FOLDER",
                   help='folder for your saved papers ("default" for ~/arxivscanner)')
    p.add_argument("--pdfs", metavar="FOLDER",
                   help='separate folder for downloaded PDFs ("default" for a pdfs folder inside the library)')
    p.add_argument("--auto-pdf", choices=("on", "off"), help="download the PDF of every paper you save")
    move = p.add_mutually_exclusive_group()
    move.add_argument("--move", action="store_true",
                      help="when changing --library or --pdfs, move what's there without asking")
    move.add_argument("--no-move", action="store_true",
                      help="when changing --library or --pdfs, leave the old files where they are")
    args = p.parse_args(argv)
    display.setup_output()

    if args.library is None and args.pdfs is None and args.auto_pdf is None:
        _show_config()
        return 0

    config = load_config()
    if args.library is not None:
        old = Path(config["library"]).expanduser() if config.get("library") else _library.default_library()
        new = _library.default_library() if args.library == "default" else Path(args.library).expanduser().resolve()
        if new.resolve() != old.resolve():
            papers, n_pdfs, size = folder_stats(old)
            choice = "fresh"
            if papers or n_pdfs:
                what = f"{papers} saved papers" + (f" and {n_pdfs} PDFs ({human_size(size)})" if n_pdfs else "")
                choice = "move" if args.move else "fresh" if args.no_move else _ask_move(what, old, new)
            if choice == "cancel":
                print("Nothing changed.")
                return 0
            if choice == "move":
                for line in move_library(old, new):
                    print(f"  {line} to {new}")
        if args.library == "default":
            config.pop("library", None)
        else:
            config["library"] = str(new)
        print(f"Library folder: {new}")
    if args.pdfs is not None:
        library_folder = Path(config["library"]).expanduser() if config.get("library") else _library.default_library()
        old_dir = pdf_folder(library_folder)
        new_dir = library_folder / "pdfs" if args.pdfs == "default" else Path(args.pdfs).expanduser().resolve()
        if new_dir.resolve() != old_dir.resolve():
            here = Library(library_folder).pdfs_in(old_dir)
            if here:
                choice = "move" if args.move else "fresh" if args.no_move else \
                    _ask_move(f"{len(here)} downloaded PDFs", old_dir, new_dir)
                if choice == "cancel":
                    print("Nothing changed.")
                    return 0
                if choice == "move":
                    print(f"  moved {move_pdfs(library_folder, old_dir, new_dir)} PDF(s) to {new_dir}")
        if args.pdfs == "default":
            config.pop("pdfs", None)
            print("PDFs: in a pdfs folder inside the library")
        else:
            config["pdfs"] = str(new_dir)
            print(f"PDFs: {config['pdfs']}")
    if args.auto_pdf is not None:
        config["auto_pdf"] = args.auto_pdf == "on"
        print(f"Auto-PDF: {args.auto_pdf}")
    save_config(config)
    if os.environ.get(ENV_LIBRARY):
        print(display.c(f"Note: {ENV_LIBRARY} is set to {os.environ[ENV_LIBRARY]}, which takes priority "
                        "over this setting until it's unset.", "yellow"))
    return 0


COMMANDS: Dict[str, Callable[[Sequence[str]], int]] = {
    "save": cmd_save,
    "saved": cmd_saved,
    "unsave": cmd_unsave,
    "config": cmd_config,
}

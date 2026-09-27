"""Colour terminal output plus JSON / Markdown export."""
from __future__ import annotations

import json
import os
import shutil
import sys
import textwrap
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Pattern, Sequence

from .models import Paper
from .taxonomy import describe

_COLORS = {
    "bold": "1", "dim": "2", "red": "31", "green": "32", "yellow": "33",
    "blue": "34", "magenta": "35", "cyan": "36",
}
TYPE_COLOR = {"new": "green", "cross": "cyan", "replace": "yellow", "replace-cross": "magenta"}

_use_color = False


def _enable_windows_vt() -> bool:
    """Turn on ANSI escape handling in Windows 10+ consoles."""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        return False


def setup_output(color: Optional[bool] = None) -> None:
    """Make stdout UTF-8 safe and decide whether to use colour."""
    global _use_color
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if color is None:
        color = sys.stdout.isatty() and "NO_COLOR" not in os.environ
    if color and os.name == "nt":
        color = _enable_windows_vt()
    _use_color = bool(color)


def c(text: str, *styles: str) -> str:
    if not _use_color or not styles:
        return text
    codes = ";".join(_COLORS[s] for s in styles)
    return f"\033[{codes}m{text}\033[0m"


def _hl(text: str, pattern: Optional[Pattern[str]], *styles: str) -> str:
    """Colour `text` with `styles`, and keyword matches in bold yellow."""
    if not pattern or not _use_color:
        return c(text, *styles)
    out, pos = [], 0
    for m in pattern.finditer(text):
        out.append(c(text[pos:m.start()], *styles) if m.start() > pos else "")
        out.append(c(m.group(0), "bold", "yellow"))
        pos = m.end()
    out.append(c(text[pos:], *styles) if pos < len(text) else "")
    return "".join(out)


def _quoted(keywords: Sequence[str]) -> str:
    return " or ".join(f'"{k}"' for k in keywords)


def _width() -> int:
    return max(60, min(shutil.get_terminal_size((100, 24)).columns, 120))


def _authors(authors: Sequence[str], limit: int = 6) -> str:
    if len(authors) <= limit:
        return ", ".join(authors)
    return ", ".join(authors[:limit]) + f", … (+{len(authors) - limit})"


def print_library_header(folder: object, total: int, tag_counts: Dict[str, int], shown: int,
                         tags: Sequence[str] = (), keywords: Sequence[str] = ()) -> None:
    print(c(f"Saved papers · {folder}", "bold"))
    if tag_counts:
        print(c("Tags: " + "  ".join(f"{t} ({n})" for t, n in tag_counts.items()), "dim"))
    filters = []
    if tags:
        filters.append("tagged " + " or ".join(tags))
    if keywords:
        filters.append("mentioning " + _quoted(keywords))
    if filters:
        print(f"{shown} of {total} saved papers {', '.join(filters)}\n")
    else:
        print(f"{total} saved paper{'' if total == 1 else 's'}\n")


def print_header(cats: Sequence[str], mode: str, meta: dict, papers: List[Paper],
                 keywords: Sequence[str] = (), searched: int = 0) -> None:
    names = ", ".join(f"{cat} ({describe(cat)})" if describe(cat) else cat for cat in cats)
    print(c(f"arXiv · {names}", "bold"))
    if mode == "today":
        when = meta.get("pub_date") or "unknown date"
        print(c(f"Announcement: {when}", "dim"))
    elif mode == "recent" and meta.get("days"):
        n = len(meta["days"])
        span = f"{_day(meta['start'])} → {_day(meta['end'])}" if n > 1 else _day(meta["end"])
        print(c(f"Last {n} announcement{'s' if n > 1 else ''}: {span}", "dim"))
    if meta.get("warning"):
        print(c(f"Warning: {meta['warning']}", "yellow"))
    counts = Counter(p.announce_type for p in papers if p.announce_type)
    order = list(TYPE_COLOR) + sorted(set(counts) - set(TYPE_COLOR))
    summary = "  ".join(c(f"{k}: {counts[k]}", TYPE_COLOR.get(k, "bold")) for k in order if counts[k])
    if keywords:
        print(f"{len(papers)} of {searched} papers match {c(_quoted(keywords), 'bold', 'yellow')}  {summary}\n")
    else:
        print(f"{len(papers)} papers  {summary}\n")


def _day(iso: str) -> str:
    """2026-09-25 -> Fri, 25 Sep 2026 (arXiv's listing style)."""
    return date.fromisoformat(iso[:10]).strftime("%a, %d %b %Y")


def _day_summary(papers: List[Paper], iso: str) -> str:
    new = sum(1 for p in papers if p.announced == iso and p.announce_type == "new")
    cross = sum(1 for p in papers if p.announced == iso and p.announce_type == "cross")
    return f"{new + cross} papers ({new} new, {cross} cross-lists)"


def print_papers(papers: List[Paper], short: bool = False, highlight: Optional[Pattern[str]] = None,
                 extra: Optional[Dict[str, List[str]]] = None) -> None:
    """Print papers, numbered. `extra` adds lines under a paper's details, keyed by arXiv id."""
    w = _width()
    day = None
    for i, p in enumerate(papers, 1):
        if p.announced and p.announced != day:
            day = p.announced
            print(c(f"── {_day(day)} · {_day_summary(papers, day)} " + "─" * 20, "bold", "magenta"))
            print()
        tag = f"[{p.announce_type}]" if p.announce_type else ""
        head = f"{i:>3}. {p.arxiv_id}{p.version} "
        print(c(head, "bold") + c(tag, TYPE_COLOR.get(p.announce_type, "dim")))
        indent = "     "
        for line in textwrap.wrap(p.title, w - len(indent)):
            print(indent + _hl(line, highlight, "bold", "blue"))
        if p.authors:
            print(textwrap.fill(_authors(p.authors), w, initial_indent=indent, subsequent_indent=indent))
        meta = [", ".join(p.categories)]
        if p.published:
            meta.append(p.published[:10])
        if p.comment:
            meta.append(p.comment)
        print(indent + c(textwrap.shorten(" · ".join(meta), w * 2 - len(indent), placeholder=" …"), "dim"))
        for line in (extra or {}).get(p.arxiv_id, []):
            print(indent + c(line, "yellow"))
        if p.abstract:
            abstract = textwrap.shorten(p.abstract, 300, placeholder=" …") if short else p.abstract
            for line in textwrap.wrap(abstract, w - len(indent)):
                print(indent + _hl(line, highlight))
        print(indent + c(p.abs_url, "cyan") + "  " + c(p.pdf_url, "dim"))
        print()


def export_json(papers: List[Paper], path: str, meta: Optional[dict] = None) -> None:
    doc = {"meta": meta or {}, "count": len(papers), "papers": [p.to_dict() for p in papers]}
    Path(path).write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def export_markdown(papers: List[Paper], path: str, title: str = "arXiv papers",
                    highlight: Optional[Pattern[str]] = None,
                    extra: Optional[Dict[str, List[str]]] = None) -> None:
    def bold(text: str) -> str:
        return highlight.sub(lambda m: f"**{m.group(0)}**", text) if highlight else text

    out = [f"# {title}", "", f"{len(papers)} papers", ""]
    day = None
    for i, p in enumerate(papers, 1):
        if p.announced and p.announced != day:
            day = p.announced
            out.append(f"## {_day(day)} · {_day_summary(papers, day)}")
            out.append("")
        tag = f" `{p.announce_type}`" if p.announce_type else ""
        out.append(f"{'###' if p.announced else '##'} {i}. {bold(p.title)}")
        out.append("")
        out.append(f"[{p.arxiv_id}{p.version}]({p.abs_url}) · [PDF]({p.pdf_url}){tag} · {', '.join(p.categories)}")
        out.append("")
        for line in (extra or {}).get(p.arxiv_id, []):
            out.append(f"_{line}_")
            out.append("")
        if p.authors:
            out.append(f"*{', '.join(p.authors)}*")
            out.append("")
        if p.comment:
            out.append(f"> {p.comment}")
            out.append("")
        if p.abstract:
            out.append(bold(p.abstract))
            out.append("")
    Path(path).write_text("\n".join(out), encoding="utf-8")

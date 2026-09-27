"""Colour terminal output plus JSON / Markdown export."""
from __future__ import annotations

import json
import os
import shutil
import sys
import textwrap
from collections import Counter
from pathlib import Path
from typing import List, Optional, Sequence

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


def _width() -> int:
    return max(60, min(shutil.get_terminal_size((100, 24)).columns, 120))


def _authors(authors: Sequence[str], limit: int = 6) -> str:
    if len(authors) <= limit:
        return ", ".join(authors)
    return ", ".join(authors[:limit]) + f", … (+{len(authors) - limit})"


def print_header(cats: Sequence[str], mode: str, meta: dict, papers: List[Paper]) -> None:
    names = ", ".join(f"{cat} ({describe(cat)})" if describe(cat) else cat for cat in cats)
    print(c(f"arXiv · {names}", "bold"))
    if mode == "today":
        when = meta.get("pub_date") or "unknown date"
        print(c(f"Announcement: {when}", "dim"))
    elif mode == "recent":
        print(c(f"Submitted {meta.get('start', '')[:10]} → {meta.get('end', '')[:10]} (UTC); "
                f"{meta.get('total', 0)} matched on arXiv", "dim"))
    if meta.get("warning"):
        print(c(f"Warning: {meta['warning']}", "yellow"))
    counts = Counter(p.announce_type for p in papers if p.announce_type)
    summary = "  ".join(c(f"{k}: {v}", TYPE_COLOR.get(k, "bold")) for k, v in counts.most_common())
    print(f"{len(papers)} papers  {summary}\n")


def print_papers(papers: List[Paper], short: bool = False) -> None:
    w = _width()
    for i, p in enumerate(papers, 1):
        tag = f"[{p.announce_type}]" if p.announce_type else ""
        head = f"{i:>3}. {p.arxiv_id}{p.version} "
        print(c(head, "bold") + c(tag, TYPE_COLOR.get(p.announce_type, "dim")))
        indent = "     "
        for line in textwrap.wrap(p.title, w - len(indent)):
            print(indent + c(line, "bold", "blue"))
        if p.authors:
            print(textwrap.fill(_authors(p.authors), w, initial_indent=indent, subsequent_indent=indent))
        meta = [", ".join(p.categories)]
        if p.published:
            meta.append(p.published[:10])
        if p.comment:
            meta.append(p.comment)
        print(indent + c(textwrap.shorten(" · ".join(meta), w * 2 - len(indent), placeholder=" …"), "dim"))
        if p.abstract:
            abstract = textwrap.shorten(p.abstract, 300, placeholder=" …") if short else p.abstract
            print(textwrap.fill(abstract, w, initial_indent=indent, subsequent_indent=indent))
        print(indent + c(p.abs_url, "cyan") + "  " + c(p.pdf_url, "dim"))
        print()


def export_json(papers: List[Paper], path: str, meta: Optional[dict] = None) -> None:
    doc = {"meta": meta or {}, "count": len(papers), "papers": [p.to_dict() for p in papers]}
    Path(path).write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def export_markdown(papers: List[Paper], path: str, title: str = "arXiv papers") -> None:
    out = [f"# {title}", "", f"{len(papers)} papers", ""]
    for i, p in enumerate(papers, 1):
        tag = f" `{p.announce_type}`" if p.announce_type else ""
        out.append(f"## {i}. {p.title}")
        out.append("")
        out.append(f"[{p.arxiv_id}{p.version}]({p.abs_url}) · [PDF]({p.pdf_url}){tag} · {', '.join(p.categories)}")
        out.append("")
        if p.authors:
            out.append(f"*{', '.join(p.authors)}*")
            out.append("")
        if p.comment:
            out.append(f"> {p.comment}")
            out.append("")
        if p.abstract:
            out.append(p.abstract)
            out.append("")
    Path(path).write_text("\n".join(out), encoding="utf-8")

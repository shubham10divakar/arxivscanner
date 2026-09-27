"""Saved papers (the library): where it lives and what is in it.

The library is one folder, chosen by (most specific first) the --library flag, the
ARXIVSCANNER_LIBRARY environment variable, the saved setting, or ~/arxivscanner. It holds
library.json and, later, downloaded PDFs. Settings and the last list shown live in
~/.arxivscanner, which never moves, so the tool can always find the library.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .models import Paper

ENV_LIBRARY = "ARXIVSCANNER_LIBRARY"
LIBRARY_FILE = "library.json"
_PAPER_FIELDS = {f.name for f in fields(Paper)}


class LibraryError(RuntimeError):
    pass


def settings_dir() -> Path:
    return Path.home() / ".arxivscanner"


def default_library() -> Path:
    return Path.home() / "arxivscanner"


def _write_json(path: Path, data: object) -> None:
    """Write atomically, so an interrupted write never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _read_json(path: Path) -> Optional[object]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        raise LibraryError(f"Could not read {path}: {e}") from e


# ---------------------------------------------------------------- settings

def load_config() -> dict:
    data = _read_json(settings_dir() / "config.json")
    return data if isinstance(data, dict) else {}


def save_config(config: dict) -> None:
    _write_json(settings_dir() / "config.json", config)


def folder_path(text: str) -> Path:
    """A folder typed by the user (or saved from one).

    Windows PowerShell 5 passes '.\\My papers\\' to programs as ".\\My papers\\" and the trailing
    backslash escapes the closing quote, so Python sees `.\\My papers"`. No Windows path can hold
    a quote, so a trailing one is dropped; one anywhere else means later arguments were swallowed.
    """
    text = text.strip()
    if os.name == "nt":
        text = text.rstrip('"').strip()
        if '"' in text:
            raise LibraryError(f"This folder has a stray quote in it: {text}\n"
                               "A quoted folder ending in a backslash confuses Windows PowerShell; "
                               "leave the last backslash off, e.g. '.\\My papers'")
    return Path(text).expanduser()


def resolve_library(override: Optional[str] = None) -> Tuple[Path, str]:
    """The library folder and what chose it: "--library", the env variable, "config" or "default"."""
    if override:
        return folder_path(override), "--library"
    env = os.environ.get(ENV_LIBRARY)
    if env:
        return folder_path(env), ENV_LIBRARY
    configured = load_config().get("library")
    if configured:
        return folder_path(configured), "config"
    return default_library(), "default"


def pdf_folder(library_folder: Path) -> Path:
    """Where PDFs go: the configured PDF folder, or `pdfs` inside the library folder."""
    configured = load_config().get("pdfs")
    return folder_path(configured) if configured else Path(library_folder) / "pdfs"


def folder_stats(library_folder: Path) -> Tuple[int, int, int]:
    """(saved papers, PDF files, total PDF bytes) for a library folder."""
    pdfs = pdf_folder(library_folder)
    files = [f for f in pdfs.glob("*.pdf") if f.is_file()] if pdfs.is_dir() else []
    return len(Library(library_folder)), len(files), sum(f.stat().st_size for f in files)


_UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


WINDOWS_PATH_LIMIT = 250   # Windows refuses paths longer than 260 characters by default


def pdf_filename(paper: Paper, folder: Optional[Path] = None, max_title: int = 80,
                 path_limit: Optional[int] = WINDOWS_PATH_LIMIT if os.name == "nt" else None) -> str:
    """'2609.30264 - AD-WM Action-Discriminative World Models for Counterfactual Model.pdf'.

    Readable in a file browser and safe on Windows, macOS and Linux. With a folder, the title is
    shortened so the full path stays under Windows' path length limit (down to just the id).
    """
    safe_id = paper.arxiv_id.replace("/", "_")
    if folder is not None and path_limit:
        room = path_limit - len(str(Path(folder).resolve())) - 1 - len(f"{safe_id} - .pdf")
        max_title = min(max_title, room)
    title = re.sub(r"\s+", " ", _UNSAFE_FILENAME.sub(" ", paper.title)).strip()
    if len(title) > max_title:
        title = title[:max_title].rsplit(" ", 1)[0] if max_title >= 10 else ""
    title = title.rstrip(" .")
    return f"{safe_id} - {title}.pdf" if title else f"{safe_id}.pdf"


def write_file_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".download-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit in ("B", "KB") else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


def move_library(src: Path, dst: Path) -> List[str]:
    """Move library.json (and the PDFs, when they live inside the library folder) from src to dst.

    Refuses when dst already holds a library, so two libraries are never silently merged.
    Returns what was moved, as messages.
    """
    src, dst = Path(src), Path(dst)
    if (dst / LIBRARY_FILE).exists():
        raise LibraryError(f"{dst} already has a library ({len(Library(dst))} papers); nothing was moved")
    dst.mkdir(parents=True, exist_ok=True)
    done = []
    if (src / LIBRARY_FILE).exists():
        shutil.move(str(src / LIBRARY_FILE), str(dst / LIBRARY_FILE))
        done.append(f"moved {LIBRARY_FILE}")
    inside_pdfs = src / "pdfs"
    if not load_config().get("pdfs") and inside_pdfs.is_dir():
        target = dst / "pdfs"
        target.mkdir(exist_ok=True)
        moved = 0
        for f in inside_pdfs.iterdir():
            if f.is_file() and not (target / f.name).exists():
                shutil.move(str(f), str(target / f.name))
                moved += 1
        done.append(f"moved {moved} PDF(s)")
        if not any(inside_pdfs.iterdir()):
            inside_pdfs.rmdir()
    if src.is_dir() and not any(src.iterdir()):
        src.rmdir()
    return done


def move_pdfs(library_folder: Path, old_dir: Path, new_dir: Path) -> int:
    """Move the library's downloaded PDFs from old_dir to new_dir and update their recorded paths."""
    library = Library(library_folder)
    new_dir.mkdir(parents=True, exist_ok=True)
    moved = 0
    for arxiv_id in library.pdfs_in(old_dir):
        current = library.pdf_path(arxiv_id)
        target = new_dir / current.name
        if not target.exists():
            shutil.move(str(current), str(target))
            moved += 1
        library.set_pdf(arxiv_id, target)
    library.save()
    return moved


# ---------------------------------------------------------------- the last list shown

def remember_list(papers: Sequence[Paper]) -> None:
    """Keep the list just shown, so `save 3 7` can refer to its numbers later."""
    _write_json(settings_dir() / "last-list.json", {
        "shown_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "papers": [p.to_dict() for p in papers],
    })


def last_list() -> List[Paper]:
    data = _read_json(settings_dir() / "last-list.json")
    if not isinstance(data, dict):
        return []
    return [paper_from_dict(d) for d in data.get("papers", [])]


def paper_from_dict(d: dict) -> Paper:
    return Paper(**{k: v for k, v in d.items() if k in _PAPER_FIELDS})


# ---------------------------------------------------------------- the library itself

class Library:
    """library.json: one entry per saved paper, with its details, tags and save date."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.file = self.folder / LIBRARY_FILE
        self._entries: Dict[str, dict] = {}
        data = _read_json(self.file)
        if isinstance(data, dict):
            for entry in data.get("papers", []):
                if entry.get("arxiv_id"):
                    self._entries[entry["arxiv_id"]] = entry

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, arxiv_id: str) -> bool:
        return arxiv_id in self._entries

    def get(self, arxiv_id: str) -> Optional[dict]:
        return self._entries.get(arxiv_id)

    def add(self, paper: Paper, tags: Iterable[str] = ()) -> bool:
        """Save a paper (or add tags to one already saved). True if it was new."""
        existing = self._entries.get(paper.arxiv_id)
        entry = paper.to_dict()
        entry.pop("announced", None)
        entry.pop("announce_type", None)
        if existing:
            entry.update({k: existing[k] for k in ("saved_at", "tags", "pdf") if k in existing})
        else:
            entry.update(saved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), tags=[], pdf=None)
        entry["tags"] = sorted(set(entry.get("tags") or []) | {t.strip() for t in tags if t.strip()})
        self._entries[paper.arxiv_id] = entry
        return existing is None

    def remove(self, arxiv_id: str) -> Optional[dict]:
        return self._entries.pop(arxiv_id, None)

    def pdf_path(self, arxiv_id: str) -> Optional[Path]:
        """Where this paper's PDF is (it may since have been deleted), or None if never downloaded."""
        stored = (self._entries.get(arxiv_id) or {}).get("pdf")
        if not stored:
            return None
        path = Path(stored)
        return path if path.is_absolute() else self.folder / path

    def set_pdf(self, arxiv_id: str, path: Optional[Path]) -> None:
        """Record a PDF's location, relative to the library folder when it is inside it,
        so the whole folder can be moved or synced."""
        if path is None:
            self._entries[arxiv_id]["pdf"] = None
            return
        try:
            stored = Path(path).resolve().relative_to(self.folder.resolve()).as_posix()
        except ValueError:
            stored = str(Path(path).resolve())
        self._entries[arxiv_id]["pdf"] = stored

    def pdfs_in(self, folder: Path) -> List[str]:
        """Ids of saved papers whose downloaded PDF sits in this folder."""
        folder = Path(folder).resolve()
        ids = []
        for arxiv_id in self._entries:
            path = self.pdf_path(arxiv_id)
            if path and path.is_file() and path.parent.resolve() == folder:
                ids.append(arxiv_id)
        return ids

    def untag(self, arxiv_id: str, tags: Iterable[str]) -> None:
        entry = self._entries[arxiv_id]
        entry["tags"] = [t for t in entry.get("tags", []) if t not in set(tags)]

    def entries(self, tags: Sequence[str] = ()) -> List[dict]:
        """Saved papers, newest first; with `tags`, only those carrying any of them."""
        wanted = set(tags)
        chosen = [e for e in self._entries.values() if not wanted or wanted & set(e.get("tags", []))]
        return sorted(chosen, key=lambda e: e.get("saved_at", ""), reverse=True)

    def tag_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for e in self._entries.values():
            for t in e.get("tags", []):
                counts[t] = counts.get(t, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

    def save(self) -> None:
        _write_json(self.file, {"version": 1, "papers": self.entries()})

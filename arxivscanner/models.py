"""The one normalised record every source produces."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Tuple

# New-style ids (2609.00001) and old-style ids (cs/0112017, math.GT/0309136), optional version.
_ID_RE = re.compile(r"(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?$")


def split_id(raw: str) -> Tuple[str, str]:
    """Return (arxiv_id, version) from an oai id, abs/pdf URL or bare id. Version may be ''."""
    raw = raw.strip()
    m = _ID_RE.search(raw)
    if not m:
        return raw, ""
    return m.group(1), m.group(2) or ""


@dataclass
class Paper:
    arxiv_id: str
    version: str = ""
    title: str = ""
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    categories: List[str] = field(default_factory=list)
    primary_category: str = ""
    announce_type: str = ""          # new | cross | replace | replace-cross ('' for API results)
    announced: Optional[str] = None  # ISO date of the arXiv listing day the paper appeared in (recent mode)
    published: Optional[str] = None  # ISO date/time of first submission (API) or announcement (RSS)
    updated: Optional[str] = None
    comment: str = ""
    journal_ref: str = ""
    doi: str = ""

    @property
    def abs_url(self) -> str:
        return f"https://arxiv.org/abs/{self.arxiv_id}"

    @property
    def pdf_url(self) -> str:
        return f"https://arxiv.org/pdf/{self.arxiv_id}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["abs_url"] = self.abs_url
        d["pdf_url"] = self.pdf_url
        return d

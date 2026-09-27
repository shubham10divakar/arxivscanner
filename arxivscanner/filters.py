"""Keyword search: keep papers whose title or abstract mentions any of the keywords."""
from __future__ import annotations

import re
from typing import Iterable, List, Optional, Pattern, Sequence

from .models import Paper


def keyword_pattern(keywords: Sequence[str]) -> Optional[Pattern[str]]:
    """One case-insensitive pattern matching any keyword at the start of a word.

    Matching from the start of a word keeps short acronyms useful: "gan" finds "GAN" and "GANs"
    but not "organization", and "attention" also finds "self-attention". A keyword with spaces is
    a phrase. Returns None when there are no keywords.
    """
    phrases = [k.split() for k in keywords if k.strip()]
    if not phrases:
        return None
    # Longest first, so "vision transformer" wins over "vision" when highlighting.
    alternatives = sorted((r"\s+".join(re.escape(w) for w in words) for words in phrases), key=len, reverse=True)
    return re.compile(r"(?<!\w)(?:" + "|".join(alternatives) + ")", re.IGNORECASE)


def filter_keywords(papers: Iterable[Paper], pattern: Pattern[str]) -> List[Paper]:
    return [p for p in papers if pattern.search(p.title) or pattern.search(p.abstract)]

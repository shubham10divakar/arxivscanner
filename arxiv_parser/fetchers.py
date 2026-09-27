"""Two sources, one output type.

fetch_today()  -> rss.arxiv.org      "What did arXiv announce today?"
fetch_recent() -> export.arxiv.org   "What was submitted in the last N days?"
"""
from __future__ import annotations

import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable, List, Optional, Sequence, Set, Tuple

from . import __version__
from .models import Paper, split_id
from .taxonomy import DOMAINS, is_domain

RSS_BASE = "https://rss.arxiv.org/rss/"
API_BASE = "https://export.arxiv.org/api/query"
USER_AGENT = f"arxiv-parser/{__version__} (personal research tool; python-urllib)"
API_DELAY = 3.0       # seconds between API calls, per arXiv's terms of use
API_PAGE = 200
ANNOUNCE_TYPES = ("new", "cross", "replace", "replace-cross")

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "dc": "http://purl.org/dc/elements/1.1/",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}


class FetchError(RuntimeError):
    pass


def _clean(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _split_authors(raw: str) -> List[str]:
    raw = _clean(raw)
    if not raw:
        return []
    parts = re.split(r",\s*|\s+and\s+", raw)
    return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------- HTTP

def http_get(url: str, retries: int = 4, backoff: float = 15.0, timeout: float = 60.0) -> bytes:
    """GET with retries and exponential back-off on network errors, 429 and 5xx."""
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/atom+xml, application/rss+xml, application/xml;q=0.9, */*;q=0.1",
    })
    last: Exception = FetchError("no attempt made")
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            # arXiv's front end sometimes answers 406 spuriously; it clears on retry.
            if e.code not in (406, 429) and e.code < 500:
                raise FetchError(f"HTTP {e.code} for {url}") from e
            last = e
            wait = backoff * (2 ** attempt)
            retry_after = e.headers.get("Retry-After") if e.headers else None
            if retry_after and retry_after.isdigit():
                wait = max(wait, float(retry_after))
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
            wait = backoff * (2 ** attempt)
        if attempt < retries:
            print(f"  ! {last}; retrying in {wait:.0f}s ({attempt + 1}/{retries})", file=sys.stderr)
            time.sleep(wait)
    hint = ""
    if isinstance(last, urllib.error.HTTPError) and last.code in (406, 429, 503):
        hint = " (arXiv is rate-limiting requests; wait a few minutes and try again)"
    raise FetchError(f"Giving up on {url}: {last}{hint}")


# ---------------------------------------------------------------- RSS (today)

def build_rss_url(cats: Sequence[str]) -> str:
    return RSS_BASE + "+".join(cats)


def parse_rss(data: bytes) -> Tuple[List[Paper], dict]:
    root = ET.fromstring(data)
    channel = root.find("channel")
    if channel is None:
        raise FetchError("Not an RSS document (no <channel>)")
    meta = {
        "title": _clean(channel.findtext("title")),
        "pub_date": _clean(channel.findtext("pubDate")),
        "last_build": _clean(channel.findtext("lastBuildDate")),
    }
    papers: List[Paper] = []
    for item in channel.findall("item"):
        guid = item.findtext("guid") or item.findtext("link") or ""
        arxiv_id, version = split_id(guid)
        desc = item.findtext("description") or ""
        m = re.search(r"Abstract:\s*(.*)", desc, re.S)
        abstract = _clean(m.group(1) if m else desc)

        announce = _clean(item.findtext("arxiv:announce_type", namespaces=NS))
        if not announce:
            m = re.search(r"Announce Type:\s*(\S+)", desc)
            announce = m.group(1) if m else ""

        cats = [_clean(c.text) for c in item.findall("category") if _clean(c.text)]
        pub = _clean(item.findtext("pubDate"))
        papers.append(Paper(
            arxiv_id=arxiv_id,
            version=version,
            title=_clean(item.findtext("title")),
            authors=_split_authors(item.findtext("dc:creator", namespaces=NS) or ""),
            abstract=abstract,
            categories=cats,
            primary_category=cats[0] if cats else "",
            announce_type=announce,
            published=_rfc822_to_iso(pub),
        ))
    return papers, meta


def _rfc822_to_iso(s: str) -> Optional[str]:
    if not s:
        return None
    try:
        return parsedate_to_datetime(s).isoformat()
    except (TypeError, ValueError):
        return s


def fetch_today(cats: Sequence[str]) -> Tuple[List[Paper], dict]:
    papers, meta = parse_rss(http_get(build_rss_url(cats)))
    return dedupe(papers), meta


# ---------------------------------------------------------------- API (recent)

def build_api_query(cats: Sequence[str], start: datetime, end: datetime) -> str:
    terms = [f"cat:{c}.*" if _has_subdomains(c) else f"cat:{c}" for c in cats]
    return f"({' OR '.join(terms)}) AND submittedDate:[{start:%Y%m%d%H%M} TO {end:%Y%m%d%H%M}]"


def _has_subdomains(code: str) -> bool:
    """cs, math -> query cs.*; quant-ph, hep-th have no subdomains and are queried as-is."""
    if not is_domain(code):
        return False
    return bool(DOMAINS[code][1]) if code in DOMAINS else True


def parse_api(data: bytes) -> Tuple[List[Paper], int]:
    root = ET.fromstring(data)
    total_txt = root.findtext("opensearch:totalResults", namespaces=NS)
    total = int(total_txt) if total_txt and total_txt.strip().isdigit() else 0
    papers: List[Paper] = []
    for e in root.findall("atom:entry", NS):
        raw_id = e.findtext("atom:id", default="", namespaces=NS)
        if "/api/errors" in raw_id:  # arXiv reports query errors as an entry
            raise FetchError("arXiv API error: " + _clean(e.findtext("atom:summary", namespaces=NS)))
        arxiv_id, version = split_id(raw_id)
        prim_el = e.find("arxiv:primary_category", NS)
        primary = prim_el.get("term", "") if prim_el is not None else ""
        cats = [primary] if primary else []
        for c in e.findall("atom:category", NS):
            t = c.get("term", "")
            if t and t not in cats:
                cats.append(t)
        papers.append(Paper(
            arxiv_id=arxiv_id,
            version=version,
            title=_clean(e.findtext("atom:title", namespaces=NS)),
            authors=[_clean(a.findtext("atom:name", namespaces=NS)) for a in e.findall("atom:author", NS)],
            abstract=_clean(e.findtext("atom:summary", namespaces=NS)),
            categories=cats,
            primary_category=primary or (cats[0] if cats else ""),
            published=e.findtext("atom:published", namespaces=NS),
            updated=e.findtext("atom:updated", namespaces=NS),
            comment=_clean(e.findtext("arxiv:comment", namespaces=NS)),
            journal_ref=_clean(e.findtext("arxiv:journal_ref", namespaces=NS)),
            doi=_clean(e.findtext("arxiv:doi", namespaces=NS)),
        ))
    return papers, total


def date_window(days: int, now: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    """Whole UTC days: today plus the (days - 1) days before it."""
    now = now or datetime.now(timezone.utc)
    end = now.replace(hour=23, minute=59, second=0, microsecond=0, tzinfo=None)
    start = (end - timedelta(days=days - 1)).replace(hour=0, minute=0)
    return start, end


def fetch_recent(cats: Sequence[str], days: int = 3, max_results: int = 500,
                 progress: bool = True) -> Tuple[List[Paper], dict]:
    start, end = date_window(days)
    query = build_api_query(cats, start, end)
    papers: List[Paper] = []
    total = 0
    offset = 0
    warning = ""
    while offset < max_results:
        if offset:
            time.sleep(API_DELAY)
        n = min(API_PAGE, max_results - offset)
        params = urllib.parse.urlencode({
            "search_query": query, "start": offset, "max_results": n,
            "sortBy": "submittedDate", "sortOrder": "descending",
        })
        try:
            page, total = parse_api(http_get(f"{API_BASE}?{params}"))
        except FetchError as e:
            if not papers:
                raise
            # arXiv rate-limits in bursts; keep what we already have rather than losing it all.
            warning = f"stopped after {len(papers)} of {total} papers: {e}"
            print(f"  ! {warning}", file=sys.stderr)
            break
        papers.extend(page)
        offset += n
        if progress:
            print(f"  fetched {len(papers)} / {min(total, max_results)}", file=sys.stderr)
        if not page or offset >= total:
            break
    meta = {"query": query, "total": total, "start": start.isoformat(), "end": end.isoformat()}
    if warning:
        meta["warning"] = warning
    return dedupe(papers), meta


# ---------------------------------------------------------------- helpers

def dedupe(papers: Iterable[Paper]) -> List[Paper]:
    seen: Set[str] = set()
    out: List[Paper] = []
    for p in papers:
        if p.arxiv_id not in seen:
            seen.add(p.arxiv_id)
            out.append(p)
    return out


def filter_types(papers: Iterable[Paper], types: Optional[Set[str]]) -> List[Paper]:
    if not types:
        return list(papers)
    return [p for p in papers if p.announce_type in types]


def parse_file(data: bytes) -> Tuple[List[Paper], dict]:
    """Parse a saved RSS or API XML document (for offline use)."""
    head = data[:2000].lstrip()
    if b"<rss" in head:
        return parse_rss(data)
    papers, total = parse_api(data)
    return papers, {"total": total}

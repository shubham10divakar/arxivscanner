"""Three sources, one output type.

fetch_today()  -> rss.arxiv.org                  "What did arXiv announce today?"
fetch_recent() -> export.arxiv.org (search API)  "What was submitted in the last N days?"
                  oaipmh.arxiv.org (OAI-PMH)     same question; fallback when the API refuses
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
USER_AGENT = f"arxivscanner/{__version__} (+https://github.com/shubham10divakar/arxivscanner)"
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

class RefusedError(FetchError):
    """The server declined the request outright (export.arxiv.org answers 406 when it throttles a host).

    Waiting does not clear it within a run, so callers should switch source instead of retrying.
    """


def http_get(url: str, retries: int = 4, backoff: float = 15.0, timeout: float = 120.0) -> bytes:
    """GET with retries and exponential back-off on network errors, 429 and 5xx (honouring Retry-After)."""
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
            if e.code in (403, 406):
                raise RefusedError(f"HTTP {e.code} {e.reason} from {urllib.parse.urlsplit(url).netloc}") from e
            if e.code != 429 and e.code < 500:
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
    if isinstance(last, urllib.error.HTTPError) and last.code in (429, 503):
        hint = " (arXiv is busy; wait a few minutes and try again)"
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


def _fetch_recent_api(cats: Sequence[str], start: datetime, end: datetime, max_results: int,
                      progress: bool) -> Tuple[List[Paper], dict]:
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
        except RefusedError:
            raise
        except FetchError as e:
            if not papers:
                raise
            # Keep what we already have rather than losing it all.
            warning = f"stopped after {len(papers)} of {total} papers: {e}"
            print(f"  ! {warning}", file=sys.stderr)
            break
        papers.extend(page)
        offset += n
        if progress:
            print(f"  fetched {len(papers)} / {min(total, max_results)}", file=sys.stderr)
        if not page or offset >= total:
            break
    meta = {"source": "api", "query": query, "total": total}
    if warning:
        meta["warning"] = warning
    return dedupe(papers), meta


# ---------------------------------------------------------------- OAI-PMH (recent, fallback)

OAI_BASE = "https://oaipmh.arxiv.org/oai"
OAI_NS = {"oai": "http://www.openarchives.org/OAI/2.0/", "ax": "http://arxiv.org/OAI/arXivRaw/"}
OAI_MAX_PAGES = 20   # safety cap; one page holds up to ~1300 records
# Archives that OAI-PMH files under the "physics" group.
PHYSICS_ARCHIVES = {
    "astro-ph", "cond-mat", "gr-qc", "hep-ex", "hep-lat", "hep-ph", "hep-th", "math-ph",
    "nlin", "nucl-ex", "nucl-th", "physics", "quant-ph",
}


def oai_set(code: str) -> str:
    """cs -> cs:cs, cs.CV -> cs:cs:CV, astro-ph.CO -> physics:astro-ph:CO, quant-ph -> physics:quant-ph."""
    archive, _, sub = code.partition(".")
    group = "physics" if archive in PHYSICS_ARCHIVES else archive
    return f"{group}:{archive}" + (f":{sub}" if sub else "")


def parse_oai(data: bytes) -> Tuple[List[Paper], str]:
    """Parse one ListRecords page in the arXivRaw format. Returns (papers, resumption token or '').

    arXivRaw lists every version with its date, so `published` is the true v1 submission time
    (the plain arXiv format's <created> is sometimes the latest version's date instead).
    """
    root = ET.fromstring(data)
    err = root.find("oai:error", OAI_NS)
    if err is not None:
        if err.get("code") == "noRecordsMatch":
            return [], ""
        raise FetchError(f"OAI-PMH error {err.get('code')}: {_clean(err.text)}")
    papers: List[Paper] = []
    for rec in root.iterfind(".//oai:record", OAI_NS):
        header = rec.find("oai:header", OAI_NS)
        if header is not None and header.get("status") == "deleted":
            continue
        m = rec.find(".//ax:arXivRaw", OAI_NS)
        if m is None:
            continue
        versions = [(v.get("version", ""), _rfc822_to_iso(_clean(v.findtext("ax:date", namespaces=OAI_NS))))
                    for v in m.iterfind("ax:version", OAI_NS)]
        cats = _clean(m.findtext("ax:categories", namespaces=OAI_NS)).split()
        papers.append(Paper(
            arxiv_id=_clean(m.findtext("ax:id", namespaces=OAI_NS)),
            version=versions[-1][0] if versions else "",
            title=_clean(m.findtext("ax:title", namespaces=OAI_NS)),
            authors=_split_authors(m.findtext("ax:authors", namespaces=OAI_NS) or ""),
            abstract=_clean(m.findtext("ax:abstract", namespaces=OAI_NS)),
            categories=cats,
            primary_category=cats[0] if cats else "",
            published=versions[0][1] if versions else None,
            updated=versions[-1][1] if len(versions) > 1 else None,
            comment=_clean(m.findtext("ax:comments", namespaces=OAI_NS)),
            journal_ref=_clean(m.findtext("ax:journal-ref", namespaces=OAI_NS)),
            doi=_clean(m.findtext("ax:doi", namespaces=OAI_NS)),
        ))
    token = _clean(root.findtext(".//oai:resumptionToken", namespaces=OAI_NS))
    return papers, token


def submitted_in(p: Paper, start: datetime, end: datetime) -> bool:
    """True if the paper's first version was submitted inside [start, end].

    OAI-PMH lists every record *changed* since a date, so papers that only got a new version
    appear too; they are dropped by their v1 date. The id's YYMM prefix is a cheap second check.
    """
    if not p.published or not re.match(r"\d{4}\.\d{4,5}$", p.arxiv_id):
        return False
    if not (start.strftime("%Y-%m-%d") <= p.published[:10] <= end.strftime("%Y-%m-%d")):
        return False
    return start.strftime("%y%m") <= p.arxiv_id[:4] <= end.strftime("%y%m")


def _fetch_recent_oai(cats: Sequence[str], start: datetime, end: datetime, max_results: int,
                      progress: bool) -> Tuple[List[Paper], dict]:
    papers: List[Paper] = []
    first = True
    for cat in cats:
        params = {"verb": "ListRecords", "metadataPrefix": "arXivRaw",
                  "from": start.strftime("%Y-%m-%d"), "set": oai_set(cat)}
        for _ in range(OAI_MAX_PAGES):
            if not first:
                time.sleep(API_DELAY)
            first = False
            page, token = parse_oai(http_get(f"{OAI_BASE}?{urllib.parse.urlencode(params)}"))
            papers.extend(p for p in page if submitted_in(p, start, end))
            if progress:
                print(f"  {oai_set(cat)}: scanned {len(page)} records, {len(papers)} submitted in window",
                      file=sys.stderr)
            if not token:
                break
            params = {"verb": "ListRecords", "resumptionToken": token}
    papers = dedupe(papers)
    papers.sort(key=lambda p: p.arxiv_id, reverse=True)  # ids grow with submission time
    total = len(papers)
    return papers[:max_results], {"source": "oai", "total": total}


def fetch_recent(cats: Sequence[str], days: int = 3, max_results: int = 500,
                 progress: bool = True, source: str = "auto") -> Tuple[List[Paper], dict]:
    """Papers submitted in the last `days` UTC days.

    source: "api" (export.arxiv.org search API), "oai" (OAI-PMH) or "auto" (API, and OAI-PMH
    when the API refuses the request, which it does with HTTP 406 while it throttles a host).
    """
    start, end = date_window(days)
    if source == "oai":
        papers, meta = _fetch_recent_oai(cats, start, end, max_results, progress)
    else:
        try:
            papers, meta = _fetch_recent_api(cats, start, end, max_results, progress)
        except RefusedError as e:
            if source == "api":
                raise FetchError(f"{e}. The arXiv API is throttling this machine; "
                                 f"try --source oai or wait a while.") from e
            print(f"  ! arXiv API refused the query ({e}); switching to OAI-PMH …", file=sys.stderr)
            papers, meta = _fetch_recent_oai(cats, start, end, max_results, progress)
    meta.update({"start": start.isoformat(), "end": end.isoformat()})
    return papers, meta


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
    """Parse a saved RSS, API or OAI-PMH XML document (for offline use)."""
    head = data[:2000].lstrip()
    if b"<rss" in head:
        return parse_rss(data)
    if b"<OAI-PMH" in head:
        papers, _ = parse_oai(data)
        return papers, {"source": "oai", "total": len(papers)}
    papers, total = parse_api(data)
    return papers, {"total": total}

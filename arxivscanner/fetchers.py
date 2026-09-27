"""Two sources, one output type.

fetch_today()  -> rss.arxiv.org      "What did arXiv announce today?"
fetch_recent() -> oaipmh.arxiv.org   "What did arXiv announce in its last N announcements?"
                                     (the same papers as arxiv.org/list/<cat>/recent, grouped by day)
"""
from __future__ import annotations

import re
import unicodedata
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from . import __version__
from .models import Paper, split_id

RSS_BASE = "https://rss.arxiv.org/rss/"
USER_AGENT = f"arxivscanner/{__version__} (+https://github.com/shubham10divakar/arxivscanner)"
API_DELAY = 3.0       # seconds between requests, per arXiv's terms of use
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
    """Collapse whitespace and turn LaTeX accents into letters."""
    return detex(re.sub(r"\s+", " ", text or "").strip())


# LaTeX accents as combining characters: \'a -> á, \v{s} -> š, \c{c} -> ç ...
_TEX_SYMBOL_ACCENTS = {"'": "\u0301", "`": "\u0300", "^": "\u0302", '"': "\u0308", "~": "\u0303",
                       "=": "\u0304", ".": "\u0307"}
_TEX_LETTER_ACCENTS = {"u": "\u0306", "v": "\u030c", "H": "\u030b", "c": "\u0327", "k": "\u0328", "r": "\u030a"}
_TEX_LETTERS = {"ss": "ß", "o": "ø", "O": "Ø", "l": "ł", "L": "Ł", "ae": "æ", "AE": "Æ",
                "oe": "œ", "OE": "Œ", "aa": "å", "AA": "Å", "i": "ı", "j": "ȷ"}
_TEX_SYMBOL_RE = re.compile(r"""\\([`'^"~=.])\s*(?:\{\s*(\\[ij]|[A-Za-z])\s*\}|(\\[ij](?![A-Za-z])|[A-Za-z]))""")
_TEX_LETTER_RE = re.compile(r"\\([uvHckr])(?:\s*\{\s*(\\[ij]|[A-Za-z])\s*\}|\s+([A-Za-z]))")
_TEX_SPECIAL_RE = re.compile(r"\{?\\(ss|ae|AE|oe|OE|aa|AA|[oOlLij])(?![A-Za-z])(?:\{\})?\}?")
_BRACED_LETTER_RE = re.compile(r"\{([^\x00-\x7f])\}")
_TEX_ESCAPES = {"&": "&", "_": "_", "%": "%", "#": "#", "dag": "†", "ddag": "‡"}
_TEX_ESCAPE_RE = re.compile(r"\\([&_%#]|d?dag(?![A-Za-z]))")


def detex(text: str) -> str:
    """Turn LaTeX accent commands, as found in arXiv metadata, into Unicode letters.

    Tom\\'as -> Tomás, Deu{\\ss}er -> Deußer, Luk\\'a\\v{s} -> Lukáš, R\\&D -> R&D. Math such as $x^{2}$
    is left alone.
    """
    if "\\" not in text:
        return text

    def accent(mark: str, base: str) -> str:
        base = {"\\i": "i", "\\j": "j"}.get(base, base)
        return unicodedata.normalize("NFC", base + mark)

    text = _TEX_SYMBOL_RE.sub(lambda m: accent(_TEX_SYMBOL_ACCENTS[m.group(1)], m.group(2) or m.group(3)), text)
    text = _TEX_LETTER_RE.sub(lambda m: accent(_TEX_LETTER_ACCENTS[m.group(1)], m.group(2) or m.group(3)), text)
    text = _TEX_SPECIAL_RE.sub(lambda m: _TEX_LETTERS[m.group(1)], text)
    text = _TEX_ESCAPE_RE.sub(lambda m: _TEX_ESCAPES[m.group(1)], text)
    return _BRACED_LETTER_RE.sub(r"\1", text)


def _split_authors(raw: str) -> List[str]:
    raw = _clean(raw)
    if not raw:
        return []
    parts = re.split(r",\s*|\s+and\s+", raw)
    return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------- HTTP

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


# ---------------------------------------------------------------- API (saved files only)

def parse_api(data: bytes) -> Tuple[List[Paper], int]:
    """Parse an export.arxiv.org API (Atom) response. Used for --from-file."""
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


# ---------------------------------------------------------------- OAI-PMH (recent)

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
        if header is None or header.get("status") == "deleted":
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
            # The datestamp is the listing day of the record's latest change; recent mode
            # replaces it with the day the paper was first announced.
            announced=_clean(header.findtext("oai:datestamp", namespaces=OAI_NS)) or None,
        ))
    token = _clean(root.findtext(".//oai:resumptionToken", namespaces=OAI_NS))
    return papers, token


def announcement_days(latest: date, n: int) -> List[date]:
    """The n arXiv listing days (Monday to Friday) ending at `latest`, oldest first."""
    days: List[date] = []
    d = latest
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return days[::-1]


def _last_weekday(d: date) -> date:
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _id_key(arxiv_id: str) -> Optional[Tuple[int, int]]:
    m = re.match(r"(\d{4})\.(\d{4,5})$", arxiv_id)
    return (int(m.group(1)), int(m.group(2))) if m else None


def _in_scope(category: str, cats: Sequence[str]) -> bool:
    return any(category == c or category.startswith(c + ".") for c in cats)


def group_by_announcement(papers: Sequence[Paper], cats: Sequence[str],
                          calendar: Sequence[date]) -> List[Paper]:
    """Rebuild arXiv's "recent" listing from OAI-PMH records.

    `papers` carry the OAI datestamp (the listing day of their latest change) in `announced`.
    `calendar` is the listing days to consider, oldest first; the first one is only a guard used
    to find where the second one starts, and is not returned.

    arXiv hands out ids in order at announcement time, so each listing day owns one block of ids.
    Papers still at v1 whose datestamp is that day mark the block. Every paper is then placed on
    the day whose block holds its id, which recovers papers that got a new version later in the
    week and drops old papers that were only edited. OAI-PMH does not record when a paper was
    cross-listed, so the few papers cross-listed into a category after their own announcement are
    missed or listed on their original day. Checked against arxiv.org/list/<cat>/recent for seven
    categories (3452 papers), about 99% match, on the same day and in the same order.
    """
    days = [d.isoformat() for d in calendar]
    candidates: Dict[str, List[Tuple[int, int]]] = {d: [] for d in days}
    for p in papers:
        k = _id_key(p.arxiv_id)
        if k is None or p.version != "v1" or p.announced not in candidates:
            continue
        announced_month = int((date.fromisoformat(p.announced) - timedelta(days=1)).strftime("%y%m"))
        if k[0] == announced_month:  # ids carry the month they were handed out in
            candidates[p.announced].append(k)

    # Where each day's block starts. A datestamp is never earlier than the announcement, so every
    # candidate of an earlier day lies inside that day's block or before it. The day's block
    # therefore starts at its first candidate above everything seen on earlier days; candidates
    # below that are older papers edited on this day.
    starts: List[Tuple[Tuple[int, int], str]] = []
    highest: Optional[Tuple[int, int]] = None
    for d in days:
        ks = [k for k in candidates[d] if highest is None or k > highest]
        if not ks:
            continue
        starts.append((min(ks), d))
        highest = max(ks)

    wanted = set(days[1:])
    out: List[Paper] = []
    for p in papers:
        k = _id_key(p.arxiv_id)
        if k is None or not p.announced:
            continue
        day = None
        for start, d in starts:
            if k >= start:
                day = d
        # A paper can only have changed on or after the day it was announced.
        if day is None or day > p.announced or day not in wanted:
            continue
        p.announced = day
        p.announce_type = "new" if _in_scope(p.primary_category, cats) else "cross"
        out.append(p)
    # arXiv's order: newest day first; within a day new submissions, then cross-lists, newest first.
    out.sort(key=lambda p: (p.announced, p.announce_type == "new", _id_key(p.arxiv_id)), reverse=True)
    return out


def fetch_recent(cats: Sequence[str], days: int = 3, max_results: Optional[int] = None,
                 progress: bool = True, today: Optional[date] = None) -> Tuple[List[Paper], dict]:
    """The last `days` arXiv announcements for `cats`: what arxiv.org/list/<cat>/recent shows."""
    today = today or datetime.now(timezone.utc).date()
    latest = _last_weekday(today)
    # One guard day to find where the oldest wanted day starts, plus one spare in case today's
    # announcement has not reached OAI-PMH yet.
    since = announcement_days(latest, days + 2)[0]

    papers: List[Paper] = []
    first = True
    for cat in cats:
        params = {"verb": "ListRecords", "metadataPrefix": "arXivRaw",
                  "from": since.isoformat(), "set": oai_set(cat)}
        for _ in range(OAI_MAX_PAGES):
            if not first:
                time.sleep(API_DELAY)
            first = False
            page, token = parse_oai(http_get(f"{OAI_BASE}?{urllib.parse.urlencode(params)}"))
            papers.extend(page)
            if progress:
                print(f"  {oai_set(cat)}: {len(papers)} records read", file=sys.stderr)
            if not token:
                break
            params = {"verb": "ListRecords", "resumptionToken": token}
    papers = dedupe(papers)

    seen = [p.announced for p in papers if p.announced]
    if seen:
        latest = min(latest, _last_weekday(date.fromisoformat(max(seen))))
    calendar = announcement_days(latest, days + 1)
    grouped = group_by_announcement(papers, cats, calendar)
    total = len(grouped)
    if max_results is not None:
        grouped = grouped[:max_results]
    per_day = []
    for d in reversed(calendar[1:]):
        iso = d.isoformat()
        per_day.append({
            "date": iso,
            "new": sum(1 for p in grouped if p.announced == iso and p.announce_type == "new"),
            "cross": sum(1 for p in grouped if p.announced == iso and p.announce_type == "cross"),
        })
    meta = {"source": "oai", "total": total, "days": per_day,
            "start": calendar[1].isoformat(), "end": calendar[-1].isoformat()}
    return grouped, meta


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

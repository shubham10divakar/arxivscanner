import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from arxivscanner import fetchers
from arxivscanner.display import export_json, export_markdown
from arxivscanner.fetchers import (build_api_query, build_rss_url, filter_types, oai_set, parse_api, parse_file,
                                   parse_oai, parse_rss, submitted_in)
from arxivscanner.models import split_id

FIX = Path(__file__).parent / "fixtures"


class TestParsers(unittest.TestCase):
    def test_rss(self):
        papers, meta = parse_rss((FIX / "sample_rss.xml").read_bytes())
        self.assertEqual(len(papers), 3)
        a = papers[0]
        self.assertEqual((a.arxiv_id, a.version), ("2609.00001", "v1"))
        self.assertEqual(a.title, "Sample Paper A: Looped Vision Transformers for Fine-Grained Recognition")
        self.assertEqual(a.authors, ["Alice Author", "Bob Builder", "Chandra Kumar"])
        self.assertTrue(a.abstract.startswith("We study looped vision transformers and show"))
        self.assertEqual(a.announce_type, "new")
        self.assertEqual(a.categories, ["cs.CV", "cs.LG"])
        self.assertIn("Mon, 28 Sep 2026", meta["pub_date"])
        self.assertEqual([p.arxiv_id for p in filter_types(papers, {"new"})], ["2609.00001"])

    def test_api(self):
        papers, total = parse_api((FIX / "sample_api.xml").read_bytes())
        self.assertEqual(total, 2)
        p = papers[0]
        self.assertEqual((p.arxiv_id, p.version), ("2609.00010", "v2"))
        self.assertEqual(p.primary_category, "cs.CV")
        self.assertEqual(p.categories, ["cs.CV", "cs.LG"])
        self.assertEqual(p.authors, ["Grace Hopper", "Alan Turing"])
        self.assertEqual(p.comment, "12 pages, 5 figures")
        self.assertEqual(p.pdf_url, "https://arxiv.org/pdf/2609.00010")

    def test_ids(self):
        self.assertEqual(split_id("oai:arXiv.org:2609.00001v1"), ("2609.00001", "v1"))
        self.assertEqual(split_id("http://arxiv.org/abs/cs/0112017v1"), ("cs/0112017", "v1"))
        self.assertEqual(split_id("2609.00001"), ("2609.00001", ""))

    def test_urls(self):
        self.assertEqual(build_rss_url(["cs.CV", "cs.LG"]), "https://rss.arxiv.org/rss/cs.CV+cs.LG")
        q = build_api_query(["cs.CV", "cs"], datetime(2026, 9, 25), datetime(2026, 9, 27, 23, 59))
        self.assertEqual(q, "(cat:cs.CV OR cat:cs.*) AND submittedDate:[202609250000 TO 202609272359]")
        # Domains without subdomains are categories themselves, so no wildcard.
        q = build_api_query(["quant-ph"], datetime(2026, 9, 25), datetime(2026, 9, 27, 23, 59))
        self.assertTrue(q.startswith("(cat:quant-ph) AND"))

    def test_oai(self):
        self.assertEqual(oai_set("cs.CV"), "cs:cs:CV")
        self.assertEqual(oai_set("cs"), "cs:cs")
        self.assertEqual(oai_set("astro-ph.CO"), "physics:astro-ph:CO")
        self.assertEqual(oai_set("quant-ph"), "physics:quant-ph")

        papers, token = parse_oai((FIX / "sample_oai.xml").read_bytes())
        self.assertEqual(token, "")
        self.assertEqual([p.arxiv_id for p in papers], ["2609.00020", "2609.00949", "2303.15533"])  # deleted skipped
        p = papers[0]
        self.assertEqual((p.version, p.title), ("v1", "New OAI Paper: Diffusion for Depth"))
        self.assertEqual(p.authors, ["Grace Hopper", "Alan Turing", "Ada Lovelace"])
        self.assertEqual((p.primary_category, p.categories), ("cs.CV", ["cs.CV", "cs.LG"]))
        self.assertEqual((p.abstract, p.comment), ("We estimate depth with diffusion.", "9 pages"))
        self.assertTrue(p.published.startswith("2026-09-25T14:02:11"))
        self.assertEqual(papers[1].version, "v2")
        self.assertTrue(papers[1].published.startswith("2026-09-01"))  # v1 date, not the v2 date

        start, end = datetime(2026, 9, 25), datetime(2026, 9, 27, 23, 59)
        kept = [p.arxiv_id for p in papers if submitted_in(p, start, end)]
        self.assertEqual(kept, ["2609.00020"])  # same-month replacement and old paper both dropped

    def test_recent_falls_back_to_oai_when_api_refuses(self):
        oai = (FIX / "sample_oai.xml").read_bytes()
        calls = []

        def fake_get(url, *a, **kw):
            calls.append(url)
            if "export.arxiv.org" in url:
                raise fetchers.RefusedError("HTTP 406 Not Acceptable from export.arxiv.org")
            return oai

        window = (datetime(2026, 9, 25), datetime(2026, 9, 27, 23, 59))
        with mock.patch.object(fetchers, "http_get", fake_get), \
                mock.patch.object(fetchers, "date_window", lambda days: window), \
                mock.patch("sys.stderr", io.StringIO()):
            papers, meta = fetchers.fetch_recent(["cs.CV"], days=3)
        self.assertEqual(meta["source"], "oai")
        self.assertEqual([p.arxiv_id for p in papers], ["2609.00020"])
        self.assertIn("export.arxiv.org", calls[0])
        self.assertIn("oaipmh.arxiv.org", calls[1])

        with mock.patch.object(fetchers, "http_get", fake_get), mock.patch("sys.stderr", io.StringIO()):
            with self.assertRaises(fetchers.FetchError):
                fetchers.fetch_recent(["cs.CV"], days=3, source="api")

    def test_parse_file_and_exports(self):
        papers, meta = parse_file((FIX / "sample_rss.xml").read_bytes())
        self.assertIn("pub_date", meta)
        papers, meta = parse_file((FIX / "sample_api.xml").read_bytes())
        self.assertEqual(meta["total"], 2)
        with tempfile.TemporaryDirectory() as d:
            export_json(papers, f"{d}/p.json")
            doc = json.loads(Path(d, "p.json").read_text(encoding="utf-8"))
            self.assertEqual(doc["count"], 2)
            self.assertEqual(doc["papers"][0]["abs_url"], "https://arxiv.org/abs/2609.00010")
            export_markdown(papers, f"{d}/p.md", title="T")
            md = Path(d, "p.md").read_text(encoding="utf-8")
            self.assertIn("## 1. Sample API Paper: Graph Attention for Crack Detection", md)


if __name__ == "__main__":
    unittest.main()

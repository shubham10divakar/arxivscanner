import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from arxivscanner.display import export_json, export_markdown
from arxivscanner.fetchers import build_api_query, build_rss_url, filter_types, parse_api, parse_file, parse_rss
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

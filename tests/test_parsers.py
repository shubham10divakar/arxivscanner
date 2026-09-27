import unittest
from datetime import datetime
from pathlib import Path

from arxiv_parser.fetchers import build_api_query, build_rss_url, filter_types, parse_api, parse_rss
from arxiv_parser.models import split_id

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


if __name__ == "__main__":
    unittest.main()

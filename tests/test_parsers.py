import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from arxivscanner import display, fetchers, taxonomy
from arxivscanner.cli import main
from arxivscanner.display import export_json, export_markdown
from arxivscanner.filters import filter_keywords, keyword_pattern
from arxivscanner.fetchers import (announcement_days, build_rss_url, filter_types, group_by_announcement, oai_set,
                                   parse_api, parse_file, parse_oai, parse_rss)
from arxivscanner.models import Paper, split_id

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
        self.assertEqual(oai_set("cs.CV"), "cs:cs:CV")
        self.assertEqual(oai_set("cs"), "cs:cs")
        self.assertEqual(oai_set("astro-ph.CO"), "physics:astro-ph:CO")
        self.assertEqual(oai_set("quant-ph"), "physics:quant-ph")

    def test_oai(self):
        papers, token = parse_oai((FIX / "sample_oai.xml").read_bytes())
        self.assertEqual(token, "")
        self.assertEqual([p.arxiv_id for p in papers], ["2609.30020", "2609.00949", "2303.15533"])  # deleted skipped
        p = papers[0]
        self.assertEqual((p.version, p.title), ("v1", "New OAI Paper: Diffusion for Depth"))
        self.assertEqual(p.authors, ["Grace Hopper", "Alan Turing", "Ada Lovelace"])
        self.assertEqual((p.primary_category, p.categories), ("cs.CV", ["cs.CV", "cs.LG"]))
        self.assertEqual((p.abstract, p.comment), ("We estimate depth with diffusion.", "9 pages"))
        self.assertTrue(p.published.startswith("2026-09-25T14:02:11"))
        self.assertEqual(p.announced, "2026-09-25")  # the OAI datestamp
        self.assertEqual(papers[1].version, "v2")
        self.assertTrue(papers[1].published.startswith("2026-09-01"))  # v1 date, not the v2 date

    def test_announcement_days(self):
        self.assertEqual(announcement_days(date(2026, 9, 25), 3),
                         [date(2026, 9, 23), date(2026, 9, 24), date(2026, 9, 25)])
        # Weekends have no listing.
        self.assertEqual(announcement_days(date(2026, 9, 28), 3),
                         [date(2026, 9, 24), date(2026, 9, 25), date(2026, 9, 28)])

    def test_group_by_announcement(self):
        def paper(aid, version, datestamp, primary="cs.CV"):
            return Paper(arxiv_id=aid, version=version, announced=datestamp,
                         categories=[primary], primary_category=primary)

        tue, wed, thu = "2026-09-22", "2026-09-23", "2026-09-24"
        papers = [
            # Tuesday's block (the guard day): 22001-22005
            paper("2609.22001", "v1", tue), paper("2609.22002", "v1", tue), paper("2609.22005", "v1", tue),
            paper("2609.22003", "v1", wed),   # edited on Wednesday: still Tuesday's, so dropped
            paper("2609.22004", "v2", thu),   # new version on Thursday: still Tuesday's, so dropped
            # Wednesday's block: 23001-23009
            paper("2609.23001", "v1", wed), paper("2609.23002", "v1", wed), paper("2609.23004", "v1", wed),
            paper("2609.23006", "v1", wed), paper("2609.23009", "v1", wed),
            paper("2609.23003", "v1", thu),   # edited on Thursday: stays on Wednesday
            paper("2609.23005", "v2", thu),   # new version on Thursday: stays on Wednesday
            # Thursday's block: 24001-24004
            paper("2609.24001", "v1", thu), paper("2609.24002", "v1", thu), paper("2609.24003", "v1", thu),
            paper("2609.24004", "v1", thu, primary="cs.LG"),  # cross-listed into cs.CV
            paper("2609.23007", "v1", thu, primary="cs.NI"),  # Wednesday cross-list, edited Thursday
            paper("2609.23008", "v2", thu, primary="cs.NI"),  # Wednesday cross-list, new version Thursday
            # Older papers that were only edited this week
            paper("2609.10000", "v1", thu),
            paper("2508.12345", "v1", wed),
        ]
        calendar = [date(2026, 9, 22), date(2026, 9, 23), date(2026, 9, 24)]
        out = group_by_announcement(papers, ["cs.CV"], calendar)
        self.assertEqual(
            [(p.arxiv_id, p.announced, p.announce_type) for p in out],
            [("2609.24003", thu, "new"), ("2609.24002", thu, "new"), ("2609.24001", thu, "new"),
             ("2609.24004", thu, "cross"),
             ("2609.23009", wed, "new"), ("2609.23006", wed, "new"), ("2609.23005", wed, "new"), ("2609.23004", wed, "new"),
             ("2609.23003", wed, "new"), ("2609.23002", wed, "new"), ("2609.23001", wed, "new"),
             ("2609.23008", wed, "cross"), ("2609.23007", wed, "cross")])
        # A whole-domain request counts every cs.* primary as new.
        self.assertTrue(all(p.announce_type == "new" for p in group_by_announcement(papers, ["cs"], calendar)))

    def test_fetch_recent(self):
        oai = (FIX / "sample_oai.xml").read_bytes()
        urls = []

        def fake_get(url, *a, **kw):
            urls.append(url)
            return oai

        with mock.patch.object(fetchers, "http_get", fake_get), mock.patch("sys.stderr", io.StringIO()):
            papers, meta = fetchers.fetch_recent(["cs.CV"], days=1, today=date(2026, 9, 27))  # a Sunday
        self.assertIn("oaipmh.arxiv.org", urls[0])
        self.assertIn("from=2026-09-23", urls[0])  # Friday plus a guard day and a spare day
        self.assertEqual([(p.arxiv_id, p.announced, p.announce_type) for p in papers],
                         [("2609.30020", "2026-09-25", "new")])  # replaced and old papers dropped
        self.assertEqual(meta["days"], [{"date": "2026-09-25", "new": 1, "cross": 0}])
        self.assertEqual((meta["start"], meta["end"]), ("2026-09-25", "2026-09-25"))

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


class TestKeywords(unittest.TestCase):
    def test_matching_rules(self):
        p = keyword_pattern(["gan", "attention", "vision transformer"])
        for text in ["GANs work", "self-attention", "Attention!", "a Vision  Transformer"]:
            self.assertTrue(p.search(text), text)
        for text in ["organization", "inattention", "vision tasks"]:
            self.assertFalse(p.search(text), text)
        self.assertIsNone(keyword_pattern([]))
        self.assertIsNone(keyword_pattern(["  "]))

    def test_filter_title_or_abstract(self):
        papers = [Paper(arxiv_id="1", title="Attention is all you need", abstract="Transformers."),
                  Paper(arxiv_id="2", title="Diffusion", abstract="We add cross-attention layers."),
                  Paper(arxiv_id="3", title="Graphs", abstract="Nothing relevant.")]
        kept = filter_keywords(papers, keyword_pattern(["attention"]))
        self.assertEqual([p.arxiv_id for p in kept], ["1", "2"])

    def test_cli(self):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as d, mock.patch("sys.stdout", out), \
                mock.patch("sys.stderr", io.StringIO()):
            code = main(["--from-file", str(FIX / "sample_rss.xml"), "--no-color", "-k", "looped", "medical segmentation",
                         "--md", f"{d}/p.md", "--json", f"{d}/p.json"])
            md = Path(d, "p.md").read_text(encoding="utf-8")
            doc = json.loads(Path(d, "p.json").read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn('2 of 3 papers match "looped" or "medical segmentation"', text)
        self.assertIn("2609.00001", text)
        self.assertIn("2609.00002", text)
        self.assertNotIn("2608.12345", text)
        self.assertIn("**Looped**", md)                       # matches are bolded in Markdown
        self.assertEqual(doc["meta"]["keywords"], ["looped", "medical segmentation"])

        out = io.StringIO()
        with mock.patch("sys.stdout", out), mock.patch("sys.stderr", io.StringIO()):
            main(["--from-file", str(FIX / "sample_rss.xml"), "--no-color", "-k", "quantum"])
        self.assertIn('None of the 3 papers mention "quantum"', out.getvalue())

    def test_highlight(self):
        with mock.patch.object(display, "_use_color", True):
            line = display._hl("Looped attention, again", keyword_pattern(["attention"]), "blue")
        self.assertIn("\033[1;33mattention\033[0m", line)

    def test_prompt(self):
        with mock.patch("builtins.input", return_value='attention "vision transformer"'):
            self.assertEqual(taxonomy.pick_keywords(), ["attention", "vision transformer"])
        with mock.patch("builtins.input", return_value=""):
            self.assertEqual(taxonomy.pick_keywords(), [])
        with mock.patch("builtins.input", return_value='unbalanced "quote'):
            self.assertEqual(taxonomy.pick_keywords(), ["unbalanced", "quote"])


if __name__ == "__main__":
    unittest.main()

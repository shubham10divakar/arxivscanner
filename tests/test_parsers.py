import io
import json
import os
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from arxivscanner import display, fetchers, library, taxonomy
from arxivscanner.cli import main
from arxivscanner.display import export_json, export_markdown
from arxivscanner.filters import filter_keywords, keyword_pattern
from arxivscanner.fetchers import (announcement_days, build_rss_url, filter_types, group_by_announcement, oai_set,
                                   parse_api, parse_file, parse_oai, parse_rss)
from arxivscanner.models import Paper, split_id

FIX = Path(__file__).parent / "fixtures"

# Keep every test away from the real ~/.arxivscanner and ~/arxivscanner.
_home = tempfile.TemporaryDirectory()
_patches = [
    mock.patch.object(library, "settings_dir", lambda: Path(_home.name) / ".arxivscanner"),
    mock.patch.object(library, "default_library", lambda: Path(_home.name) / "arxivscanner"),
    mock.patch.dict(os.environ, {library.ENV_LIBRARY: ""}),
]


def setUpModule():
    for p in _patches:
        p.start()


def tearDownModule():
    for p in reversed(_patches):
        p.stop()
    _home.cleanup()


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

    def test_detex(self):
        cases = {
            r"Tom\'as Lozano-P\'erez": "Tomás Lozano-Pérez",
            r"Tobias Deu{\ss}er": "Tobias Deußer",
            r"Frederik M{\o}llskov Trier": "Frederik Møllskov Trier",
            r"Luk\'a\v{s} Br\r{u}na": "Lukáš Brůna",
            r"Mateusz J\k{a}kalak, Rafa{\l} Jakubowski": "Mateusz Jąkalak, Rafał Jakubowski",
            r"Sophie T\"otterstr\"om, Moun\^im": "Sophie Tötterström, Mounîm",
            r"Fran\c{c}ois \'{E}mile, Na\"{\i}ve": "François Émile, Naïve",
            r"Syed{\dag}, EDF R\&D, Overlay\_dx, 90.07\%": "Syed†, EDF R&D, Overlay_dx, 90.07%",
            # Math and other commands are left alone.
            r"$x^{2}$ with \emph{math}, $\lambda \in \Omega$, \daggerfoo": r"$x^{2}$ with \emph{math}, $\lambda \in \Omega$, \daggerfoo",
        }
        for src, want in cases.items():
            self.assertEqual(fetchers.detex(src), want)

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
        self.assertEqual(p.authors, ["Grace Hopper", "Tomás Lozano-Pérez", "Ada Lovelace"])  # LaTeX accents decoded
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


def run_cli(*argv):
    """Run the command line; return (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class TestLibrary(unittest.TestCase):
    def setUp(self):
        home = Path(_home.name)
        shutil.rmtree(home, ignore_errors=True)
        home.mkdir()
        os.environ[library.ENV_LIBRARY] = ""
        self.default = home / "arxivscanner"

    def test_resolve_library(self):
        self.assertEqual(library.resolve_library(), (self.default, "default"))
        library.save_config({"library": str(Path(_home.name) / "research")})
        self.assertEqual(library.resolve_library()[1], "config")
        os.environ[library.ENV_LIBRARY] = str(Path(_home.name) / "from-env")
        self.assertEqual(library.resolve_library(), (Path(_home.name) / "from-env", library.ENV_LIBRARY))
        self.assertEqual(library.resolve_library("elsewhere"), (Path("elsewhere"), "--library"))

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell quoting")
    def test_folder_path_powershell_quote(self):
        # PowerShell 5 turns '.\My papers\' into `.\My papers"`
        self.assertEqual(library.folder_path('D:\\My papers"'), Path("D:\\My papers"))
        with self.assertRaises(library.LibraryError):
            library.folder_path('D:\\My papers" --auto-pdf on')
        # a setting saved before the fix heals itself
        library.save_config({"library": 'D:\\My papers"', "pdfs": 'D:\\My papers\\pdfs"'})
        self.assertEqual(library.resolve_library()[0], Path("D:\\My papers"))
        self.assertEqual(library.pdf_folder(Path("x")), Path("D:\\My papers\\pdfs"))

    def test_save_saved_unsave(self):
        run_cli("--from-file", str(FIX / "sample_rss.xml"), "--no-color")      # shows 3 papers
        code, out, err = run_cli("save", "1", "3", "--tag", "important")
        self.assertEqual(code, 0, err)
        self.assertIn("2609.00001", out)
        self.assertIn("2608.12345", out)
        lib = library.Library(self.default)
        self.assertEqual(len(lib), 2)
        self.assertEqual(lib.get("2609.00001")["tags"], ["important"])
        self.assertTrue((self.default / "library.json").exists())

        # Saving again adds tags and keeps the save date.
        first_saved = lib.get("2609.00001")["saved_at"]
        run_cli("save", "1", "--tag", "to-read")
        lib = library.Library(self.default)
        self.assertEqual(lib.get("2609.00001")["tags"], ["important", "to-read"])
        self.assertEqual(lib.get("2609.00001")["saved_at"], first_saved)

        code, out, _ = run_cli("saved", "--no-color")
        self.assertIn("2 saved papers", out)
        self.assertIn("Tags: important (2)  to-read (1)", out)
        self.assertIn("tags: important, to-read", out)

        code, out, _ = run_cli("saved", "--tag", "to-read", "--no-color")
        self.assertIn("1 of 2 saved papers tagged to-read", out)
        self.assertNotIn("2608.12345", out)

        code, out, _ = run_cli("saved", "-k", "looped", "--no-color")
        self.assertIn("1 of 2 saved papers mentioning \"looped\"", out)

        # `saved` becomes the last list, so its numbers work for unsave.
        run_cli("saved", "--no-color")
        code, out, _ = run_cli("unsave", "1", "--tag", "to-read")
        self.assertEqual(library.Library(self.default).get(
            library.last_list()[0].arxiv_id)["tags"], ["important"])
        code, out, _ = run_cli("unsave", "2608.12345")
        self.assertEqual(code, 0)
        self.assertEqual(len(library.Library(self.default)), 1)

    def test_save_by_id_looks_up_arxiv(self):
        oai = (FIX / "sample_oai.xml").read_bytes()
        with mock.patch.object(fetchers, "http_get", lambda url, *a, **kw: oai),                 mock.patch.object(fetchers.time, "sleep"):
            code, out, err = run_cli("save", "https://arxiv.org/abs/2609.30020v1", "2609.99999")
        self.assertEqual(code, 1)                       # one of the two wasn't found
        self.assertIn("2609.30020", out)
        self.assertIn("2609.99999: not found on arXiv", err)
        self.assertIn("2609.30020", library.Library(self.default))

    def test_bad_references(self):
        code, _, err = run_cli("save", "3")
        self.assertEqual(code, 1)
        self.assertIn("no list to pick from yet", err)
        run_cli("--from-file", str(FIX / "sample_rss.xml"), "--no-color")
        code, _, err = run_cli("save", "9", "hello")
        self.assertIn("#9: the last list had 3 papers", err)
        self.assertIn("hello: not a list number or an arXiv id", err)
        code, _, err = run_cli("unsave", "2")
        self.assertIn("isn't in your library", err)

    def test_config_show_and_settings(self):
        code, out, _ = run_cli("config")
        self.assertIn("Built with ♥ by Subham Divakar", out)
        self.assertIn(f"Library:   {self.default}\n", out)
        self.assertIn("default · change with: arxivscanner config --library FOLDER", out)
        self.assertIn(str(self.default / "pdfs"), out)
        self.assertIn("default, inside the library · change with: arxivscanner config --pdfs FOLDER", out)
        self.assertIn("Auto-PDF:  off (default · turn on with: arxivscanner config --auto-pdf on)", out)

        run_cli("config", "--library", str(Path(_home.name) / "research"))
        code, out, _ = run_cli("config")
        self.assertIn("your setting · back to the default with: arxivscanner config --library default", out)
        run_cli("config", "--library", "default")

        pdfs = Path(_home.name) / "big-drive" / "papers"
        run_cli("config", "--pdfs", str(pdfs), "--auto-pdf", "on")
        self.assertEqual(library.pdf_folder(self.default), pdfs.resolve())
        self.assertTrue(library.load_config()["auto_pdf"])
        run_cli("config", "--pdfs", "default", "--auto-pdf", "off")
        self.assertEqual(library.pdf_folder(self.default), self.default / "pdfs")
        self.assertFalse(library.load_config()["auto_pdf"])

    def test_config_library_move(self):
        run_cli("--from-file", str(FIX / "sample_rss.xml"), "--no-color")
        run_cli("save", "1", "2")
        (self.default / "pdfs").mkdir()
        (self.default / "pdfs" / "2609.00001 - Sample.pdf").write_bytes(b"%PDF-1.4 test")
        research = Path(_home.name) / "research"

        code, out, _ = run_cli("config", "--library", str(research), "--move")
        self.assertEqual(code, 0)
        self.assertEqual(library.resolve_library(), (research.resolve(), "config"))
        self.assertEqual(len(library.Library(research)), 2)
        self.assertTrue((research / "pdfs" / "2609.00001 - Sample.pdf").exists())
        self.assertFalse(self.default.exists())          # emptied, so removed

        # Moving back into a folder that already has a library is refused.
        other = Path(_home.name) / "other"
        run_cli("save", "3", "--library", str(other))
        code, _, err = run_cli("config", "--library", str(other), "--move")
        self.assertEqual(code, 1)
        self.assertIn("already has a library", err)
        self.assertEqual(library.resolve_library()[0], research.resolve())   # unchanged

        # --no-move switches folders and leaves the old library alone.
        code, out, _ = run_cli("config", "--library", "default", "--no-move")
        self.assertEqual(library.resolve_library(), (self.default, "default"))
        self.assertEqual(len(library.Library(research)), 2)
        self.assertEqual(len(library.Library(self.default)), 0)

    def test_config_move_prompt(self):
        run_cli("--from-file", str(FIX / "sample_rss.xml"), "--no-color")
        run_cli("save", "1")
        target = Path(_home.name) / "research"
        with mock.patch("sys.stdin.isatty", return_value=True), mock.patch("builtins.input", return_value="c"):
            code, out, _ = run_cli("config", "--library", str(target))
        self.assertIn("Nothing changed.", out)
        self.assertEqual(library.resolve_library()[1], "default")
        with mock.patch("sys.stdin.isatty", return_value=True), mock.patch("builtins.input", return_value=""):
            run_cli("config", "--library", str(target))
        self.assertEqual(len(library.Library(target)), 1)
        # Without a terminal to ask in, nothing is moved.
        with mock.patch("sys.stdin.isatty", return_value=False):
            code, out, _ = run_cli("config", "--library", "default")
        self.assertIn("run the same command with --move", out)
        self.assertEqual(len(library.Library(target)), 1)

    def _fake_arxiv(self):
        """Serve fake PDFs, and a non-PDF for 2608.12345; count the requests."""
        self.pdf_requests = []

        def fake_get(url, *a, **kw):
            self.pdf_requests.append(url)
            if url.endswith("2608.12345"):
                return b"<html>not ready</html>"
            return b"%PDF-1.4 fake " + url.encode()

        return mock.patch.multiple(fetchers, http_get=fake_get, time=mock.DEFAULT)

    def test_pdf_filename(self):
        self.assertEqual(library.pdf_filename(Paper(arxiv_id="2609.30264", title='AD-WM: "Action"/World <Models>?')),
                         "2609.30264 - AD-WM Action World Models.pdf")
        long = Paper(arxiv_id="cs/0112017", title="word " * 40 + "end.")
        name = library.pdf_filename(long)
        self.assertTrue(name.startswith("cs_0112017 - word word"))
        self.assertLessEqual(len(name), len("cs_0112017 - ") + 80 + len(".pdf"))
        # Deep folders: the title shrinks so the full path fits Windows' limit, down to just the id.
        paper = Paper(arxiv_id="2609.30264", title="Mind What Matters for Reasoning: Aligning Cross-Modal Attention")
        deep = Path(_home.name) / ("d" * 150)
        name = library.pdf_filename(paper, deep, path_limit=250)
        self.assertLessEqual(len(str(deep.resolve() / name)), 250)
        self.assertTrue(name.startswith("2609.30264 - Mind"))
        self.assertEqual(library.pdf_filename(paper, Path(_home.name) / ("d" * 240), path_limit=250), "2609.30264.pdf")
        self.assertEqual(library.pdf_filename(paper, deep, path_limit=None),
                         "2609.30264 - Mind What Matters for Reasoning Aligning Cross-Modal Attention.pdf")

    def test_save_with_pdf(self):
        run_cli("--from-file", str(FIX / "sample_rss.xml"), "--no-color")
        with self._fake_arxiv():
            code, out, err = run_cli("save", "1", "3", "--pdf")
        self.assertEqual(code, 1)                                        # #3 (2608.12345) has no PDF
        self.assertIn("2608.12345: arXiv didn't return a PDF", err)
        pdf = self.default / "pdfs" / "2609.00001 - Sample Paper A Looped Vision Transformers for Fine-Grained Recognition.pdf"
        self.assertTrue(pdf.is_file())
        lib = library.Library(self.default)
        self.assertEqual(lib.get("2609.00001")["pdf"], "pdfs/" + pdf.name)   # stored relative to the library
        self.assertIsNone(lib.get("2608.12345")["pdf"])

        code, out, _ = run_cli("saved", "--no-color")
        self.assertIn(f"PDF: {pdf}", out)

        # Saving with --pdf again doesn't download again.
        with self._fake_arxiv():
            run_cli("save", "1", "--pdf")
        self.assertEqual(self.pdf_requests, [])

    def test_saved_download_and_unsave_delete(self):
        run_cli("--from-file", str(FIX / "sample_rss.xml"), "--no-color")
        run_cli("save", "1", "2", "--tag", "important")
        run_cli("save", "3")
        with self._fake_arxiv():
            code, out, err = run_cli("saved", "--tag", "important", "--download", "--no-color")
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.pdf_requests), 2)                      # only the tagged ones
        self.assertEqual(len(list((self.default / "pdfs").glob("*.pdf"))), 2)

        pdf = library.Library(self.default).pdf_path("2609.00002")
        code, out, _ = run_cli("unsave", "2609.00002")
        self.assertIn("PDF kept", out)
        self.assertTrue(pdf.is_file())
        run_cli("save", "2609.00001")
        pdf1 = library.Library(self.default).pdf_path("2609.00001")
        code, out, _ = run_cli("unsave", "2609.00001", "--delete-pdf")
        self.assertFalse(pdf1.exists())

        # A PDF deleted by hand is reported, and --download fetches it again.
        run_cli("--from-file", str(FIX / "sample_rss.xml"), "--no-color")
        with self._fake_arxiv():
            run_cli("save", "1", "--pdf")
        library.Library(self.default).pdf_path("2609.00001").unlink()
        code, out, _ = run_cli("saved", "--no-color")
        self.assertIn("PDF missing", out)

    def test_auto_pdf_and_moving_pdfs(self):
        run_cli("config", "--auto-pdf", "on")
        run_cli("--from-file", str(FIX / "sample_rss.xml"), "--no-color")
        with self._fake_arxiv():
            run_cli("save", "1", "2")
        self.assertEqual(len(list((self.default / "pdfs").glob("*.pdf"))), 2)

        big = Path(_home.name) / "big-drive"
        code, out, _ = run_cli("config", "--pdfs", str(big), "--move")
        self.assertIn("moved 2 PDF(s)", out)
        lib = library.Library(self.default)
        self.assertEqual(lib.pdf_path("2609.00001").parent, big.resolve())
        self.assertTrue(lib.pdf_path("2609.00001").is_file())
        self.assertFalse(list((self.default / "pdfs").glob("*.pdf")))

        # New downloads go to the new folder.
        run_cli("unsave", "2609.00002", "--delete-pdf")
        run_cli("--from-file", str(FIX / "sample_rss.xml"), "--no-color")
        with self._fake_arxiv():
            run_cli("save", "2")          # auto-PDF is on
        self.assertEqual(library.Library(self.default).pdf_path("2609.00002").parent, big.resolve())
        self.assertEqual(len(list(big.glob("*.pdf"))), 2)

    def test_interactive_save_prompt(self):
        rss = parse_rss((FIX / "sample_rss.xml").read_bytes())
        answers = iter(["1 2", "important", "x", "3", "", ""])   # save #1 #2 tagged; bad input; save #3; finish
        with mock.patch.object(taxonomy, "pick_categories", return_value=["cs.CV"]), \
                mock.patch.object(taxonomy, "pick_mode", return_value=("today", 1)), \
                mock.patch.object(taxonomy, "pick_keywords", return_value=[]), \
                mock.patch("arxivscanner.cli.fetch_today", return_value=rss), \
                mock.patch("builtins.input", lambda prompt="": next(answers)):
            code, out, err = run_cli("--no-color")
        self.assertEqual(code, 0, err)
        self.assertIn("Welcome to arxivscanner", out)                # the welcome banner comes first
        self.assertIn("Built with ♥ by Subham Divakar", out)
        self.assertIn("See your settings any time with: arxivscanner config", out)
        self.assertLess(out.index("Welcome"), out.index("Sample Paper A"))
        self.assertIn("Numbers from the list only", out)
        lib = library.Library(self.default)
        self.assertEqual(len(lib), 3)
        self.assertEqual(lib.get("2609.00001")["tags"], ["important"])
        self.assertEqual(lib.get("2608.12345")["tags"], [])
        self.assertNotIn("arxivscanner save <numbers>", err)     # no tip: the prompt replaces it

        # Pressing Enter straight away saves nothing.
        with mock.patch.object(taxonomy, "pick_categories", return_value=["cs.CV"]), \
                mock.patch.object(taxonomy, "pick_mode", return_value=("today", 1)), \
                mock.patch.object(taxonomy, "pick_keywords", return_value=[]), \
                mock.patch("arxivscanner.cli.fetch_today", return_value=rss), \
                mock.patch("builtins.input", return_value=""):
            run_cli("--no-color")
        self.assertEqual(len(library.Library(self.default)), 3)

    def test_welcome_only_in_interactive_mode_and_help(self):
        code, out, _ = run_cli("--from-file", str(FIX / "sample_rss.xml"), "--no-color")
        self.assertNotIn("Welcome", out)                               # scripts and pipes stay clean
        from arxivscanner.cli import build_parser
        help_text = build_parser().format_help()
        self.assertIn("Built with ♥ by Subham Divakar", help_text)
        self.assertIn("arxivscanner config", help_text)

    def test_library_flag_and_empty_library(self):
        other = Path(_home.name) / "other"
        run_cli("--from-file", str(FIX / "sample_rss.xml"), "--no-color")
        run_cli("save", "2", "--library", str(other))
        self.assertEqual(len(library.Library(other)), 1)
        self.assertEqual(len(library.Library(self.default)), 0)
        code, out, _ = run_cli("saved", "--no-color")
        self.assertIn("Your library is empty", out)


if __name__ == "__main__":
    unittest.main()

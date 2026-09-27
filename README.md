# arXiv Scanner

[![PyPI version](https://img.shields.io/pypi/v/arxivscanner.svg)](https://pypi.org/project/arxivscanner/)
[![PyPI downloads](https://img.shields.io/pypi/dm/arxivscanner.svg)](https://pypistats.org/packages/arxivscanner)
[![Python versions](https://img.shields.io/pypi/pyversions/arxivscanner.svg)](https://pypi.org/project/arxivscanner/)
[![Tests](https://github.com/shubham10divakar/arxivscanner/actions/workflows/tests.yml/badge.svg)](https://github.com/shubham10divakar/arxivscanner/actions/workflows/tests.yml)

**PyPI:** https://pypi.org/project/arxivscanner/

A command-line tool that fetches and shows new arXiv papers for a chosen **domain** (archive, for example `cs`) and **subdomain** (category, for example `cs.CV`), and keeps a reading list of the ones you want.

Built with ♥ by Subham Divakar.

It has no dependencies beyond the Python standard library. It needs Python 3.9 or later and runs on Windows, macOS and Linux; the test suite runs on all three, with Python 3.9 to 3.14, on every push.

## Installation

Install from [PyPI](https://pypi.org/project/arxivscanner/):

### Windows

```bash
pip install arxivscanner
arxivscanner --version     # check it works
```

### Linux and macOS

Newer Linux distributions (Ubuntu 23.04+, Debian 12+, Fedora) and Homebrew Python refuse `pip install` into the system Python with an `externally-managed-environment` error. That's a system policy, not a problem with the tool. Install it with [pipx](https://pipx.pypa.io/), which gives command-line tools their own environment:

```bash
sudo apt install pipx      # Debian/Ubuntu; on Fedora: sudo dnf install pipx; on macOS: brew install pipx
pipx ensurepath            # adds ~/.local/bin to PATH; open a new terminal afterwards
pipx install arxivscanner
arxivscanner --version     # check it works
```

Or use a virtual environment:

```bash
python3 -m venv ~/.venvs/arxivscanner
~/.venvs/arxivscanner/bin/pip install arxivscanner
~/.venvs/arxivscanner/bin/arxivscanner --version
```

On older systems without that restriction, `python3 -m pip install --user arxivscanner` also works. The command then lands in `~/.local/bin`, which may need adding to your `PATH`.

### Upgrading

Run `pip install -U arxivscanner`, or `pipx upgrade arxivscanner` if you installed with pipx.

Installing adds an `arxivscanner` command. `python -m arxivscanner …` (or `python3 -m arxivscanner …`) works the same way.

## How to use it

### 1. Interactive mode (easiest)

1. **Start the tool** with no arguments:
   ```bash
   arxivscanner
   ```
   It greets you with your current settings: where saved papers and PDFs go, whether each one is the default or yours, and how to change it (see [See your current settings](#see-your-current-settings)).
2. **Pick a domain.** Type its number, for example `1` for `cs` (Computer Science).
3. **Pick one or more subdomains.** Type a number such as `1` (cs.AI), several numbers such as `8,23` (cs.CV and cs.LG), or `0` for the whole domain. You can also type arXiv codes directly, for example `cs.CV cs.LG`.
4. **Pick a mode.**
   - `1` (today) shows today's announcement feed.
   - `2` (recent) shows the last N announcements, grouped by day, the same papers as arXiv's "recent" page. It asks for N; press Enter to accept the default of 3.
5. **Optionally search by keyword.** Type one or more words to keep only papers whose title or abstract mentions them, for example `attention "world model"` (quotes group a phrase). Press Enter to skip and see everything.
6. **Read the results.** Each paper shows its id, title, authors, categories, first-submission date and comments, the abstract, and links to the abstract page and the PDF. In recent mode each day starts with a header line, like the day headings on arXiv's page. Keyword matches are highlighted.
7. **Save the ones you want.** Type their numbers, then optional tags such as `important`. It asks again until you press Enter. See them later with `arxivscanner saved` (see [Saving papers](#saving-papers-your-reading-list)).

Here's a real session: Computer Science → cs.AI → recent, the last 4 announcements. Long lists are shortened with `…`.

```
PS C:\Users\you> arxivscanner
Welcome to arxivscanner 0.2.0
Built with ♥ by Subham Divakar

Your settings (you can change them any time):
  Library:   C:\Users\you\arxivscanner
             default · change with: arxivscanner config --library FOLDER
  PDFs:      C:\Users\you\arxivscanner\pdfs
             default, inside the library · change with: arxivscanner config --pdfs FOLDER
  Auto-PDF:  off (default · turn on with: arxivscanner config --auto-pdf on)
See your settings any time with: arxivscanner config

Domains:
    1. cs                     Computer Science
    2. eess                   Electrical Engineering and Systems Science
    3. stat                   Statistics
    4. math                   Mathematics
    …
   15. nlin                   Nonlinear Sciences
Pick a domain: 1

Computer Science subdomains:
    1. cs.AI                  Artificial Intelligence
    2. cs.AR                  Hardware Architecture
    …
    8. cs.CV                  Computer Vision and Pattern Recognition
    …
   23. cs.LG                  Machine Learning
    …
   40. cs.SY                  Systems and Control
    0. (all of cs)
Pick subdomain(s): 1

Mode:
    1. today   (today's announcement feed)
    2. recent  (the last N announcements, like arXiv's 'recent' page)
Pick a mode [1]: 2
How many announcement days? [3]: 4
Keywords to filter by (Enter to skip):

Fetching the last 4 announcement(s) for cs.AI from arXiv OAI-PMH …
  cs:cs:AI: 1300 records read
  cs:cs:AI: 2135 records read

arXiv · cs.AI (Artificial Intelligence)
Last 4 announcements: Tue, 22 Sep 2026 → Fri, 25 Sep 2026
1074 papers  new: 378  cross: 696

── Fri, 25 Sep 2026 · 259 papers (107 new, 152 cross-lists) ────────────────────

  1. 2609.30264v1 [new]
     AD-WM: Action-Discriminative World Models for Counterfactual Model Predictive Control
     Jiabin Qiu, Zixuan Chen, Hongye Cao, Jieqi Shi, Jing Huo, Yang Gao
     cs.AI, cs.RO · 2026-09-24 · 9 pages, 5 figures, 4 tables. Project page: https://ad-wm.github.io/
     Latent world models are typically trained to predict factual transitions, whereas model
     predictive control (MPC) must compare alternative actions from the same state. …
     https://arxiv.org/abs/2609.30264  https://arxiv.org/pdf/2609.30264

  …

── Thu, 24 Sep 2026 · 192 papers (59 new, 133 cross-lists) ────────────────────
  …
── Wed, 23 Sep 2026 · 239 papers (101 new, 138 cross-lists) ────────────────────
  …
── Tue, 22 Sep 2026 · 384 papers (111 new, 273 cross-lists) ────────────────────
  …

Save papers? Type their numbers (e.g. 3 7 12), or press Enter to finish: 1 5
Tags for them (e.g. important to-read; Enter for none): important
Saved to C:\Users\you\arxivscanner
    #1  2609.30264  AD-WM: Action-Discriminative World Models for…  [important]
    #5  2609.30186  Jev-Mobile: Jev as an Executor for Mobile GUI Agents  [important]
2 papers in your library. See them with: arxivscanner saved

Save papers? Type their numbers (e.g. 3 7 12), or press Enter to finish:
```

Abstracts are printed in full. Add `--short` to trim each one to about 300 characters, or `--md papers.md` to save the list as a Markdown reading list.

### 2. Command-line flags

Pass `-c` with one or more codes to skip the prompts:

```bash
arxivscanner -c cs.CV                          # today's Computer Vision list
arxivscanner -c cs.CV --type new               # only brand-new submissions (no cross-lists or updates)
arxivscanner -c cs.CV cs.LG --short            # two subdomains, abstracts trimmed
arxivscanner -c cs                             # the whole Computer Science domain
arxivscanner -c cs.CV --mode recent            # the last 3 announcements, like arXiv's "recent" page
arxivscanner -c cs.CV --mode recent --days 5 --type new   # the last 5, new submissions only
arxivscanner -c cs.CV --md cv.md --json cv.json   # also save the results to files
arxivscanner -c cs.AI --mode recent --days 4 -k attention   # only papers mentioning "attention"
arxivscanner --from-file saved_feed.xml        # parse a saved RSS, OAI-PMH or API XML file offline
```

| Flag | Meaning | Default |
|---|---|---|
| `-c, --cats CODE …` | Domain(s) or subdomain(s), such as `cs.CV cs.LG`, `cs` or `quant-ph`. Leave it out to get the interactive picker. | — |
| `--mode today\|recent` | `today` is today's announcement feed. `recent` is the last `--days` announcements, like arXiv's "recent" page. | `today` |
| `--days N` | Number of announcement days for `--mode recent`. arXiv announces on weekdays, so `--days 5` is about a week. | `3` |
| `--max N` | Maximum number of papers for `--mode recent`. | no cap |
| `--type T …` | Keep only these announcement types: `new` or `cross` (cross-listed from another category); today mode also has `replace` and `replace-cross` (updated versions). | all |
| `-k, --keyword WORD …` | Keep only papers whose title or abstract mentions any of these words. Quote a phrase: `-k "vision transformer"`. See [Searching by keyword](#searching-by-keyword). | — |
| `--short` | Trim each abstract to about 300 characters. | off |
| `--json FILE` | Also save the results as JSON (all fields plus the abs and PDF URLs). | — |
| `--md FILE` | Also save the results as a Markdown reading list. | — |
| `--from-file XML` | Parse a saved RSS, OAI-PMH (`arXivRaw`) or API XML file instead of fetching. | — |
| `--list` | Print every built-in domain and subdomain, then exit. | — |
| `--no-color` | Plain output, for example when piping to a file. `NO_COLOR` is also respected. | — |
| `--version` | Show the version. | — |

### Searching by keyword

Add `-k` with one or more words to keep only the papers whose title or abstract mentions any of them:

```bash
arxivscanner -c cs.AI --mode recent --days 4 -k attention              # one word
arxivscanner -c cs.CV -k attention transformer                         # either word
arxivscanner -c cs.CV -k "vision transformer"                          # an exact phrase
arxivscanner -c cs.AI cs.LG --mode recent --days 5 -k agent --type new --md agents.md   # with other options
```

The header shows how many papers matched, and the matches are highlighted in yellow (and in bold in `--md` files):

```
arXiv · cs.AI (Artificial Intelligence)
Last 4 announcements: Tue, 22 Sep 2026 → Fri, 25 Sep 2026
76 of 1074 papers match "attention"  new: 12  cross: 64

── Fri, 25 Sep 2026 · 15 papers (2 new, 13 cross-lists) ────────────────────
  …
```

How matching works:

- **Upper and lower case don't matter.** `attention` finds "Attention" too.
- **Matches start at the beginning of a word.** `gan` finds "GAN" and "GANs" but not "organization", and `attention` also finds "self-attention". A word inside a longer name, such as "StyleGAN", needs its own keyword (`stylegan`).
- **Several keywords mean any of them.** `-k attention transformer` keeps papers that mention either.
- **Plain words also match their everyday meaning.** "attention" also finds "has gained increasing attention", so a phrase like `"attention mechanism"` or a word like `self-attention` gives tighter results.

In interactive mode, type the keywords at the `Keywords to filter by` prompt, with quotes around phrases.

### Saving papers (your reading list)

Every list is numbered. Save the papers you want by their numbers, optionally with tags such as `important` or `to-read`:

```bash
arxivscanner -c cs.CV --mode recent -k attention      # read the list…
arxivscanner save 1 3 --tag important                 # …save #1 and #3 from it
arxivscanner save 7 12 --tag to-read
arxivscanner save 2609.30249                          # or any paper by arXiv id or link
```

The tool remembers the last list it showed, so the numbers keep working after the command finishes. Saving a paper again just adds the new tags.

See your saved papers at any time, in the same format as the normal output:

```bash
arxivscanner saved                        # everything, newest first
arxivscanner saved --tag important        # only papers with this tag
arxivscanner saved -k diffusion           # keyword search works here too
arxivscanner saved --md reading-list.md   # export (JSON works too)
```

```
Saved papers · C:\Users\you\arxivscanner
Tags: important (2)  to-read (1)
3 saved papers

  1. 2609.29940v1
     Mind What Matters for Reasoning: Aligning Cross-Modal Attention via Selective Probability Mass
     Concentration
     Jiaqi Deng, Zonghan Wu, Zhan Heng, Xiaoshui Huang, Huan Huo, Guandong Xu
     cs.CV, cs.AI · 2026-09-24
     ★ Saved 27 Sep 2026 · tags: important
     …
```

Remove papers, or just a tag, with `unsave`. The numbers come from the last list shown, so `arxivscanner saved` followed by `arxivscanner unsave 2` works as you'd expect:

```bash
arxivscanner unsave 2609.30249           # remove a paper
arxivscanner unsave 2 --tag to-read      # keep the paper, drop the tag
```

### See your current settings

Run `arxivscanner config` with no options at any time:

```bash
arxivscanner config
```

```
arxivscanner 0.2.0 · Built with ♥ by Subham Divakar

Library:   D:\Research\arxiv
           your setting · back to the default with: arxivscanner config --library default
PDFs:      D:\Research\arxiv\pdfs
           default, inside the library · change with: arxivscanner config --pdfs FOLDER
Auto-PDF:  off (default · turn on with: arxivscanner config --auto-pdf on)
Settings:  C:\Users\you\.arxivscanner\config.json
Saved papers: 214   PDFs: 187 (1.9 GB)
```

Each setting says whether it's the default or yours, and the exact command to change it. The same summary appears when interactive mode starts. If you never change anything, these defaults apply:

| Setting | Default | Change it with | Back to the default |
|---|---|---|---|
| Library (saved papers) | `~/arxivscanner` (`C:\Users\<you>\arxivscanner` on Windows) | `arxivscanner config --library FOLDER` | `arxivscanner config --library default` |
| PDFs | a `pdfs` folder inside the library | `arxivscanner config --pdfs FOLDER` | `arxivscanner config --pdfs default` |
| Auto-PDF | off: PDFs download only with `--pdf` or `--download` | `arxivscanner config --auto-pdf on` | `arxivscanner config --auto-pdf off` |

The settings are stored in `~/.arxivscanner/config.json`.

### Choosing where saved papers go

Saved papers live in one folder, `~/arxivscanner` by default (`C:\Users\<you>\arxivscanner` on Windows). It holds a plain `library.json` you can back up or sync, and later the downloaded PDFs. If you'll use the tool for a long time, point it at a folder of your choice once:

```bash
arxivscanner config --library "D:/Research/arxiv"    # remembered from now on
arxivscanner config --pdfs "E:/big-drive/papers"      # optional: PDFs in a separate, bigger folder
```

If you already have saved papers when you change the folder, the tool asks whether to move them there, start fresh, or cancel (`--move` or `--no-move` answer up front). It never merges two libraries: if the new folder already has one, nothing is moved. PDF paths are stored relative to the library folder, so you can also move or copy the whole folder yourself, for example into Dropbox or OneDrive, and point `config --library` at it.

| Way to choose the folder | Example | Use it for |
|---|---|---|
| Default | `~/arxivscanner` | Nothing to set up |
| Saved setting | `arxivscanner config --library "D:/Research/arxiv"` | Your normal setup |
| For one command | `arxivscanner saved --library "E:/old-library"` | Looking at a second library |
| Environment variable | `ARXIVSCANNER_LIBRARY=/data/arxiv` | Scripts and servers |

The most specific one wins: the flag, then the environment variable, then the saved setting, then the default. `arxivscanner config --library default` or `--pdfs default` goes back to the defaults. The settings themselves stay in `~/.arxivscanner/config.json`, so the tool can always find your library.

### Downloading PDFs

Download the PDFs of the papers you save, only when you ask:

```bash
arxivscanner save 1 3 --pdf                          # save and download
arxivscanner saved --tag important --download        # download what those saved papers are missing
arxivscanner config --auto-pdf on                    # or: always download when saving
```

```
  PDF 1/2  2609.29940 - Mind What Matters for Reasoning Aligning Cross-Modal.pdf  (5.9 MB)
  PDF 2/2  2609.29726 - A Multimodal Dataset for Survival Prediction in.pdf  (1.1 MB)
  PDFs are in D:\Research\arxiv\pdfs
```

- **Readable file names:** the arXiv id plus the start of the title, so you can find papers in your file browser. On Windows the title is shortened when needed to stay within Windows' path length limit.
- **Where they go:** a `pdfs` folder inside your library, or the folder set with `arxivscanner config --pdfs "E:/big-drive/papers"`. Changing it offers to move the PDFs you already have.
- **Shown in your list:** `arxivscanner saved` prints each PDF's path under the paper. A PDF you deleted by hand is flagged, and `--download` fetches it again.
- **Removing papers:** `unsave` keeps the PDF file unless you add `--delete-pdf`.
- **One at a time:** downloads pause 3 seconds between files, as arXiv asks. The tool is for your own reading list, not for bulk downloading.

### Which mode should I use?

| Mode | Source | Answers | Notes |
|---|---|---|---|
| `today` (default) | `rss.arxiv.org/rss/<cats>` | "What did arXiv announce today?" | Matches arXiv's daily "new" listing. Each paper is tagged `new`, `cross` (cross-listed from another category), `replace` or `replace-cross` (an updated version of an older paper). |
| `recent` | `oaipmh.arxiv.org/oai` | "What did arXiv announce in its last N announcements?" | The same papers as `arxiv.org/list/<cat>/recent`: grouped by announcement day, newest day first, new submissions then cross-lists, in arXiv's order. Includes author comments and journal refs. See [How recent mode works](#how-recent-mode-works). |

**When is there something new?** arXiv announces Sunday to Thursday at 20:00 US Eastern time, which is about **05:30 IST the next morning**. There are no announcements on Friday or Saturday nights US Eastern, so the Saturday and Sunday (IST) feeds are empty. On those days, `--mode recent --days 1` shows Friday's announcement. `cs.CV` usually has 150–300 papers per announcement.

### Codes

Run `arxivscanner --list` to see all built-in codes. They cover cs, eess, stat, math, q-bio, q-fin, econ, astro-ph, cond-mat, physics, nlin, quant-ph, gr-qc, hep-th and hep-ph. Any other valid arXiv code also works, even if it isn't in the list. Some common ones:

| Code | Subject |
|---|---|
| `cs.CV` | Computer Vision and Pattern Recognition |
| `cs.LG` | Machine Learning |
| `cs.CL` | Computation and Language (NLP) |
| `cs.AI` | Artificial Intelligence |
| `cs.RO` | Robotics |
| `eess.IV` | Image and Video Processing |
| `stat.ML` | Machine Learning (Statistics) |

### How recent mode works

arXiv's "recent" page lists what was announced on each of the last few announcement days. That's different from when papers were submitted: a day's list includes papers held in moderation for weeks and papers cross-listed from other categories.

The tool rebuilds that page from arXiv's OAI-PMH feed (`oaipmh.arxiv.org`), which carries full metadata and abstracts. arXiv hands out ids in order at announcement time, so each announcement day owns one block of ids. The tool finds each day's block and places every paper on the day whose block holds its id. That keeps papers that got a new version later in the week on the day they were announced, and leaves out old papers that were only edited.

Checked against `arxiv.org/list/<cat>/recent` for seven categories over a week (cs.AI, cs.CV, quant-ph, math.CO, eess.SP, hep-th, stat.ML; 3,452 papers), 99% of the papers appear on the same day and in the same order. OAI-PMH doesn't record when a paper was cross-listed, so papers cross-listed into a category some time after their own announcement are occasionally missed or shown on their original day. Categories with many late cross-lists, such as hep-th, see a few more of these.

Busy responses (`429`, `503`) and network errors are retried with back-off, honouring `Retry-After`, and the tool waits 3 seconds between requests, as arXiv's terms ask.

## Development

To work on the code, clone the repo and install it in editable mode:

```bash
git clone https://github.com/shubham10divakar/arxivscanner.git
cd arxivscanner
pip install -e .
python -m unittest discover -s tests     # offline tests, using the XML fixtures in tests/fixtures
python -m build                          # builds dist/arxivscanner-<version>.tar.gz and .whl (pip install build)
```

The version lives in `arxivscanner/__init__.py` (`__version__`).

## Design

```
arxivscanner ──► cli.py ──► fetchers.py ──► arXiv (RSS / OAI-PMH)
                   │             │
                   │             └─► models.Paper   (one normalised record)
                   ├─► taxonomy.py  (domain → subdomain names, picker)
                   ├─► filters.py   (keyword search)
                   ├─► commands.py  (save / saved / unsave / config) ─► library.py (reading list)
                   └─► display.py   (terminal view, JSON / Markdown export)
```

| Module | Role |
|---|---|
| `taxonomy.py` | Built-in map of domains and subdomains, plus the interactive picker. |
| `models.py` | `Paper` dataclass: id, version, title, authors, abstract, categories, primary category, announce type, dates, comment, journal ref, DOI, abs and PDF URLs. |
| `fetchers.py` | Two sources, one output type. `fetch_today()` reads the RSS feed. `fetch_recent()` pages through OAI-PMH (`arXivRaw` records) and `group_by_announcement()` rebuilds arXiv's recent listing from them. Also handles retries with back-off, the 3 s delay between calls, de-duplication and type filtering. |
| `library.py` | The reading list: where the library folder is (flag, environment variable, setting or default), `library.json` with each saved paper's details, tags and save date, and the last list shown. |
| `commands.py` | The `save`, `saved`, `unsave` and `config` commands. |
| `filters.py` | Keyword search: `keyword_pattern()` builds the case-insensitive, word-start pattern and `filter_keywords()` keeps papers whose title or abstract matches. |
| `display.py` | Colour terminal output (works in Windows 10+ consoles too), grouped by announcement day in recent mode, plus `export_json` and `export_markdown`. |
| `cli.py` | Flags and the interactive picker. `--from-file` parses a saved XML file offline. |

## Roadmap

- **0.1** Fetch, display and export by domain and subdomain.
- **0.2** (current) `recent` mode matches arXiv's "recent" page (the last N announcements, grouped by day), keyword search with `-k`, author names with accents shown correctly, and tests on Linux, macOS and Windows.
- **0.3** Saved profiles (`--profile vision` for your usual categories and keywords) and remembering papers already seen, so each run shows only new ones.
- **0.4** Daily digest: a scheduled run that writes an HTML or Markdown digest, or sends it by email.
- **0.5** Ranking by interest (keyword weights, favourite authors; later embeddings).
- **Later** Bookmarks, BibTeX/Zotero export and PDF download; an interactive browser or dashboard.

# arXiv Scanner

A command-line tool that fetches and shows new arXiv papers for a chosen **domain** (archive, for example `cs`) and **subdomain** (category, for example `cs.CV`).

It uses only the Python standard library, so there is nothing to `pip install`. It needs Python 3.9 or later and runs on Windows, macOS and Linux.

## Installation

Install from GitHub with pip:

```bash
pip install git+https://github.com/shubham10divakar/arxivscanner.git
arxivscanner --list        # check it works: prints every known domain and subdomain
```

This installs an `arxivscanner` command. `python -m arxivscanner …` works the same way. Use `python3 -m pip` on macOS or Linux if `pip` points at an older Python.

To work on the code instead, clone the repo and install it in editable mode:

```bash
git clone https://github.com/shubham10divakar/arxivscanner.git
cd arxivscanner
pip install -e .
```

Without installing, `python run.py …` from the repo folder also works.

## How to use it

### 1. Interactive mode (easiest)

Run the tool with no arguments and answer the prompts:

```bash
arxivscanner
```

1. **Pick a domain.** Type its number (for example `1` for `cs`).
2. **Pick one or more subdomains.** Type numbers such as `8` or `8,23`, or type `0` for the whole domain. You can also type arXiv codes directly (`cs.CV cs.LG`).
3. **Pick a mode.** `1` shows today's announcement. `2` shows papers submitted in the last N days, and asks for N.

### 2. Command-line flags

Pass `-c` with one or more codes to skip the prompts:

```bash
arxivscanner -c cs.CV                          # today's Computer Vision list
arxivscanner -c cs.CV --type new               # only brand-new submissions (no cross-lists or updates)
arxivscanner -c cs.CV cs.LG --short            # two subdomains, abstracts trimmed
arxivscanner -c cs                             # the whole Computer Science domain
arxivscanner -c cs.CV --mode recent --days 3   # everything submitted in the last 3 days
arxivscanner -c cs.CV --md cv.md --json cv.json   # also save the results to files
arxivscanner --from-file saved_feed.xml        # parse a previously saved RSS/API XML file offline
```

| Flag | Meaning | Default |
|---|---|---|
| `-c, --cats CODE …` | Domain(s) or subdomain(s), such as `cs.CV cs.LG`, `cs` or `quant-ph`. Leave it out to get the interactive picker. | — |
| `--mode today\|recent` | `today` is today's announcement (RSS). `recent` is everything submitted in the last `--days` days (API). | `today` |
| `--days N` | Window size for `--mode recent`, in whole UTC days, including today. | `3` |
| `--max N` | Maximum number of papers for `--mode recent`. | `500` |
| `--type T …` | Keep only these announcement types (today mode): `new`, `cross`, `replace`, `replace-cross`. | all |
| `--short` | Trim each abstract to about 300 characters. | off |
| `--json FILE` | Also save the results as JSON (all fields plus the abs and PDF URLs). | — |
| `--md FILE` | Also save the results as a Markdown reading list. | — |
| `--from-file XML` | Parse a saved RSS or API XML file instead of fetching. | — |
| `--list` | Print every built-in domain and subdomain, then exit. | — |
| `--no-color` | Plain output, for example when piping to a file. `NO_COLOR` is also respected. | — |
| `--version` | Show the version. | — |

### Which mode should I use?

| Mode | Source | Answers | Notes |
|---|---|---|---|
| `today` (default) | `rss.arxiv.org/rss/<cats>` | "What did arXiv announce today?" | Matches arXiv's daily "new" listing. Each paper is tagged `new`, `cross` (cross-listed from another category), `replace` or `replace-cross` (an updated version of an older paper). |
| `recent` | `export.arxiv.org/api/query` | "What was submitted in the last N days?" | Filters on submission date (UTC). Also includes author comments (page counts, venue) and journal refs. Capped by `--max`. |

**When is there something new?** arXiv announces Sunday to Thursday at 20:00 US Eastern time, which is about **05:30 IST the next morning**. There are no announcements on Friday or Saturday nights US Eastern, so the Saturday and Sunday (IST) feeds are empty. On those days, use `--mode recent --days 3`. `cs.CV` usually has 150–300 papers per announcement.

### Example output

```
arXiv · cs.CV (Computer Vision and Pattern Recognition)
Announcement: Mon, 28 Sep 2026 00:00:00 -0400
3 papers  new: 1  cross: 1  replace: 1

  1. 2609.00001v1 [new]
     Sample Paper A: Looped Vision Transformers for Fine-Grained Recognition
     Alice Author, Bob Builder, Chandra Kumar
     cs.CV, cs.LG · 2026-09-28
     We study looped vision transformers and show strong results on fine-grained benchmarks.
     https://arxiv.org/abs/2609.00001  https://arxiv.org/pdf/2609.00001
```

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

### Rate limiting

The arXiv API sometimes rate-limits in bursts, answering `406` or `429` for a few minutes. The tool retries with back-off for up to about 4 minutes per request and waits 3 seconds between pages, as arXiv's terms ask. If a later page still fails, it keeps the papers it already fetched and prints a warning. If the first request fails, wait a few minutes and run the command again. The RSS feed (`today` mode) is rarely affected.

## Development

```bash
python -m unittest discover -s tests     # offline tests, using the XML fixtures in tests/fixtures
python -m build                          # builds dist/arxivscanner-<version>.tar.gz and .whl (pip install build)
```

The version lives in `arxivscanner/__init__.py` (`__version__`).

## Design

```
arxivscanner ──► cli.py ──► fetchers.py ──► arXiv (RSS / API)
                   │             │
                   │             └─► models.Paper   (one normalised record)
                   ├─► taxonomy.py  (domain → subdomain names, picker)
                   └─► display.py   (terminal view, JSON / Markdown export)
```

| Module | Role |
|---|---|
| `taxonomy.py` | Built-in map of domains and subdomains, plus the interactive picker. |
| `models.py` | `Paper` dataclass: id, version, title, authors, abstract, categories, primary category, announce type, dates, comment, journal ref, DOI, abs and PDF URLs. |
| `fetchers.py` | Two sources, one output type. `fetch_today()` reads the RSS feed. `fetch_recent()` pages through the API. Also handles retries with back-off, the 3 s delay between API calls, de-duplication and type filtering. |
| `display.py` | Colour terminal output (works in Windows 10+ consoles too) plus `export_json` and `export_markdown`. |
| `cli.py` | Flags and the interactive picker. `--from-file` parses a saved XML file offline. |

## Roadmap

- **0.1** (current) Fetch, display and export by domain and subdomain.
- **0.2** Remember papers already seen (a local SQLite or JSON file) so each run shows only unseen papers.
- **0.3** Keyword or interest filtering and ranking (title and abstract match, later embeddings).
- **0.4** Daily automation (a scheduled task or cron) and a digest by email, Telegram or HTML.
- **0.5** Dashboard view with bookmarking.

# arXiv Scanner

[![PyPI version](https://img.shields.io/pypi/v/arxivscanner.svg)](https://pypi.org/project/arxivscanner/)
[![PyPI downloads](https://img.shields.io/pypi/dm/arxivscanner.svg)](https://pypistats.org/packages/arxivscanner)
[![Python versions](https://img.shields.io/pypi/pyversions/arxivscanner.svg)](https://pypi.org/project/arxivscanner/)

**PyPI:** https://pypi.org/project/arxivscanner/

A command-line tool that fetches and shows new arXiv papers for a chosen **domain** (archive, for example `cs`) and **subdomain** (category, for example `cs.CV`).

It uses only the Python standard library, so there is nothing to `pip install`. It needs Python 3.9 or later and runs on Windows, macOS and Linux.

## Installation

Install from [PyPI](https://pypi.org/project/arxivscanner/):

```bash
pip install arxivscanner
arxivscanner --version     # check it works
```

To upgrade later, run `pip install -U arxivscanner`.

This installs an `arxivscanner` command. `python -m arxivscanner …` works the same way. On macOS or Linux, use `python3 -m pip install arxivscanner` if `pip` points at an older Python.

## How to use it

### 1. Interactive mode (easiest)

1. **Start the tool** with no arguments:
   ```bash
   arxivscanner
   ```
2. **Pick a domain.** Type its number, for example `1` for `cs` (Computer Science).
3. **Pick one or more subdomains.** Type a number such as `1` (cs.AI), several numbers such as `8,23` (cs.CV and cs.LG), or `0` for the whole domain. You can also type arXiv codes directly, for example `cs.CV cs.LG`.
4. **Pick a mode.**
   - `1` (today) shows today's announcement.
   - `2` (recent) shows papers submitted in the last N days, and asks for N. Press Enter to accept the default of 3.
5. **Read the results.** Each paper shows its id, title, authors, categories, submission date and comments, the abstract, and links to the abstract page and the PDF.

Here's a real session: Computer Science → cs.AI → recent, over the last 4 days. The arXiv API refused the query here, so the tool switched to OAI-PMH on its own (see [Rate limiting](#rate-limiting)). Long lists are shortened with `…`.

```
PS C:\Users\you> arxivscanner

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
    1. today   (today's announcement, RSS)
    2. recent  (submitted in the last N days, API)
Pick a mode [1]: 2
How many days? [3]: 4

Querying the arXiv API for cs.AI, last 4 day(s) …
  ! arXiv API refused the query (HTTP 406 Not Acceptable from export.arxiv.org); switching to OAI-PMH …
  cs:cs:AI: scanned 659 records, 172 submitted in window
arXiv · cs.AI (Artificial Intelligence)
Submitted 2026-09-24 → 2026-09-27 (UTC); 172 matched via OAI-PMH
172 papers

  1. 2609.30266v1
     LLM Agents Can Easily Tamper With Their Own Traces
     Jeremy Qin, David Schmotz, Derck Prinzhorn, Luca Beurer-Kellner, Ameya Prabhu, Maksym Andriushchenko
     cs.CR, cs.AI · 2026-09-24
     Asynchronous monitoring, incident investigations, and compliance audits primarily rely on agent traces to
     reconstruct what happened. These analyses assume that LLM agents cannot tamper with their own execution traces.
     …
     https://arxiv.org/abs/2609.30266  https://arxiv.org/pdf/2609.30266

  2. 2609.30264v1
     AD-WM: Action-Discriminative World Models for Counterfactual Model Predictive Control
     Jiabin Qiu, Zixuan Chen, Hongye Cao, Jieqi Shi, Jing Huo, Yang Gao
     cs.AI, cs.RO · 2026-09-24 · 9 pages, 5 figures, 4 tables. Project page: https://ad-wm.github.io/
     Latent world models are typically trained to predict factual transitions, whereas model predictive control
     (MPC) must compare alternative actions from the same state. A model can therefore achieve low factual
     …
     https://arxiv.org/abs/2609.30264  https://arxiv.org/pdf/2609.30264

  …

172. 2609.28859v1
     Human-AI-Powered Hypothesis Testing: Cost-Aware Selective AI Scoring and Sequential Human Escalation
     Dae Woong (David) Ham, Xuejun Zhao, Stefanus Jasin, Fenghua Yang
     cs.AI, cs.IT, math.IT, stat.ME · 2026-09-24
     …
     https://arxiv.org/abs/2609.28859  https://arxiv.org/pdf/2609.28859
```

Abstracts are printed in full. Add `--short` to trim each one to about 300 characters, or `--md papers.md` to save the list as a Markdown reading list.

### 2. Command-line flags

Pass `-c` with one or more codes to skip the prompts:

```bash
arxivscanner -c cs.CV                          # today's Computer Vision list
arxivscanner -c cs.CV --type new               # only brand-new submissions (no cross-lists or updates)
arxivscanner -c cs.CV cs.LG --short            # two subdomains, abstracts trimmed
arxivscanner -c cs                             # the whole Computer Science domain
arxivscanner -c cs.CV --mode recent --days 3   # everything submitted in the last 3 days
arxivscanner -c cs.CV --mode recent --source oai   # same, read straight from OAI-PMH
arxivscanner -c cs.CV --md cv.md --json cv.json   # also save the results to files
arxivscanner --from-file saved_feed.xml        # parse a saved RSS, API or OAI-PMH XML file offline
```

| Flag | Meaning | Default |
|---|---|---|
| `-c, --cats CODE …` | Domain(s) or subdomain(s), such as `cs.CV cs.LG`, `cs` or `quant-ph`. Leave it out to get the interactive picker. | — |
| `--mode today\|recent` | `today` is today's announcement (RSS). `recent` is everything submitted in the last `--days` days. | `today` |
| `--days N` | Window size for `--mode recent`, in whole UTC days, including today. | `3` |
| `--max N` | Maximum number of papers for `--mode recent`. | `500` |
| `--source auto\|api\|oai` | Where `--mode recent` reads from. `api` is the arXiv search API, `oai` is arXiv's OAI-PMH feed, and `auto` tries the API and switches to OAI-PMH if the API refuses (see [Rate limiting](#rate-limiting)). | `auto` |
| `--type T …` | Keep only these announcement types (today mode): `new`, `cross`, `replace`, `replace-cross`. | all |
| `--short` | Trim each abstract to about 300 characters. | off |
| `--json FILE` | Also save the results as JSON (all fields plus the abs and PDF URLs). | — |
| `--md FILE` | Also save the results as a Markdown reading list. | — |
| `--from-file XML` | Parse a saved RSS, API or OAI-PMH (`arXivRaw`) XML file instead of fetching. | — |
| `--list` | Print every built-in domain and subdomain, then exit. | — |
| `--no-color` | Plain output, for example when piping to a file. `NO_COLOR` is also respected. | — |
| `--version` | Show the version. | — |

### Which mode should I use?

| Mode | Source | Answers | Notes |
|---|---|---|---|
| `today` (default) | `rss.arxiv.org/rss/<cats>` | "What did arXiv announce today?" | Matches arXiv's daily "new" listing. Each paper is tagged `new`, `cross` (cross-listed from another category), `replace` or `replace-cross` (an updated version of an older paper). |
| `recent` | `export.arxiv.org/api/query`, or `oaipmh.arxiv.org/oai` as a fallback | "What was submitted in the last N days?" | Filters on first-version submission date (UTC), newest first. Also includes author comments (page counts, venue) and journal refs. Capped by `--max`. |

**When is there something new?** arXiv announces Sunday to Thursday at 20:00 US Eastern time, which is about **05:30 IST the next morning**. There are no announcements on Friday or Saturday nights US Eastern, so the Saturday and Sunday (IST) feeds are empty. On those days, use `--mode recent --days 4` or more. A paper only becomes visible once it is announced, so papers submitted on Friday or over the weekend first show up after Sunday night's announcement, in both modes. `cs.CV` usually has 150–300 papers per announcement.

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

The arXiv search API (`export.arxiv.org`) throttles hosts. While it does, it answers `HTTP 406 Not Acceptable` to any query it hasn't cached, and waiting a few minutes often doesn't clear it. So with the default `--source auto`, the tool doesn't retry a 406. It switches straight to arXiv's OAI-PMH feed (`oaipmh.arxiv.org`), which gives the same papers with the same fields:

```
Querying the arXiv API for cs.AI, last 4 day(s) …
  ! arXiv API refused the query (HTTP 406 Not Acceptable from export.arxiv.org); switching to OAI-PMH …
  cs:cs:AI: scanned 659 records, 172 submitted in window
```

OAI-PMH lists every record changed since a date, including older papers that only got a new version. The tool keeps only papers whose first version was submitted inside the window. For a 4-day `cs.AI` window this gave exactly the same 172 papers as the API.

Busy responses (`429`, `503`) and network errors are retried with back-off, honouring `Retry-After`. The tool waits 3 seconds between requests, as arXiv's terms ask. If a later API page fails for another reason, it keeps the papers it already has and prints a warning. The RSS feed (`today` mode) is rarely affected.

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
arxivscanner ──► cli.py ──► fetchers.py ──► arXiv (RSS / API / OAI-PMH)
                   │             │
                   │             └─► models.Paper   (one normalised record)
                   ├─► taxonomy.py  (domain → subdomain names, picker)
                   └─► display.py   (terminal view, JSON / Markdown export)
```

| Module | Role |
|---|---|
| `taxonomy.py` | Built-in map of domains and subdomains, plus the interactive picker. |
| `models.py` | `Paper` dataclass: id, version, title, authors, abstract, categories, primary category, announce type, dates, comment, journal ref, DOI, abs and PDF URLs. |
| `fetchers.py` | Three sources, one output type. `fetch_today()` reads the RSS feed. `fetch_recent()` pages through the search API and falls back to OAI-PMH (`arXivRaw` records, filtered by v1 date) when the API refuses. Also handles retries with back-off, the 3 s delay between calls, de-duplication and type filtering. |
| `display.py` | Colour terminal output (works in Windows 10+ consoles too) plus `export_json` and `export_markdown`. |
| `cli.py` | Flags and the interactive picker. `--from-file` parses a saved XML file offline. |

## Roadmap

- **0.1** (current) Fetch, display and export by domain and subdomain. 0.1.1 adds the OAI-PMH fallback for `--mode recent`.
- **0.2** Remember papers already seen (a local SQLite or JSON file) so each run shows only unseen papers.
- **0.3** Keyword or interest filtering and ranking (title and abstract match, later embeddings).
- **0.4** Daily automation (a scheduled task or cron) and a digest by email, Telegram or HTML.
- **0.5** Dashboard view with bookmarking.

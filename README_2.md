# arXiv Parser — Design 0.1

Fetch and display new arXiv papers for a chosen **domain** (archive, e.g. `cs`) and **subdomain** (category, e.g. `cs.CV`).
Pure Python standard library, so there is nothing to `pip install`. Needs Python 3.9 or later.

## Quick start

```bash
python run.py                                   # interactive: pick domain → subdomain → mode
python run.py -c cs.CV                          # today's Computer Vision & Pattern Recognition list
python run.py -c cs.CV --type new               # only brand-new submissions
python run.py -c cs.CV cs.LG --short            # two subdomains, abstracts trimmed
python run.py -c cs                             # the whole Computer Science domain
python run.py -c cs.CV --mode recent --days 3   # everything submitted in the last 3 days
python run.py -c cs.CV --md cv_today.md --json cv_today.json   # also save to files
python run.py --list                            # show all known domains/subdomains
python -m unittest discover -s tests            # offline tests
```

## Design

```
run.py ──► cli.py ──► fetchers.py ──► arXiv (RSS / API)
             │             │
             │             └─► models.Paper   (one normalised record)
             ├─► taxonomy.py  (domain → subdomain names, picker)
             └─► display.py   (terminal view, JSON / Markdown export)
```

| Module | Role |
|---|---|
| `taxonomy.py` | Built-in map of domains and subdomains (cs, eess, stat, math, q-bio, q-fin, econ, selected physics). Any valid arXiv code also works. |
| `models.py` | `Paper` dataclass: id, version, title, authors, abstract, categories, primary category, announce type, dates, comment, journal ref, DOI, abs and PDF URLs. |
| `fetchers.py` | Two sources, one output type. `fetch_today()` reads the RSS feed. `fetch_recent()` pages through the API. Also handles retries with back-off, a 3 s delay between API calls, de-duplication and type filtering. |
| `display.py` | Colour terminal output (works in Windows 10+ consoles too) plus `export_json` and `export_markdown`. |
| `cli.py` | Flags and the interactive picker. `--from-file` parses a saved XML file offline. |

### Two modes, two sources

| Mode | Source | Answers | Notes |
|---|---|---|---|
| `today` (default) | `rss.arxiv.org/rss/<cats>` | "What did arXiv announce today?" | Matches arXiv's daily "new" listing. Each paper is tagged `new`, `cross` (cross-listed), `replace` or `replace-cross` (updated versions). |
| `recent` | `export.arxiv.org/api/query` | "What was submitted in the last N days?" | Filters on submission date (UTC). Returns comments and journal refs. Capped by `--max` (default 500). |

### arXiv timing

New lists go out Sunday to Thursday at 20:00 US Eastern time, which is about **05:30 IST the next morning**. There are no announcements on Friday or Saturday nights US Eastern, so the Saturday and Sunday IST feeds are empty. `cs.CV` usually has 150–300 papers per announcement.

## Roadmap (next versions)

- **0.2** Remember papers already seen (a local SQLite or JSON file) so each run shows only unseen papers.
- **0.3** Keyword or interest filtering and ranking (title and abstract match, later embeddings).
- **0.4** Daily automation (a scheduled task or cron) and a digest by email, Telegram or HTML.
- **0.5** Dashboard view with bookmarking.

# arXiv Scanner: Plan

Status as of 0.3.0. For how to use what's built, see the [README](README.md).

## Done

| Version | What shipped |
|---|---|
| **0.1** | Fetch, display and export papers by domain and subdomain; today's announcement feed. |
| **0.2** | `recent` mode matches arXiv's "recent" page: the last N announcements, grouped by day (about 99% of papers on the same day and in the same order, checked against 7 categories). Keyword search with `-k`: case-insensitive, matching from the start of a word, any of the keywords, title and abstract, with matches highlighted. Accented author names shown correctly. Tests on Linux, macOS and Windows with Python 3.9 to 3.14. |
| **0.3** | A reading list: `save`, `saved` and `unsave` with tags, by list number or arXiv id. PDF downloads (`save --pdf`, `saved --download`, `config --auto-pdf on`). Your choice of folders (`config --library`, `config --pdfs`), with an offer to move existing papers. A save prompt in interactive mode, and a welcome screen showing your settings. |

The fuller keyword design once proposed here (`--match all`, `--in`, `--rank`) was dropped in favour of the simplest version. Ranking returns in 0.6 below.

## Known limits

- **Late cross-lists in `recent` mode.** OAI-PMH doesn't record when a paper was cross-listed into a category, so papers cross-listed some time after their own announcement are occasionally missed or shown on their original day. Categories with many late cross-lists, such as hep-th, are affected most.
- **Keywords inside longer names.** "StyleGAN" doesn't match `gan`, because matching starts at the beginning of a word; search `stylegan` instead.
- **Very deep PDF folders on Windows.** New downloads shorten their file names to fit Windows' path length limit, but moving existing PDFs into a much deeper folder keeps their names and could hit the limit. It stops with an error rather than losing files.

## Next

| Version | Plan |
|---|---|
| **0.4** | **Saved profiles** (`--profile vision` for your usual categories and keywords) and **remembering papers already seen**, so each run shows only new ones. Together these make a daily "what's new for me" feed. |
| **0.5** | **Daily digest**: a scheduled run (Windows Task Scheduler or cron) that writes an HTML or Markdown digest, or sends it by email. Builds on profiles and seen-papers memory. |
| **0.6** | **Ranking by interest**: keyword weights, favourite authors and categories. Later, optionally, similarity to papers you've saved (an optional install, since it needs extra packages). |
| **Later** | **BibTeX export** of saved papers (for LaTeX and Zotero), **notes** on papers, and a **local web UI** (`arxivscanner ui`): a browser page to browse, search and save, using only the standard library and the same library folder as the terminal. The same UI could later run on a VPS for access from any device. |

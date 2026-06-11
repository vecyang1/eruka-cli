# Changelog

## 0.2.0 - 2026-06-11

### Added
- New `trend` command: weekly search-interest history with a momentum summary
  (recent vs prior 12-week average), `--country` and `--window` options.
- Briefs now include a search-interest momentum line sourced from the trend
  endpoint, and degrade gracefully (with a stderr warning) when it is down.
- Keyword alias deduplication: rows sharing identical volume/CPC/competition
  metrics are collapsed to the first canonical keyword. `keyword --all` keeps
  the raw alias rows.
- Book results are now source-labeled (`eurekaa`, `google_books`,
  `openlibrary`), and fallback usage is reported to stderr and in JSON output.
- `doctor` gained a trend check and now reports which book source answered.

### Fixed
- Markdown rendering no longer crashes when the backend returns `null` counts
  (platforms/categories/students) or `null` keyword metrics; missing values
  render as `?`.
- `doctor` now exits 2 whenever a public check fails (previously always exited
  0 without `--from-chrome`, a trap for scripts and cron health checks).
- Network failures, malformed JSON responses, and Ctrl-C now produce clean
  one-line errors and correct exit codes instead of raw tracebacks.
- GraphQL responses with `data: null` and non-JSON bodies raise a clear error
  instead of silently returning empty results.
- Opportunity scoring distinguishes "course data unavailable" from a genuine
  zero-course market instead of awarding the empty-market competition floor.
- Briefs render the actual auth failure reason as a callout in the Course
  Examples section instead of silently omitting courses.

### Changed
- HTTP client hardening: descriptive User-Agent, automatic retries with
  backoff on 429/502/503/504, and split connect/read timeouts.
- `doctor` output no longer includes the account email (kept in `auth-status`,
  which the user invokes deliberately).
- Brief filenames now use UTC timestamps to match the embedded `generatedAt`.

## 0.1.4 - 2026-05-23

- Removed internal agent-continuity and implementation-note files from the
  public community repository.
- Moved the sample brief to `examples/` and ignored local generated research
  output.

## 0.1.3 - 2026-05-23

- Sanitized public-facing docs before community push by removing local machine
  paths and private account-status wording.

## 0.1.2 - 2026-05-23

- Refreshed the e2e verification snapshot and latest authenticated sample
  report.
- Updated CLI help and docs so book research consistently reflects the
  Eurekaa-first, Google Books/Open Library fallback contract.

## 0.1.1 - 2026-05-23

- Added public course-market signals to Markdown briefs so no-auth reports still
  include real course evidence from Eurekaa public summary data.
- Added Eurekaa public GraphQL book search as the first book source, with Google
  Books and Open Library retained as fallbacks.
- Updated the latest verified sample report.

## 0.1.0 - 2026-05-23

- Initialized the Eruka CLI with read-only course, keyword, book, summary,
  authenticated course, doctor, auth-status, and brief commands.

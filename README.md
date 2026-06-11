# Eruka CLI

Eruka is a local, agent-friendly CLI for course research, market research, book
research, and keyword validation. It uses real Eurekaa-adjacent data surfaces:
public Eurekaa backend endpoints, public/authenticated Eurekaa GraphQL when
available, and Google Books/Open Library as public book-research fallbacks.

The goal is not to clone Eurekaa's UI. The goal is to give agents a fast research
machine: one command that gathers demand, competition, platform saturation,
keyword economics, search-interest momentum, course examples, and book examples
into a compact brief.

## Quick Start

```bash
cd eruka-cli
python3 -m pip install -e .
python3 -m eruka_cli doctor
python3 -m eruka_cli summary "marketing"
python3 -m eruka_cli keyword "digital marketing" --limit 10
python3 -m eruka_cli trend "digital marketing" --country US
python3 -m eruka_cli brief "digital marketing" --limit 5 --out research
```

If Chrome is already logged in to Eurekaa, authenticated course search can read
the in-page API token without printing it. It first tries direct Chrome CDP and
then falls back to the installed `browser-harness` daemon:

```bash
python3 -m eruka_cli auth-status --from-chrome
python3 -m eruka_cli courses "digital marketing" --limit 5 --from-chrome
```

You can also provide a token explicitly:

```bash
ERUKA_API_TOKEN="..." python3 -m eruka_cli courses "digital marketing" --limit 5
```

## Commands

- `doctor` checks the public backend, GraphQL introspection, book search, the
  trend endpoint, and optional Chrome token access. Exits 2 if any public
  check fails, so it is safe to use as a cron/CI health probe.
- `summary <keyword>` returns course demand, platform/category distribution, and
  the Eruka opportunity score.
- `keyword <keyword>` returns Google keyword volume/CPC/competition data plus
  related keyword ideas. Alias rows with identical metrics are deduplicated;
  pass `--all` to keep them.
- `trend <keyword>` returns weekly search-interest history with a momentum
  summary (recent vs prior 12-week average). Supports `--country US` and
  `--window N`.
- `courses <keyword>` returns detailed course rows from authenticated GraphQL.
- `book-search <query>` returns Eurekaa public GraphQL book results first, with
  Google Books/Open Library fallbacks for book-market research. Every book row
  carries a `source` label, and fallback usage is reported on stderr.
- `brief <keyword>` creates a Markdown or JSON research brief combining all safe
  available sources, including search-interest momentum. Degraded sections are
  called out explicitly in the document.
- `auth-status` reports whether an API token is available without revealing it.

## Behavior Notes

- All commands exit 0 on success, 2 on errors (including failed doctor checks),
  and 130 on interrupt. Errors are single human-readable lines on stderr.
- HTTP calls use retries with backoff on 429/502/503/504 and identify
  themselves with an `eruka-cli/<version>` User-Agent.
- JSON output (`--json`) is stable and agent-friendly; warnings (book-source
  fallbacks, degraded auth) appear in dedicated fields rather than polluting
  the data payload.

## Verification Snapshot

Verified on 2026-06-11 against live endpoints:

- `python3 -m compileall -q eruka_cli`
- `python3 -m pytest -q` -> 48 passed
- `python3 -m eruka_cli doctor` (public checks ok; trend check ok)
- `python3 -m eruka_cli summary "python programming"`
- `python3 -m eruka_cli keyword "digital marketing" --limit 5`
- `python3 -m eruka_cli trend "ai automation"` and `--country JP`
- `python3 -m eruka_cli book-search "digital marketing" --limit 3`
- `python3 -m eruka_cli brief "ai automation" --limit 3`
- CJK keyword smoke test (`keyword "日本語学習"`)

Sample report:
`examples/digital-marketing-brief.md`

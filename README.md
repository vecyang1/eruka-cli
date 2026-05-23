# Eruka CLI

Eruka is a local, agent-friendly CLI for course research, market research, book
research, and keyword validation. It uses real Eurekaa-adjacent data surfaces:
public Eurekaa backend endpoints, public/authenticated Eurekaa GraphQL when
available, and Google Books/Open Library as public book-research fallbacks.

The goal is not to clone Eurekaa's UI. The goal is to give agents a fast research
machine: one command that gathers demand, competition, platform saturation,
keyword economics, course examples, and book examples into a compact brief.

## Quick Start

```bash
cd eruka-cli
python3 -m pip install -e .
python3 -m eruka_cli doctor
python3 -m eruka_cli summary "marketing"
python3 -m eruka_cli keyword "digital marketing" --limit 10
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

- `doctor` checks public backend, GraphQL introspection, book search, and
  optional Chrome token access.
- `summary <keyword>` returns course demand, platform/category distribution, and
  the Eruka opportunity score.
- `keyword <keyword>` returns Google keyword volume/CPC/competition data plus
  related keyword ideas.
- `courses <keyword>` returns detailed course rows from authenticated GraphQL.
- `book-search <query>` returns Eurekaa public GraphQL book results first, with
  Google Books/Open Library fallbacks for book-market research.
- `brief <keyword>` creates a Markdown or JSON research brief combining all safe
  available sources.
- `auth-status` reports whether an API token is available without revealing it.

## Verification Snapshot

Verified on 2026-05-23:

- `python3 -m compileall -q eruka_cli`
- `python3 -m pytest -q` -> 6 passed
- `python3 -m eruka_cli doctor`
- `python3 -m eruka_cli summary "marketing" --json`
- `python3 -m eruka_cli book-search "digital marketing" --limit 3 --json`
- `python3 -m eruka_cli auth-status --from-chrome --json`
- `python3 -m eruka_cli courses "digital marketing" --limit 3 --from-chrome --json`
- `python3 -m eruka_cli brief "digital marketing" --limit 3 --out research`
- `python3 -m eruka_cli brief "digital marketing" --limit 3 --from-chrome --out research`

Sample report:
`examples/digital-marketing-brief.md`

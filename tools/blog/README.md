# Automatic field notes

`autopost.py` writes one blog post when one is due, about five every two
months. GitHub Actions runs it every Monday morning
(`.github/workflows/field-notes.yml`); when the last automatic post is at
least 12 days old it writes a new one and publishes it to the `cloudflare`
branch, which Cloudflare Pages then deploys.

## What it writes

Posts alternate between two kinds.

- **News.** The script reads the feeds in `sources.yml`, keeps articles from
  the last five weeks that mention surveying, GNSS, GIS, mapping or Earth
  observation (Kenya and East Africa rank first), skips adverts, events and
  defence stories, and reads the best article in full. The post explains it
  for clients in Kenya and cites it under "Sources".
- **Guides.** When there is no suitable news, or in turn with it, it writes
  the next unwritten guide from `sources.yml`. Each guide has a brief, and
  the post may use no specific facts beyond it.

Each draft is written by Claude, then checked by a second, separate request
that compares it with its source and removes anything it cannot support.
The script then checks length, headings, links and a list of filler phrases.
A draft that fails any check is not published; the Actions log says why.

## Setting it up

1. Create an API key at console.anthropic.com and add a little credit.
2. In the repository on GitHub: Settings > Secrets and variables > Actions >
   New repository secret, named `ANTHROPIC_API_KEY`.
3. GitHub runs scheduled jobs only from the repository's default branch.
   Either make `cloudflare` the default branch (Settings > General > Default
   branch), which suits a site hosted on Cloudflare, or copy
   `.github/workflows/field-notes.yml` to the default branch.
4. To test it at once: Actions > Field notes > Run workflow, with "Write a
   post now" ticked.

To read each post before it goes live, add a repository variable
`FIELD_NOTES_REVIEW` = `true` (Settings > Secrets and variables > Actions >
Variables). Each post then arrives as a pull request; merge it to publish,
close it to discard. GitHub may also need Settings > Actions > General >
"Allow GitHub Actions to create and approve pull requests" switched on.

## Cost

The script uses Claude Opus 5.5 by default, at $4 per million input tokens
and $20 per million output tokens (November 2026). One post takes two
requests of roughly 10 000 to 20 000 tokens in and a few thousand out, about
US$0.30 to US$0.60. At five posts every two months that is about US$10 to
US$20 a year. Set a repository variable `CLAUDE_MODEL` to `claude-sonnet-5-5` (about half the price) or
`claude-haiku-5-5` (a small fraction of it) to spend less, at some cost in
quality. Check current prices before relying on these figures.

## Keeping it useful

- Add guides to `sources.yml` as you think of questions clients ask. Each is
  written once; when they run out, only news is written.
- Add or remove feeds in `sources.yml`. `python tools/blog/autopost.py
  --check-feeds` loads every feed and reports which work.
- Every automatic post has `auto: true` in its front matter. Edit or delete
  it like any other post.
- `python tools/blog/autopost.py --dry-run --force` runs everything except
  the API call and writes a sample post to a temporary folder, never to
  `_posts`.

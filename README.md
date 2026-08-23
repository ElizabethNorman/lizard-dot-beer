# lizard dot beer

This repository contains the source and generated static site for
[lizard.beer](https://lizard.beer), plus the `beer.lizard.blog.post` Lexicon
and its local ATProto publisher.

## Layout

- `content/pages/` contains the permanent page bodies.
- `content/posts/` contains blog post sources with YAML frontmatter.
- `templates/` contains the shared HTML structure.
- `static/` contains CSS, JavaScript, images, and map data.
- `public/` is generated static output. Do not edit it by hand.
- `lexicons/` contains the custom ATProto Lexicon.
- `.lizard-publish.json` records published ATProto record keys.

Both source Markdown and generated HTML are committed. Cloudflare Pages serves
`public/` directly with no build command.

## Local setup

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Write and build

Create a safely opted-out draft:

```bash
.venv/bin/python publish.py new "Post title"
```

Edit the new file in `content/posts/`. Before it can appear on the website,
set `draft: false`. Before it can be published to ATProto, also deliberately
set `publishToAtproto: true`.

Generate the complete website:

```bash
.venv/bin/python publish.py build
```

Preview it locally:

```bash
python -m http.server --directory public
```

Open <http://localhost:8000>. Re-run `build` after every source or template
change.

## Publish

Commit both the source and generated output, then push them to GitHub. Once the
canonical page is live, inspect the exact ATProto record:

```bash
.venv/bin/python publish.py preview 2026-08-22
```

Publish that one post:

```bash
.venv/bin/python publish.py publish 2026-08-22
```

The command refuses drafts and posts with `publishToAtproto: false`. It never
publishes every post implicitly. Commit `.lizard-publish.json` after a
successful write so later edits update the same record instead of creating a
duplicate.

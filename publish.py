#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from string import Template
from typing import Any
import tempfile

import markdown
import yaml

ROOT = Path(__file__).resolve().parent
PAGES_DIR = ROOT / "content/pages"
POSTS_DIR = ROOT / "content/posts"
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
PUBLIC_DIR = ROOT / "public"
STATE_FILE = ROOT / ".lizard-publish.json"
SITE_URL = "https://lizard.beer"
AT_DID = "did:plc:3hmpatr4emhvmci3tvnkiav6"
AT_COLLECTION = "beer.lizard.blog.post"
PDSLS_URL = "https://pdsls.dev"
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class Page:
    source: Path
    title: str
    route: str
    extra_head: str = ""
    extra_scripts: str = ""


class Post:
    def __init__(self, path: Path, metadata: dict[str, Any], content: str):
        self.path = path
        self.content = content.strip()
        self.title = required_text(metadata, "title", path)
        self.slug = required_text(metadata, "slug", path)
        if not SLUG_PATTERN.fullmatch(self.slug):
            die(f"{path}: slug may contain lowercase letters, numbers, and hyphens")
        self.created_at = normalized_datetime(metadata.get("createdAt"), path)
        self.summary = str(metadata.get("summary", "")).strip()
        self.draft = required_bool(metadata, "draft", path)
        self.publish_to_atproto = required_bool(
            metadata, "publishToAtproto", path
        )

    @property
    def display_date(self) -> str:
        value = datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
        return f"{value.strftime('%B')} {value.day}, {value.year}"

    @property
    def canonical_url(self) -> str:
        return f"{SITE_URL}/blog/{self.slug}/"

    @property
    def source_hash(self) -> str:
        value = json.dumps(
            {
                "title": self.title,
                "slug": self.slug,
                "summary": self.summary,
                "content": self.content,
                "createdAt": self.created_at,
                "canonicalUrl": self.canonical_url,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(value.encode()).hexdigest()


def die(message: str) -> None:
    print(f"🔴 {message}", file=sys.stderr)
    raise SystemExit(1)


def required_text(metadata: dict[str, Any], name: str, path: Path) -> str:
    value = metadata.get(name)
    if value is None or not str(value).strip():
        die(f"{path}: '{name}' is required")
    return str(value).strip()


def required_bool(metadata: dict[str, Any], name: str, path: Path) -> bool:
    value = metadata.get(name)
    if not isinstance(value, bool):
        die(f"{path}: '{name}' must explicitly be true or false")
    return value


def normalized_datetime(value: Any, path: Path) -> str:
    if value is None:
        die(f"{path}: 'createdAt' is required")
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    except ValueError:
        die(f"{path}: createdAt is not a valid ISO-8601 datetime")
    if parsed.tzinfo is None:
        die(f"{path}: createdAt must include a timezone")
    return parsed.isoformat().replace("+00:00", "Z")


def read_post(path: Path) -> Post:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        die(f"{path}: post is missing YAML frontmatter")
    parts = raw.split("---", 2)
    if len(parts) != 3:
        die(f"{path}: malformed YAML frontmatter")
    metadata = yaml.safe_load(parts[1]) or {}
    if not isinstance(metadata, dict):
        die(f"{path}: frontmatter must be a YAML object")
    return Post(path, metadata, parts[2])


def get_posts() -> list[Post]:
    posts = [read_post(path) for path in sorted(POSTS_DIR.glob("*.md"))]
    seen: dict[str, Path] = {}
    for post in posts:
        if post.slug in seen:
            die(f"Duplicate slug '{post.slug}' in {seen[post.slug]} and {post.path}")
        seen[post.slug] = post.path
    return posts


def find_post(posts: list[Post], slug: str) -> Post:
    for post in posts:
        if post.slug == slug:
            return post
    die(f"No post with slug '{slug}'")


def template(name: str) -> Template:
    path = TEMPLATES_DIR / name
    if not path.exists():
        die(f"Missing template: {path}")
    return Template(path.read_text(encoding="utf-8"))


def visible_posts(posts: list[Post]) -> list[Post]:
    return sorted(
        (post for post in posts if not post.draft),
        key=lambda post: post.created_at,
        reverse=True,
    )


def pdsls_url(uri: str) -> str:
    return f"{PDSLS_URL}/{uri}"


def navigation(posts: list[Post]) -> str:
    links = [
        ("/", "Home"),
        ("/malcolm/", "Malcolm"),
        ("/roaming/", "Roam"),
        ("/blog/", "Blog"),
        ("/lizard/", "Lizard"),
    ]
    main_links = "\n".join(
        f'<li><a href="{url}">{label}</a></li>' for url, label in links
    )
    post_links = "\n".join(
        f'<li><a href="/blog/{post.slug}/">{html.escape(post.display_date)}</a></li>'
        for post in visible_posts(posts)
    )
    return (
        f'<ul class="site-links">{main_links}</ul>'
        '<p class="nav-heading">Posts</p>'
        f'<ul class="post-list" aria-label="Posts">{post_links}</ul>'
    )


def document(
    title: str,
    content: str,
    posts: list[Post],
    canonical_url: str,
    description: str = "",
    extra_head: str = "",
    extra_scripts: str = "",
    body_class: str = "",
    show_header: bool = True,
) -> str:
    site_header = template("wordmark.html").safe_substitute(
        navigation=navigation(posts)
    ) if show_header else ""
    return template("base.html").safe_substitute(
        title=html.escape(title),
        description=html.escape(description),
        canonical_url=html.escape(canonical_url),
        body_class=body_class,
        site_header=site_header,
        content=content,
        extra_head=extra_head,
        extra_scripts=extra_scripts,
    )


def write_route(build_dir: Path, route: str, contents: str) -> None:
    path = build_dir / "index.html" if route == "/" else (
        build_dir / route.strip("/") / "index.html"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    print(f"🟢 HTML  {route}")


def pages() -> list[Page]:
    return [
        Page(PAGES_DIR / "home.html", "Home", "/"),
        Page(PAGES_DIR / "malcolm.html", "Malcolm", "/malcolm/"),
        Page(PAGES_DIR / "lizard.html", "Lizard", "/lizard/"),
        Page(
            PAGES_DIR / "roaming.html",
            "Lizard does PG",
            "/roaming/",
            '<link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css">',
            '<script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>\n'
            '<script src="/js/roaming.js"></script>',
        ),
    ]


def build_site() -> None:
    posts = get_posts()
    publication_state = load_state()["posts"]
    staging = ROOT / ".public-build"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    shutil.copytree(STATIC_DIR, staging, dirs_exist_ok=True)

    for page in pages():
        body = page.source.read_text(encoding="utf-8").strip()
        content = template("page.html").safe_substitute(content=body)
        write_route(
            staging,
            page.route,
            document(
                page.title,
                content,
                posts,
                f"{SITE_URL}{page.route}",
                extra_head=page.extra_head,
                extra_scripts=page.extra_scripts,
                body_class="home-page" if page.route == "/" else "section-page",
            ),
        )

    entries: list[str] = []
    published_posts = visible_posts(posts)
    for index, post in enumerate(published_posts):
        summary = f"<p>{html.escape(post.summary)}</p>" if post.summary else ""
        entries.append(
            template("archive-entry.html").safe_substitute(
                title=html.escape(post.title), slug=post.slug,
                created_at=post.created_at, display_date=post.display_date,
                summary=summary,
            )
        )
        rendered_body = markdown.markdown(
            post.content, extensions=["extra", "sane_lists"], output_format="html5"
        )
        rendered_body = re.sub(
            r"^\s*<h[12][^>]*>.*?</h[12]>\s*", "", rendered_body,
            count=1, flags=re.IGNORECASE | re.DOTALL,
        )
        media_items: list[str] = []

        def collect_image(match: re.Match[str]) -> str:
            image_tag = match.group(0)
            if not re.search(r"\balt\s*=", image_tag, flags=re.IGNORECASE):
                image_tag = image_tag[:-1] + (
                    f' alt="Walking progress map for {html.escape(post.display_date)}">'
                )
            media_items.append(image_tag)
            return ""

        rendered_body = re.sub(
            r"<img\b[^>]*>", collect_image, rendered_body,
            flags=re.IGNORECASE,
        )
        rendered_body = re.sub(r"<p>\s*</p>", "", rendered_body)
        next_post = published_posts[index - 1] if index > 0 else None
        prev_post = published_posts[index + 1] if index + 1 < len(published_posts) else None
        next_link = (
            f'<a class="post-nav__link post-nav__next" href="/blog/{next_post.slug}/" rel="next">Next</a>'
            if next_post else '<span class="post-nav__empty" aria-hidden="true"></span>'
        )
        prev_link = (
            f'<a class="post-nav__link post-nav__prev" href="/blog/{prev_post.slug}/" rel="prev">Prev</a>'
            if prev_post else '<span class="post-nav__empty" aria-hidden="true"></span>'
        )
        media = (
            '<aside class="post-media" aria-label="Post images">'
            + "\n".join(media_items) + "</aside>"
            if media_items else ""
        )
        published_record = publication_state.get(post.slug)
        atmosphere_link = ""
        if published_record and published_record.get("uri"):
            record_url = pdsls_url(published_record["uri"])
            atmosphere_link = (
                '<p class="atmosphere-link">'
                f'<a href="{html.escape(record_url)}">view this post on PDSls</a>'
                '</p>'
            )
        post_page = template("post.html").safe_substitute(
            title=html.escape(post.title), created_at=post.created_at,
            display_date=post.display_date, content=rendered_body,
            next_link=next_link, prev_link=prev_link, media=media,
            atmosphere_link=atmosphere_link,
            layout_class="post-layout--with-media" if media_items else "post-layout--text-only",
        )
        write_route(
            staging,
            f"/blog/{post.slug}/",
            document(
                post.title, post_page, posts, post.canonical_url, post.summary,
                body_class="post-page", show_header=False,
            ),
        )

    archive = template("archive.html").safe_substitute(posts="\n".join(entries))
    write_route(
        staging, "/blog/",
        document("Blog", archive, posts, f"{SITE_URL}/blog/", body_class="section-page archive-page"),
    )
    if PUBLIC_DIR.exists():
        shutil.rmtree(PUBLIC_DIR)
    staging.rename(PUBLIC_DIR)
    print(f"🦎 Built {len(visible_posts(posts))} posts in public/")


def atproto_content(post: Post) -> str:
    content = re.sub(r"\]\(/", f"]({SITE_URL}/", post.content)
    return re.sub(
        r'((?:src|href)=["\'])/', rf"\1{SITE_URL}/", content,
        flags=re.IGNORECASE,
    )


def validate_for_atproto(post: Post) -> None:
    if post.draft:
        die(f"{post.path}: drafts cannot be published")
    if not post.publish_to_atproto:
        die(f"{post.path}: publishToAtproto is false")
    limits = [
        ("title", post.title, 3_000, 300),
        ("summary", post.summary, 10_000, 1_000),
        ("slug", post.slug, 500, None),
        ("content", atproto_content(post), 20_000, None),
    ]
    for name, value, byte_limit, character_limit in limits:
        if len(value.encode("utf-8")) > byte_limit:
            die(f"{post.path}: {name} exceeds {byte_limit:,} bytes")
        if character_limit and len(value) > character_limit:
            die(f"{post.path}: {name} exceeds {character_limit:,} characters")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def atproto_record(post: Post, is_update: bool) -> dict[str, Any]:
    validate_for_atproto(post)
    record: dict[str, Any] = {
        "$type": AT_COLLECTION,
        "title": post.title,
        "content": atproto_content(post),
        "createdAt": post.created_at,
        "canonicalUrl": post.canonical_url,
        "slug": post.slug,
    }
    if post.summary:
        record["summary"] = post.summary
    if is_update:
        record["updatedAt"] = utc_now()
    return record


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"posts": {}}
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        die(f"{STATE_FILE} contains invalid JSON: {exc}")
    if not isinstance(state, dict) or not isinstance(state.get("posts"), dict):
        die(f"{STATE_FILE} must contain a 'posts' object")
    return state


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def require_goat() -> None:
    try:
        subprocess.run(
            ["goat", "--help"], check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        die("'goat' was not found; install it and log in before publishing")


def goat_command(arguments: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(arguments, capture_output=True, text=True, check=check)


def publish_post(slug: str, force: bool) -> None:
    post = find_post(get_posts(), slug)
    state = load_state()
    existing = state["posts"].get(slug)

    validate_for_atproto(post)

    if existing and existing.get("sourceHash") == post.source_hash and not force:
        print(f"⚪ AT    {slug}: unchanged")
        return

    if existing and not existing.get("rkey"):
        die(f"{STATE_FILE}: {slug} is missing its rkey")

    require_goat()

    if existing:
        rkey = existing["rkey"]
    else:
        result = goat_command(["goat", "syntax", "tid", "generate"])
        rkey = result.stdout.strip()

        if not rkey:
            die("goat did not return a TID")

    record = atproto_record(post, existing is not None)

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        encoding="utf-8",
        delete=False,
    ) as temp:
        json.dump(record, temp, ensure_ascii=False)
        temp_path = temp.name

    try:
        if existing:
            command = [
                "goat",
                "record",
                "update",
                "--no-validate",
                "--rkey",
                rkey,
                temp_path,
            ]
        else:
            command = [
                "goat",
                "record",
                "create",
                "--no-validate",
                "--rkey",
                rkey,
                temp_path,
            ]

        result = goat_command(command, check=False)

    finally:
        Path(temp_path).unlink(missing_ok=True)

    if result.returncode:
        print(result.stderr, file=sys.stderr)
        die("ATProto write failed; publication state was not changed")

    # goat record create/update prints something like:
    #
    # at://did/.../collection/rkey    bafy...
    parts = result.stdout.strip().split()
    uri_index = next(
        (index for index, part in enumerate(parts) if part.startswith("at://")),
        None,
    )
    uri = (
        parts[uri_index]
        if uri_index is not None
        else f"at://{AT_DID}/{AT_COLLECTION}/{rkey}"
    )
    cid = (
        parts[uri_index + 1]
        if uri_index is not None
        and uri_index + 1 < len(parts)
        and parts[uri_index + 1].startswith("bafy")
        else None
    )

    state["posts"][slug] = {
        "rkey": rkey,
        "uri": uri,
        "cid": cid,
        "sourceHash": post.source_hash,
        "publishedAt": utc_now(),
    }

    save_state(state)

    print(
        f"🦎 AT    {slug}: {'updated' if existing else 'created'}\n"
        f"         {uri}\n"
        f"         {pdsls_url(uri)}"
    )

def preview_post(slug: str) -> None:
    post = find_post(get_posts(), slug)
    existing = load_state()["posts"].get(slug)
    print(json.dumps(atproto_record(post, existing is not None), indent=2, ensure_ascii=False))


def new_post(title: str | None) -> None:
    now = datetime.now(timezone.utc)
    actual_title = title or f"{now.strftime('%B')} {now.day}, {now.year}"
    slug = re.sub(r"[^a-z0-9]+", "-", actual_title.lower()).strip("-")
    if not slug:
        slug = now.strftime("%Y-%m-%d")
    path = POSTS_DIR / f"{slug}.md"
    if path.exists():
        die(f"{path} already exists")
    safe_title = actual_title.replace('"', '\\"')
    path.write_text(
        f'---\ntitle: "{safe_title}"\nslug: "{slug}"\n'
        f'createdAt: "{utc_now()}"\nsummary: ""\n'
        'draft: true\npublishToAtproto: false\n---\n\n'
        f'# {actual_title}\n\nStart writing here.\n',
        encoding="utf-8",
    )
    print(f"🦎 Created {path.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="lizard.beer site and ATProto publisher")
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("new", help="create an opted-out draft")
    new.add_argument("title", nargs="?")
    commands.add_parser("build", help="generate the static site in public/")
    preview = commands.add_parser("preview", help="show a record without writing it")
    preview.add_argument("slug")
    publish = commands.add_parser("publish", help="publish one opted-in post")
    publish.add_argument("slug")
    publish.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.command == "new":
        new_post(args.title)
    elif args.command == "build":
        build_site()
    elif args.command == "preview":
        preview_post(args.slug)
    elif args.command == "publish":
        publish_post(args.slug, args.force)
        build_site()


if __name__ == "__main__":
    main()

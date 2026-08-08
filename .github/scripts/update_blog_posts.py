#!/usr/bin/env python3
"""Fetch the latest posts from the corbinr40.com RSS feed and update README.md.

Rewrites only the block between the BLOG-POST-LIST markers, leaving the rest
of the README untouched. Uses the Python standard library only, so it runs
on a stock GitHub Actions runner (and locally) with no installs.
"""

import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

FEED_URL = "https://corbinr40.com/rss"
README = Path(__file__).resolve().parents[2] / "README.md"
MAX_POSTS = 5
START_MARKER = "<!-- BLOG-POST-LIST:START -->"
END_MARKER = "<!-- BLOG-POST-LIST:END -->"
# Cloudflare in front of corbinr40.com serves a 404 to non-browser user
# agents (curl/urllib defaults), so identify as a Mozilla-compatible bot.
USER_AGENT = (
    "Mozilla/5.0 (compatible; corbinr40-readme-bot/1.0; "
    "+https://github.com/corbinr40/corbinr40)"
)


def fetch_feed(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def parse_posts(feed_xml: bytes) -> list[dict]:
    # A legitimate RSS feed never declares a DOCTYPE; rejecting DTDs outright
    # blocks XXE and entity-expansion (billion laughs) attacks — the same
    # mitigation defusedxml applies — without leaving the stdlib.
    if b"<!DOCTYPE" in feed_xml:
        raise ValueError("feed contains a DOCTYPE/DTD, refusing to parse it")
    root = ET.fromstring(feed_xml)
    posts = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        if not title or not link:
            continue
        try:
            published = parsedate_to_datetime(pub_date)
        except (TypeError, ValueError):
            published = None
        posts.append({"title": title, "link": link, "published": published})

    # Feeds are normally newest-first already; sort to guarantee it.
    # Undated posts sink to the bottom rather than crashing the sort.
    dated = [p for p in posts if p["published"] is not None]
    undated = [p for p in posts if p["published"] is None]
    dated.sort(key=lambda p: p["published"], reverse=True)
    return (dated + undated)[:MAX_POSTS]


def format_post(post: dict) -> str:
    # Square brackets in a title would break the markdown link syntax.
    title = post["title"].replace("[", r"\[").replace("]", r"\]")
    line = f"- [{title}]({post['link']})"
    if post["published"] is not None:
        line += f" — {post['published'].strftime('%-d %b %Y')}"
    return line


def update_readme(posts: list[dict]) -> bool:
    content = README.read_text(encoding="utf-8")
    pattern = re.compile(
        re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER), re.DOTALL
    )
    if not pattern.search(content):
        sys.exit(f"ERROR: markers {START_MARKER} / {END_MARKER} not found in {README}")

    block = "\n".join([START_MARKER, *map(format_post, posts), END_MARKER])
    # Replace via a callable so backslashes in titles aren't treated as
    # regex group references.
    new_content = pattern.sub(lambda _: block, content, count=1)
    if new_content == content:
        return False
    README.write_text(new_content, encoding="utf-8")
    return True


def main() -> None:
    posts = parse_posts(fetch_feed(FEED_URL))
    if not posts:
        sys.exit("ERROR: no posts found in feed — refusing to empty the README section")

    if update_readme(posts):
        print(f"README updated with {len(posts)} post(s):")
    else:
        print(f"README already up to date ({len(posts)} post(s)):")
    for post in posts:
        print(f"  {format_post(post)}")


if __name__ == "__main__":
    main()

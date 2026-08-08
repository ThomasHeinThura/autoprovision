"""Serves the Requirements, Guide and Theory documents for a workload.

Content is markdown under content/<slug>/, so it lives next to the code it
describes and can be edited without touching the console.
"""

from __future__ import annotations

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT_DIR = os.path.join(BASE_DIR, "content")

PAGES = ("requirements", "guide", "theory")


def read(slug: str, page: str) -> str | None:
    if page not in PAGES:
        return None
    # slug comes from the registry, never from user input, but normalise anyway.
    safe_slug = os.path.basename(slug.strip())
    if not safe_slug or safe_slug.startswith("."):
        return None
    path = os.path.join(CONTENT_DIR, safe_slug, f"{page}.md")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def handbook() -> list[dict]:
    """Every Theory page, assembled into one manual."""
    if not os.path.isdir(CONTENT_DIR):
        return []
    out = []
    for slug in sorted(os.listdir(CONTENT_DIR)):
        body = read(slug, "theory")
        if body:
            title = body.lstrip().split("\n", 1)[0].lstrip("# ").strip()
            out.append({"slug": slug, "title": title or slug, "body": body})
    return out

#!/usr/bin/env python3
"""Verify every relative markdown link resolves to something on disk.

Documentation drifts silently. A file moves, the link keeps rendering as a link,
and nobody finds out until someone follows it during an incident. Run this in
pre-commit and the class of problem stops existing.

    scripts/check-links.py            # check
    scripts/check-links.py --list     # also list every link that was checked
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "node_modules", ".aidlc-rule-details", "dist", "data"}

# [text](target) — ignore images, anchors, and anything with a scheme.
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def is_external(target: str) -> bool:
    return (
        target.startswith(("http://", "https://", "mailto:", "#"))
        or target.startswith("{{")          # Jinja inside a playbook comment
    )


def main() -> int:
    show_all = "--list" in sys.argv
    broken: list[tuple[Path, str, Path]] = []
    checked = 0

    files = [
        p for p in ROOT.rglob("*.md")
        if not any(part in SKIP_DIRS for part in p.parts)
    ]

    for path in sorted(files):
        for raw in LINK.findall(path.read_text(encoding="utf-8", errors="replace")):
            target = raw.split("#", 1)[0]        # strip the anchor
            if not target or is_external(raw):
                continue
            checked += 1
            resolved = (path.parent / target).resolve()
            if show_all:
                print(f"  {path.relative_to(ROOT)} → {target}")
            if not resolved.exists():
                broken.append((path.relative_to(ROOT), target, resolved))

    if broken:
        print(f"\n{len(broken)} broken link{'s' if len(broken) != 1 else ''}:\n")
        for source, target, resolved in broken:
            print(f"  {source}")
            print(f"    → {target}")
            try:
                print(f"      (resolves to {resolved.relative_to(ROOT)}, which does not exist)")
            except ValueError:
                print(f"      (resolves outside the repository: {resolved})")
        return 1

    print(f"All {checked} relative links resolve across {len(files)} markdown files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

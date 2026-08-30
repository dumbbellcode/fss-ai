#!/usr/bin/env python3
"""Remove generated Markdown and JSON artifacts under the assets directory."""

import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET = PROJECT_ROOT / "assets"

PATTERNS = ("*.md", "*.cleaned.md", "*.cleaned.json")


def cleanup(target: str | Path = DEFAULT_TARGET) -> list[Path]:
    target = Path(target)
    files = {
        path
        for pattern in PATTERNS
        for path in target.rglob(pattern)
        if path.is_file()
    }
    for path in sorted(files):
        path.unlink()
        print(f"Removed: {path}")
    return sorted(files)


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove generated Markdown and JSON artifacts.")
    parser.add_argument("target", nargs="?", default=DEFAULT_TARGET, type=Path)
    args = parser.parse_args()
    cleanup(args.target)


if __name__ == "__main__":
    main()
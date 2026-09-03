#!/usr/bin/env python3
"""Remove generated stage artifacts under the assets directory.

The ``converted/`` and ``cleaned/`` stage directories and the pipeline manifest
are removed; source PDFs under ``original/`` are kept.
"""

import argparse
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET = PROJECT_ROOT / "assets"

GENERATED_DIRS = {"converted", "cleaned", "post_amendment", "ingestion"}
GENERATED_FILES = {"manifest.json"}


def cleanup(target: str | Path = DEFAULT_TARGET) -> list[Path]:
    target = Path(target)
    removed = []
    for path in sorted(target.rglob("*")):
        if path.is_dir() and path.name in GENERATED_DIRS:
            shutil.rmtree(path)
            removed.append(path)
        elif path.is_file() and path.name in GENERATED_FILES:
            path.unlink()
            removed.append(path)
    for path in removed:
        print(f"Removed: {path}")
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove generated stage artifacts.")
    parser.add_argument("target", nargs="?", default=DEFAULT_TARGET, type=Path)
    args = parser.parse_args()
    cleanup(args.target)


if __name__ == "__main__":
    main()

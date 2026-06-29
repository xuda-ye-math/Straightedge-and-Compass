"""Persist construction documents to ``data/commands/<n>.json`` for reuse.

Paths are resolved relative to the package so the cache works regardless of the current
working directory.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COMMANDS_DIR = REPO_ROOT / "data" / "commands"


def path_for(n: int) -> Path:
    """Return the cache file path for a given n (zero-padded to 4 digits)."""
    return COMMANDS_DIR / f"{n:04d}.json"


def save(doc: dict) -> Path:
    """Write a construction document to the cache; returns the file path."""
    COMMANDS_DIR.mkdir(parents=True, exist_ok=True)
    path = path_for(doc["n"])
    with path.open("w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    return path


def load(n: int) -> dict | None:
    """Load a cached construction document for n, or None if absent."""
    path = path_for(n)
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def cached_ns() -> list[int]:
    """List the n values currently present in the cache, sorted."""
    if not COMMANDS_DIR.exists():
        return []
    out = []
    for p in COMMANDS_DIR.glob("*.json"):
        try:
            out.append(int(p.stem))
        except ValueError:
            continue
    return sorted(out)

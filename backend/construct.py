"""Top-level entry: turn an integer ``n`` into a construction document.

Constructibility is decided by :mod:`backend.constructible`; the construction stream for
every constructible n is assembled by :mod:`backend.compose` (Fermat-prime Carlyle chains,
arc bisection for factors of 2, and Bezout arc-combination for distinct prime products).
"""

from __future__ import annotations

import math

from . import compose
from .constructible import FERMAT_PRIME_SET, analyze
from .dsl import non_constructible_doc


def can_plot(n: int) -> bool:
    """Whether a regular n-gon can be drawn (i.e. is straightedge-compass constructible).

    Only documents for which this is True are worth caching to disk.
    """
    return analyze(n).constructible


def build(n: int) -> dict:
    """Build the construction document for the regular n-gon."""
    info = analyze(n)
    if not info.constructible:
        return non_constructible_doc(info)

    doc = compose.build_polygon(n).to_doc()
    doc["supported"] = True
    doc["reason"] = info.reason
    return doc


def validate_doc(doc: dict, tol: float = 1e-6) -> tuple[bool, float]:
    """Check a supported document's polygon vertices against exp(2*pi*i*k/n).

    Returns ``(ok, max_error)``.  Vertices are emitted in order (V0..V_{n-1} at angle
    2*pi*k/n), so each is compared to its expected position in a single O(n) pass.
    """
    if not doc.get("supported") or not doc.get("commands"):
        return True, 0.0
    n = doc["n"]
    coords = {c["id"]: c["at"] for c in doc["commands"] if c["op"] == "point"}
    polys = [c for c in doc["commands"] if c["op"] == "polygon"]
    if not polys:
        return False, float("inf")
    verts = [coords[v] for v in polys[-1]["vertices"]]
    if len(verts) != n:
        return False, float("inf")
    max_err = 0.0
    for k, (vx, vy) in enumerate(verts):
        ix = math.cos(2 * math.pi * k / n)
        iy = math.sin(2 * math.pi * k / n)
        max_err = max(max_err, math.hypot(vx - ix, vy - iy))
    return max_err <= tol, max_err


__all__ = ["build", "can_plot", "validate_doc", "FERMAT_PRIME_SET"]

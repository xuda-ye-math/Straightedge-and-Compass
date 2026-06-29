"""Pure geometry primitives for straightedge-and-compass intersections.

All functions take and return plain ``(x, y)`` float tuples.  They model the only
loci an idealized straightedge and compass can produce (lines and circles) and the
three intersection kinds between them.  Selecting which of two intersection points to
keep is done with a small ``pick`` rule, most robustly ``("near", (x, y))`` which keeps
the candidate closest to a known target — the disambiguation a draughtsman makes by eye.
"""

from __future__ import annotations

import math

Point = tuple[float, float]

EPS = 1e-9


def _select(candidates: list[Point], pick) -> Point:
    """Choose one of up to two intersection candidates by a ``pick`` rule.

    ``pick`` is one of:
      ("near", (x, y)) -> the candidate nearest the target point;
      "pos_x"/"neg_x"/"pos_y"/"neg_y" -> extreme along an axis;
      0 / 1 -> raw index.
    """
    if not candidates:
        raise ValueError("no intersection")
    if isinstance(pick, tuple) and pick and pick[0] == "near":
        tx, ty = pick[1]
        return min(candidates, key=lambda c: (c[0] - tx) ** 2 + (c[1] - ty) ** 2)
    if pick == "pos_x":
        return max(candidates, key=lambda c: c[0])
    if pick == "neg_x":
        return min(candidates, key=lambda c: c[0])
    if pick == "pos_y":
        return max(candidates, key=lambda c: c[1])
    if pick == "neg_y":
        return min(candidates, key=lambda c: c[1])
    if isinstance(pick, int):
        return candidates[pick]
    raise ValueError(f"unknown pick rule: {pick!r}")


def line_line(p1: Point, p2: Point, q1: Point, q2: Point) -> list[Point]:
    """Intersection of line p1p2 with line q1q2 (0 or 1 point)."""
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = q1
    x4, y4 = q2
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < EPS:
        return []  # parallel or coincident
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    return [(x1 + t * (x2 - x1), y1 + t * (y2 - y1))]


def line_circle(p1: Point, p2: Point, center: Point, r: float) -> list[Point]:
    """Intersections of line p1p2 with circle (center, r), sorted by x then y."""
    cx, cy = center
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    fx, fy = p1[0] - cx, p1[1] - cy
    a = dx * dx + dy * dy
    b = 2 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - r * r
    disc = b * b - 4 * a * c
    if disc < -EPS or a < EPS:
        return []
    disc = max(disc, 0.0)
    sq = math.sqrt(disc)
    out = []
    for t in ((-b - sq) / (2 * a), (-b + sq) / (2 * a)):
        out.append((p1[0] + t * dx, p1[1] + t * dy))
    return sorted(set(out), key=lambda c: (c[0], c[1]))


def circle_circle(c1: Point, r1: float, c2: Point, r2: float) -> list[Point]:
    """Intersections of two circles, sorted by x then y (0, 1, or 2 points)."""
    x1, y1 = c1
    x2, y2 = c2
    dx, dy = x2 - x1, y2 - y1
    d = math.hypot(dx, dy)
    if d < EPS:
        return []  # concentric
    if d > r1 + r2 + EPS or d < abs(r1 - r2) - EPS:
        return []  # too far apart or one inside the other
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h2 = r1 * r1 - a * a
    h = math.sqrt(max(h2, 0.0))
    xm, ym = x1 + a * dx / d, y1 + a * dy / d
    rx, ry = -dy / d * h, dx / d * h
    out = [(xm + rx, ym + ry), (xm - rx, ym - ry)]
    return sorted(set(out), key=lambda c: (c[0], c[1]))


def carlyle_circle(s: float, q: float) -> tuple[Point, float]:
    """Center and radius of the Carlyle circle for ``x**2 - s*x + q = 0``.

    The circle has the segment from A=(0, 1) to B=(s, q) as a diameter, so its
    intersections with the x-axis are exactly the two roots of the quadratic.
    """
    center = (s / 2.0, (1.0 + q) / 2.0)
    radius = math.hypot(s - 0.0, q - 1.0) / 2.0
    return center, radius


def select(candidates: list[Point], pick) -> Point:
    """Public wrapper around the candidate-selection rule."""
    return _select(candidates, pick)

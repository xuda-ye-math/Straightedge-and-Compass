"""Drawing-command model and the construction builder.

A construction is an ordered stream of drawing **commands** plus a small metadata
header.  Each command is a JSON object describing one visible primitive (point, line,
circle, arc, polygon).  Every point carries a ``def`` recording its origin, one of:

* ``given`` — a free point (only the center O and the unit point);
* ``intersect`` — the intersection of two previously drawn loci (``of: [a, b]``);
* ``carlyle_endpoint`` — a Carlyle-circle diameter endpoint ``B=(s,q)``, an algebraically
  known constructible length placed directly;
* ``carlyle_center`` — a Carlyle circle's center, the midpoint of A and B (``of: [A, B]``).

No point is ever placed by raw angle; vertices and period points are intersections of
prior objects (their exact coordinates may be supplied via ``at`` while keeping the
intersection provenance), keeping the construction structurally honest.

The frontend renders this stream in real time; coordinates are precomputed floats so the
frontend does no geometry.  Each command also carries a Chinese ``desc`` for the side
panel, kept in one-to-one correspondence with the animation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from . import geometry as geo

SCHEMA_VERSION = 1


@dataclass
class Construction:
    """Accumulates drawing commands while tracking coordinates for intersections."""

    n: int
    meta: dict[str, Any] = field(default_factory=dict)

    commands: list[dict] = field(default_factory=list)
    # Geometry registry used to evaluate intersections; not serialized directly.
    _points: dict[str, geo.Point] = field(default_factory=dict)
    _loci: dict[str, tuple] = field(default_factory=dict)  # id -> ("line"/"circle", ...)
    _counters: dict[str, int] = field(default_factory=dict)

    # -- id allocation --------------------------------------------------------
    def _new_id(self, prefix: str) -> str:
        i = self._counters.get(prefix, 0)
        self._counters[prefix] = i + 1
        return f"{prefix}{i}"

    # -- points ---------------------------------------------------------------
    def given_point(self, x: float, y: float, label: str, role: str, desc: str) -> str:
        """Add one of the two free points (center or unit point)."""
        pid = self._new_id("P")
        self._points[pid] = (x, y)
        self.commands.append({
            "op": "point", "id": pid, "label": label, "at": [x, y],
            "def": {"type": "given", "role": role}, "desc": desc,
        })
        return pid

    def placed_point(self, x: float, y: float, label: str, defn: dict, desc: str) -> str:
        """Add a point at an exact, algebraically-known coordinate with provenance ``defn``.

        Used for points whose location is given by algebra rather than a float intersection:
        the Carlyle diameter endpoint ``B=(s,q)`` and a Carlyle circle's center (midpoint of
        A and B).  ``defn`` is the ``def`` object stored verbatim.
        """
        pid = self._new_id("P")
        self._points[pid] = (x, y)
        self.commands.append({
            "op": "point", "id": pid, "label": label, "at": [x, y], "def": defn, "desc": desc,
        })
        return pid

    def intersect(self, obj_a: str, obj_b: str, pick, label: str, desc: str,
                  at: tuple[float, float] | None = None) -> str:
        """Add a point defined as the intersection of two prior loci.

        ``at`` optionally supplies the exact coordinate of that intersection (used when
        it is known to higher precision than float geometry can recover, e.g. deep in
        the period tower).  The point's provenance is still recorded as the intersection.
        """
        if at is None:
            cands = self._intersection_candidates(obj_a, obj_b)
            x, y = geo.select(cands, pick)
        else:
            x, y = at
        pid = self._new_id("P")
        self._points[pid] = (x, y)
        self.commands.append({
            "op": "point", "id": pid, "label": label, "at": [x, y],
            "def": {"type": "intersect", "of": [obj_a, obj_b], "pick": _pick_json(pick)},
            "desc": desc,
        })
        return pid

    # -- lines & circles ------------------------------------------------------
    def line(self, p1: str, p2: str, desc: str, kind: str = "line") -> str:
        """Draw a straight line / ray / segment through two existing points."""
        lid = self._new_id("L")
        a, b = self._points[p1], self._points[p2]
        self._loci[lid] = ("line", a, b)
        self.commands.append({
            "op": "line", "id": lid, "p1": p1, "p2": p2, "kind": kind, "desc": desc,
        })
        return lid

    def circle_through(self, center: str, through: str, desc: str) -> str:
        """Compass circle centered at ``center`` passing through ``through``."""
        c, t = self._points[center], self._points[through]
        r = math.hypot(t[0] - c[0], t[1] - c[1])
        cid = self._new_id("C")
        self._loci[cid] = ("circle", c, r)
        self.commands.append({
            "op": "circle", "id": cid, "center": center,
            "radius": {"through": through}, "desc": desc,
        })
        return cid

    def circle_radius_seg(self, center: str, seg_a: str, seg_b: str, desc: str) -> str:
        """Compass circle centered at ``center`` with radius = |seg_a seg_b| (copied)."""
        c = self._points[center]
        a, b = self._points[seg_a], self._points[seg_b]
        r = math.hypot(b[0] - a[0], b[1] - a[1])
        cid = self._new_id("C")
        self._loci[cid] = ("circle", c, r)
        self.commands.append({
            "op": "circle", "id": cid, "center": center,
            "radius": {"segment": [seg_a, seg_b]}, "desc": desc,
        })
        return cid

    def note(self, refs: list[str], desc: str) -> str:
        """A compute/explanation step: draws no new object, but highlights the existing
        points in ``refs`` while ``desc`` explains a quantity (used to define s and q before
        a Carlyle circle is plotted)."""
        nid = self._new_id("N")
        self.commands.append({"op": "note", "id": nid, "refs": list(refs), "desc": desc})
        return nid

    def polygon(self, vertices: list[str], desc: str) -> str:
        """Highlight the final regular polygon through the given vertices."""
        gid = self._new_id("G")
        self.commands.append({
            "op": "polygon", "id": gid, "vertices": list(vertices), "desc": desc,
        })
        return gid

    # -- intersection evaluation ---------------------------------------------
    def _intersection_candidates(self, a: str, b: str) -> list[geo.Point]:
        la, lb = self._loci[a], self._loci[b]
        ka, kb = la[0], lb[0]
        if ka == "line" and kb == "line":
            return geo.line_line(la[1], la[2], lb[1], lb[2])
        if ka == "line" and kb == "circle":
            return geo.line_circle(la[1], la[2], lb[1], lb[2])
        if ka == "circle" and kb == "line":
            return geo.line_circle(lb[1], lb[2], la[1], la[2])
        if ka == "circle" and kb == "circle":
            return geo.circle_circle(la[1], la[2], lb[1], lb[2])
        raise ValueError(f"cannot intersect {ka} with {kb}")

    def point_xy(self, pid: str) -> geo.Point:
        """Coordinates of a previously added point."""
        return self._points[pid]

    # -- serialization --------------------------------------------------------
    def to_doc(self) -> dict:
        """Assemble the full JSON-serializable construction document."""
        doc = {
            "schema_version": SCHEMA_VERSION,
            "n": self.n,
            "constructible": True,
            "num_steps": len(self.commands),
            "commands": self.commands,
        }
        doc.update(self.meta)
        return doc


def _pick_json(pick) -> Any:
    """Make a pick rule JSON-serializable (round the 'near' target)."""
    if isinstance(pick, tuple) and pick and pick[0] == "near":
        x, y = pick[1]
        return {"near": [round(x, 6), round(y, 6)]}
    return pick


def non_constructible_doc(analysis) -> dict:
    """Document returned for an n whose regular polygon is not constructible."""
    return {
        "schema_version": SCHEMA_VERSION,
        "n": analysis.n,
        "constructible": False,
        "reason": analysis.reason,
        "factorization": {str(k): v for k, v in analysis.factorization.items()},
        "commands": [],
    }

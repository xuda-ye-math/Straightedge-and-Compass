"""Scene setup and reusable construction primitives for the unit-circle constructions.

This module holds the low-level, reusable pieces shared by every construction:

  * :func:`setup_scene` draws the starting circle and the two coordinate axes;
  * :func:`carlyle_two_cos` runs a Fermat prime's Carlyle-circle chain to build the
    length ``2*cos(2*pi/p)`` on the x-axis;
  * :func:`vertex_at_cos` turns such a length into the corresponding vertex on the circle;
  * :func:`chord_step` walks a known side-length around the circle to reach every vertex.

The recursive vertex builder and the full per-n polygon assembly live in
:mod:`backend.compose`; :func:`build_prime` is kept as a thin wrapper for the prime case.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from . import geometry as geo
from .dsl import Construction
from .periods import build_tower, q_decomposition

# Above this loop length, emit flushed progress so large-n builds are never opaque.
_PROGRESS_THRESHOLD = 8000


def _progress(tag: str, i: int, total: int, t0: float) -> None:
    if total > _PROGRESS_THRESHOLD and (i % 4000 == 0 or i == total):
        print(f"    [{tag}] {i}/{total}  ({time.perf_counter() - t0:.1f}s)", flush=True)


@dataclass
class Scene:
    """Ids of the base objects shared by a construction (the starting circle and axes)."""

    O: str          # center (0, 0)
    V0: str         # unit point / first vertex (1, 0)
    W: str          # (-1, 0) = 2*cos(2*pi/2); also the level-0 period P_0 = -1
    omega: str      # the unit circle (circumscribed)
    x_axis: str     # horizontal axis through O, V0
    y_axis: str     # vertical axis through O
    A: str          # (0, 1) top of the circle, apex of every Carlyle circle


def setup_scene(con: Construction) -> Scene:
    """Draw the starting unit circle, both axes, and the points W=(-1,0) and A=(0,1)."""
    O = con.given_point(0.0, 0.0, "O", "center", "取圆心 O")
    V0 = con.given_point(1.0, 0.0, "V0", "unit", "取单位点 V0=(1,0)，作为第一个顶点")
    omega = con.circle_through(O, V0, "作外接圆（单位圆），所有顶点都在其上")
    x_axis = con.line(O, V0, "作过 O、V0 的水平轴")
    W = con.intersect(omega, x_axis, ("near", (-1.0, 0.0)), "W", "圆与水平轴的左交点 (-1,0)")

    cR = con.circle_through(V0, W, "以 V0 为心、过 W 作辅助圆")
    cL = con.circle_through(W, V0, "以 W 为心、过 V0 作辅助圆")
    tTop = con.intersect(cR, cL, "pos_y", "Ty", "两辅助圆上交点")
    tBot = con.intersect(cR, cL, "neg_y", "Ty'", "两辅助圆下交点")
    y_axis = con.line(tTop, tBot, "连得竖直轴（过 O 且垂直于水平轴）")
    A = con.intersect(y_axis, omega, ("near", (0.0, 1.0)), "A", "竖直轴与圆的上交点 A=(0,1)")
    return Scene(O=O, V0=V0, W=W, omega=omega, x_axis=x_axis, y_axis=y_axis, A=A)


def midpoint(con: Construction, pa: str, pb: str, label: str, desc: str) -> str:
    """Construct the midpoint of segment pa-pb via its perpendicular bisector."""
    ax, ay = con.point_xy(pa)
    bx, by = con.point_xy(pb)
    ca = con.circle_through(pa, pb, "作辅助圆：以一端点为心、过另一端点")
    cb = con.circle_through(pb, pa, "作辅助圆：以另一端点为心、过前一端点")
    t1 = con.intersect(ca, cb, 0, f"{label}T1", "两辅助圆的交点之一")
    t2 = con.intersect(ca, cb, 1, f"{label}T2", "两辅助圆的另一交点")
    bis = con.line(t1, t2, "连接两交点得垂直平分线")
    seg = con.line(pa, pb, "连接两端点得线段")
    return con.intersect(bis, seg, ("near", ((ax + bx) / 2, (ay + by) / 2)),
                         label, "垂直平分线与线段的交点即中点")


def erect_perpendicular(con: Construction, foot: str, axis: str, other_on_axis: str,
                        desc: str) -> str:
    """Erect the perpendicular to ``axis`` at point ``foot`` (which lies on ``axis``)."""
    fx, fy = con.point_xy(foot)
    ref = con.circle_through(foot, other_on_axis, "以垂足为心、过参考点作圆")
    ox, oy = con.point_xy(other_on_axis)
    mirror = con.intersect(ref, axis, ("near", (2 * fx - ox, 2 * fy - oy)),
                           "M", "该圆与轴的另一交点（关于垂足对称）")
    c1 = con.circle_through(other_on_axis, mirror, "作等半径辅助圆（圆心：参考点）")
    c2 = con.circle_through(mirror, other_on_axis, "作等半径辅助圆（圆心：对称点）")
    u1 = con.intersect(c1, c2, "pos_y", "U1", "两辅助圆交点（上）")
    u2 = con.intersect(c1, c2, "neg_y", "U2", "两辅助圆交点（下）")
    return con.line(u1, u2, desc)


def carlyle_two_cos(con: Construction, scene: Scene, p: int) -> str:
    """Run the period tower's Carlyle circles; return the point at (2*cos(2*pi/p), 0)."""
    tower = build_tower(p)
    pt_node: dict[tuple[int, int], str] = {(0, 0): scene.W}  # P_0 = -1 sits at W=(-1,0)
    t0 = time.perf_counter()
    total = len(tower.steps)
    for k, st in enumerate(tower.steps):
        _progress("carlyle", k, total, t0)
        # The Carlyle circle has the segment A=(0,1) -- B=(s,q) as a diameter; its two
        # x-axis crossings are the roots of x^2 - s*x + q (the two child periods).  We
        # show the diameter explicitly so the center reads as its midpoint.
        parent_pt = pt_node[st.parent]   # a point already marked on the x-axis, at (s, 0)
        (cx, cy), _ = geo.carlyle_circle(st.s, st.q)   # Carlyle center = midpoint of A and B

        # --- compute s and q explicitly from points already on the axis ----------------
        con.note([parent_pt], f"计算 s = 高亮点的横坐标 = {st.s:.4g}。")
        decomp = q_decomposition(tower, st)
        if decomp is None:                       # too large to expand cheaply
            con.note([], f"计算 q = {st.q:.4g}（前面横轴上若干已作点横坐标的整数倍之和）。")
            q_refs: list[str] = []
        elif st.level == 1:
            con.note([parent_pt], f"计算 q = −(p−1)/4 = {st.q:.0f}。")
            q_refs = [parent_pt]
        else:
            _, terms = decomp
            q_refs = [pt_node[node] for node, _ in terms]
            parts = " + ".join(
                f"{m}×(≈{tower.value[node]:.4g} 处的点)" for node, m in terms)
            con.note(q_refs, f"计算 q = {parts} = {st.q:.4g}。")

        # --- plot B, the diameter, the center, the circle, the two new points -----------
        b = con.placed_point(
            st.s, st.q, f"B{k}",
            {"type": "carlyle_endpoint", "of": [parent_pt, *q_refs],
             "parent": list(st.parent), "s": st.s, "q": st.q},
            f"标出 B=({st.s:.4g},{st.q:.4g})。",
        )
        con.line(scene.A, b, "连接 A=(0,1) 与 B，作直径。", kind="segment")
        center = con.placed_point(
            cx, cy, f"K{k}",
            {"type": "carlyle_center", "of": [scene.A, b],
             "parent": list(st.parent), "s": st.s, "q": st.q},
            f"圆心 K = 直径 AB 中点 = ({cx:.4g},{cy:.4g})。",
        )
        circ = con.circle_through(
            center, scene.A,
            f"以 K 为圆心、过 A 作圆；与水平轴交于 x²−({st.s:.4g})x+({st.q:.4g})=0 的两根。",
        )
        lo = con.intersect(circ, scene.x_axis, ("near", (st.root_lo, 0.0)),
                           f"p{st.child_lo[0]}_{st.child_lo[1]}",
                           f"左交点 ≈ {st.root_lo:.4g}。", at=(st.root_lo, 0.0))
        hi = con.intersect(circ, scene.x_axis, ("near", (st.root_hi, 0.0)),
                           f"p{st.child_hi[0]}_{st.child_hi[1]}",
                           f"右交点 ≈ {st.root_hi:.4g}。", at=(st.root_hi, 0.0))
        pt_node[st.child_lo] = lo
        pt_node[st.child_hi] = hi
    _progress("carlyle", total, total, t0)
    return pt_node[tower.cos_node]


def vertex_at_cos(con: Construction, scene: Scene, two_cos_pt: str, n: int,
                  label: str) -> str:
    """From a point at (2*cos(2*pi/n), 0), construct the vertex at angle 2*pi/n.

    The vertex coordinate is taken from the *constructed* cosine (the period-tower
    output, accurate to working precision), keeping the deep-tower float error out of
    the final vertex while leaving the genuine perpendicular-intersection provenance.
    """
    cos_v = con.point_xy(two_cos_pt)[0] / 2.0     # = cos(2*pi/n), from the construction
    sin_v = math.sqrt(max(1.0 - cos_v * cos_v, 0.0))
    X = midpoint(con, scene.O, two_cos_pt, f"{label}x",
                 "取 O 与该点的中点，得 (cos(2π/n),0)")
    perp = erect_perpendicular(con, X, scene.x_axis, scene.O, "在该处作水平轴的垂线")
    return con.intersect(perp, scene.omega, ("near", (cos_v, sin_v)),
                         label, f"垂线与圆的上交点，即角 2π/{n} 处的顶点", at=(cos_v, sin_v))


def chord_step(con: Construction, scene: Scene, vertices: list[str], n: int) -> None:
    """Given vertices[0]=V0 and vertices[1]=V1, step the side V0V1 around to all n vertices."""
    V0, V1 = vertices[0], vertices[1]
    prev = V1
    t0 = time.perf_counter()
    for k in range(2, n):
        _progress("chord-step", k, n, t0)
        ang = 2 * math.pi * k / n
        target = (math.cos(ang), math.sin(ang))
        step_circle = con.circle_radius_seg(prev, V0, V1,
                                            f"以 V{k - 1} 为心、以边长 V0V1 为半径作圆")
        vk = con.intersect(step_circle, scene.omega, ("near", target),
                           f"V{k}", f"沿圆周量取等弦，得顶点 V{k}")
        vertices.append(vk)
        prev = vk
    _progress("chord-step", n, n, t0)


def build_prime(p: int) -> Construction:
    """Delegate to :func:`backend.compose.build_polygon`; convenience entry point for the
    Fermat-prime case (used by the tests)."""
    from .compose import build_polygon  # late import avoids a circular dependency
    return build_polygon(p)

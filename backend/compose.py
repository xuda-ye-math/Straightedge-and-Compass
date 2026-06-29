"""Compose prime building blocks into the full construction for any constructible n.

The whole problem reduces to constructing a single vertex at angle ``2*pi/n`` on the unit
circle; once that vertex exists, stepping its chord around the circle
(:func:`backend.blocks.chord_step`) reaches every vertex.  :func:`construct_vertex` builds
that one vertex recursively:

  * **Fermat prime p** — run the Carlyle-circle chain to get ``2*cos(2*pi/p)`` and erect the
    vertex (:mod:`backend.blocks`).
  * **even n = 2*m** — build the vertex at ``2*pi/m`` and bisect the arc from V0 to it,
    halving the angle to ``2*pi/n``.
  * **odd composite n = p*b** (p the least prime factor, gcd(p, b) = 1) — Bezout gives
    integers ``u, v`` with ``u*p + v*b = 1``, hence ``2*pi/n = u*(2*pi/b) + v*(2*pi/p)``;
    walk ``u`` steps of the b-gon chord and ``v`` steps of the p-gon chord from V0.
"""

from __future__ import annotations

import math

from . import blocks
from .constructible import FERMAT_PRIME_SET, analyze
from .dsl import Construction


def _egcd(a: int, b: int) -> tuple[int, int, int]:
    """Extended Euclid: return (g, x, y) with a*x + b*y = g = gcd(a, b)."""
    if b == 0:
        return a, 1, 0
    g, x1, y1 = _egcd(b, a % b)
    return g, y1, x1 - (a // b) * y1


def _least_odd_prime_factor(n: int) -> int:
    d = 3
    while d * d <= n:
        if n % d == 0:
            return d
        d += 2
    return n


def _bisect_arc(con: Construction, scene: blocks.Scene, pa: str, pb: str,
                target_angle: float, label: str) -> str:
    """Construct the midpoint of the arc from ``pa`` to ``pb`` nearest ``target_angle``."""
    ca = con.circle_through(pa, pb, "作弦的等半径辅助圆（圆心 A）")
    cb = con.circle_through(pb, pa, "作弦的等半径辅助圆（圆心 B）")
    t1 = con.intersect(ca, cb, 0, f"{label}T1", "两辅助圆交点之一")
    t2 = con.intersect(ca, cb, 1, f"{label}T2", "两辅助圆另一交点")
    diam = con.line(t1, t2, "连得弦的垂直平分线（过圆心的直径）")
    target = (math.cos(target_angle), math.sin(target_angle))
    return con.intersect(diam, scene.omega, ("near", target), label,
                         "垂直平分线与圆的交点即弧中点（角度二等分）")


def _walk(con: Construction, scene: blocks.Scene, cur: str, cur_angle: float,
          seg_a: str, seg_b: str, arc: float, count: int) -> tuple[str, float]:
    """Step ``count`` times (sign = direction) by the chord seg_a-seg_b (arc width ``arc``)."""
    sign = 1 if count >= 0 else -1
    for _ in range(abs(count)):
        cur_angle += sign * arc
        target = (math.cos(cur_angle), math.sin(cur_angle))
        circ = con.circle_radius_seg(cur, seg_a, seg_b, "以当前点为心、以子多边形边长为半径作圆")
        cur = con.intersect(circ, scene.omega, ("near", target), "S",
                            "圆与外接圆的交点：沿圆周转过一个子多边形的弧")
    return cur, cur_angle


def construct_vertex(con: Construction, scene: blocks.Scene, n: int) -> str:
    """Construct and return the point at angle 2*pi/n on the unit circle."""
    if n == 1:
        return scene.V0                      # angle 0
    if n == 2:
        return scene.W                       # angle pi -> (-1, 0)
    if n in FERMAT_PRIME_SET:
        two_cos = blocks.carlyle_two_cos(con, scene, n)
        return blocks.vertex_at_cos(con, scene, two_cos, n, f"P[2π/{n}]")
    if n % 2 == 0:
        m = n // 2
        vm = construct_vertex(con, scene, m)  # vertex at 2*pi/m
        return _bisect_arc(con, scene, scene.V0, vm, 2 * math.pi / n, f"P[2π/{n}]")

    # odd composite: n = p * b with p the least prime factor and gcd(p, b) = 1
    p = _least_odd_prime_factor(n)
    b = n // p
    vp = construct_vertex(con, scene, p)      # vertex at 2*pi/p
    vb = construct_vertex(con, scene, b)      # vertex at 2*pi/b
    g, u, v = _egcd(p, b)                      # u*p + v*b = 1
    assert g == 1, (n, p, b)
    # 2*pi/n = u*(2*pi/b) + v*(2*pi/p)
    cur, ang = scene.V0, 0.0
    cur, ang = _walk(con, scene, cur, ang, scene.V0, vb, 2 * math.pi / b, u)
    cur, ang = _walk(con, scene, cur, ang, scene.V0, vp, 2 * math.pi / p, v)
    return cur


def build_polygon(n: int) -> Construction:
    """Build the full SC construction for any constructible regular n-gon (n >= 3)."""
    info = analyze(n)
    if not info.constructible:
        raise ValueError(f"regular {n}-gon is not constructible")
    con = Construction(n=n, meta={
        "factorization": {str(k): v for k, v in info.factorization.items()},
        "fermat_primes": info.fermat_primes,
        "power_of_two": info.power_of_two,
        "view": {"cx": 0.0, "cy": 0.0, "scale": 1.0},
    })

    if n <= 2:   # degenerate cases, drawn directly
        o = con.given_point(0.0, 0.0, "O", "center", "取圆心 O")
        v0 = con.given_point(1.0, 0.0, "V0", "unit", "取点 V0=(1,0)")
        omega = con.circle_through(o, v0, "作单位圆")
        if n == 1:
            con.polygon([v0], "正 1 边形即单个点 (1,0)")
        else:
            x_axis = con.line(o, v0, "作水平轴")
            v1 = con.intersect(omega, x_axis, ("near", (-1.0, 0.0)), "V1",
                               "圆与水平轴的另一交点 (−1,0)")
            con.polygon([v0, v1], "正 2 边形即直径，两端点 (1,0) 与 (−1,0)")
        return con

    scene = blocks.setup_scene(con)
    v1 = construct_vertex(con, scene, n)
    vertices = [scene.V0, v1]
    blocks.chord_step(con, scene, vertices, n)
    con.polygon(vertices, f"依次连接 {n} 个顶点，得正 {n} 边形")
    return con

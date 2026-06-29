"""Gaussian period tower for a Fermat prime, realized with Carlyle circles.

For a Fermat prime ``p`` we have ``p - 1 = 2**m``.  Let ``M = (p - 1) // 2`` and let
``g`` be a primitive root mod ``p``.  Order the residues as ``r_k = g**k mod p``.
Because ``g**M == -1 (mod p)``, the values

    c_k = 2 * cos(2*pi * r_k / p),   k = 0 .. M-1

are the ``M`` distinct "doubled cosines"; note ``c_0 = 2*cos(2*pi/p)`` (since r_0 = 1).

We build a binary tree of *real* periods.  At level ``r`` (0 <= r <= m-1) the index
set ``{0..M-1}`` is partitioned by ``k mod 2**r`` into ``2**r`` classes; the period of
class ``j`` is

    P_r(j) = sum( c_k : k == j (mod 2**r) ).

Level 0 is the single period ``P_0 = -1`` (sum of all doubled cosines).  Level ``m-1``
has ``M`` singleton periods, and ``P_{m-1}(0) = c_0 = 2*cos(2*pi/p)``.

A parent ``P_{r-1}(i)`` has exactly two children, ``P_r(i)`` and ``P_r(i + 2**(r-1))``,
whose sum is the parent and whose product ``q`` reduces (classical period algebra) to a
constructible length.  The two children are therefore the roots of

    x**2 - P_{r-1}(i) * x + q = 0,

which a single Carlyle circle solves: the circle on the diameter from (0, 1) to
(P_{r-1}(i), q) meets the x-axis exactly at the two roots.  Chaining these circles from
level 1 down to level m-1 constructs ``2*cos(2*pi/p)`` from rational data alone.
"""

from __future__ import annotations

from dataclasses import dataclass

import mpmath as mp
from sympy.ntheory.residue_ntheory import primitive_root

# Working precision (decimal digits) used locally while evaluating the tower; comfortably
# exact for p up to 257 and well below any drawable tolerance.  Applied via mp.workdps so
# the caller's global mpmath precision is left untouched.
_WORKING_DPS = 60


@dataclass(frozen=True)
class CarlyleStep:
    """One quadratic ``x**2 - s*x + q = 0`` solved by a Carlyle circle.

    ``parent`` / ``child_lo`` / ``child_hi`` are node ids ``(level, class_index)``.
    ``s`` is the parent period (sum of the two children); ``q`` is their product.
    ``root_lo <= root_hi`` are the two roots; ``child_lo`` is the node whose period
    equals ``root_lo`` and ``child_hi`` the one equal to ``root_hi``.
    """

    level: int
    parent: tuple[int, int]
    child_lo: tuple[int, int]
    child_hi: tuple[int, int]
    s: float
    q: float
    root_lo: float
    root_hi: float


@dataclass
class PeriodTower:
    """The full period tree and Carlyle step sequence for a Fermat prime ``p``."""

    p: int
    m: int                              # p - 1 == 2**m
    M: int                              # (p - 1) // 2 == 2**(m-1)
    g: int                              # primitive root used
    residues: list[int]                 # r_k = g**k mod p, k = 0..M-1
    value: dict[tuple[int, int], float] # node id -> numeric period value
    steps: list[CarlyleStep]            # ordered Carlyle circles (level 1 .. m-1)
    dlog: list[int]                     # dlog[v] = e with g**e == v (mod p); v=0 unused

    @property
    def cos_node(self) -> tuple[int, int]:
        """Node id whose period equals ``2*cos(2*pi/p)`` (the bottom-level r_0=1 class)."""
        return (self.m - 1, 0)

    @property
    def two_cos(self) -> float:
        """``2 * cos(2*pi / p)``."""
        return self.value[self.cos_node]


def _ilog2(x: int) -> int:
    """Exact integer log2 of a power of two (raises if x is not a power of two)."""
    b = x.bit_length() - 1
    if 1 << b != x:
        raise ValueError(f"{x} is not a power of two")
    return b


def build_tower(p: int) -> PeriodTower:
    """Build the Gaussian-period tower and Carlyle steps for Fermat prime ``p``."""
    if p == 2:
        raise ValueError("p must be an odd Fermat prime")
    m = _ilog2(p - 1)               # p - 1 = 2**m
    M = (p - 1) // 2                # = 2**(m-1)
    g = int(primitive_root(p))

    residues = [pow(g, k, p) for k in range(M)]
    with mp.workdps(_WORKING_DPS):
        cos_val = [2 * mp.cos(2 * mp.pi * r / p) for r in residues]  # c_k

        # Numeric value of every node P_r(j) = sum of c_k over class k == j (mod 2**r).
        # Bucket by residue class in one O(M) pass per level (not O(M^2)), so the
        # 65537-gon (M = 32768, 16 levels) stays fast.
        value: dict[tuple[int, int], float] = {}
        for r in range(m):          # levels 0 .. m-1
            mod = 1 << r
            acc = [mp.mpf(0)] * mod
            for k in range(M):
                acc[k % mod] += cos_val[k]
            for j in range(mod):
                value[(r, j)] = float(acc[j])

    # Carlyle steps: for each parent at level r-1, split into its two level-r children.
    steps: list[CarlyleStep] = []
    for r in range(1, m):           # levels 1 .. m-1
        half = 1 << (r - 1)
        for i in range(half):       # parents at level r-1
            lo_node = (r, i)
            hi_node = (r, i + half)
            s = value[(r - 1, i)]                       # parent = sum of children
            v_lo, v_hi = value[lo_node], value[hi_node]
            q = v_lo * v_hi                             # product of children
            # The two children ARE the roots of x^2 - s*x + q; use their accurately
            # summed period values directly instead of re-deriving them through a
            # cancellation-prone sqrt (critical for the 16-level p=65537 tower).
            if v_lo <= v_hi:
                root_lo, root_hi, clo, chi = v_lo, v_hi, lo_node, hi_node
            else:
                root_lo, root_hi, clo, chi = v_hi, v_lo, hi_node, lo_node
            steps.append(
                CarlyleStep(
                    level=r,
                    parent=(r - 1, i),
                    child_lo=clo,
                    child_hi=chi,
                    s=s,
                    q=q,
                    root_lo=root_lo,
                    root_hi=root_hi,
                )
            )

    dlog = [0] * p              # dlog[g**e mod p] = e, built once (O(p))
    cur = 1
    for e in range(p - 1):
        dlog[cur] = e
        cur = cur * g % p

    return PeriodTower(
        p=p, m=m, M=M, g=g, residues=residues, value=value, steps=steps, dlog=dlog,
    )


def q_decomposition(tower: PeriodTower, step: CarlyleStep,
                    max_child_cosines: int = 512):
    """Exact integer decomposition of a Carlyle step's constant term ``q``.

    Returns ``(const, terms)`` with ``terms = [(node_id, coeff), ...]`` (integer ``coeff``,
    ``node_id`` a level-(r-1) period node already marked on the x-axis) satisfying
    ``q == const + sum(coeff * tower.value[node_id])``.  For this tower ``const`` is always
    0 and every ``coeff`` is a non-negative integer.  Returns ``None`` when the step's child
    classes are too large to expand cheaply (caller falls back to stating q numerically).

    Derivation: q is the product of the two sibling periods; expanding the cosine sums via
    2cos(a)2cos(b) = 2cos(a+b)+2cos(a-b) and regrouping by the parent-level class gives the
    coefficients.  ``g**(M)`` swaps the two children and fixes their product, so the result
    lives in the level-(r-1) field — hence the regrouping is exact with integer counts.
    """
    p, M, r = tower.p, tower.M, step.level
    if r == 1:                                   # closed form (also the costliest level)
        return 0, [((0, 0), (p - 1) // 4)]       # q = ((p-1)/4) * P_0 = -(p-1)/4
    child = M >> r                               # cosines in each child class
    if child > max_child_cosines:
        return None                              # too expensive -> caller falls back
    mod_r = 1 << r
    mod_prev = 1 << (r - 1)
    res, dlog = tower.residues, tower.dlog
    # class j at level r is residues[j], residues[j+2^r], ... -> stride, not a full scan
    a_res = res[step.child_lo[1]:M:mod_r]
    b_res = res[step.child_hi[1]:M:mod_r]
    cnt: dict[int, int] = {}                     # c-index (mod M) -> multiplicity
    const = 0
    for ra in a_res:
        for rb in b_res:
            for t in ((ra + rb) % p, (ra - rb) % p):
                if t == 0:
                    const += 2                   # provably never occurs for sibling products
                else:
                    k = dlog[t] % M              # 2cos is even -> c-index mod M
                    cnt[k] = cnt.get(k, 0) + 1
    # regroup the touched c-indices into parent-level classes (counts within a class are
    # provably equal, so one representative per class suffices)
    cls: dict[int, int] = {}
    for k, c in cnt.items():
        j = k % mod_prev
        assert cls.get(j, c) == c, "period-algebra regularity violated"
        cls[j] = c
    terms = sorted(((r - 1, j), c) for j, c in cls.items())
    return const, terms

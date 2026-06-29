"""Standalone tests for the backend modules (stdlib unittest, no pytest needed).

Run with the project venv:
    .venv/bin/python -m unittest discover -s tests -v
Each test exercises one module independently so failures localize cleanly.
"""

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import geometry as geo  # noqa: E402
from backend.blocks import build_prime  # noqa: E402
from backend.constructible import FERMAT_PRIMES, analyze, factorize  # noqa: E402
from backend.construct import build, validate_doc  # noqa: E402
from backend.periods import build_tower  # noqa: E402


class TestConstructible(unittest.TestCase):
    def test_factorize(self):
        self.assertEqual(factorize(60), {2: 2, 3: 1, 5: 1})
        self.assertEqual(factorize(65537), {65537: 1})

    def test_known_constructible(self):
        for n in [3, 4, 5, 6, 8, 10, 12, 15, 16, 17, 20, 34, 51, 257, 65535]:
            self.assertTrue(analyze(n).constructible, n)

    def test_known_non_constructible(self):
        for n in [7, 9, 11, 13, 14, 18, 25, 49]:
            self.assertFalse(analyze(n).constructible, n)

    def test_degenerate(self):
        # n=1 (single point) and n=2 (diameter) are supported degenerate cases
        self.assertTrue(analyze(1).constructible)
        self.assertTrue(analyze(2).constructible)
        for n in [1, 2]:
            ok, err = validate_doc(build(n))
            self.assertTrue(ok, (n, err))


class TestGeometry(unittest.TestCase):
    def test_line_line(self):
        p = geo.line_line((0, 0), (2, 2), (0, 2), (2, 0))
        self.assertEqual(len(p), 1)
        self.assertAlmostEqual(p[0][0], 1.0)
        self.assertAlmostEqual(p[0][1], 1.0)

    def test_circle_circle(self):
        pts = geo.circle_circle((0, 0), 1.0, (1, 0), 1.0)
        self.assertEqual(len(pts), 2)
        for x, y in pts:
            self.assertAlmostEqual(x, 0.5)

    def test_carlyle(self):
        # x^2 - 3x + 2 = 0 -> roots 1, 2 on the x-axis
        center, r = geo.carlyle_circle(3.0, 2.0)
        roots = geo.line_circle((0, 0), (1, 0), center, r)
        xs = sorted(round(p[0], 9) for p in roots)
        self.assertEqual(xs, [1.0, 2.0])


class TestPeriods(unittest.TestCase):
    def test_two_cos(self):
        for p in [3, 5, 17, 257]:
            t = build_tower(p)
            self.assertAlmostEqual(t.two_cos, 2 * math.cos(2 * math.pi / p), places=10)
            self.assertAlmostEqual(t.value[(0, 0)], -1.0, places=10)

    def test_steps_solve_quadratic(self):
        t = build_tower(17)
        for st in t.steps:
            for x in (st.root_lo, st.root_hi):
                self.assertAlmostEqual(x * x - st.s * x + st.q, 0.0, places=8)

    def test_reject_two(self):
        with self.assertRaises(ValueError):
            build_tower(2)


class TestBlocksAndConstruct(unittest.TestCase):
    def test_prime_vertices_exact(self):
        for p in [3, 5, 17, 257]:
            doc = build_prime(p).to_doc()
            doc["supported"] = True
            ok, err = validate_doc(doc)
            self.assertTrue(ok, (p, err))
            self.assertLess(err, 1e-6, (p, err))

    def test_structural_purity(self):
        doc = build_prime(17).to_doc()
        seen = set()
        for c in doc["commands"]:
            if c["op"] == "point" and c["def"]["type"] == "intersect":
                for ref in c["def"]["of"]:
                    self.assertIn(ref, seen, ("dangling ref", ref))
            seen.add(c.get("id"))

    def test_build_dispatch(self):
        self.assertTrue(build(17)["supported"])              # odd prime
        self.assertFalse(build(7)["constructible"])          # non-constructible
        self.assertTrue(build(15)["supported"])              # composite odd via Bezout
        self.assertTrue(build(16)["supported"])              # power of two via bisection

    def test_composite_and_even_vertices(self):
        for n in [4, 6, 8, 12, 15, 16, 30, 51, 60, 85, 120, 255]:
            ok, err = validate_doc(build(n))
            self.assertTrue(ok, (n, err))


if __name__ == "__main__":
    unittest.main()

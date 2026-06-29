"""Constructibility test for the regular n-gon (Gauss-Wantzel theorem).

A regular n-gon is straightedge-and-compass constructible iff

    n = 2^k * (product of DISTINCT Fermat primes)

where the only known Fermat primes are {3, 5, 17, 257, 65537}.  A polygon needs
n >= 3; n in {1, 2} is degenerate and reported as non-constructible-as-a-polygon.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The five known Fermat primes (2^(2^t) + 1 for t = 0..4).
FERMAT_PRIMES = (3, 5, 17, 257, 65537)
FERMAT_PRIME_SET = frozenset(FERMAT_PRIMES)


def factorize(n: int) -> dict[int, int]:
    """Return the prime factorization of n >= 1 as {prime: exponent}."""
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    factors: dict[int, int] = {}
    m = n
    d = 2
    while d * d <= m:
        while m % d == 0:
            factors[d] = factors.get(d, 0) + 1
            m //= d
        d += 1 if d == 2 else 2
    if m > 1:
        factors[m] = factors.get(m, 0) + 1
    return factors


@dataclass
class Constructibility:
    """Result of the constructibility analysis for a given n."""

    n: int
    constructible: bool
    factorization: dict[int, int]
    power_of_two: int = 0            # exponent k in the 2^k factor
    fermat_primes: list[int] = field(default_factory=list)  # distinct odd primes used
    reason: str = ""                 # human-readable reason (Chinese), set when relevant

    @property
    def odd_part(self) -> int:
        """The odd part of n (n with all factors of 2 removed)."""
        return self.n >> self.power_of_two


def analyze(n: int) -> Constructibility:
    """Analyze whether the regular n-gon is SC-constructible."""
    if n < 1:
        raise ValueError(f"n must be a positive integer, got {n}")

    factors = factorize(n)
    power_of_two = factors.get(2, 0)

    if n <= 2:   # degenerate: n=1 is the single point (1,0); n=2 is the diameter
        return Constructibility(
            n=n,
            constructible=True,
            factorization=factors,
            power_of_two=power_of_two,
            reason="可用尺规作图（退化情形）。",
        )

    odd_factors = {p: e for p, e in factors.items() if p != 2}

    # Each odd prime must be a Fermat prime and appear at most once.
    bad_primes = [p for p in odd_factors if p not in FERMAT_PRIME_SET]
    repeated = [p for p, e in odd_factors.items() if e > 1]

    if bad_primes:
        worst = min(bad_primes)
        return Constructibility(
            n=n,
            constructible=False,
            factorization=factors,
            power_of_two=power_of_two,
            reason=f"n 含有非费马素数因子 {worst}，故正 {n} 边形不可用尺规作图。",
        )
    if repeated:
        p = min(repeated)
        return Constructibility(
            n=n,
            constructible=False,
            factorization=factors,
            power_of_two=power_of_two,
            reason=f"费马素数 {p} 在分解中出现了 {odd_factors[p]} 次（需互不相同），"
            f"故正 {n} 边形不可用尺规作图。",
        )

    return Constructibility(
        n=n,
        constructible=True,
        factorization=factors,
        power_of_two=power_of_two,
        fermat_primes=sorted(odd_factors),
        reason="可用尺规作图。",
    )


def is_constructible(n: int) -> bool:
    """Convenience boolean wrapper around :func:`analyze`."""
    return analyze(n).constructible

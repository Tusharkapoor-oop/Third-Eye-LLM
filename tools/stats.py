"""Reporter-side statistics: Wilson intervals and a seeded bootstrap.

Every interval in the report is computed here from raw per-case rows. The seed is
fixed so a rebuild is byte-identical.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence

SEED = 20261101


def wilson(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def percentile(values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile, q in [0, 100]."""
    if not values:
        return float("nan")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    pos = (len(ordered) - 1) * q / 100.0
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return float(ordered[lo])
    frac = pos - lo
    return float(ordered[lo] * (1 - frac) + ordered[hi] * frac)


def mean(values: Sequence[float]) -> float:
    return float(sum(values) / len(values)) if values else float("nan")


def bootstrap_ci(
    values: Sequence[float],
    stat: Callable[[Sequence[float]], float] = mean,
    *,
    resamples: int = 10_000,
    seed: int = SEED,
) -> tuple[float, float]:
    """Percentile bootstrap CI. Fixed seed; at least 10,000 resamples."""
    if not values:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    n = len(values)
    estimates: list[float] = []
    for _ in range(resamples):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        estimates.append(stat(sample))
    estimates.sort()
    return (percentile(estimates, 2.5), percentile(estimates, 97.5))


def label_ratio(ratio: float, lower: float) -> str:
    """The only verdict labels the report may use for efficiency ratios."""
    if ratio >= 10 and lower >= 10:
        return "ACHIEVED_10X"
    if ratio >= 2:
        return "PARTIAL"
    return "TIE_OR_WORSE"


def fmt_pct(k: int, n: int) -> str:
    if n <= 0:
        return "0/0 (not measured)"
    lo, hi = wilson(k, n)
    return f"{k}/{n} ({100 * k / n:.1f}% [{100 * lo:.1f}%, {100 * hi:.1f}%])"


def fmt_num(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}"

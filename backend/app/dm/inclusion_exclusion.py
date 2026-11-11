"""
Inclusion-Exclusion Principle for Multi-Source Set Unions & Overlaps.

Formula:
|A_1 U ... U A_k| = sum_{non-empty I <= {1..k}} (-1)^(|I|-1) * |intersection_{i in I} A_i|

Time Complexity: O(2^K * sum(|A_i|)) where K <= 4
Space Complexity: O(sum(|A_i|))
"""

from itertools import combinations
from typing import Any


def union_size(sets: list[set[Any]]) -> int:
    """Compute |union of sets| via exact inclusion-exclusion alternating sums."""
    non_empty = [set(s) for s in sets if s]
    k = len(non_empty)
    if k == 0:
        return 0
    if k == 1:
        return len(non_empty[0])

    total = 0
    for r in range(1, k + 1):
        sign = 1 if (r % 2 == 1) else -1
        for combo in combinations(range(k), r):
            inter = set(non_empty[combo[0]])
            for idx in combo[1:]:
                inter &= non_empty[idx]
            total += sign * len(inter)
    return total


def inclusion_exclusion_breakdown(named_sets: dict[str, set[Any]]) -> dict[str, Any]:
    """
    Compute individual counts, pairwise overlaps, triple overlaps, and union size
    via inclusion-exclusion over up to 4 named sets.
    """
    names = list(named_sets.keys())
    clean_sets = {name: set(vals) for name, vals in named_sets.items()}

    singles = {name: len(clean_sets[name]) for name in names}
    pairwise: dict[str, int] = {}
    for a, b in combinations(names, 2):
        pairwise[f"{a} & {b}"] = len(clean_sets[a] & clean_sets[b])

    triple: dict[str, int] = {}
    for a, b, c in combinations(names, 3):
        triple[f"{a} & {b} & {c}"] = len(clean_sets[a] & clean_sets[b] & clean_sets[c])

    ie_union = union_size([clean_sets[n] for n in names])
    return {
        "singles": singles,
        "pairwise": pairwise,
        "triple": triple,
        "union_size": ie_union,
    }

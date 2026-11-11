"""
Disjoint-Set (Union-Find) with path compression and union by rank.

Time Complexity:
- find / union / connected: O(alpha(N)) amortized (~O(1))
- components: O(N * alpha(N))
Space Complexity: O(N)
"""

from collections.abc import Iterable
from typing import Any


class UnionFind:
    def __init__(self, items: Iterable[Any] = ()) -> None:
        """Initialize disjoint sets for the given items in O(N) time and space."""
        self.parent: dict[Any, Any] = {}
        self.rank: dict[Any, int] = {}
        for x in items:
            self.make_set(x)

    def make_set(self, x: Any) -> None:
        """Create singleton set for x if not already present. O(1) time/space."""
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0

    def find(self, x: Any) -> Any:
        """Find set representative with iterative path compression. O(alpha(N)) amortized."""
        self.make_set(x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            nxt = self.parent[x]
            self.parent[x] = root
            x = nxt
        return root

    def union(self, a: Any, b: Any) -> bool:
        """Merge sets containing a and b by rank. Returns True if merged. O(alpha(N))."""
        ra = self.find(a)
        rb = self.find(b)
        if ra == rb:
            return False
        if self.rank[ra] < self.rank[rb]:
            self.parent[ra] = rb
        elif self.rank[ra] > self.rank[rb]:
            self.parent[rb] = ra
        else:
            self.parent[rb] = ra
            self.rank[ra] += 1
        return True

    def connected(self, a: Any, b: Any) -> bool:
        """Return True if a and b belong to the same set. O(alpha(N))."""
        return self.find(a) == self.find(b)

    def components(self) -> list[list[Any]]:
        """Return all disjoint sets grouped by representative. O(N * alpha(N)) time, O(N) space."""
        groups: dict[Any, list[Any]] = {}
        for item in self.parent:
            root = self.find(item)
            groups.setdefault(root, []).append(item)
        return list(groups.values())

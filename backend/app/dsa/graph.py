"""
Adjacency-List Graph Data Structure and Core Traversals (BFS, DFS, Components, Cycle Detection).

Time Complexity:
- add_node / add_edge / has_edge: O(1) expected
- bfs / dfs / connected_components / has_cycle: O(V + E)
Space Complexity: O(V + E)
"""

from collections import deque
from typing import Any

from app.dsa.union_find import UnionFind


class Graph:
    def __init__(self, directed: bool = True) -> None:
        """Initialize an empty directed or undirected weighted graph. O(1)."""
        self.directed = directed
        self._adj: dict[Any, dict[Any, dict[str, Any]]] = {}
        self._node_attrs: dict[Any, dict[str, Any]] = {}

    def add_node(self, u: Any, **attrs: Any) -> None:
        """Add node u (or update attributes). O(1)."""
        if u not in self._adj:
            self._adj[u] = {}
            self._node_attrs[u] = {}
        if attrs:
            self._node_attrs[u].update(attrs)

    def add_edge(self, u: Any, v: Any, weight: float = 1.0, **attrs: Any) -> None:
        """Add edge (u, v) with weight and attributes. O(1)."""
        self.add_node(u)
        self.add_node(v)
        data = {"weight": float(weight), **attrs}
        self._adj[u][v] = data
        if not self.directed and u != v:
            self._adj[v][u] = dict(data)

    def has_node(self, u: Any) -> bool:
        """Return True if u is in the graph. O(1)."""
        return u in self._adj

    def has_edge(self, u: Any, v: Any) -> bool:
        """Return True if edge (u, v) exists. O(1)."""
        return u in self._adj and v in self._adj[u]

    def get_edge_data(self, u: Any, v: Any) -> dict[str, Any] | None:
        """Return edge metadata dict if present, else None. O(1)."""
        if not self.has_edge(u, v):
            return None
        return self._adj[u][v]

    def nodes(self) -> list[Any]:
        """Return all vertices. O(V)."""
        return list(self._adj.keys())

    def neighbors(self, u: Any) -> list[Any]:
        """Return out-neighbors (or neighbors if undirected) of u. O(deg(u))."""
        if u not in self._adj:
            return []
        return list(self._adj[u].keys())

    def edges(self) -> list[tuple[Any, Any, dict[str, Any]]]:
        """Return edge tuples (u, v, attrs). Deduplicates undirected edges. O(V + E)."""
        out: list[tuple[Any, Any, dict[str, Any]]] = []
        seen_undirected: set[tuple[Any, Any]] = set()
        for u, nbrs in self._adj.items():
            for v, data in nbrs.items():
                if not self.directed:
                    key = (u, v) if repr(u) <= repr(v) else (v, u)
                    if key in seen_undirected:
                        continue
                    seen_undirected.add(key)
                out.append((u, v, data))
        return out

    def __len__(self) -> int:
        return len(self._adj)


def bfs(graph: Graph, start: Any) -> list[Any]:
    """Breadth-first traversal starting from `start`. O(V + E) time, O(V) space."""
    if not graph.has_node(start):
        return []
    visited: set[Any] = {start}
    order: list[Any] = []
    queue: deque[Any] = deque([start])
    while queue:
        u = queue.popleft()
        order.append(u)
        for v in graph.neighbors(u):
            if v not in visited:
                visited.add(v)
                queue.append(v)
    return order


def dfs(graph: Graph, start: Any, recursive: bool = False) -> list[Any]:
    """Depth-first traversal (iterative or recursive) starting from `start`. O(V + E) time, O(V) space."""
    if not graph.has_node(start):
        return []
    visited: set[Any] = set()
    order: list[Any] = []

    if recursive:
        def _visit(u: Any) -> None:
            visited.add(u)
            order.append(u)
            for v in graph.neighbors(u):
                if v not in visited:
                    _visit(v)
        _visit(start)
        return order

    stack: list[Any] = [start]
    while stack:
        u = stack.pop()
        if u in visited:
            continue
        visited.add(u)
        order.append(u)
        for v in reversed(graph.neighbors(u)):
            if v not in visited:
                stack.append(v)
    return order


def connected_components(graph: Graph) -> list[list[Any]]:
    """
    Compute (weakly) connected components using Union-Find.
    O((V + E) * alpha(V)) time, O(V) space.
    """
    uf = UnionFind(graph.nodes())
    for u, v, _ in graph.edges():
        uf.union(u, v)
    return uf.components()


def has_cycle(graph: Graph) -> bool:
    """
    Detect cycles in directed (3-color DFS) or undirected (Union-Find / self-loop) graphs.
    O(V + E) time, O(V) space.
    """
    if graph.directed:
        # 0 = unvisited, 1 = on recursion stack, 2 = finished
        state: dict[Any, int] = {}
        for start in graph.nodes():
            if state.get(start, 0) != 0:
                continue
            stack: list[tuple[Any, int]] = [(start, 0)]
            state[start] = 1
            while stack:
                u, idx = stack[-1]
                nbrs = graph.neighbors(u)
                if idx < len(nbrs):
                    stack[-1] = (u, idx + 1)
                    v = nbrs[idx]
                    st = state.get(v, 0)
                    if st == 1:
                        return True
                    if st == 0:
                        state[v] = 1
                        stack.append((v, 0))
                else:
                    state[u] = 2
                    stack.pop()
        return False

    uf = UnionFind(graph.nodes())
    for u, v, _ in graph.edges():
        if u == v:
            return True
        if not uf.union(u, v):
            return True
    return False

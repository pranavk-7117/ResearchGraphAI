"""
Kahn's Topological Sort, Cycle Witness Extraction, and Unique Order Verification.

Time Complexity:
- kahn_topological_sort: O(V + E)
- is_unique_topological_order: O(V + E)
Space Complexity: O(V + E)
"""

from collections import deque
from typing import Any

from app.dsa.graph import Graph


class CycleError(ValueError):
    """Raised when topological sort encounters a directed cycle."""

    def __init__(self, cycle: list[Any], message: str | None = None) -> None:
        self.cycle = cycle
        msg = message or f"Graph contains a directed cycle: {' -> '.join(str(x) for x in cycle)}"
        super().__init__(msg)


def _extract_cycle(graph: Graph, candidates: set[Any]) -> list[Any]:
    """Find an explicit simple cycle among nodes not emitted by Kahn's algorithm. O(V + E)."""
    state: dict[Any, int] = {}
    parent: dict[Any, Any] = {}
    for start in candidates:
        if state.get(start, 0) != 0:
            continue
        stack: list[tuple[Any, int]] = [(start, 0)]
        state[start] = 1
        while stack:
            u, idx = stack[-1]
            nbrs = [v for v in graph.neighbors(u) if v in candidates]
            if idx < len(nbrs):
                stack[-1] = (u, idx + 1)
                v = nbrs[idx]
                st = state.get(v, 0)
                if st == 1:
                    cyc = [v, u]
                    cur = u
                    while cur != v and cur in parent:
                        cur = parent[cur]
                        cyc.append(cur)
                    cyc.reverse()
                    return cyc
                if st == 0:
                    parent[v] = u
                    state[v] = 1
                    stack.append((v, 0))
            else:
                state[u] = 2
                stack.pop()
    return list(candidates)


def kahn_topological_sort(graph: Graph) -> list[Any]:
    """
    Compute a topological ordering via Kahn's BFS algorithm.
    Raises CycleError listing an explicit cycle if the directed graph is cyclic.
    O(V + E) time, O(V + E) space.
    """
    if not graph.directed:
        raise ValueError("Topological sort requires a directed graph.")

    nodes = graph.nodes()
    in_degree: dict[Any, int] = {u: 0 for u in nodes}
    for u in nodes:
        for v in graph.neighbors(u):
            in_degree[v] = in_degree.get(v, 0) + 1

    queue: deque[Any] = deque(u for u in nodes if in_degree[u] == 0)
    order: list[Any] = []

    while queue:
        u = queue.popleft()
        order.append(u)
        for v in graph.neighbors(u):
            in_degree[v] -= 1
            if in_degree[v] == 0:
                queue.append(v)

    if len(order) != len(nodes):
        remaining = {u for u in nodes if u not in set(order)}
        cycle = _extract_cycle(graph, remaining)
        raise CycleError(cycle)

    return order


def is_unique_topological_order(graph: Graph) -> bool:
    """
    Return True iff the directed graph is a DAG with a unique topological ordering
    (equivalently, the DAG has a Hamiltonian path linking every consecutive pair).
    O(V + E) time, O(V + E) space.
    """
    try:
        order = kahn_topological_sort(graph)
    except CycleError:
        return False

    if len(order) <= 1:
        return True

    for i in range(len(order) - 1):
        if not graph.has_edge(order[i], order[i + 1]):
            return False
    return True

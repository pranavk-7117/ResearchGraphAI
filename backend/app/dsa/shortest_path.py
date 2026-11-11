"""
Dijkstra's Shortest Path using Hand-Built Binary Min-Heap.

Edge cost mapping for scholarly path explanation:
- Citation edge (cites): cost = 0.1
- Similarity / coupling edge: cost = max(0.01, 1.0 - score)

Time Complexity: O((V + E) log V)
Space Complexity: O(V + E)
"""

from typing import Any

from app.dsa.graph import Graph
from app.dsa.heap import MinHeap


def edge_traversal_cost(data: dict[str, Any]) -> float:
    """Compute non-negative Dijkstra traversal cost from edge metadata."""
    rel_type = data.get("relation_type")
    if rel_type == "cites":
        return 0.1
    if "weight" in data and rel_type is None:
        return max(0.0, float(data["weight"]))
    score = float(data.get("score", data.get("weight", 0.5)))
    return max(0.01, 1.0 - score)


def dijkstra(
    graph: Graph,
    source: Any,
    target: Any | None = None,
    use_semantic_cost: bool = False,
) -> tuple[dict[Any, float], dict[Any, Any]] | tuple[float, list[Any]] | None:
    """
    Compute shortest paths from `source` using our binary MinHeap.
    - If `target` is given: returns (total_cost, path_nodes) or None if unreachable.
    - If `target` is None: returns (distances_dict, predecessors_dict).
    O((V + E) log V) time, O(V) space.
    """
    if not graph.has_node(source):
        return None if target is not None else ({}, {})
    if target is not None and not graph.has_node(target):
        return None

    dist: dict[Any, float] = {source: 0.0}
    prev: dict[Any, Any] = {}
    pq = MinHeap(key=lambda item: item[0])
    pq.push((0.0, source))

    while len(pq) > 0:
        d, u = pq.pop()
        if d > dist.get(u, float("inf")):
            continue
        if target is not None and u == target:
            break

        for v in graph.neighbors(u):
            edata = graph.get_edge_data(u, v) or {}
            w = edge_traversal_cost(edata) if use_semantic_cost else float(edata.get("weight", 1.0))
            if w < 0:
                raise ValueError("Dijkstra does not support negative edge weights.")
            nd = d + w
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = u
                pq.push((nd, v))

    if target is None:
        return dist, prev

    if target not in dist:
        return None

    path: list[Any] = []
    cur: Any = target
    while cur is not None:
        path.append(cur)
        cur = prev.get(cur)
    path.reverse()
    return dist[target], path

"""
Kruskal's Minimum and Maximum Spanning Tree using Hand-Built Union-Find.

Used to extract an acyclic Maximum Spanning Tree backbone of the similarity graph.

Time Complexity: O(E log E + E * alpha(V))
Space Complexity: O(V + E)
"""

from typing import Any

from app.dsa.graph import Graph
from app.dsa.union_find import UnionFind


def kruskal_mst(graph: Graph, maximum: bool = False) -> list[tuple[Any, Any, float]]:
    """
    Compute Kruskal's minimum (maximum=False) or maximum (maximum=True) spanning forest.
    Returns list of (u, v, weight) edges included in the spanning tree/forest.
    O(E log E) time, O(V + E) space.
    """
    uf = UnionFind(graph.nodes())
    weighted_edges = [
        (u, v, float(data.get("weight", 1.0)))
        for u, v, data in graph.edges()
        if u != v
    ]
    weighted_edges.sort(key=lambda e: e[2], reverse=maximum)

    mst_edges: list[tuple[Any, Any, float]] = []
    for u, v, w in weighted_edges:
        if uf.union(u, v):
            mst_edges.append((u, v, w))
    return mst_edges


def maximum_spanning_tree(graph: Graph) -> list[tuple[Any, Any, float]]:
    """Convenience alias for Kruskal Maximum Spanning Tree backbone. O(E log E)."""
    return kruskal_mst(graph, maximum=True)

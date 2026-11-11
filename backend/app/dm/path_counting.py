"""
Search Path Count (SPC) Dynamic Programming over DAG Topological Order.

For each vertex:
- N(v) = number of paths from any source (in_deg == 0) to v:
    N(v) = 1 if v is a source, else sum_{(u, v) in E} N(u)
- M(u) = number of paths from u to any sink (out_deg == 0):
    M(u) = 1 if u is a sink, else sum_{(u, v) in E} M(v)
For each edge (u, v):
- SPC(u, v) = N(u) * M(v) = exact count of source-to-sink paths traversing edge (u, v).

Time Complexity: O(V + E)
Space Complexity: O(V + E)
"""

from typing import Any

from app.dsa.graph import Graph
from app.dsa.topo import kahn_topological_sort


def compute_spc(dag: Graph) -> dict[str, Any]:
    """Compute forward N(v), backward M(u), and Search Path Count SPC(u, v) = N(u)*M(v)."""
    order = kahn_topological_sort(dag)
    if not order:
        return {"N": {}, "M": {}, "edge_spc": {}, "total_paths": 0, "topo_order": []}

    in_deg: dict[Any, int] = {u: 0 for u in order}
    for u in order:
        for v in dag.neighbors(u):
            in_deg[v] = in_deg.get(v, 0) + 1

    sources = [u for u in order if in_deg[u] == 0]
    sinks = [u for u in order if len(dag.neighbors(u)) == 0]

    # Forward DP: N(v)
    N: dict[Any, int] = {u: (1 if in_deg[u] == 0 else 0) for u in order}
    for u in order:
        for v in dag.neighbors(u):
            N[v] += N[u]

    # Backward DP: M(u)
    M: dict[Any, int] = {u: (1 if len(dag.neighbors(u)) == 0 else 0) for u in order}
    for u in reversed(order):
        for v in dag.neighbors(u):
            M[u] += M[v]

    edge_spc: dict[tuple[Any, Any], int] = {}
    for u in order:
        for v in dag.neighbors(u):
            edge_spc[(u, v)] = N[u] * M[v]

    total_paths = sum(M[s] for s in sources) if dag.edges() else 0

    return {
        "N": N,
        "M": M,
        "edge_spc": edge_spc,
        "sources": sources,
        "sinks": sinks,
        "total_paths": total_paths,
        "topo_order": order,
    }

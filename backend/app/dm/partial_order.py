"""
Partial Order Operations on Citation DAGs: Transitive Closure and Transitive Reduction (Hasse Diagram).

Time Complexity:
- transitive_closure: O(V * (V + E)) via topological reverse DP with set union
- transitive_reduction: O(V * (V + E)) via transitive closure check
Space Complexity: O(V^2) for closure reachability sets
"""

from typing import Any

from app.dsa.graph import Graph
from app.dsa.topo import kahn_topological_sort


def transitive_closure(dag: Graph) -> Graph:
    """
    Compute the transitive closure (reachability relation) of a directed acyclic graph.
    Returns a new directed Graph containing all pairs (u, v) where v is reachable from u via >= 1 step.
    """
    order = kahn_topological_sort(dag)
    reach: dict[Any, set[Any]] = {u: set() for u in order}

    for u in reversed(order):
        for v in dag.neighbors(u):
            reach[u].add(v)
            reach[u].update(reach[v])

    closure = Graph(directed=True)
    for u in order:
        closure.add_node(u)
    for u in order:
        for v in reach[u]:
            closure.add_edge(u, v)
    return closure


def transitive_reduction(dag: Graph) -> Graph:
    """
    Compute the Hasse diagram (unique transitive reduction) of a DAG.
    Edge (u, v) is preserved iff there is NO intermediate vertex w in out(u) (w != v)
    from which v is reachable in the transitive closure.
    """
    order = kahn_topological_sort(dag)
    reach: dict[Any, set[Any]] = {u: set() for u in order}
    for u in reversed(order):
        for v in dag.neighbors(u):
            reach[u].add(v)
            reach[u].update(reach[v])

    hasse = Graph(directed=True)
    for u in order:
        hasse.add_node(u)

    for u in order:
        nbrs = dag.neighbors(u)
        for v in nbrs:
            has_indirect = any(w != v and v in reach[w] for w in nbrs)
            if not has_indirect:
                data = dict(dag.get_edge_data(u, v) or {})
                w_val = float(data.pop("weight", 1.0))
                hasse.add_edge(u, v, weight=w_val, **data)

    return hasse

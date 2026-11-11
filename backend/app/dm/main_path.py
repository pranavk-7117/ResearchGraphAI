"""
Main-Path Analysis (Global Main Path & Key-Route Main Path) using SPC Weights.

Time Complexity: O(V + E + K * (V + E))
Space Complexity: O(V + E)
"""

from typing import Any

from app.dm.path_counting import compute_spc
from app.dsa.graph import Graph
from app.dsa.heap import top_k


def global_main_path(dag: Graph) -> dict[str, Any]:
    """
    Find the source-to-sink path maximizing total SPC weight via DAG dynamic programming.
    Returns empty result with explanatory field when the DAG has no edges.
    """
    if not dag.edges():
        return {
            "path": [],
            "edges": [],
            "total_spc": 0,
            "total_paths": 0,
            "edge_spc": {},
            "explanation": "No citation edges present in this corpus; main path cannot be traced.",
        }

    spc_info = compute_spc(dag)
    order = spc_info["topo_order"]
    edge_spc = spc_info["edge_spc"]
    sources = set(spc_info["sources"])
    sinks = set(spc_info["sinks"])

    dp: dict[Any, int] = {u: (0 if u in sources else -1) for u in order}
    parent: dict[Any, Any] = {}

    for u in order:
        if dp[u] < 0:
            continue
        for v in dag.neighbors(u):
            cand = dp[u] + edge_spc.get((u, v), 0)
            if cand > dp[v]:
                dp[v] = cand
                parent[v] = u

    best_sink = max(sinks, key=lambda t: dp[t])
    path: list[Any] = []
    cur: Any = best_sink
    while cur is not None:
        path.append(cur)
        cur = parent.get(cur)
    path.reverse()

    edges_out = [
        {"from": path[i], "to": path[i + 1], "spc": edge_spc.get((path[i], path[i + 1]), 0)}
        for i in range(len(path) - 1)
    ]

    return {
        "path": path,
        "edges": edges_out,
        "total_spc": dp[best_sink],
        "total_paths": spc_info["total_paths"],
        "edge_spc": edge_spc,
        "explanation": f"Global main path traverses {len(edges_out)} citation step(s) with total SPC={dp[best_sink]}.",
    }


def key_route_main_path(dag: Graph, top_k_edges: int = 3) -> dict[str, Any]:
    """
    Key-route main path: select top-K edges by SPC weight and extend each edge
    both forward (to a sink) and backward (to a source) along max-SPC incident edges.
    """
    if not dag.edges():
        return {
            "key_route_edges": [],
            "key_route_paths": [],
            "explanation": "No citation edges present in this corpus; key-route main path is empty.",
        }

    spc_info = compute_spc(dag)
    edge_spc = spc_info["edge_spc"]
    order = spc_info["topo_order"]

    incoming: dict[Any, list[Any]] = {u: [] for u in order}
    for u in order:
        for v in dag.neighbors(u):
            incoming[v].append(u)

    top_edges = top_k(
        edge_spc.items(),
        top_k_edges,
        key=lambda item: item[1],
        reverse=True,
    )

    union_edges: dict[tuple[Any, Any], int] = {}
    paths: list[list[Any]] = []

    for (u_start, v_start), w_start in top_edges:
        # Extend backward from u_start to a source
        back = [u_start]
        cur = u_start
        while incoming.get(cur):
            prev_u = max(incoming[cur], key=lambda p: edge_spc.get((p, cur), 0))
            union_edges[(prev_u, cur)] = edge_spc[(prev_u, cur)]
            back.append(prev_u)
            cur = prev_u
        back.reverse()

        # Include key-route edge itself
        union_edges[(u_start, v_start)] = w_start

        # Extend forward from v_start to a sink
        fwd = [v_start]
        cur = v_start
        while dag.neighbors(cur):
            nxt_v = max(dag.neighbors(cur), key=lambda q: edge_spc.get((cur, q), 0))
            union_edges[(cur, nxt_v)] = edge_spc[(cur, nxt_v)]
            fwd.append(nxt_v)
            cur = nxt_v

        paths.append(back + fwd)

    edge_list = [
        {"from": u, "to": v, "spc": spc}
        for (u, v), spc in sorted(union_edges.items(), key=lambda x: x[1], reverse=True)
    ]

    return {
        "key_route_edges": edge_list,
        "key_route_paths": paths,
        "explanation": f"Key-route analysis extracted {len(edge_list)} backbone citation edge(s) from top-{len(top_edges)} SPC links.",
    }

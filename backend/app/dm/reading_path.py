"""
Topological Prerequisite Reading-Path Planner over Citation DAG.

Given a target paper, finds its cited ancestor set within `max_hops`, selects the top-N
most authoritative prerequisites ranked by citation-DAG PageRank, and orders them
in dependency-first topological order (read cited foundational paper before citing paper).

Time Complexity: O(V + E + M log M) where M is reachable ancestor count
Space Complexity: O(V + E)
"""

from collections import deque
from typing import Any

from app.dsa.graph import Graph
from app.dsa.heap import top_k
from app.dsa.topo import CycleError, kahn_topological_sort


def compute_reading_path(
    dag: Graph,
    target_paper_id: int,
    pagerank: dict[int, float] | None = None,
    max_hops: int = 3,
    max_papers: int = 10,
) -> list[dict[str, Any]]:
    """
    Return ordered reading prerequisites (ancestors in citation lineage) for `target_paper_id`
    within `max_hops`, ranked by citation-DAG PageRank, capped at `max_papers`, in topological reading order.
    """
    if not dag.has_node(target_paper_id):
        return []

    pr_map = pagerank or {}

    # BFS along outgoing citation edges (citing -> cited prerequisites)
    hops: dict[Any, int] = {target_paper_id: 0}
    queue: deque[Any] = deque([target_paper_id])
    while queue:
        u = queue.popleft()
        if hops[u] >= max_hops:
            continue
        for v in dag.neighbors(u):
            if v not in hops:
                hops[v] = hops[u] + 1
                queue.append(v)

    # Ancestors excluding target itself
    ancestors = [pid for pid, h in hops.items() if h >= 1]
    if not ancestors:
        return []

    # Select top `max_papers` prerequisites by citation-DAG PageRank (tie-break closer hops)
    selected_set = set(
        top_k(
            ancestors,
            max_papers,
            key=lambda pid: (pr_map.get(pid, 0.0), -hops[pid]),
            reverse=True,
        )
    )

    # Build induced subgraph of selected prerequisites (+ target for topological consistency)
    sub = Graph(directed=True)
    for pid in selected_set:
        sub.add_node(pid)
    for u in selected_set:
        for v in dag.neighbors(u):
            if v in selected_set:
                sub.add_edge(u, v)

    # In citing -> cited edges (u -> v means u cites v), topological sort puts u before v.
    # Reversing topological order ensures foundational cited paper v appears BEFORE citing paper u!
    try:
        topo = list(reversed(kahn_topological_sort(sub)))
    except CycleError:
        # Fallback ordering by descending hops (deepest foundations first), then PageRank
        topo = sorted(selected_set, key=lambda pid: (-hops[pid], -pr_map.get(pid, 0.0)))

    return [
        {
            "paper_id": pid,
            "step": idx + 1,
            "hop_distance": hops[pid],
            "pagerank": round(float(pr_map.get(pid, 0.0)), 6),
        }
        for idx, pid in enumerate(topo)
    ]

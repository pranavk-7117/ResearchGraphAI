from app.services.research_graph import ResearchGraph


def test_bfs_and_dfs_reachable_order():
    graph = ResearchGraph()
    graph.add_edge(1, 2, "citation")
    graph.add_edge(1, 3, "similarity")
    graph.add_edge(2, 4, "semantic_relation", "extends")

    assert graph.bfs(1) == [2, 3, 4]
    assert graph.bfs(1, max_hops=1) == [2, 3]
    assert graph.dfs(1) == [1, 2, 4, 3]


def test_shortest_path_returns_edges():
    graph = ResearchGraph()
    graph.add_edge(1, 2, "citation", "cites")
    graph.add_edge(2, 3, "similarity", "similar")
    graph.add_edge(1, 4, "citation", "cites")

    path = graph.shortest_path(1, 3)

    assert [(edge.source_id, edge.target_id) for edge in path] == [(1, 2), (2, 3)]


def test_topo_sort_breaks_weakest_extends_cycle():
    graph = ResearchGraph()
    graph.add_edge(1, 2, "semantic_relation", "extends", 0.9)
    graph.add_edge(2, 3, "semantic_relation", "extends", 0.8)
    graph.add_edge(3, 1, "semantic_relation", "extends", 0.1)

    assert graph.topo_sort_extends_chain([1, 2, 3]) == [1, 2, 3]

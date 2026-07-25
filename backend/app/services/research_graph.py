from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass
class GraphEdge:
    source_id: int
    target_id: int
    edge_type: str
    relation_label: str | None = None
    confidence: float = 1.0


class ResearchGraph:
    def __init__(self) -> None:
        self.adj: dict[int, list[GraphEdge]] = defaultdict(list)
        self.nodes: set[int] = set()

    def add_paper(self, paper_id: int) -> None:
        """Add a paper node. Time: O(1)."""
        self.nodes.add(paper_id)
        self.adj.setdefault(paper_id, [])

    def add_edge(
        self,
        source_id: int,
        target_id: int,
        edge_type: str,
        label: str | None = None,
        confidence: float = 1.0,
    ) -> None:
        """Add a directed edge. Time: O(1)."""
        self.add_paper(source_id)
        self.add_paper(target_id)
        self.adj[source_id].append(GraphEdge(source_id, target_id, edge_type, label, confidence))

    def bfs(self, start_id: int, max_hops: int | None = None) -> list[int]:
        """Return related papers in breadth-first order. Time: O(V + E)."""
        if start_id not in self.nodes:
            return []
        visited = {start_id}
        queue: deque[tuple[int, int]] = deque([(start_id, 0)])
        result: list[int] = []
        while queue:
            node, depth = queue.popleft()
            if max_hops is not None and depth >= max_hops:
                continue
            for edge in self.adj.get(node, []):
                if edge.target_id in visited:
                    continue
                visited.add(edge.target_id)
                result.append(edge.target_id)
                queue.append((edge.target_id, depth + 1))
        return result

    def dfs(self, start_id: int) -> list[int]:
        """Return the connected component reachable from start using DFS. Time: O(V + E)."""
        if start_id not in self.nodes:
            return []
        visited: set[int] = set()
        result: list[int] = []

        def visit(node: int) -> None:
            visited.add(node)
            result.append(node)
            for edge in self.adj.get(node, []):
                if edge.target_id not in visited:
                    visit(edge.target_id)

        visit(start_id)
        return result

    def shortest_path(self, a_id: int, b_id: int) -> list[GraphEdge]:
        """Find an unweighted shortest directed path using BFS. Time: O(V + E)."""
        if a_id not in self.nodes or b_id not in self.nodes:
            return []
        queue = deque([a_id])
        parents: dict[int, tuple[int, GraphEdge] | None] = {a_id: None}
        while queue:
            node = queue.popleft()
            if node == b_id:
                break
            for edge in self.adj.get(node, []):
                if edge.target_id not in parents:
                    parents[edge.target_id] = (node, edge)
                    queue.append(edge.target_id)
        if b_id not in parents:
            return []
        path: list[GraphEdge] = []
        current = b_id
        while parents[current] is not None:
            previous, edge = parents[current]
            path.append(edge)
            current = previous
        return list(reversed(path))

    def topo_sort_extends_chain(self, paper_ids: list[int]) -> list[int]:
        """Topologically sort 'extends' semantic edges, dropping weakest cycle edges. Time: O(V + E)."""
        allowed = set(paper_ids)
        edges = [
            edge
            for source in allowed
            for edge in self.adj.get(source, [])
            if edge.target_id in allowed
            and edge.edge_type == "semantic_relation"
            and edge.relation_label == "extends"
        ]
        while True:
            cycle = self._find_cycle(allowed, edges)
            if not cycle:
                break
            weakest = min(cycle, key=lambda edge: edge.confidence)
            edges.remove(weakest)

        indegree = {paper_id: 0 for paper_id in allowed}
        outgoing: dict[int, list[GraphEdge]] = defaultdict(list)
        for edge in edges:
            outgoing[edge.source_id].append(edge)
            indegree[edge.target_id] += 1
        queue = deque(sorted([node for node, degree in indegree.items() if degree == 0]))
        ordered: list[int] = []
        while queue:
            node = queue.popleft()
            ordered.append(node)
            for edge in outgoing.get(node, []):
                indegree[edge.target_id] -= 1
                if indegree[edge.target_id] == 0:
                    queue.append(edge.target_id)
        return ordered

    def connected_components(self) -> list[list[int]]:
        """Find weak-ish components by following stored edges. Time: O(V + E)."""
        unseen = set(self.nodes)
        components: list[list[int]] = []
        while unseen:
            start = unseen.pop()
            component = [start, *self.bfs(start)]
            components.append(component)
            unseen -= set(component)
        return components

    def _find_cycle(self, nodes: set[int], edges: list[GraphEdge]) -> list[GraphEdge]:
        outgoing: dict[int, list[GraphEdge]] = defaultdict(list)
        for edge in edges:
            outgoing[edge.source_id].append(edge)
        visiting: set[int] = set()
        visited: set[int] = set()
        stack: list[GraphEdge] = []

        def visit(node: int) -> list[GraphEdge]:
            visiting.add(node)
            for edge in outgoing.get(node, []):
                if edge.target_id in visiting:
                    return [*stack, edge]
                if edge.target_id not in visited:
                    stack.append(edge)
                    found = visit(edge.target_id)
                    if found:
                        return found
                    stack.pop()
            visiting.remove(node)
            visited.add(node)
            return []

        for node in nodes:
            if node not in visited:
                found = visit(node)
                if found:
                    return found
        return []

"""
Hand-built Data Structures package (DS-1) for ResearchGraphAI.
Strictly zero third-party graph or ML library imports (no networkx, no sklearn).
"""

from app.dsa.graph import Graph, bfs, connected_components, dfs, has_cycle
from app.dsa.hashtable import HashTable
from app.dsa.heap import MinHeap, top_k
from app.dsa.mst import kruskal_mst, maximum_spanning_tree
from app.dsa.shortest_path import dijkstra
from app.dsa.topo import CycleError, is_unique_topological_order, kahn_topological_sort
from app.dsa.trie import Trie
from app.dsa.union_find import UnionFind

__all__ = [
    "Graph",
    "bfs",
    "dfs",
    "connected_components",
    "has_cycle",
    "UnionFind",
    "CycleError",
    "kahn_topological_sort",
    "is_unique_topological_order",
    "MinHeap",
    "top_k",
    "dijkstra",
    "kruskal_mst",
    "maximum_spanning_tree",
    "Trie",
    "HashTable",
]

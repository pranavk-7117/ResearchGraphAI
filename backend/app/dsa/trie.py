"""
Prefix Trie for Fast Case-Insensitive Title & Author Autocomplete.

Time Complexity:
- insert(word): O(L), where L = len(word)
- search_prefix(prefix, limit): O(P + M * L_avg), where P = len(prefix), M = limit
Space Complexity: O(sum(len(words)))
"""

from collections import deque
from typing import Any


class _TrieNode:
    __slots__ = ("children", "terminals")

    def __init__(self) -> None:
        self.children: dict[str, _TrieNode] = {}
        self.terminals: list[tuple[str, Any]] = []


class Trie:
    def __init__(self) -> None:
        """Initialize empty prefix trie. O(1)."""
        self.root = _TrieNode()
        self._size = 0

    def __len__(self) -> int:
        return self._size

    def insert(self, text: str, payload: Any = None) -> None:
        """Insert a string key and optional payload (paper_id/metadata). O(len(text))."""
        clean = " ".join((text or "").split())
        if not clean:
            return
        node = self.root
        for ch in clean.lower():
            if ch not in node.children:
                node.children[ch] = _TrieNode()
            node = node.children[ch]
        node.terminals.append((clean, payload))
        self._size += 1

    def search_prefix(self, prefix: str, limit: int = 10) -> list[dict[str, Any]]:
        """
        Return up to `limit` matches starting with `prefix` via BFS for shortest-first results.
        O(|prefix| + visited_subtree) time.
        """
        clean_prefix = " ".join((prefix or "").split()).lower()
        node = self.root
        for ch in clean_prefix:
            if ch not in node.children:
                return []
            node = node.children[ch]

        results: list[dict[str, Any]] = []
        queue: deque[_TrieNode] = deque([node])
        while queue and len(results) < limit:
            curr = queue.popleft()
            for original_text, payload in curr.terminals:
                results.append({"text": original_text, "payload": payload})
                if len(results) >= limit:
                    return results
            for ch in sorted(curr.children.keys()):
                queue.append(curr.children[ch])
        return results

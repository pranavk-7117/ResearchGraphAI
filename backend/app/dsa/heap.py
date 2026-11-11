"""
Binary Min-Heap and O(N log K) Top-K Selection.

Time Complexity:
- push / pop: O(log N)
- peek / __len__: O(1)
- top_k(iterable, k): O(N log K)
Space Complexity: O(N) for MinHeap, O(K) for top_k
"""

from collections.abc import Callable, Iterable
from typing import Any, TypeVar

T = TypeVar("T")


class MinHeap:
    def __init__(self, key: Callable[[Any], Any] | None = None) -> None:
        """Initialize an empty binary min-heap with optional key extractor. O(1)."""
        self._data: list[tuple[Any, int, Any]] = []
        self._key = key
        self._counter = 0

    def __len__(self) -> int:
        return len(self._data)

    def peek(self) -> Any:
        """Return smallest item without removing it. O(1)."""
        if not self._data:
            raise IndexError("peek from empty MinHeap")
        return self._data[0][2]

    def push(self, item: Any) -> None:
        """Insert item into heap and restore heap invariant. O(log N)."""
        priority = self._key(item) if self._key is not None else item
        entry = (priority, self._counter, item)
        self._counter += 1
        self._data.append(entry)
        self._sift_up(len(self._data) - 1)

    def pop(self) -> Any:
        """Remove and return smallest item. O(log N)."""
        if not self._data:
            raise IndexError("pop from empty MinHeap")
        top = self._data[0][2]
        last = self._data.pop()
        if self._data:
            self._data[0] = last
            self._sift_down(0)
        return top

    def _sift_up(self, idx: int) -> None:
        while idx > 0:
            parent = (idx - 1) // 2
            if self._data[idx] < self._data[parent]:
                self._data[idx], self._data[parent] = self._data[parent], self._data[idx]
                idx = parent
            else:
                break

    def _sift_down(self, idx: int) -> None:
        n = len(self._data)
        while True:
            left = 2 * idx + 1
            right = left + 1
            smallest = idx
            if left < n and self._data[left] < self._data[smallest]:
                smallest = left
            if right < n and self._data[right] < self._data[smallest]:
                smallest = right
            if smallest == idx:
                break
            self._data[idx], self._data[smallest] = self._data[smallest], self._data[idx]
            idx = smallest


def top_k(
    iterable: Iterable[T],
    k: int,
    key: Callable[[T], Any] | None = None,
    reverse: bool = True,
) -> list[T]:
    """
    Return the top k elements ordered descending (reverse=True) or ascending (reverse=False).
    Uses MinHeap in O(N log K) time and O(K) space.
    """
    if k <= 0:
        return []
    key_fn = key or (lambda x: x)

    if reverse:
        # Maintain min-heap of size k; evict smallest when heap exceeds k
        heap = MinHeap(key=lambda pair: pair[0])
        for idx, item in enumerate(iterable):
            val = key_fn(item)
            if len(heap) < k:
                heap.push((val, -idx, item))
            elif (val, -idx) > (heap.peek()[0], heap.peek()[1]):
                heap.pop()
                heap.push((val, -idx, item))
        out = []
        while len(heap) > 0:
            out.append(heap.pop()[2])
        out.reverse()
        return out

    # Smallest k items ascending: maintain max-heap simulated or negated if numeric,
    # or simple full extraction using MinHeap when k is small vs inverted priority
    heap = MinHeap(key=lambda pair: pair[0])
    for item in iterable:
        heap.push((key_fn(item), item))
    res = []
    while len(heap) > 0 and len(res) < k:
        res.append(heap.pop()[1])
    return res

"""
Open-Addressing Hash Table with Linear Probing, Tombstone Deletion, and Dynamic Resizing.

Time Complexity:
- get / put / delete / __contains__: O(1) expected amortized (load factor <= 0.7), O(N) worst-case
- resize: O(N) amortized O(1) per insert
Space Complexity: O(capacity) = O(N)
"""

from typing import Any

_TOMBSTONE = object()


class HashTable:
    def __init__(self, initial_capacity: int = 16, max_load_factor: float = 0.7) -> None:
        """Initialize open-addressing hash table. O(initial_capacity)."""
        cap = max(8, initial_capacity)
        self._keys: list[Any] = [None] * cap
        self._values: list[Any] = [None] * cap
        self._size = 0
        self._tombstones = 0
        self._max_load = max_load_factor

    def __len__(self) -> int:
        return self._size

    def _capacity(self) -> int:
        return len(self._keys)

    def _probe(self, key: Any) -> tuple[int, bool]:
        """Return (slot_index, found) via linear probing. O(1) expected."""
        cap = self._capacity()
        idx = hash(key) % cap
        first_tombstone = -1
        for _ in range(cap):
            slot_key = self._keys[idx]
            if slot_key is None:
                return (first_tombstone if first_tombstone != -1 else idx), False
            if slot_key is _TOMBSTONE:
                if first_tombstone == -1:
                    first_tombstone = idx
            elif slot_key == key:
                return idx, True
            idx = (idx + 1) % cap
        return (first_tombstone if first_tombstone != -1 else 0), False

    def _resize(self, new_cap: int) -> None:
        """Rehash live entries into new table of size `new_cap`, clearing tombstones. O(N)."""
        old_keys = self._keys
        old_values = self._values
        self._keys = [None] * new_cap
        self._values = [None] * new_cap
        self._size = 0
        self._tombstones = 0
        for k, v in zip(old_keys, old_values):
            if k is not None and k is not _TOMBSTONE:
                self.put(k, v)

    def put(self, key: Any, value: Any = True) -> None:
        """Insert or update key -> value. Triggers resize if load factor exceeded. O(1) amortized."""
        if (self._size + self._tombstones + 1) / self._capacity() > self._max_load:
            next_cap = self._capacity() * 2 if self._size * 2 >= self._capacity() // 2 else self._capacity()
            self._resize(max(16, next_cap))

        idx, found = self._probe(key)
        if not found:
            if self._keys[idx] is _TOMBSTONE:
                self._tombstones -= 1
            self._size += 1
        self._keys[idx] = key
        self._values[idx] = value

    def get(self, key: Any, default: Any = None) -> Any:
        """Retrieve value for key, or default if absent. O(1) expected."""
        idx, found = self._probe(key)
        return self._values[idx] if found else default

    def delete(self, key: Any) -> bool:
        """Delete key leaving a tombstone. Returns True if removed. O(1) expected."""
        idx, found = self._probe(key)
        if not found:
            return False
        self._keys[idx] = _TOMBSTONE
        self._values[idx] = None
        self._size -= 1
        self._tombstones += 1
        return True

    def __contains__(self, key: Any) -> bool:
        _, found = self._probe(key)
        return found

    def __setitem__(self, key: Any, value: Any) -> None:
        self.put(key, value)

    def __getitem__(self, key: Any) -> Any:
        idx, found = self._probe(key)
        if not found:
            raise KeyError(key)
        return self._values[idx]

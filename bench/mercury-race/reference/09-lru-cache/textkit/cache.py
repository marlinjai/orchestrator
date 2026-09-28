from collections import OrderedDict


class LRUCache:
    def __init__(self, capacity: int):
        if capacity < 1:
            raise ValueError(capacity)
        self._cap = capacity
        self._d = OrderedDict()

    def put(self, key, value):
        if key in self._d:
            self._d.move_to_end(key)
        elif len(self._d) >= self._cap:
            self._d.popitem(last=False)
        self._d[key] = value

    def get(self, key, default=None):
        if key not in self._d:
            return default
        self._d.move_to_end(key)
        return self._d[key]

    def __len__(self):
        return len(self._d)

    def __contains__(self, key):
        return key in self._d

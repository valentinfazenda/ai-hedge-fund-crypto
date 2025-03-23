class Cache:
    """In-memory cache for API responses."""

    def __init__(self):
        self._prices_cache: dict[str, list[dict[str, any]]] = {}

    def _merge_data(self, existing: list[dict] | None, new_data: list[dict], key_field: str) -> list[dict]:
        """Merge existing and new data, avoiding duplicates based on a key field."""
        if not existing:
            return new_data

        # Create a set of existing keys for O(1) lookup
        existing_keys = {item[key_field] for item in existing}
        # Only add items that don't exist yet
        merged = existing.copy()
        merged.extend([item for item in new_data if item[key_field] not in existing_keys])
        return merged

    def get_prices(self, ticker: str) -> list[dict[str, any]] | None:
        """Get cached price data if available."""
        return self._prices_cache.get(ticker)

    def set_prices(self, ticker: str, data: list[dict[str, any]]):
        """Append new price data to cache."""
        self._prices_cache[ticker] = self._merge_data(self._prices_cache.get(ticker), data, key_field="time")


# Global cache instance
_cache = Cache()


def get_cache() -> Cache:
    """Get the global cache instance."""
    return _cache

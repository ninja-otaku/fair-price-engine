"""
SQLite key-value cache with TTL. Used by live price sources in v1.1.
No external dependencies — stdlib sqlite3 only.
"""
import json
import sqlite3
import time


class PriceCache:
    DEFAULT_TTL = 7 * 86_400   # 7 days for compute rates
    COMMODITY_TTL = 86_400     # 24 hours for FRED/BLS commodity prices

    def __init__(self, path: str = "price_cache.db") -> None:
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS cache "
            "(key TEXT PRIMARY KEY, value TEXT, expires_at REAL)"
        )
        self._db.commit()

    def get(self, key: str) -> dict | None:
        row = self._db.execute(
            "SELECT value FROM cache WHERE key=? AND expires_at > ?",
            (key, time.time()),
        ).fetchone()
        return json.loads(row[0]) if row else None

    def set(self, key: str, value: dict, ttl: int | None = None) -> None:
        exp = time.time() + (ttl or self.DEFAULT_TTL)
        self._db.execute(
            "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?,?,?)",
            (key, json.dumps(value), exp),
        )
        self._db.commit()

    def evict_expired(self) -> int:
        c = self._db.execute("DELETE FROM cache WHERE expires_at <= ?", (time.time(),))
        self._db.commit()
        return c.rowcount

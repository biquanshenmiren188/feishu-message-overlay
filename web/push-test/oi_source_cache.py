"""Bounded, process-wide cache for public OI source data only.

Returned dictionaries are shared read-only snapshots. Profile settings, rule
decisions and authorization must stay with the caller. A refresh replaces the
whole source dictionary; it never updates observation times inside records.
"""
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock


VENUES = frozenset(('binance', 'bitget', 'bybit', 'okx', 'gate', 'aster', 'hyperliquid'))


class OISourceCache:
    def __init__(self):
        self._lock = Lock()
        self._entries = {}
        self._pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix='oi-source')

    def _request(self, exchange, now, ttl, loader):
        if exchange not in VENUES:
            raise ValueError('Unsupported OI source')
        if ttl <= 0:
            raise ValueError('OI source TTL must be positive')
        with self._lock:
            entry = self._entries.setdefault(exchange, dict(data={}, at=None, pending=None))
            if entry['pending'] is not None:
                return entry['pending']
            if entry['at'] is not None and 0 <= now-entry['at'] < ttl:
                result = Future()
                result.set_result(entry['data'])
                return result
            result = Future()
            entry['pending'] = result
            try:
                self._pool.submit(self._load, exchange, now, loader, result)
            except RuntimeError:
                entry['pending'] = None
                raise
            return result

    def _load(self, exchange, now, loader, result):
        try:
            data = loader()
            if not isinstance(data, dict):
                data = {}
        except Exception:
            # Failed reads become missing OI. Never extend an old observation's
            # life or keep using the last success after a failed refresh.
            data = {}
        with self._lock:
            self._entries[exchange].update(data=data, at=now, pending=None)
        result.set_result(data)

    def read(self, exchange, now, ttl, loader):
        """Read one source; loader() returns its public OI dictionary."""
        return self._request(exchange, now, ttl, loader).result()

    def read_many(self, exchanges, now, ttls, loader):
        """Read sources with at most three loaders running in this cache.

        ttls maps each exchange to its refresh interval. loader(exchange)
        returns the public dictionary. All reads are submitted before waiting,
        so callers must not create another pool around this method.
        """
        futures = {ex: self._request(ex, now, ttls[ex], lambda ex=ex: loader(ex))
                   for ex in dict.fromkeys(exchanges)}
        return {ex: future.result() for ex, future in futures.items()}

    def close(self):
        """Release an explicitly constructed cache, primarily in tests."""
        self._pool.shutdown(wait=True)


_shared = OISourceCache()


def shared_read(exchange, now, ttl, loader):
    return _shared.read(exchange, now, ttl, loader)


def shared_read_many(exchanges, now, ttls, loader):
    return _shared.read_many(exchanges, now, ttls, loader)

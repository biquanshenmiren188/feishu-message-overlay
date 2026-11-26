"""Shared official USDT ticker snapshots, with exact exchange symbols and units.

REST sampling is intentionally explicit: crossings between snapshots can be missed.
No browser display cache or bid/ask midpoint is used. Routing lives in sources.py.
"""
import json
import gzip
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlencode
from engine import number
from sources import QuoteSnapshot
from instruments import load as load_instruments

VENUES = ('binance', 'bybit', 'okx', 'bitget', 'gate', 'aster')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def get(url):
    request = Request(url, headers={'Accept': 'application/json', 'Accept-Encoding': 'gzip', 'User-Agent': 'RadarPriceAlarms/1'})
    with build_opener(NoRedirect).open(request, timeout=8) as response:
        if response.headers.get('Content-Encoding', '').lower() == 'gzip':
            with gzip.GzipFile(fileobj=response) as stream:
                data = stream.read(8000001)
        else:
            data = response.read(8000001)
        if len(data) > 8000000:
            raise ValueError('market_response_too_large')
        return json.loads(data)


class Market:
    def __init__(self, getter=get):
        self.get = getter
        self.lock = threading.RLock()
        self.quotes = {}
        self.health = {}
        self.meta = {}
        self.pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix='quotes')
        self.pending = {}
        self.partial = {}
        self.last_catalog = {}
        self.cached_snapshot = None
        self.cached_quotes = None

    def instruments(self, exchange, market, root):
        key = exchange, market
        cached = self.meta.get(key)
        if cached and time.time() - cached[0] < 300:
            return cached[1]
        names = load_instruments(self.get, exchange, market, root)
        self.meta[key] = time.time(), names
        return names

    def fetch(self, exchange, market, symbol=None):
        started = time.time()
        wanted = symbol
        future = market == 'future'
        prices, marks, names = [], {}, None
        if exchange in ('binance', 'aster'):
            root = ('https://fapi.binance.com/fapi/v1' if future else 'https://api.binance.com/api/v3') if exchange == 'binance' else ('https://fapi.asterdex.com/fapi/v1' if future else 'https://sapi.asterdex.com/api/v1')
            names = self.instruments(exchange, market, root)
            raw = self.get(root + '/ticker/24hr')
            if future:
                marks = {x['symbol']: x for x in self.get(root + '/premiumIndex')}
            for r in raw:
                m = marks.get(r['symbol'], {})
                prices.append((r['symbol'], r['symbol'][:-4], r.get('lastPrice'), m.get('markPrice'), r.get('closeTime'), m.get('time')))
        elif exchange == 'bybit':
            raw = self.get('https://api.bybit.com/v5/market/tickers?category=' + ('linear' if future else 'spot'))
            if raw.get('retCode') != 0:
                raise ValueError('bybit_rejected')
            for r in raw['result']['list']:
                if future and (float(r.get('deliveryTime') or 0) != 0 or not r.get('fundingRate')):
                    continue
                prices.append((r['symbol'], r['symbol'][:-4], r.get('lastPrice'), r.get('markPrice'), raw.get('time'), raw.get('time')))
        elif exchange == 'okx':
            kind = 'SWAP' if future else 'SPOT'
            endpoint = 'ticker?' + urlencode({'instId':symbol}) if symbol else 'tickers?instType=' + kind
            raw = self.get('https://www.okx.com/api/v5/market/' + endpoint)
            if raw.get('code') != '0':
                raise ValueError('okx_rejected')
            if future:
                query = '&' + urlencode({'instId':symbol}) if symbol else ''
                mark = self.get('https://www.okx.com/api/v5/public/mark-price?instType=SWAP' + query)
                if mark.get('code') != '0':
                    raise ValueError('okx_mark_rejected')
                marks = {r['instId']: r for r in mark['data']}
            for r in raw['data']:
                suffix = '-USDT-SWAP' if future else '-USDT'
                if not r['instId'].endswith(suffix):
                    continue
                m = marks.get(r['instId'], {})
                prices.append((r['instId'], r['instId'][:-len(suffix)], r.get('last'), m.get('markPx'), r.get('ts'), m.get('ts')))
        elif exchange == 'bitget':
            raw = self.get('https://api.bitget.com/api/v2/' + ('mix/market/tickers?productType=USDT-FUTURES' if future else 'spot/market/tickers'))
            if raw.get('code') != '00000':
                raise ValueError('bitget_rejected')
            for r in raw['data']:
                if future and float(r.get('deliveryTime') or 0) > 0:
                    continue
                prices.append((r['symbol'], r['symbol'][:-4], r.get('lastPr'), r.get('markPrice'), r.get('ts') or raw.get('requestTime'), r.get('ts') or raw.get('requestTime')))
        else:
            names = self.instruments(exchange, market, '')
            raw = self.get('https://api.gateio.ws/api/v4/' + ('futures/usdt/tickers' if future else 'spot/tickers'))
            for r in raw:
                symbol = r.get('contract') if future else r.get('currency_pair')
                if not symbol or not symbol.endswith('_USDT'):
                    continue
                prices.append((symbol, symbol[:-5], r.get('last'), r.get('mark_price'), None, None))
        names = names if names is not None else self.instruments(exchange, market, '')
        result = {}
        for symbol, base, last, mark, last_at, mark_at in prices:
            if wanted and symbol != wanted:
                continue
            if names is not None and symbol not in names:
                continue
            if exchange not in ('okx', 'gate') and not symbol.endswith('USDT'):
                continue
            q = dict(exchange=exchange, market=market, symbol=symbol, base=base, quote='USDT', observedAt=started, unit=base)
            q.update(names[symbol])
            for kind, value, stamp in [('last', last, last_at), ('mark', mark, mark_at)]:
                try:
                    q[kind] = str(number(value))
                    q[kind + 'At'] = float(stamp) / 1000 if stamp else started
                except (ValueError, TypeError):
                    q[kind] = None
            if q.get('last') or q.get('mark'):
                result[(exchange, market, symbol)] = q
        if wanted and future:
            quote = result.get((exchange, market, wanted), {})
            if not (quote.get('mark') and quote.get('last')):
                raise ValueError('incomplete_single_ticker')
        if not result:
            raise ValueError('empty_market')
        return result

    def poll(self, active):
        now = time.time()
        with self.lock:
            for group, future in list(self.pending.items()):
                if not future.done():
                    continue
                del self.pending[group]
                symbol = self.partial.pop(group, None)
                try:
                    rows = future.result()
                    if symbol:
                        self.quotes = self.quotes.copy()
                    else:
                        self.quotes = {k: v for k, v in self.quotes.items() if k[:2] != group}
                        self.last_catalog[group] = now
                    self.quotes.update(rows)
                    self.cached_snapshot = None
                    count = self.health.get(group, {}).get('count', len(rows)) if symbol else len(rows)
                    self.health[group] = dict(ok=True, checkedAt=now, count=count)
                except Exception as exc:
                    self.health[group] = dict(ok=False, checkedAt=now, error=type(exc).__name__)
                    if symbol:
                        # Retry the original full endpoint in this polling cycle when a single-ticker call fails.
                        self.last_catalog.pop(group, None)
                        self.pending[group] = self.pool.submit(self.fetch, *group)
            groups = sorted(((e, m) for e in VENUES for m in ('spot', 'future')), key=lambda g: g not in active)
            for exchange, market in groups:
                group = exchange, market
                period = 2 if group in active else 60
                if group not in self.pending and now - self.health.get(group, {}).get('checkedAt', 0) >= period:
                    symbol = active.get(group) if isinstance(active, dict) else None
                    # Binance's individual 24hr feed can lag its bulk feed. Keep that native source.
                    if (symbol and exchange == 'okx' and
                            now - self.last_catalog.get(group, 0) < 60 and (*group, symbol) in self.quotes):
                        self.partial[group] = symbol
                        self.pending[group] = self.pool.submit(self.fetch, *group, symbol)
                    else:
                        self.pending[group] = self.pool.submit(self.fetch, *group)

    def snapshot(self):
        with self.lock:
            if self.cached_snapshot is None or self.cached_quotes is not self.quotes:
                self.cached_snapshot = QuoteSnapshot(self.quotes)
                self.cached_quotes = self.quotes
            return self.cached_snapshot, {'/'.join(k): dict(v) for k, v in self.health.items()}

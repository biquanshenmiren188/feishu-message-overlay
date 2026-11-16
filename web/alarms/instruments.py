"""Official instrument metadata. Price units are not contract lot sizes."""
from urllib.parse import quote


def load(get, exchange, market, root):
    future = market == 'future'
    result = {}
    def add(symbol, base, currency, allowed=True, fallback_allowed=True):
        if allowed and symbol and base and currency == 'USDT':
            result[symbol] = dict(base=base, quote=currency, unit=base, instrumentVerified=True, fallbackAllowed=fallback_allowed)
    if exchange in ('binance', 'aster'):
        suffix = '?permissions=SPOT&showPermissionSets=false&symbolStatus=TRADING' if exchange == 'binance' and not future else ''
        for r in get(root + '/exchangeInfo' + suffix)['symbols']:
            add(r['symbol'], r.get('baseAsset'), r.get('quoteAsset'), r.get('status') == 'TRADING' and (not future or r.get('contractType') in ('PERPETUAL', 'TRADIFI_PERPETUAL')), r.get('contractType') != 'TRADIFI_PERPETUAL')
    elif exchange == 'bybit':
        cursor, seen = '', set()
        while True:
            url = 'https://api.bybit.com/v5/market/instruments-info?category=' + ('linear' if future else 'spot') + '&limit=1000'
            raw = get(url + ('&cursor=' + quote(cursor, safe='') if cursor else ''))
            if raw.get('retCode') != 0:
                raise ValueError('bybit_instruments_rejected')
            for r in raw['result']['list']:
                add(r['symbol'], r.get('baseCoin'), r.get('quoteCoin'), r.get('status') == 'Trading' and (not future or r.get('contractType') == 'LinearPerpetual'), r.get('symbolType') != 'xstocks')
            cursor = raw['result'].get('nextPageCursor')
            if not cursor:
                break
            if cursor in seen or len(seen) >= 10:
                raise ValueError('bybit_instruments_pagination')
            seen.add(cursor)
    elif exchange == 'okx':
        raw = get('https://www.okx.com/api/v5/public/instruments?instType=' + ('SWAP' if future else 'SPOT'))
        if raw.get('code') != '0':
            raise ValueError('okx_instruments_rejected')
        for r in raw['data']:
            if future:
                family = (r.get('uly') or r.get('instFamily') or '').split('-')
                if len(family) != 2:
                    continue
                base, currency = family
                allowed = r.get('state') == 'live' and r.get('ctType') == 'linear' and r.get('settleCcy') == 'USDT' and r.get('ctValCcy') == base
            else:
                base, currency, allowed = r.get('baseCcy'), r.get('quoteCcy'), r.get('state') == 'live'
            add(r['instId'], base, currency, allowed)
    elif exchange == 'bitget':
        raw = get('https://api.bitget.com/api/v2/' + ('mix/market/contracts?productType=USDT-FUTURES' if future else 'spot/public/symbols'))
        if raw.get('code') != '00000':
            raise ValueError('bitget_instruments_rejected')
        for r in raw['data']:
            allowed = r.get('symbolStatus') == 'normal' and r.get('symbolType') == 'perpetual' if future else r.get('status') == 'online'
            add(r['symbol'], r.get('baseCoin'), r.get('quoteCoin'), allowed)
    elif exchange == 'gate':
        raw = get('https://api.gateio.ws/api/v4/' + ('futures/usdt/contracts' if future else 'spot/currency_pairs'))
        for r in raw:
            if future:
                # Gate's documented contract name is BASE_QUOTE, ticker price is per base.
                parts = r['name'].rsplit('_', 1)
                if len(parts) == 2:
                    add(r['name'], *parts, not r.get('in_delisting') and r.get('status', 'trading') == 'trading')
            else:
                add(r['id'], r.get('base'), r.get('quote'), r.get('trade_status') == 'tradable')
    if not result:
        raise ValueError('empty_instruments')
    return result

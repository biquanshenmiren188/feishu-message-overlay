"""Normalize the existing Hyperliquid market cache for USDT OI thresholds.

Native perpetual denominations are independent of their USDC collateral:
https://hyperliquid.gitbook.io/hyperliquid-docs/trading/contract-specifications
The gateway's openInterestUsd is already double-sided in its native quote.
Never double it, strip a k-prefix, or collapse a builder's namespace.
"""
import math
import re

SOURCE = 'https://api.hyperliquid.xyz/info'
NATIVE_MAX_AGE = 120000
FX_MAX_AGE = 30000


def number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def fresh(stamp, now, maximum):
    return number(stamp) and stamp > 0 and -1000 <= now-stamp <= maximum


def hyperliquid_oi(payload, now):
    """Return double-v1 USDT values; ``now`` and source times are milliseconds.

    Only exact native futures from the existing gateway are eligible. Keys use
    the rule engine's uppercase convention, retaining the full native ticker.
    Any case-fold collision is removed, including collisions with invalid rows.
    Display/native identities and source observation times remain in the values.
    """
    if not number(now) or now <= 0 or not isinstance(payload, dict):
        return {}
    data = payload.get('data')
    book = data.get('hyperliquidFuture') if isinstance(data, dict) else None
    rows = book.get('list') if isinstance(book, dict) else None
    if not isinstance(rows, list):
        return {}
    out, seen, ambiguous = {}, set(), set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        coin, name = row.get('nativeCoin'), row.get('name')
        if not isinstance(coin, str) or not re.fullmatch(r'[A-Za-z0-9]{1,32}', coin):
            continue
        if name != coin+'USDT':
            continue
        key = 'hyperliquid:'+name.upper()
        if key in seen:
            ambiguous.add(key)
            continue
        seen.add(key)
        quote = 'USDC' if coin in ('HYPE', 'PURR') else 'USDT'
        value, stamp = row.get('openInterestUsd'), row.get('oiTs')
        if (row.get('quoteCurrency') != quote or row.get('settleCurrency') != 'USDC'
                or row.get('sourceUrl') != SOURCE or not number(value) or value < 0
                or not fresh(stamp, now, NATIVE_MAX_AGE)):
            continue
        ratio, fx_stamp = row.get('quoteConversion'), row.get('quoteConversionAt')
        if not number(ratio) or ratio <= 0:
            continue
        if quote == 'USDT':
            if ratio != 1:
                continue
            converted, effective = value, stamp
        else:
            if not fresh(fx_stamp, now, FX_MAX_AGE):
                continue
            converted, effective = value*ratio, min(stamp, fx_stamp)
        if not number(converted):
            continue
        out[key] = dict(value=converted, rawValue=value, multiplier=1,
                        basis='double-v1', evidence='platform-definition',
                        time=effective, timeBasis='observed', sourceTime=None,
                        source=SOURCE, nativeCoin=coin, nativeSymbol=name,
                        nativeQuote=quote, quoteCurrency='USDT',
                        quoteConversion=ratio, quoteConversionAt=fx_stamp,
                        observedAt=stamp,
                        expiresAt=min(stamp+NATIVE_MAX_AGE, fx_stamp+FX_MAX_AGE) if quote=='USDC' else stamp+NATIVE_MAX_AGE)
    for key in ambiguous:
        out.pop(key, None)
    return out

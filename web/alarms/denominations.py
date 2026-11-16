"""Reviewed native price denominations, NOT a numeric-prefix normalizer.

Each entry is scoped to a venue, market and exact instrument. See
docs/ALARM-DENOMINATIONS-20261113.md for identity evidence and review policy.
Contract lot sizes, decimal precision and observed price ratios are not evidence.
"""
from decimal import Decimal, localcontext
from engine import number

VERSION = 'reviewed-20261113-v1'

# Explicit contract denominations. Never infer a new alias by stripping digits.
FUTURES = {
    'binance': {
        '1000PEPE': ('PEPE', 1000), '1000SHIB': ('SHIB', 1000),
        '1000BONK': ('BONK', 1000), '1000FLOKI': ('FLOKI', 1000),
        '1000LUNC': ('LUNC', 1000), '1000XEC': ('XEC', 1000),
        '1000RATS': ('RATS', 1000), '1000CAT': ('CAT', 1000),
        '1000CHEEMS': ('CHEEMS', 1000), '1000SATS': ('SATS', 1000),
        '1000000MOG': ('MOG', 1000000), '1MBABYDOGE': ('BABYDOGE', 1000000),
    },
    'bybit': {
        '1000PEPE': ('PEPE', 1000), 'SHIB1000': ('SHIB', 1000),
        '1000BONK': ('BONK', 1000), '1000FLOKI': ('FLOKI', 1000),
        '1000LUNC': ('LUNC', 1000), '1000XEC': ('XEC', 1000),
        '1000RATS': ('RATS', 1000), '1000CAT': ('CAT', 1000),
        '10000SATS': ('SATS', 10000), '1000000MOG': ('MOG', 1000000),
        '1000000BABYDOGE': ('BABYDOGE', 1000000), '1000BTT': ('BTT', 1000),
        '1000NEIROCTO': ('NEIROCTO', 1000), '1000TAG': ('TAG', 1000),
        '1000TOSHI': ('TOSHI', 1000), '1000TURBO': ('TURBO', 1000),
    },
    'bitget': {
        '1000BONK': ('BONK', 1000), '1000XEC': ('XEC', 1000),
        '1000SATS': ('SATS', 1000), '1000RATS': ('RATS', 1000),
        '1000000MOG': ('MOG', 1000000), '1000CAT': ('CAT', 1000),
        '1MBABYDOGE': ('BABYDOGE', 1000000), '1MCHEEMS': ('CHEEMS', 1000000),
    },
    'aster': {
        '1000PEPE': ('PEPE', 1000), '1000SHIB': ('SHIB', 1000),
        '1000FLOKI': ('FLOKI', 1000), '1000LUNC': ('LUNC', 1000),
        '1000CHEEMS': ('CHEEMS', 1000), '1000XEC': ('XEC', 1000),
        '1000BONK': ('BONK', 1000), '1000CAT': ('CAT', 1000),
        '1000RATS': ('RATS', 1000),
    },
}

# Spot identities independently named by official index components. A listing
# must ALSO be present and trading in that venue's live instrument metadata.
SPOTS = {
    'binance': 'PEPE SHIB BONK FLOKI LUNC XEC TURBO'.split(),
    'okx': 'PEPE SHIB BONK FLOKI CAT BABYDOGE SATS TOSHI TURBO'.split(),
    'bybit': 'PEPE SHIB BONK FLOKI LUNC RATS CAT BABYDOGE MOG SATS BTT NEIROCTO TOSHI'.split(),
    'bitget': 'PEPE BONK FLOKI RATS CHEEMS MOG BTT NEIROCTO TAG'.split(),
    'gate': 'PEPE SHIB BONK FLOKI LUNC XEC RATS CHEEMS MOG BABYDOGE SATS BTT TAG TOSHI TURBO'.split(),
}


def native(venue, market, base):
    return base + ('_USDT' if venue == 'gate' else
                   '-USDT-SWAP' if venue == 'okx' and market == 'future' else
                   '-USDT' if venue == 'okx' else 'USDT')


REGISTRY = {}
for venue, bases in SPOTS.items():
    for base in bases:
        REGISTRY[venue, 'spot', native(venue, 'spot', base)] = (base, base, 1)
        # Same native token's perpetual, if actually listed. No aliases here.
        REGISTRY[venue, 'future', native(venue, 'future', base)] = (base, base, 1)
for venue, entries in FUTURES.items():
    for base, (asset, units) in entries.items():
        REGISTRY[venue, 'future', native(venue, 'future', base)] = (base, asset, units)
for base, asset, units in [('1000CAT', 'CAT', 1000), ('1000SATS', 'SATS', 1000),
                           ('1000CHEEMS', 'CHEEMS', 1000), ('1MBABYDOGE', 'BABYDOGE', 1000000),
                           ('BTTC', 'BTT', 1), ('NEIRO', 'NEIROCTO', 1)]:
    REGISTRY['binance', 'spot', native('binance', 'spot', base)] = (base, asset, units)


def denomination(q):
    if not q or not q.get('instrumentVerified') or q.get('quote') != 'USDT':
        return None
    record = REGISTRY.get(tuple(q.get(k) for k in ('exchange', 'market', 'symbol')))
    if not record or record[0] != q.get('base') or q.get('unit', q['base']) != q['base']:
        return None
    return dict(assetId=record[1], units=str(record[2]), denominationVersion=VERSION)


def converted(q, target):
    """Copy a verified quote into the ORIGINAL rule's native price unit.

    Keep raw quote/timestamps untouched. Mapping/version is part of source
    identity, so a queued event cannot be sent under a different conversion.
    """
    origin = denomination(q)
    if not origin or origin['assetId'] != target.get('assetId'):
        return None
    with localcontext() as ctx:
        ctx.prec = 80
        factor = Decimal(target['units']) / Decimal(origin['units'])
        result = dict(q)
        for kind in ('last', 'mark'):
            if q.get(kind) is not None:
                result[kind] = format(number(q[kind]) * factor, 'f')
    result.update(rawLast=q.get('last'), conversionFactor=format(factor, 'f'),
                  targetUnit=target['unit'], assetId=origin['assetId'],
                  denominationVersion=VERSION)
    return result

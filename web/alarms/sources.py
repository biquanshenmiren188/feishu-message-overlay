"""Exact instrument identities and deterministic, persisted quote failover.

Never remove numeric prefixes, alias wrapped assets, or convert quote currencies.
Candidate warm-up compares simultaneous prices; it is an extra sanity check,
not evidence that similarly named tokens are the same asset.
"""
import math
import re
from engine import number, FALLBACK_VENUES

SPOT_PRIORITY = ('binance', 'okx', 'bybit', 'bitget', 'gate')
MAX_AGE = 12
# Tickers with known collisions require a reviewed asset-specific mapping.
AMBIGUOUS = frozenset(('PAY', 'TIME', 'KEY', 'DODOX', 'LUNA', 'LUNC', 'BTG'))


def backup_venues(rule):
    choice = rule.get('fallbackExchange', 'auto')
    venues = SPOT_PRIORITY if choice == 'auto' else (choice,) if choice in FALLBACK_VENUES else ()
    return tuple(v for v in venues if v != rule['exchange'])


def identity(q):
    if not q or not q.get('instrumentVerified'):
        return None
    base, quote = q.get('base'), q.get('quote')
    if not isinstance(base, str) or not re.fullmatch(r'[A-Z0-9][A-Z0-9._-]{0,39}', base) or quote != 'USDT':
        return None
    # Metadata contract size is an order quantity, never a price multiplier.
    return dict(base=base, quote=quote, unit=q.get('unit', base), pair=base + '/' + quote, fallbackAllowed=q.get('fallbackAllowed', True))


def eligible(asset):
    return bool(asset and asset.get('fallbackAllowed', True) and asset['unit'] == asset['base'] and asset['base'] not in AMBIGUOUS
                and not re.match(r'^\d', asset['base'])
                and not re.search(r'(?:[235](?:L|S)|UP|DOWN|BULL|BEAR)$', asset['base']))


def fresh(q, kind, now):
    try:
        observed = float(q['observedAt'])
        stamp = float(q.get(kind + 'At') or observed)
        return (math.isfinite(stamp) and math.isfinite(observed)
                and -2 <= now - observed <= MAX_AGE and -2 <= now - stamp <= MAX_AGE
                and bool(number(q.get(kind))))
    except (ValueError, TypeError, KeyError, AttributeError):
        return False


def source(q, kind, fallback=False):
    return dict(exchange=q['exchange'], market=q['market'], symbol=q['symbol'], priceType=kind, fallback=fallback)


def source_key(s):
    return tuple(s.get(k) for k in ('exchange', 'market', 'symbol', 'priceType')) if s else None


def select(rule, previous, quotes, now, advance=True):
    """Return effective quote, evaluation rule, routing state; no IO or config edits.

    Recovery counts DISTINCT successful requests, never watch-loop iterations.
    Send-time callers do not advance recovery or candidate qualification.
    """
    state = dict(previous)
    primary_key = rule['exchange'], rule['market'], rule['symbol']
    primary = quotes.get(primary_key)
    asset = identity(primary) or state.get('asset')
    if asset:
        if state.get('asset') != asset:
            state.pop('qualifiedSources', None)
        state['asset'] = asset
    primary_ok = fresh(primary, rule['priceType'], now)
    primary_source = dict(exchange=rule['exchange'], market=rule['market'], symbol=rule['symbol'], priceType=rule['priceType'], fallback=False)
    old_source = state.get('source') or primary_source
    candidates = []
    if eligible(asset):
        for venue in backup_venues(rule):
            matching = [q for k, q in quotes.items() if k[:2] == (venue, 'spot') and identity(q) == asset]
            # Ambiguous listings in the same venue are never selected.
            if len(matching) == 1 and fresh(matching[0], 'last', now):
                candidates.append(matching[0])
    # Qualify only while both sources are live, with three distinct paired samples.
    qualified = dict(state.get('qualifiedSources', {}))
    if advance and primary_ok:
        for q in candidates:
            key = q['exchange'] + ':' + q['symbol']
            record = dict(qualified.get(key, {}))
            stamp = [primary['observedAt'], q['observedAt']]
            ratio = number(q['last']) / number(primary[rule['priceType']])
            if not .95 <= ratio <= 1.05:
                qualified.pop(key, None)
            elif stamp[0] != record.get('stamp', [None, None])[0] and stamp[1] != record.get('stamp', [None, None])[1]:
                record.update(stamp=stamp, count=min(3, record.get('count', 0) + 1), at=now)
                qualified[key] = record
        state['qualifiedSources'] = qualified
    fresh_candidates = len(candidates)
    candidates = [q for q in candidates if qualified.get(q['exchange'] + ':' + q['symbol'], {}).get('count', 0) >= 3
                  and now - qualified[q['exchange'] + ':' + q['symbol']].get('at', 0) <= 86400]
    recovering = old_source.get('fallback', False)
    count = state.get('primaryRecoveryCount', 0)
    if advance:
        if primary_ok:
            if primary['observedAt'] != state.get('primaryRecoveryStamp'):
                count = min(3, count + 1)
                state['primaryRecoveryStamp'] = primary['observedAt']
        else:
            count = 0
            state.pop('primaryRecoveryStamp', None)
        state['primaryRecoveryCount'] = count
    # Stay on a healthy fallback until primary has three distinct healthy samples.
    selected = primary if primary_ok and (not recovering or count >= 3) else None
    selected_source = primary_source
    if selected is None and candidates:
        selected = next((q for q in candidates if source_key(source(q, 'last', True)) == source_key(old_source)), candidates[0])
        selected_source = source(selected, 'last', True)
    # If backup also fails, any fresh primary is preferable to a blind gap.
    if selected is None and primary_ok:
        selected, selected_source = primary, primary_source
    effective = dict(rule, priceType=selected_source['priceType'])
    if selected is not None:
        if source_key(selected_source) != source_key(old_source):
            # Cross-venue timestamps need not be monotonic. Start a gap, retain cadence.
            state.pop('sampleAt', None)
            state.update(gap=True, pending=None)
        state['source'] = selected_source
        state['sourceStatus'] = 'fallback' if selected_source['fallback'] else 'primary'
        state['routingReason'] = 'healthy_backup' if selected_source['fallback'] else 'healthy_primary'
    else:
        state['sourceStatus'] = 'unavailable'
        state['routingReason'] = ('backup_disabled' if rule.get('fallbackExchange') == 'off' else
                                  'asset_ineligible' if not eligible(asset) else
                                  'backup_unqualified' if fresh_candidates else 'no_fresh_backup')
    return selected, effective, state


def active_groups(rule, state):
    groups = {(rule['exchange'], rule['market'])}
    if eligible(state.get('asset')):
        groups.update((v, 'spot') for v in backup_venues(rule))
    return groups


def source_label(s):
    return f"{'备用行情：' if s.get('fallback') else ''}{s['exchange'].upper()} · {'现货' if s['market'] == 'spot' else '永续'} · {s['symbol']} · {'最新成交价' if s['priceType'] == 'last' else '标记价格'}"

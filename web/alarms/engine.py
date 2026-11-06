"""Decimal price crossings. No network, delivery or wall clock inside evaluation."""
from decimal import Decimal, InvalidOperation


def number(value):
    try:
        if isinstance(value, bool) or len(str(value)) > 64:
            raise ValueError()
        result = Decimal(str(value))
        if not result.is_finite() or result <= 0 or result > Decimal('1e18'):
            raise ValueError()
        return result
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('价格必须为大于零的有效数字') from None


def validate(raw):
    if not isinstance(raw, dict):
        raise ValueError('报警格式错误')
    rule = {k: raw.get(k) for k in ('exchange', 'market', 'symbol', 'priceType', 'condition')}
    if rule['exchange'] not in ('binance', 'bybit', 'okx', 'bitget', 'gate', 'aster'):
        raise ValueError('请选择支持的交易所')
    if rule['market'] not in ('spot', 'future') or rule['priceType'] not in ('last', 'mark'):
        raise ValueError('请选择市场和价格类型')
    if rule['market'] == 'spot' and rule['priceType'] != 'last':
        raise ValueError('现货只支持最新成交价')
    if not isinstance(rule['symbol'], str) or not 1 <= len(rule['symbol']) <= 64:
        raise ValueError('请选择交易对')
    if rule['condition'] not in ('above', 'below', 'enter', 'exit'):
        raise ValueError('请选择报警条件')
    rule['target'] = str(number(raw.get('target')))
    rule['upper'] = str(number(raw.get('upper'))) if rule['condition'] in ('enter', 'exit') else None
    if rule['upper'] and number(rule['upper']) <= number(rule['target']):
        raise ValueError('区间上限必须高于下限')
    for key, default, low, high in [('hold', 0, 0, 60), ('cooldown', 300, 30, 86400)]:
        value = raw.get(key, default)
        if type(value) is not int or not low <= value <= high:
            raise ValueError('确认时间或重复间隔不正确')
        rule[key] = value
    try:
        margin = Decimal(str(raw.get('hysteresis', '0.2')))
        if not margin.is_finite() or not Decimal('0') <= margin <= Decimal('10'):
            raise ValueError()
    except (InvalidOperation, ValueError):
        raise ValueError('恢复幅度应为 0 至 10%') from None
    rule['hysteresis'] = str(margin)
    for key, default in [('repeat', False), ('immediate', False), ('recovery', False), ('enabled', True)]:
        if type(raw.get(key, default)) is not bool:
            raise ValueError('报警开关格式错误')
        rule[key] = raw.get(key, default)
    rule['expiresAt'] = raw.get('expiresAt')
    if rule['expiresAt'] is not None and (type(rule['expiresAt']) not in (int, float) or not 0 < rule['expiresAt'] < 4102444800):
        raise ValueError('有效期不正确')
    rule['level'] = raw.get('level', 'active')
    if rule['level'] not in ('active', 'timeSensitive'):
        raise ValueError('提醒方式不正确')
    rule['note'] = raw.get('note', '')
    if not isinstance(rule['note'], str) or len(rule['note']) > 100:
        raise ValueError('备注最多 100 字')
    return rule


def matches(rule, price):
    low = number(rule['target'])
    kind = rule['condition']
    if kind == 'above':
        return price >= low
    if kind == 'below':
        return price <= low
    high = number(rule['upper'])
    return low <= price <= high if kind == 'enter' else price < low or price > high


def recovered(rule, price):
    low = number(rule['target'])
    margin = Decimal(rule['hysteresis']) / 100
    if rule['condition'] == 'above':
        return price < low and price <= low * (1 - margin)
    if rule['condition'] == 'below':
        return price > low and price >= low * (1 + margin)
    high = number(rule['upper'])
    if rule['condition'] == 'enter':
        return (price < low and price <= low * (1 - margin)) or (price > high and price >= high * (1 + margin))
    # For a narrow exit range, cap hysteresis at a quarter of its width.
    band = min(low * margin, (high - low) / 4)
    return low + band <= price <= high - band


def evaluate(rule, previous, quote, now, max_age=12):
    state = dict(previous)
    if not rule['enabled']:
        return dict(state, status='paused', pending=None), None
    if rule['expiresAt'] and now >= rule['expiresAt']:
        return dict(state, status='expired', pending=None), None
    if state.get('fired') and not rule['repeat']:
        return dict(state, status='triggered', pending=None), None
    if not quote or now - quote['observedAt'] > max_age or quote['observedAt'] > now + 2:
        return dict(state, status='stale', pending=None, gap=True), None
    try:
        price = number(quote.get(rule['priceType']))
    except ValueError:
        return dict(state, status='unavailable', pending=None, gap=True), None
    stamp = quote.get(rule['priceType'] + 'At') or quote['observedAt']
    if now - stamp > max_age or stamp > now + 2:
        return dict(state, status='stale', pending=None, gap=True), None
    if stamp <= state.get('sampleAt', 0):
        return state, None
    gap = state.get('gap', False) or bool(state.get('sampleAt') and stamp - state['sampleAt'] > max_age)
    hit = matches(rule, price)
    first = 'sampleAt' not in state
    state.update(price=str(price), sampleAt=stamp, observedAt=quote['observedAt'], gap=False)
    if first or gap:
        state.update(armed=not hit, pending=None)
        if hit and ((first and rule['immediate']) or (gap and rule['recovery'])):
            state.update(armed=True, pending=now, reason='recovery' if gap else 'initial')
    if not hit:
        state['pending'] = None
        if recovered(rule, price):
            state['armed'] = True
    if hit and state.get('armed'):
        if state.get('pending') is None:
            state.update(pending=now, reason='crossing')
        if now - state['pending'] >= rule['hold'] and now >= state.get('lastFire', 0) + (rule['cooldown'] if state.get('fired') else 0):
            reason = state.get('reason', 'crossing')
            state.update(armed=False, pending=None, lastFire=now, fired=True, status='watching' if rule['repeat'] else 'triggered')
            return state, dict(price=str(price), sampleAt=stamp, at=now, reason=reason)
    state['status'] = 'confirming' if state.get('pending') is not None else 'watching' if state.get('armed') else 'waiting'
    return state, None

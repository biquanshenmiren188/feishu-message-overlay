"""Receive all levels by default, with explicit exclusions."""
import copy,math,re
import advanced_rules
from decimal import Decimal

DEFAULTS = dict(rows=4, excluded_ranks=[], excluded_modes=[], min_percent=None,
                excluded_coins=[], excluded_exchanges=[], notify_enabled=True, notify_interval_seconds=60)
EXCHANGES = ['BINANCE', 'BITGET', 'BYBIT', 'OKX', 'GATE', 'ASTER', 'HL']
INTERVALS = [30, 60, 180, 300, 600, 1800]


def normalize_rank(value):
    match = re.fullmatch(r'R(\d{1,24})(\+?)', value.upper(), re.ASCII)
    if not match:
        raise ValueError('等级格式无效')
    return 'R'+str(int(match[1]))+match[2]


def validate(raw):
    if not isinstance(raw, dict) or set(raw) not in (set(DEFAULTS), set(DEFAULTS)|{'advanced'}):
        raise ValueError('设置字段不完整，请重新打开设置')
    out = copy.deepcopy(raw)
    if 'advanced' in out:out['advanced']=advanced_rules.validate(out['advanced'])
    if type(out['rows']) is not int or not 1 <= out['rows'] <= 4:
        raise ValueError('显示条数必须在 1–4 条之间')
    if type(out['notify_enabled']) is not bool:
        raise ValueError('提醒开关无效')
    if type(out['notify_interval_seconds']) is not int or out['notify_interval_seconds'] not in INTERVALS:
        raise ValueError('请选择有效的提醒间隔')
    for field, allowed in [('excluded_modes', ['SF', 'FS', 'FF']), ('excluded_exchanges', EXCHANGES)]:
        values = out[field]
        if not isinstance(values, list) or len(values) > len(allowed) or any(type(v) is not str or v not in allowed for v in values):
            raise ValueError('筛选选项无效')
        out[field] = [v for v in allowed if v in values]
    ranks = out['excluded_ranks']
    if not isinstance(ranks, list) or len(ranks) > 100 or any(not isinstance(v, str) for v in ranks):
        raise ValueError('屏蔽等级无效')
    out['excluded_ranks'] = sorted(set(normalize_rank(v) for v in ranks))
    coins = out['excluded_coins']
    if not isinstance(coins, list) or len(coins) > 50 or any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,23}', v) for v in coins):
        raise ValueError('币种最多 50 个，只填币种代码，例如 BTC、ETH')
    out['excluded_coins'] = sorted(set(v.upper() for v in coins))
    v = out['min_percent']
    if v is not None and (type(v) not in (int, float) or not math.isfinite(v) or not -100 <= v <= 100):
        raise ValueError('最低百分比需在 -100 到 100 之间，留空表示不限')
    return out


def matches(row, settings):
    return not exclusion_reasons(row,settings)

def exclusion_reasons(row,settings):
    reasons=[]
    if row['rank'] in settings['excluded_ranks'] or row['rank'].rstrip('+') in settings['excluded_ranks']:reasons.append(row['rank']+' 等级屏蔽')
    if row['mode'] in settings['excluded_modes']:reasons.append(row['mode']+' 类型屏蔽')
    if row['coin'] in settings['excluded_coins']:reasons.append(row['coin']+' 币种屏蔽')
    for ex in set((row['buy'],row['sell'])):
        if ex in settings['excluded_exchanges']:reasons.append(ex+' 整所屏蔽')
    if settings['min_percent'] is not None and Decimal(row['value'].rstrip('%')) < Decimal(str(settings['min_percent'])):reasons.append('R 百分比低于 '+str(settings['min_percent'])+'%')
    return reasons+advanced_rules.reasons(row,settings.get('advanced'))

"""Receive all levels by default, with explicit exclusions."""
import copy,math,re
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
    if not isinstance(raw, dict) or set(raw) != set(DEFAULTS):
        raise ValueError('设置字段不完整，请重新打开设置')
    out = copy.deepcopy(raw)
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
    return (row['rank'] not in settings['excluded_ranks'] and row['rank'].rstrip('+') not in settings['excluded_ranks'] and row['mode'] not in settings['excluded_modes']
            and row['coin'] not in settings['excluded_coins']
            and row['buy'] not in settings['excluded_exchanges'] and row['sell'] not in settings['excluded_exchanges']
            and (settings['min_percent'] is None or Decimal(row['value'].rstrip('%')) >= Decimal(str(settings['min_percent']))))

"""Normalize authorized BOT opportunities; percentages come only from R ranks."""
import hashlib,json,re,unicodedata
from datetime import datetime

EXCHANGES = {'BINANCE': 'BINANCE', 'BITGET': 'BITGET', 'BYBIT': 'BYBIT',
             'OKX': 'OKX', 'OKEX': 'OKX', 'GATE': 'GATE', 'GATE.IO': 'GATE',
             'ASTER': 'ASTER', 'HYPERLIQUID': 'HL', 'HL': 'HL', 'HYPER': 'HL', 'HY': 'HL'}
RANK = re.compile(r'(?<![A-Z0-9])R([0-9]{1,24})(?=\s|[+-])(\+(?=\s))?\s*([+-]?\d+(?:\.\d+)?)\s*%(?![\d.])', re.I)
TITLE = re.compile(r'^\s*([A-Z0-9][A-Z0-9._-]{0,23})\s*[|·]\s*(SF|FS|FF)\b', re.I)
DIRECTION = re.compile(r'(?:买入|买|做多)\s*([A-Z][A-Z0-9.]*)\s*(现货|永续|合约)?\s*(?:→|->|⇒)\s*(?:卖出|卖|做空)\s*([A-Z][A-Z0-9.]*)\s*(现货|永续|合约)?', re.I)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def stamp(value):
    try:
        d = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return d.timestamp() if d.tzinfo else None
    except (TypeError, ValueError, AttributeError):
        return None


def clean(value):
    return unicodedata.normalize('NFKC', value).replace('**', '').replace('`', '')


def parse_message(message, now):
    if not isinstance(message, dict) or message.get('senderType') != 'bot':
        return None
    mid, title, body = (message.get(k) for k in ('id', 'title', 'body'))
    sent = stamp(message.get('sentAt'))
    if not isinstance(mid, str) or not re.fullmatch(r'[0-9a-f]{64}', mid):
        return None
    if not isinstance(title, str) or not isinstance(body, str) or len(title) > 1024 or len(body) > 16000:
        return None
    if sent is None or sent > now + 30 or now - sent > 1800:
        return None
    title, body = clean(title), clean(body)
    head, ranks, directions = TITLE.search(title), RANK.findall(title), DIRECTION.findall(body)
    # The percentage must follow the R rank in the title. Never substitute net/funding rates.
    if not head or len(ranks) != 1 or len(directions) != 1:
        return None
    coin, mode = head.group(1).upper(), head.group(2).upper()
    buy, buy_kind, sell, sell_kind = directions[0]
    buy, sell = EXCHANGES.get(buy.upper()), EXCHANGES.get(sell.upper())
    if not buy or not sell or (buy == sell and mode == 'FF'):
        return None
    for actual, expected in zip((buy_kind, sell_kind), mode):
        if actual and ('S' if actual == '现货' else 'F') != expected:
            return None
    rank, suffix, value = ranks[0]
    if len(value) > 12:
        return None
    if not value.startswith(('+', '-')):
        value = '+' + value
    fields = dict(coin=coin, mode=mode, buy=buy, sell=sell, rank='R'+str(int(rank))+suffix, value=value+'%')
    return dict(fields, id=mid, at=int(sent), fingerprint=digest(fields))


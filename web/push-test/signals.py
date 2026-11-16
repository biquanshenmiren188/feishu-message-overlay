"""Normalize BOT rank percentages and explicit per-route strong-signal values."""
import hashlib,json,re,unicodedata
from datetime import datetime
from functools import lru_cache

EXCHANGES = {'BINANCE': 'BINANCE', 'BITGET': 'BITGET', 'BYBIT': 'BYBIT',
             'OKX': 'OKX', 'OKEX': 'OKX', 'GATE': 'GATE', 'GATE.IO': 'GATE',
             'ASTER': 'ASTER', 'HYPERLIQUID': 'HL', 'HL': 'HL', 'HYPER': 'HL', 'HY': 'HL'}
RANK = re.compile(r'(?<![A-Z0-9])R([0-9]{1,24})(?=\s|[+-])(\+(?=\s))?\s*([+-]?\d+(?:\.\d+)?)\s*%(?![\d.])', re.I)
# Accept Unicode symbols up to the coin rules' 32-character limit. A namespace
# remains part of the identity; never turn xyz:ABC into the unrelated ABC coin.
COIN = r'\w[\w.:-]{0,31}'
TITLE = re.compile(r'^\s*('+COIN+r')\s*[|·]\s*(SF|FS|FF)\b', re.I)
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


def message_fields(message, now, *, max_age=1800):
    if not isinstance(message, dict) or message.get('senderType') != 'bot':
        return None
    mid, title, body = (message.get(k) for k in ('id', 'title', 'body'))
    sent = stamp(message.get('sentAt'))
    if not isinstance(mid, str) or not re.fullmatch(r'[0-9a-f]{64}', mid):
        return None
    if not isinstance(title, str) or not isinstance(body, str) or len(title) > 1024 or len(body) > 16000:
        return None
    if sent is None or sent > now + 30 or (max_age is not None and now - sent > max_age):
        return None
    return mid, clean(title), clean(body), sent


def parse_message(message, now, *, max_age=1800):
    source = message_fields(message, now, max_age=max_age)
    if source is None:
        return None
    mid, title, body, sent = source
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


def parse_messages(message, now, *, max_age=1800):
    """Ordinary rank percentage, or explicit per-route strong-signal blocks."""
    single = parse_message(message, now, max_age=max_age)
    if single is not None:
        return [single]
    source = message_fields(message, now, max_age=max_age)
    if source is None:
        return []
    mid, title, body, sent = source
    header = re.fullmatch(r'\s*(?:🚨\s*)*强信号聚集\s*[|·]\s*('+COIN+r')\s*[|·]\s*(\d{1,2})\s*组同时\s+ACTIVE\s*', title, re.I)
    if not header or not 1 <= int(header[2]) <= 50:
        return []
    # The observed V2 source adds this fixed window before each route's net
    # value. Keep the value on the immediately following line and require all
    # declared groups; headline percentages and adjacent routes are not values.
    net_prefix = r'(?:V2收敛[ \t]*·[ \t]*[1-9]\d{0,5}秒[ \t]*·[ \t]*)?'
    blocks = re.findall(r'^\s*R(\d{1,24})(\+?)\s*[|·]\s*(SF|FS|FF)\s*[|·]\s*([^\n]+)\n[ \t]*'+net_prefix+r'净均[ \t]*([+-]?\d+(?:\.\d+)?)[ \t]*%[ \t]*·[ \t]*ACTIVE[^\n]*$', body, re.M | re.I)
    if len(blocks) != int(header[2]):
        return []
    result = []
    for rank, suffix, mode, route, value in blocks:
        direction = DIRECTION.fullmatch(route.strip())
        if not direction or len(value) > 12:
            return []
        buy, buy_kind, sell, sell_kind = direction.groups()
        buy, sell, mode = EXCHANGES.get(buy.upper()), EXCHANGES.get(sell.upper()), mode.upper()
        if not buy or not sell or (buy == sell and mode == 'FF'):
            return []
        if any(actual and ('S' if actual == '现货' else 'F') != expected
               for actual, expected in zip((buy_kind, sell_kind), mode)):
            return []
        if not value.startswith(('+', '-')):
            value = '+' + value
        fields = dict(coin=header[1].upper(), mode=mode, buy=buy, sell=sell,
                      rank='R'+str(int(rank))+suffix, value=value+'%')
        # Each route has its own identity and still deduplicates with normal
        # signals through the existing content fingerprint.
        result.append(dict(fields, id=digest([mid, fields]), at=int(sent), fingerprint=digest(fields), aggregate=True))
    return result


def desktop_rows(message, now):
    """Filter retained desktop history, independently of the mobile send window.

    Only explicit source formats produce rows. P-priority and topic take prices
    are not R ranks or R percentages, so they keep coin/route/OI checks only.
    """
    rows=parse_messages(message,now,max_age=None)
    if rows:return rows
    fields=message_fields(message,now,max_age=None)
    if not fields:return []
    mid,title,body,sent=fields
    result=[]

    def add(coin,mode,buy,sell,buy_kind='',sell_kind='',**extra):
        buy,sell=EXCHANGES.get(buy.upper()),EXCHANGES.get(sell.upper())
        invalid=not buy or not sell or (buy==sell and mode=='FF') or any(
            kind and ('S' if kind=='现货' else 'F')!=expected
            for kind,expected in zip((buy_kind,sell_kind),mode))
        row=dict(id=mid,coin=coin.upper(),mode=mode,buy=buy or '',sell=sell or '',
                 rank='',value='0%',at=sent,unranked=True)
        row.update(extra)
        if invalid:row['invalidSignal']=True
        result.append(row)

    # A clearly identified strong-signal envelope must not become an unrelated
    # announcement when one route/value is damaged. The strict parser above
    # rejected the whole group, so do not borrow another route's R percentage.
    # Preserve only identifiable coin/route context for the existing invalid
    # signal policy (filtered profiles protect; receive-all stays unchanged).
    strong=re.match(r'^\s*(?:🚨\s*)*强信号聚集\s*[|·]\s*('+COIN+r')(?=\s*(?:[|·]|$))',title,re.I)
    if strong:
        routes=re.findall(r'^\s*R[^|·\n]*[|·]\s*(SF|FS|FF)\s*[|·]\s*([^\n]+)$',body,re.M|re.I)
        for mode,route in routes:
            direction=DIRECTION.fullmatch(route.strip())
            if direction:
                buy,bk,sell,sk=direction.groups()
                add(strong[1],mode.upper(),buy,sell,bk,sk,invalidSignal=True)
        if not result:add(strong[1],'','','',invalidSignal=True)
        return result

    # Actual source envelope and numbered entries, as used by the native and
    # webpage summary parsers. Do not infer a topic from arbitrary prose.
    topic=re.search(r'^\s*\[Binance\s*/\s*Aster\s+专题价差\]',title+'\n'+body,re.M|re.I)
    if topic:
        pattern=r'^\s*\d+[.、)]\s*('+COIN+r')\s*[|·]\s*多\s+([A-Z][A-Z0-9.]*)\s*/\s*空\s+([A-Z][A-Z0-9.]*)\s*$'
        for coin,buy,sell in re.findall(pattern,body,re.M|re.I):
            add(coin,'FF',buy,sell,invalidSignal=buy.upper() not in ('BINANCE','ASTER') or sell.upper() not in ('BINANCE','ASTER'))
        return result

    dex=r'^\s*\d+[.、)]\s*\[P\d+\+?\]\s*\[(期期|现期|期现|FF|SF|FS)\]\s*('+COIN+r')\s*[|·]\s*多\s+([A-Z][A-Z0-9.]*)(?:\s+(现货|合约|永续))?\s*/\s*(?:空|借卖)\s+([A-Z][A-Z0-9.]*)(?:\s+(现货|合约|永续))?\s*$'
    for mode,coin,buy,bk,sell,sk in re.findall(dex,body,re.M|re.I):
        add(coin,{'期期':'FF','现期':'SF','期现':'FS'}.get(mode,mode.upper()),buy,sell,bk,sk)
    if result:return result

    # Legacy topic titles can carry a normal R value. Preserve it if present;
    # a malformed R signal must not masquerade as an intentionally unranked one.
    head=re.search(r'(?:^|[|·])\s*('+COIN+r')\s*[|·]\s*(SF|FS|FF)\b',title,re.I)
    if not head:return []
    ranks=RANK.findall(title)
    has_rank=re.search(r'(?<![\w])R\d',title,re.I) is not None
    extra={}
    if has_rank:
        if len(ranks)==1 and len(ranks[0][2])<=12:
            rank,suffix,value=ranks[0]
            extra=dict(rank='R'+str(int(rank))+suffix,value=(value if value.startswith(('+','-')) else '+'+value)+'%',unranked=False)
        else:extra=dict(invalidSignal=True,unranked=False)
    directions=DIRECTION.findall(body)
    for buy,bk,sell,sk in directions:
        add(head[1],head[2].upper(),buy,sell,bk,sk,**extra)
    if has_rank and not directions:
        add(head[1],head[2].upper(),'','',**extra)
    return result



# Cache syntax parsing only. Age and clock validation run on EVERY call; mutable
# OI/rule enrichment always receives fresh row dictionaries. Bounded per process.
_parse_messages_uncached = parse_messages

@lru_cache(maxsize=128)
def _parsed_content(mid, title, body, sent_at, sent):
    return _parse_messages_uncached(dict(senderType='bot', id=mid, title=title,
                                        body=body, sentAt=sent_at), sent, max_age=None)

def parse_messages(message, now, *, max_age=1800):
    fields = message_fields(message, now, max_age=max_age)
    if fields is None:
        return []
    mid, title, body, sent = fields
    return [dict(row) for row in _parsed_content(mid, message['title'], message['body'], message['sentAt'], sent)]

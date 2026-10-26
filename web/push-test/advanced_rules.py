"""Optional per-leg exclusions and OI thresholds; legacy settings remain valid."""
import copy
import math
import re
import time
import json
from urllib.request import urlopen
from hyperliquid_oi import hyperliquid_oi
from oi_source_cache import shared_read_many

VENUES = ('binance','bitget','bybit','okx','gate','aster','hyperliquid')
DEFAULT = dict(coins=[], legRules=[], globalOI=None, exchangeOI={}, coinOI=[], missing='block')

def amount(value):
    return value is None or (type(value) in (float,int) and math.isfinite(value) and 0 <= value <= 1e12)

def symbol(value):
    return isinstance(value,str) and bool(re.fullmatch(r'[\w.-]{1,32}',value,re.UNICODE))

def validate(value):
    if not isinstance(value,dict) or set(value)!=set(DEFAULT):
        raise ValueError('扩展规则字段不完整，请重新加载')
    out=copy.deepcopy(value)
    if not amount(out['globalOI']) or out['missing'] not in ('block','allow'):
        raise ValueError('OI 门槛或缺失策略无效')
    for key in ('coins','legRules','coinOI'):
        if not isinstance(out[key],list) or len(out[key])>100:
            raise ValueError('规则最多 100 条')
        for r in out[key]:
            fields={'exchange','enabled'} | ({'side','market'} if key=='legRules' else {'coin','value'} if key=='coinOI' else {'coin'})
            if not isinstance(r,dict) or set(r)!=fields or type(r['enabled']) is not bool:
                raise ValueError('规则格式无效')
            if r['exchange'] not in (*VENUES,'all') or (r['exchange']=='all' and key!='coins'):
                raise ValueError('规则交易所无效')
            if key=='legRules':
                if r['side'] not in ('left','right','all') or r['market'] not in ('spot','perp','all'):
                    raise ValueError('方向或市场无效')
            else:
                if not symbol(r['coin']):raise ValueError('币种格式无效')
                r['coin']=r['coin'].upper()
                if key=='coinOI' and not amount(r['value']):raise ValueError('OI 门槛无效')
    if not isinstance(out['exchangeOI'],dict) or any(e not in VENUES for e in out['exchangeOI']):
        raise ValueError('OI 交易所无效')
    for r in out['exchangeOI'].values():
        if not isinstance(r,dict) or set(r)!={'mode','value'} or r['mode'] not in ('inherit','custom','none') or not amount(r['value']) or (r['mode']=='custom' and r['value'] is None):
            raise ValueError('交易所 OI 门槛无效')
    return out

def venue(v):return 'hyperliquid' if v in ('HL','HY','HYPERLIQUID') else v.lower()

def threshold(a,coin,exchange):
    special=next((r for r in a.get('coinOI',[]) if r['enabled'] and r['coin']==coin and r['exchange']==exchange),None)
    if special:return special['value']
    r=a.get('exchangeOI',{}).get(exchange,{})
    if r.get('mode')=='none':return None
    if r.get('mode')=='custom':return r['value']
    return a.get('globalOI')

def legs(row):
    return [('left',venue(row['buy']),'spot' if row['mode'].startswith('S') else 'perp'),
            ('right',venue(row['sell']),'spot' if row['mode'].endswith('S') else 'perp')]

def reasons(row,a):
    if not a:return []
    result=[]
    for side,ex,market in legs(row):
        side_name='左腿' if side=='left' else '右腿'
        for r in a['coins']:
            if r['enabled'] and r['coin']==row['coin'] and r['exchange'] in ('all',ex):
                result.append(row['coin']+' 币种屏蔽 · '+ex)
        for r in a['legRules']:
            if r['enabled'] and r['exchange']==ex and r['side'] in ('all',side) and r['market'] in ('all',market):
                result.append(ex+' '+side_name+' · '+('现货' if market=='spot' else '永续')+' 定向屏蔽')
        limit=threshold(a,row['coin'],ex)
        if market=='perp' and limit is not None:
            data=row.get('oi',{}).get(side,{})
            if not isinstance(data,dict):data={}
            value=data.get('value')
            now=row.get('oiCheckedAt',time.time())*1000
            ts=data.get('time',0)
            fresh=type(ts) in (int,float) and math.isfinite(ts) and -30000 <= now-ts <= 300000
            if ex=='hyperliquid':
                expiry=data.get('expiresAt')
                fresh=fresh and type(expiry) in (int,float) and math.isfinite(expiry) and now<=expiry
            if type(value) not in (int,float) or not math.isfinite(value) or value<0 or not fresh or data.get('basis')!='double-v1':
                if a['missing']=='block':result.append(ex+' '+side_name+' OI 缺失或过期')
            elif value < limit*10000:
                result.append(ex+' '+side_name+' OI 低于 '+str(limit)+' 万 USDT')
    return list(dict.fromkeys(result))

class OISnapshot:
    """Read the site's existing normalized OI cache, never a different venue's OI.

    The shared relay reports double-v1 USD notional, matching the radar UI.
    Aster is collected separately by market-stats, just as on the main site;
    the relay's open-interest route does not support it. Its official website
    value is already double-sided USDT. Preserve its observation timestamp and
    basis: reading the cache must neither double the amount nor renew its age.
    Exact USDT symbols only; ambiguous aliases remain missing.
    """
    def __init__(self, source_cache=None):
        self.cache={};self.at={}
        self.read_sources=source_cache.read_many if source_cache is not None else shared_read_many
    def _read(self,ex,now):
        try:
            url=('http://127.0.0.1:8795/api/hyperliquid/market' if ex=='hyperliquid' else
                 'http://127.0.0.1:8792/api/market-stats' if ex=='aster' else
                 'http://127.0.0.1:8787/api/open-interest?exchange='+ex+'&basis=double-v1')
            with urlopen(url,timeout=2) as response:
                raw=response.read(8*1024*1024+1)
            if len(raw)>8*1024*1024:raise ValueError('oversize')
            data=json.loads(raw)
            if ex=='hyperliquid':return ex,hyperliquid_oi(data,now*1000)
            if ex=='aster':
                return ex,data['asterOI'] if isinstance(data,dict) and isinstance(data.get('asterOI'),dict) else {}
            return ex,data['data'] if isinstance(data,dict) and data.get('basis')=='double-v1' and isinstance(data.get('data'),dict) else {}
        except (OSError,ValueError,TypeError):return ex,{}
    def enrich(self,rows,a,now):
        needed={ex for row in rows for _,ex,market in legs(row) if ex in VENUES and market=='perp' and threshold(a,row['coin'],ex) is not None}
        # Every consumer observes the shared source generation. A per-consumer
        # fetch timestamp would incorrectly prolong an already 29s-old cache.
        sources=self.read_sources(needed,now,{ex:10 if ex=='hyperliquid' else 30 for ex in needed},lambda ex:self._read(ex,now)[1])
        # Dormant consumers retain only requested symbols, not another complete
        # historical generation of every venue's thousands of contracts.
        keys={row['coin']+'USDT' for row in rows}
        self.cache={ex:{ex+':'+key:values[ex+':'+key] for key in keys if ex+':'+key in values} for ex,values in sources.items()}
        self.at={ex:now for ex in needed}
        for row in rows:
            row['oiCheckedAt']=now
            row['oi']={}
            for side,ex,market in legs(row):
                if market!='perp' or ex not in needed:continue
                value=self.cache.get(ex,{}).get(ex+':'+row['coin']+'USDT',{})
                if ex=='hyperliquid' and 'oiContracts' in row:
                    contract=row['oiContracts'].get(side)
                    # Cards have native leg symbols. A namespace or k-prefix
                    # must not be discarded to borrow another contract's OI.
                    if not isinstance(value,dict) or not isinstance(contract,str) or contract.upper() not in (str(value.get('nativeCoin','')).upper(),str(value.get('nativeSymbol','')).upper()):value={}
                row['oi'][side]=value

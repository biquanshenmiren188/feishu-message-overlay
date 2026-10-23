"""Separate desktop policies. Only the original owner may edit them.

Signed desktop readers request decisions through a loopback-only route. The
source feed and phone settings are never rewritten by this module.
"""
import copy, hashlib, json, os, re, threading, time
from pathlib import Path
from datetime import datetime
import preferences
from advanced_rules import DEFAULT as ADVANCED, OISnapshot, VENUES, symbol
from signals import parse_messages, message_fields, DIRECTION, EXCHANGES

def defaults():
    return dict(settings=dict(copy.deepcopy(preferences.DEFAULTS), advanced=copy.deepcopy(ADVANCED)), action='hide')

class DesktopRules:
    def __init__(self, directory, feed='/var/lib/robot-push/feed.json', cards='/var/lib/robot-push/basispulse.json'):
        self.path=Path(directory)/'desktop-rules.json'; self.feed=Path(feed); self.cards=Path(cards)
        self.lock=threading.RLock(); self.oi=OISnapshot(); self.last_seen=0
        self.data=json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else dict(revision=0, desktop=defaults(), cards=defaults(), history=[], seen={})
        desktop=self.data['desktop']
        if 'rules' not in desktop:
            desktop['rules']={action:copy.deepcopy(desktop['settings']) if desktop['action']==action else defaults()['settings'] for action in ('mute','hide')}
        self.card_cache_path=Path(directory)/'desktop-card-cache.json'
        try:self.card_cache=json.loads(self.card_cache_path.read_text())
        except (OSError,ValueError):self.card_cache={}

    def save(self):
        temp=self.path.with_suffix('.next')
        with open(temp,'w',encoding='utf-8') as f:
            os.chmod(temp,0o600); json.dump(self.data,f,ensure_ascii=False); f.flush(); os.fsync(f.fileno())
        os.replace(temp,self.path)

    def status(self):
        with self.lock:
            return copy.deepcopy({k:self.data[k] for k in ('revision','desktop','cards','history')})|{'connected':time.time()-self.last_seen<20}

    def configure(self, raw):
        if set(raw)!={'revision','channel','settings','action'} or raw['channel'] not in ('desktop','cards') or raw['action'] not in ('hide','mute'):
            raise ValueError('电脑规则字段无效')
        if raw['channel']=='cards' and raw['action']!='hide':raise ValueError('行情卡片仅控制显示，不产生提示音')
        settings=preferences.validate(raw['settings'])
        with self.lock:
            if type(raw['revision']) is not int or raw['revision']!=self.data['revision']:raise ValueError('电脑规则已在其他页面更新，请刷新后重试')
            previous=copy.deepcopy(self.data)
            if raw['channel']=='desktop':
                policy=self.data['desktop'];policy['settings']=settings;policy['action']=raw['action'];policy['rules'][raw['action']]=copy.deepcopy(settings)
                for rules in policy['rules'].values():rules['notify_enabled']=settings['notify_enabled']
            else:self.data['cards']=dict(settings=settings,action=raw['action'])
            self.data['revision']+=1
            try:self.save()
            except OSError:
                self.data=previous
                raise
            return self.status()

    def coin_state(self, account):
        with self.lock, account.lock:
            live=account.state['live']
            return dict(desktop=self.status(),mobile=dict(settings=copy.deepcopy(live['settings']),revision=live['revision']),operations=copy.deepcopy(self.data.get('coinOperations',[])))

    @staticmethod
    def add_coins(settings, coins, exchange):
        result=copy.deepcopy(settings)
        advanced=result.setdefault('advanced',copy.deepcopy(ADVANCED))
        for coin in coins:
            # Existing broader exclusions already cover this requested scope.
            if coin in result['excluded_coins'] or any(r['enabled'] and r['coin']==coin and r['exchange'] in ('all',exchange) for r in advanced['coins']):continue
            found=next((r for r in advanced['coins'] if r['coin']==coin and r['exchange']==exchange),None)
            if found:found['enabled']=True
            else:advanced['coins'].append(dict(coin=coin,exchange=exchange,enabled=True))
        return preferences.validate(result)

    def block_coins(self, raw, account):
        if set(raw)!={'requestId','coins','exchange'} or not isinstance(raw['requestId'],str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,64}',raw['requestId']):raise ValueError('一键屏蔽请求无效')
        if not isinstance(raw['coins'],list) or not 1<=len(raw['coins'])<=30 or any(not symbol(c) for c in raw['coins']) or raw['exchange'] not in (*VENUES,'all'):raise ValueError('请填写有效币种和交易所，每次最多30个币种')
        coins=sorted(set(c.upper() for c in raw['coins']));exchange=raw['exchange'];identity=raw['requestId']
        with self.lock, account.lock:
            operations=self.data.setdefault('coinOperations',[])
            operation=next((x for x in operations if x['id']==identity),None)
            if operation and (operation.get('kind')=='edit' or operation['coins']!=coins or operation['exchange']!=exchange):raise ValueError('重试内容不一致，请重新操作')
            if operation is None:
                operation=dict(id=identity,at=time.time(),coins=coins,exchange=exchange,results={c:dict(state='pending') for c in ('desktop','cards','mobile')})
                self.data['coinOperations']=[operation,*operations][:100]
                # Write intent first; an interrupted call can be retried with the same id.
                try:self.save()
                except OSError:
                    self.data['coinOperations']=operations
                    raise
            for channel in ('desktop','cards','mobile'):
                if operation['results'][channel]['state']=='saved':continue
                before=copy.deepcopy(self.data)
                try:
                    if channel=='mobile':
                        live=account.state['live'];settings=self.add_coins(live['settings'],coins,exchange)
                        if settings!=live['settings']:account.configure(dict(revision=live['revision'],settings=settings))
                    else:
                        current=self.data['desktop']['rules']['hide'] if channel=='desktop' else self.data['cards']['settings']
                        settings=self.add_coins(current,coins,exchange)
                        if settings!=current:
                            if channel=='desktop':
                                self.data['desktop']['rules']['hide']=settings
                                if self.data['desktop']['action']=='hide':self.data['desktop']['settings']=copy.deepcopy(settings)
                            else:self.data['cards']['settings']=settings
                            self.data['revision']+=1
                    operation['results'][channel]=dict(state='saved')
                    self.save()
                except (OSError,ValueError) as error:
                    self.data=before
                    operation=next(x for x in self.data['coinOperations'] if x['id']==identity)
                    operation['results'][channel]=dict(state='failed',error=str(error)[:120] if isinstance(error,ValueError) else '保存暂时失败，请重试')
                    self.save()
            return self.coin_state(account)|dict(operation=copy.deepcopy(operation))

    def edit_coins(self, raw, account):
        from coin_edits import edit_coins
        return edit_coins(self, raw, account)

    @staticmethod
    def rows(message, now):
        rows=parse_messages(message,now)
        if rows:return rows
        # Topic cards can omit an R value. Still enforce coin / route / OI.
        fields=message_fields(message,now)
        if not fields:return []
        mid,title,body,sent=fields
        head=re.search(r'(?:^|[|｜·])\s*([\w.-]{1,32})\s*[|｜·]\s*(SF|FS|FF)\b',title,re.I)
        directions=DIRECTION.findall(body)
        if not head:return []
        out=[]
        for buy,bk,sell,sk in directions:
            buy,sell=EXCHANGES.get(buy.upper()),EXCHANGES.get(sell.upper())
            if buy and sell:out.append(dict(id=mid,coin=head[1].upper(),mode=head[2].upper(),buy=buy,sell=sell,rank='',value='0%',at=sent,unranked=True))
        return out

    def decision(self, channel, identity, rows, now):
        policy=self.data[channel]; settings=policy['settings']; reasons=[];action='hide'
        if not settings['notify_enabled']:reasons=['接收已关闭']
        else:
            candidates=[('hide',policy['rules']['hide']),('mute',policy['rules']['mute'])] if channel=='desktop' else [('hide',settings)]
            for candidate,rule in candidates:
                checked=copy.deepcopy(rows)
                self.oi.enrich(checked,rule.get('advanced',ADVANCED),now)
                for row in checked:
                    check=rule if not row.get('unranked') else dict(rule,min_percent=None,excluded_ranks=[])
                    reasons.extend(preferences.exclusion_reasons(row,check))
                if reasons:action=candidate;break
        if not reasons:return None
        key=channel+':'+identity+':'+str(self.data['revision'])+':'+action
        reasons=list(dict.fromkeys(reasons))
        if key not in self.data['seen']:
            self.data['seen'][key]=now
            row=rows[0] if rows else {}
            self.data['history'].insert(0,dict(id=hashlib.sha256(key.encode()).hexdigest(),channel=channel,action=action,at=now,messageAt=row.get('at'),coin=row.get('coin','未识别组合'),mode=row.get('mode',''),buy=row.get('buy',''),sell=row.get('sell',''),rank=row.get('rank',''),value=row.get('value',''),reasons=reasons,revision=self.data['revision']))
            self.data['history']=self.data['history'][:200]
        return action

    def retained_cards(self, envelope, now):
        # The desktop retains removed cards as "expired" for 30 seconds. Keep
        # evaluating those exact cards too, including after edits or a restart.
        before=json.dumps(self.card_cache,sort_keys=True)
        snapshot=envelope.get('snapshot') or {};present=set()
        for card in snapshot.get('active',[])[:1000]:
            identity=card.get('pair') or card.get('id','')
            if not identity or len(identity)>512:continue
            present.add(identity)
            data={k:card.get(k) for k in ('id','pair','asset','strategy','v2Residual','validUntil')}
            data['details']={'legs':[{'exchange':leg.get('exchange')} for leg in card.get('details',{}).get('legs',[])[:2]]}
            self.card_cache[identity]={'card':data,'missing':None}
        for identity,entry in list(self.card_cache.items()):
            if identity not in present and snapshot.get('complete') and entry['missing'] is None:entry['missing']=now
            try:expires=datetime.fromisoformat(entry['card']['validUntil'].replace('Z','+00:00')).timestamp()
            except (ValueError,TypeError,AttributeError):expires=now if identity in present else 0
            if entry['missing'] is not None:expires=min(expires,entry['missing'])
            # One extra 30s window covers client polling/transport delay: its
            # local "missing" clock starts after the server observes removal.
            if now>=expires+60:del self.card_cache[identity]
        # Match the signed reader's bounded decision map; current cards win.
        if len(self.card_cache)>1100:
            order=sorted(self.card_cache,key=lambda key:(key in present,self.card_cache[key]['missing'] or now),reverse=True)
            self.card_cache={key:self.card_cache[key] for key in order[:1100]}
        if before!=json.dumps(self.card_cache,sort_keys=True):
            temp=self.card_cache_path.with_suffix('.next')
            with open(temp,'w',encoding='utf-8') as f:
                os.chmod(temp,0o600);json.dump(self.card_cache,f);f.flush();os.fsync(f.fileno())
            os.replace(temp,self.card_cache_path)
        return [entry['card'] for entry in self.card_cache.values()]

    def card_decisions(self, envelope, now):
        """One evaluator for desktop and authenticated BOT cards; caller holds lock."""
        decisions={}
        for card in self.retained_cards(envelope,now):
            legs=card.get('details',{}).get('legs',[]);mode=card.get('strategy');rows=[]
            if len(legs)==2 and mode in ('SF','FS','FF'):
                residual=card.get('v2Residual') or {};level=residual.get('level');bps=residual.get('bps')
                rows=[dict(coin=card.get('asset','').split(':')[-1].upper(),mode=mode,buy=EXCHANGES.get(legs[0].get('exchange','').upper(),''),sell=EXCHANGES.get(legs[1].get('exchange','').upper(),''),rank='R'+str(level) if level is not None else '',value=str(bps/100 if type(bps) in (int,float) else 0)+'%',at=now,unranked=level is None or bps is None)]
            identity=card.get('pair') or card.get('id','')
            decisions[identity]=self.decision('cards',identity,rows,now) or 'allow'
        return decisions

    def prune_seen(self, now):
        self.data['seen']={k:v for k,v in self.data['seen'].items() if now-v<86400}
        if len(self.data['seen'])>10000:self.data['seen']=dict(sorted(self.data['seen'].items(),key=lambda x:x[1])[-10000:])

    def web_cards(self):
        # Do not update desktop heartbeat or evaluate computer messages here.
        # A missing source is an error, not a successful empty/unfiltered result.
        with self.lock:
            envelope=json.loads(self.cards.read_text())
            if not isinstance(envelope.get('snapshot'),dict):raise ValueError('cards_source_unavailable')
            now=time.time();before=dict(self.data['seen'])
            decisions=self.card_decisions(envelope,now)
            self.prune_seen(now)
            if self.data['seen']!=before:self.save()
            return dict(revision=self.data['revision'],cardsEnabled=self.data['cards']['settings']['notify_enabled'],decisions=decisions)

    def evaluate(self):
        with self.lock:
            now=time.time();self.last_seen=now
            feed=json.loads(self.feed.read_text());messages=list(feed.get('messages',[]))
            if feed.get('pinned'):messages.append(feed['pinned'])
            result=dict(revision=self.data['revision'],messages={},cards={},desktopEnabled=self.data['desktop']['settings']['notify_enabled'],cardsEnabled=self.data['cards']['settings']['notify_enabled'])
            before=len(self.data['seen'])
            for m in messages[:101]:
                action=self.decision('desktop',m['id'],self.rows(m,now),now)
                if action:result['messages'][m['id']]=action
            try:envelope=json.loads(self.cards.read_text())
            except (OSError,ValueError,AttributeError):envelope={}
            result['cards']={key:action for key,action in self.card_decisions(envelope,now).items() if action!='allow'}
            changed=len(self.data['seen'])!=before
            self.prune_seen(now)
            if changed:self.save()
            return result

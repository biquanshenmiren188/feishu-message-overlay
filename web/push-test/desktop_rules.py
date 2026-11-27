"""Separate per-code desktop policies, shared by native and website readers.

Signed native readers use a loopback-only route; website decisions require the
corresponding account token. Reading decisions never rewrites the source feed.
"""
import copy, hashlib, json, os, re, threading, time
from pathlib import Path
from datetime import datetime
import preferences
from advanced_rules import DEFAULT as ADVANCED, OISnapshot, VENUES, symbol, card_oi_evidence
from signals import desktop_rows, EXCHANGES

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
        return desktop_rows(message,now)

    def decision(self, channel, identity, rows, now, oi_evidence=None, *, record=True):
        if channel=='desktop' and rows and all(r.get('aggregate') for r in rows) and len(rows)>1:
            outcomes=[self.decision(channel,identity,[row],now,record=False) or 'allow' for row in rows]
            if 'allow' in outcomes:return None
            if 'mute' in outcomes:return 'mute'
        policy=self.data[channel]; settings=policy['settings']; reasons=[];action='hide'
        if not settings['notify_enabled']:reasons=['接收已关闭']
        else:
            candidates=[('hide',policy['rules']['hide']),('mute',policy['rules']['mute'])] if channel=='desktop' else [('hide',settings)]
            for candidate,rule in candidates:
                checked=copy.deepcopy(rows)
                self.oi.enrich(checked,rule.get('advanced',ADVANCED),now,all_legs=channel=='cards' and oi_evidence is not None)
                if channel=='cards' and oi_evidence is not None and checked:
                    oi_evidence.update(card_oi_evidence(checked[0],rule.get('advanced',ADVANCED)))
                for row in checked:
                    if row.get('invalidSignal'):
                        # Default receive-all still includes malformed source
                        # messages. With filters, an explicit trading signal
                        # cannot bypass checks by pretending to be unranked.
                        advanced=rule.get('advanced',{})
                        filtered=(rule.get('min_percent') is not None or any(rule.get(k) for k in
                                  ('excluded_ranks','excluded_modes','excluded_coins','excluded_exchanges'))
                                  or advanced.get('globalOI') is not None
                                  or any(r.get('enabled') for k in ('coins','legRules','coinOI') for r in advanced.get(k,[]))
                                  or any(r.get('mode')=='custom' for r in advanced.get('exchangeOI',{}).values()))
                        if filtered:reasons.append('信号等级或方向数据无效')
                        continue
                    check=rule if not row.get('unranked') else dict(rule,min_percent=None,excluded_ranks=[])
                    reasons.extend(preferences.exclusion_reasons(row,check))
                if reasons:action=candidate;break
        if not reasons:return None
        # Website refreshes apply the same policy without recording delivery,
        # advancing the native desktop heartbeat or mutating blocked history.
        if not record:return action
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
        retained={entry['card'].get('pair') or entry['card'].get('id',''):entry for entry in snapshot.get('retained',[])[:1000]}
        current=snapshot.get('active',[])[:1000]
        current_ids={card.get('pair') or card.get('id','') for card in current}
        candidates=current+[entry['card'] for key,entry in retained.items() if key not in current_ids]
        for card in candidates:
            identity=card.get('pair') or card.get('id','')
            if not identity or len(identity)>512:continue
            present.add(identity)
            data={k:card.get(k) for k in ('id','pair','asset','strategy','v2Residual','validUntil')}
            data['details']={'legs':[{'exchange':leg.get('exchange'),'symbol':leg.get('symbol')} for leg in card.get('details',{}).get('legs',[])[:2]]}
            entry=retained.get(identity) if identity not in current_ids else None
            missing=datetime.fromisoformat(entry['expiredAt'].replace('Z','+00:00')).timestamp() if entry else None
            self.card_cache[identity]={'card':data,'missing':missing}
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

    def card_decisions(self, envelope, now, oi_details=None):
        """One evaluator for desktop and authenticated BOT cards; caller holds lock."""
        decisions={}
        for card in self.retained_cards(envelope,now):
            legs=card.get('details',{}).get('legs',[]);mode=card.get('strategy');rows=[]
            if len(legs)==2 and mode in ('SF','FS','FF'):
                residual=card.get('v2Residual') or {};level=residual.get('level');bps=residual.get('bps')
                rows=[dict(coin=card.get('asset','').split(':')[-1].upper(),mode=mode,buy=EXCHANGES.get(legs[0].get('exchange','').upper(),''),sell=EXCHANGES.get(legs[1].get('exchange','').upper(),''),rank='R'+str(level) if level is not None else '',value=str(bps/100 if type(bps) in (int,float) else 0)+'%',at=now,unranked=level is None or bps is None)]
                rows[0]['oiContracts']={side:leg.get('symbol') for side,leg in zip(('left','right'),legs)}
            identity=card.get('pair') or card.get('id','')
            evidence={} if oi_details is not None else None
            decisions[identity]=self.decision('cards',identity,rows,now,oi_evidence=evidence) or 'allow'
            if oi_details is not None:oi_details[identity]=evidence
        return decisions

    def prune_seen(self, now):
        self.data['seen']={k:v for k,v in self.data['seen'].items() if now-v<86400}
        if len(self.data['seen'])>10000:self.data['seen']=dict(sorted(self.data['seen'].items(),key=lambda x:x[1])[-10000:])

    def public_card_oi(self):
        """Public market data only: no account rules, decisions, history or writes."""
        with self.lock:
            envelope=json.loads(self.cards.read_text());snapshot=envelope.get('snapshot')
            if not isinstance(snapshot,dict):raise ValueError('cards_source_unavailable')
            now=time.time();rows=[]
            cards=list(snapshot.get('active',[]))[:1000]+[entry['card'] for entry in snapshot.get('retained',[])[:1000]]
            seen=set()
            for card in cards:
                identity=card.get('pair') or card.get('id');legs=card.get('details',{}).get('legs',[]);mode=card.get('strategy')
                if not identity or identity in seen or len(legs)!=2 or mode not in ('SF','FS','FF'):continue
                seen.add(identity)
                rows.append(dict(id=identity,coin=card.get('asset','').split(':')[-1].upper(),mode=mode,buy=EXCHANGES.get(str(legs[0].get('exchange','')).upper(),''),sell=EXCHANGES.get(str(legs[1].get('exchange','')).upper(),''),oiContracts={side:leg.get('symbol') for side,leg in zip(('left','right'),legs)}))
            self.oi.enrich(rows,ADVANCED,now,all_legs=True)
            return dict(oi={row['id']:card_oi_evidence(row,ADVANCED) for row in rows})

    def web_cards(self):
        # Do not update desktop heartbeat or evaluate computer messages here.
        # A missing source is an error, not a successful empty/unfiltered result.
        with self.lock:
            envelope=json.loads(self.cards.read_text())
            if not isinstance(envelope.get('snapshot'),dict):raise ValueError('cards_source_unavailable')
            now=time.time();before=dict(self.data['seen'])
            oi_details={};decisions=self.card_decisions(envelope,now,oi_details)
            self.prune_seen(now)
            if self.data['seen']!=before:self.save()
            return dict(revision=self.data['revision'],cardsEnabled=self.data['cards']['settings']['notify_enabled'],decisions=decisions,oi=oi_details)

    @staticmethod
    def message_fingerprint(message):
        """Match UTF-8 JSON.stringify([id,title,body,sentAt]) in the browser.

        Hash the original strings, before display normalization. A source edit
        retaining its id must never inherit an older message's allow decision.
        """
        if not isinstance(message,dict) or message.get('senderType')!='bot':return None
        values=[message.get(k) for k in ('id','title','body','sentAt')]
        if any(not isinstance(v,str) or len(v)>limit for v,limit in zip(values,(256,1024,16000,64))) or not values[0]:return None
        try:return hashlib.sha256(json.dumps(values,ensure_ascii=False,separators=(',',':')).encode('utf-8')).hexdigest()
        except UnicodeEncodeError:return None

    def web_messages(self, feed=None):
        """Read-only, per-code decisions for the current public feed snapshot.

        Unknown ids/content are intentionally absent so clients wait for a
        matching decision. Pinned messages are evaluated independently of the
        bounded history, including while their original send time is old.
        """
        with self.lock:
            if feed is None:
                feed=json.loads(self.feed.read_text(encoding='utf-8'))
            if not isinstance(feed,dict) or not isinstance(feed.get('messages'),list):raise ValueError('feed_source_unavailable')
            messages=feed['messages'][:1000]
            if feed.get('pinned') is not None:messages=[*messages,feed['pinned']]
            now=time.time();decisions={}
            for message in messages:
                fingerprint=self.message_fingerprint(message)
                if fingerprint is None:continue
                identity=message['id']
                action=self.decision('desktop',identity,self.rows(message,now),now,record=False) or 'allow'
                decisions[identity]=dict(action=action,fingerprint=fingerprint)
            return dict(revision=self.data['revision'],desktopEnabled=self.data['desktop']['settings']['notify_enabled'],decisions=decisions)

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

"""Exact-scope coin edits with durable intent, conflict checks and deletion undo."""
import copy,re,time
import preferences
from advanced_rules import DEFAULT,VENUES,symbol
CHANNELS=('desktop','mute','cards','mobile')

def rule_map(settings):
    rules={(c,'all'):True for c in settings['excluded_coins']}
    for r in settings.get('advanced',{}).get('coins',[]):
        key=(r['coin'],r['exchange']);rules[key]=rules.get(key,False) or r['enabled']
    return rules

def patch_settings(settings,changes,allow_applied=False):
    result=copy.deepcopy(settings);current=rule_map(settings)
    for c in changes:
        key=(c['coin'],c['exchange']);actual=current.get(key)
        if actual is not c['before'] and not (allow_applied and actual is c['after']):
            raise ValueError(c['coin']+' / '+c['exchange']+' 规则已变化，请重新打开管理后编辑')
    for c in changes:
        coin,exchange=c['coin'],c['exchange']
        if exchange=='all':result['excluded_coins']=[x for x in result['excluded_coins'] if x!=coin]
        advanced=result.setdefault('advanced',copy.deepcopy(DEFAULT))
        advanced['coins']=[r for r in advanced['coins'] if (r['coin'],r['exchange'])!=(coin,exchange)]
        if c['after'] is not None:advanced['coins'].append(dict(coin=coin,exchange=exchange,enabled=c['after']))
    return preferences.validate(result)

def edit_coins(app,raw,account):
    if not isinstance(raw,dict) or set(raw) not in ({'requestId','changes'},{'requestId','changes','undoOf'}):raise ValueError('规则编辑请求无效')
    identity=raw['requestId']
    if not isinstance(identity,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,64}',identity):raise ValueError('操作编号无效')
    source=raw['changes'];changes=[];seen=set()
    if not isinstance(source,list) or not 1<=len(source)<=40:raise ValueError('每次最多修改40项规则')
    for c in source:
        if not isinstance(c,dict) or set(c)!={'channel','coin','exchange','before','after'}:raise ValueError('规则编辑字段无效')
        if c['channel'] not in CHANNELS or not symbol(c['coin']) or c['exchange'] not in (*VENUES,'all'):raise ValueError('币种、渠道或交易所无效')
        if any(v is not None and type(v) is not bool for v in (c['before'],c['after'])) or c['before'] is c['after']:raise ValueError('规则状态无效或未修改')
        c=dict(c,coin=c['coin'].upper());key=(c['channel'],c['coin'],c['exchange'])
        if key in seen:raise ValueError('同一规则不能重复修改')
        seen.add(key);changes.append(c)
    changes.sort(key=lambda c:(c['channel'],c['coin'],c['exchange']))
    undo=raw.get('undoOf')
    if undo is not None and (not isinstance(undo,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,64}',undo)):raise ValueError('撤销编号无效')
    with app.lock,account.lock:
        operations=app.data.setdefault('coinOperations',[])
        operation=next((x for x in operations if x['id']==identity),None)
        if operation and (operation.get('kind')!='edit' or operation['changes']!=changes or operation.get('undoOf')!=undo):raise ValueError('重试内容不一致，请重新操作')
        retry=operation is not None
        if operation is None:
            if undo:
                original=next((x for x in operations if x['id']==undo and x.get('kind')=='edit'),None)
                if not original:raise ValueError('原删除记录已不存在，无法撤销')
                permitted=[dict(c,before=None,after=c['before']) for c in original['changes'] if c['after'] is None and original['results'][c['channel']]['state']=='saved']
                if any(c not in permitted for c in changes):raise ValueError('只能撤销原操作中已完成的删除')
                # A restore never overwrites a newly added or disabled rule.
                for c in changes:
                    settings=account.state['live']['settings'] if c['channel']=='mobile' else app.data['cards']['settings'] if c['channel']=='cards' else app.data['desktop']['rules']['hide' if c['channel']=='desktop' else 'mute']
                    if (c['coin'],c['exchange']) in rule_map(settings):raise ValueError(c['coin']+' 规则已重新设置，请在管理中查看，不能覆盖恢复')
            operation=dict(id=identity,kind='edit',at=time.time(),coins=sorted({c['coin'] for c in changes}),exchange='mixed',changes=changes,undoOf=undo,results={c:dict(state='pending' if any(x['channel']==c for x in changes) else 'skipped') for c in CHANNELS})
            app.data['coinOperations']=[operation,*operations][:100]
            try:app.save()
            except OSError:
                app.data['coinOperations']=operations;raise
        for channel in CHANNELS:
            if operation['results'][channel]['state'] in ('saved','skipped'):continue
            before=copy.deepcopy(app.data)
            try:
                edits=[c for c in changes if c['channel']==channel]
                if channel=='mobile':
                    live=account.state['live'];settings=patch_settings(live['settings'],edits,retry)
                    if settings!=live['settings']:account.configure(dict(revision=live['revision'],settings=settings))
                else:
                    action='hide' if channel=='desktop' else 'mute'
                    current=app.data['cards']['settings'] if channel=='cards' else app.data['desktop']['rules'][action]
                    settings=patch_settings(current,edits,retry)
                    if settings!=current:
                        if channel=='cards':app.data['cards']['settings']=settings
                        else:
                            app.data['desktop']['rules'][action]=settings
                            if app.data['desktop']['action']==action:app.data['desktop']['settings']=copy.deepcopy(settings)
                        app.data['revision']+=1
                operation['results'][channel]=dict(state='saved');app.save()
            except (OSError,ValueError) as error:
                app.data=before;operation=next(x for x in app.data['coinOperations'] if x['id']==identity)
                operation['results'][channel]=dict(state='failed',error=str(error)[:160] if isinstance(error,ValueError) else '保存暂时失败，请重试');app.save()
        return app.coin_state(account)|dict(operation=copy.deepcopy(operation))

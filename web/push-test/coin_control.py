"""Narrow loopback operations for the already signed desktop management route."""
def dispatch(desktop, owner, data):
    if set(data)=={'op'} and data['op']=='state':return desktop.coin_state(owner)
    if set(data)=={'op','request'} and isinstance(data['request'],dict):
        if data['op']=='block':return desktop.block_coins(data['request'],owner)
        if data['op']=='edit':return desktop.edit_coins(data['request'],owner)
    raise ValueError('币种规则操作无效')

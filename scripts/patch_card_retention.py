"""Patch only the verified live renderer; retain its scrolling/clipboard fixes."""
import hashlib

EXPECTED = '78bcfbca815ada8c2d7b4c9413f2a861225fc5794dcb77a4ef733f4b3be4d930'

def patch_bundle(raw):
    if hashlib.sha256(raw).hexdigest() != EXPECTED:
        raise ValueError('Live bundle changed; inspect before patching')
    source = raw.decode()
    old = 'Rn=new Ye,Ve=new Map'
    assert source.count(old) == 1
    source = source.replace(old, 'Rn=new UnifiedOpportunities,Ve=new Map')
    start = 'for(let[l,f]of Ve)if(!r.has(l)){'
    end = 'Ne.textContent=`${a} ACTIVE`'
    assert source.count(start) == source.count(end) == 1
    left, right = source.index(start), source.index(end)
    assert 'if(__defer)' in source[left:right] and 'Ve.delete(l)' in source[left:right]
    source = source[:left] + start + 'f.card.remove();Ve.delete(l);}' + source[right:]
    return ('import {Opportunities as UnifiedOpportunities} from "/radar/robot-push/basispulse-model.js?v=20261025-retention1";\n' + source).encode()

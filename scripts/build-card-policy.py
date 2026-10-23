"""Patch the verified live bundle, preserving all existing GC/clipboard/modules."""
import hashlib,sys
from pathlib import Path
EXPECTED='8db43cfeb5cd754668bdd04ec5572720c2eecda947887a50599c9cc3949f06fb'
def patch_bundle(raw):
 assert hashlib.sha256(raw).hexdigest()==EXPECTED,'Live BOT bundle changed; inspect before adapting'
 source=raw.decode()
 replacements=[
  ('for(let l of t){let f=l.data.id,p=En(l,i,e)', 'for(let l of t){if(!__cardPolicy.visible(l.data)){Ve.get(l.data.id)?.card.remove();Ve.delete(l.data.id);continue;}let f=l.data.id,p=En(l,i,e)'),
  ('D=Dn(l,g);u&&u.card.replaceWith(D.card)', 'D=Dn(l,g);__cardPolicy.decorate(D.card,l.data);u&&u.card.replaceWith(D.card)'),
  ('}var oi,me,On,In,Ne,Qe,Xe,kt,Rn,Ve,W,Mt,li,Fn,ci,Hn=', ';__cardPolicy.summary(t)}var __cardPolicy,oi,me,On,In,Ne,Qe,Xe,kt,Rn,Ve,W,Mt,li,Fn,ci,Hn='),
  ('$e("basispulse",{data(e){W=e', '__cardPolicy=createCardPolicy(On,Nt);$e("basispulse",{data(e){W=e'),
 ]
 for old,new in replacements:
  assert source.count(old)==1,old
  source=source.replace(old,new)
 return ('import {createCardPolicy} from "/radar/robot-push/card-policy.js?v=20261023-inline1";\n'+source).encode()
if __name__=='__main__':
 Path(sys.argv[2]).write_bytes(patch_bundle(Path(sys.argv[1]).read_bytes()))

"""Patch the inspected production BOT without rebuilding older overlapping assets."""
import argparse,hashlib,json,pathlib

def digest(raw):return hashlib.sha256(raw).hexdigest()

def prepare(baseline,out):
    root=pathlib.Path(__file__).resolve().parents[1]
    manifest=json.loads((baseline/'manifest.json').read_text(encoding='utf-8'))
    original='performance-20261017/bot-cards-8d81b8292063.js'
    raw=(baseline/original).read_bytes()
    assert digest(raw)==manifest['hashes'][original]=='8d81b8292063538188eef38c9178f4b610e9365d2a139b0aee026dfe7f268fec', 'Inspect changed production bundle first'
    helper=(root/'web/robot-push/mobile-scroll.js').read_bytes()
    module='mobile-reading-20261024/mobile-scroll-'+digest(helper)[:12]+'.js'
    text=raw.decode('utf-8')
    replacements=[
        ('import {mobileScrollGate as __radarScroll,stablePaneBottom as __radarBottom} from "/radar/scroll-stability-20261017/mobile-scroll.js";',
         'import {mobileScrollGate as __radarScroll,stablePaneBottom as __radarBottom,preserveCardViewport as __radarPreserve} from "/radar/'+module+'";'),
        ('function Nt(){const __defer=__radarScroll.defer(Nt);',
         'function Nt(){const __defer=__radarScroll.defer(Nt);return __radarPreserve(Xe,()=>{'),
        ('__cardPolicy.summary(t)}var __cardPolicy,', '__cardPolicy.summary(t)})}var __cardPolicy,'),
        ('__cardPolicy.decorate(D.card,l.data);', 'D.card.dataset.pair=l.data.pair||"";__cardPolicy.decorate(D.card,l.data);')]
    for before,after in replacements:
        assert text.count(before)==1, 'Unexpected bundle structure: '+before
        text=text.replace(before,after)
    body=text.encode('utf-8');bundle='performance-20261017/bot-cards-'+digest(body)[:12]+'.js'
    files={module:helper,bundle:body}
    for source in ['robot-push/index.html','pwa-index.html']:
        html=(baseline/source).read_bytes()
        old=('/radar/'+original).encode();new=('/radar/'+bundle).encode()
        assert html.count(old)==1,'Unexpected entry: '+source
        files[source]=html.replace(old,new)
    for name,content in files.items():
        dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(content)
    report=dict(original=original,bundle=bundle,module=module,patches=len(replacements),
                baseline=manifest,fallbackBefore=digest((baseline/'pwa-index.html').read_bytes()),
                hashes={n:digest(v) for n,v in files.items()})
    (out/'candidate.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('original','bundle','module','patches','hashes')}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True)
    a=p.parse_args();prepare(a.baseline,a.out)

"""Prepare an exact live-bundle patch; never rebuild or publish the BOT page.

Usage: python prepare-strong-v2.py BASELINE_DIR CANDIDATE_DIR
The baseline is a raw-byte download with baseline.json, static/, backend/ and
fallback/. Run again after committing so sourceCommit identifies final source.
"""
import hashlib,json,re,subprocess,sys
from pathlib import Path

REPO=Path(__file__).resolve().parents[1]
BUNDLE='performance-20261017/bot-cards-bad2bcae5dcc.js'
EXPECTED_BUNDLE='bad2bcae5dccd2abfbaa6d0e57a882b41a0a59da9b17f7f63bf6bbde404062eb'
EXPECTED_INDEX='532832f526b404e83709299a1009921d6773aa272e327b591d0620471870f1c8'
EXPECTED_FALLBACK='73f8e063fdf5976a7cb96fada8be4b10a3fb6701dec267e7c214f21204027b83'
EXPECTED_SIGNALS='15f54d33c014bc022bb590636d7eea4724384fd83b1e633afe2917bed0e59293'
OLD_EXPRESSION=r'value=(line+`'+'\n'+r'`+(/^净均/u.test(next)?next:"")).match(/净均\s*([+−-]?\d+(?:\.\d+)?%)/u)?.[1]'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def safe(name):return not name.startswith('/') and '..' not in name.split('/') and '\\' not in name
def once(raw,old,new):
    assert raw.count(old)==1,'Expected exactly one inspected replacement'
    return raw.replace(old,new)

def main():
    baseline=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]).resolve()
    assert out!=baseline and (not out.exists() or not any(out.iterdir())),'Use an empty candidate directory'
    inventory=json.loads((baseline/'baseline.json').read_text(encoding='utf-8'))
    assert inventory['staticFiles'][BUNDLE]==EXPECTED_BUNDLE
    assert inventory['staticFiles']['robot-push/index.html']==EXPECTED_INDEX
    assert inventory['backendSha256']==EXPECTED_SIGNALS
    assert inventory['fallbackSha256']==EXPECTED_FALLBACK
    for name,expected in inventory['staticFiles'].items():
        assert safe(name) and sha((baseline/'static'/name).read_bytes())==expected,name
    assert sha((baseline/'backend/signals.py').read_bytes())==EXPECTED_SIGNALS
    fallback=(baseline/'fallback/index.html').read_bytes()
    assert sha(fallback)==EXPECTED_FALLBACK
    names=['web/push-test/signals.py','web/robot-push/summary.js','web/robot-push/summary.mjs']
    sources={name:(REPO/name).read_bytes() for name in names}
    normalize=lambda raw:raw.replace(b'\r\n',b'\n')
    assert normalize(sources[names[1]])==normalize(sources[names[2]]),'Summary source variants differ'
    summary=sources[names[1]].decode('utf-8')
    expressions=re.findall(r'const value=(.*?);\s*signals\.push',summary,re.S)
    assert len(expressions)==1 and '??next.match(' in expressions[0] and '180秒' in expressions[0],'Inspect changed summary source'
    expression='value='+expressions[0]
    original=(baseline/'static'/BUNDLE).read_bytes()
    patched=once(original,OLD_EXPRESSION.encode('utf-8'),expression.encode('utf-8'))
    bundle='performance-20261017/bot-cards-strong-v2-'+sha(patched)[:16]+'.js'
    old_url=('/radar/'+BUNDLE).encode();new_url=('/radar/'+bundle).encode()
    index=once((baseline/'static/robot-push/index.html').read_bytes(),old_url,new_url)
    pwa=once(fallback,old_url,new_url)
    files={'backend/signals.py':sources[names[0]],'static/'+bundle:patched,'static/robot-push/index.html':index,'fallback/index.html':pwa}
    artifacts={names[0]:'backend/signals.py',names[1]:'verification/summary.js',names[2]:'verification/summary.mjs'}
    for name,target in artifacts.items():files[target]=sources[name]
    files['verification/summary.test.mjs']=(REPO/'web/robot-push/summary.test.mjs').read_bytes()
    # Keep all verification dependencies in the candidate. Only the four
    # deployment payloads above may be copied to production by the deployer.
    backend_sources=subprocess.check_output(['git','ls-files','web/push-test/*.py'],cwd=REPO,text=True).splitlines()
    for name in backend_sources:files['verification/backend/'+Path(name).name]=(REPO/name).read_bytes()
    for name in ('deploy-strong-v2.py','deploy-aster-oi.py','prepare-strong-v2.py','verify-strong-v2-candidate.mjs'):
        files[name]=(REPO/'scripts'/name).read_bytes()
    compile(files['backend/signals.py'],'signals.py','exec')
    source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
    assert re.fullmatch('[a-f0-9]{40}',source_sha)
    plan=dict(sourceCommit=source_sha,sourceFiles={name:dict(sha256=sha(raw),normalizedSha256=sha(normalize(raw))) for name,raw in sources.items()},
              sourceArtifacts=artifacts,baseline=inventory,previousBundle=BUNDLE,bundle=bundle,summaryExpression=expression,
              staticFiles={bundle:sha(patched),'robot-push/index.html':sha(index)},backendFiles={'signals.py':sha(sources[names[0]])},
              fallbackSha256=sha(pwa),candidateFiles={name:sha(raw) for name,raw in files.items()},
              changes=['one strong-signal value expression in live bundled Xt','BOT and PWA bundle URL only','signals.py only'])
    for name,raw in sources.items():assert (REPO/name).read_bytes()==raw,'Source changed during preparation: '+name
    out.mkdir(parents=True,exist_ok=True)
    for name,raw in files.items():target=out/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    subprocess.run(['node','--check',str(out/'static'/bundle)],check=True,capture_output=True)
    (out/'strong-v2-plan.json').write_bytes((json.dumps(plan,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    print(json.dumps(dict(candidate=str(out),sourceCommit=source_sha,bundle=bundle,files=plan['candidateFiles'])))

if __name__=='__main__':main()

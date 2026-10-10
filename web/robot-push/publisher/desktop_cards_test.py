import json,tempfile
from pathlib import Path
from desktop_cards import read_cards

with tempfile.TemporaryDirectory() as folder:
    root=Path(folder)
    assert read_cards(root)['status']=='unavailable'
    path=root/'basispulse.json'
    expected={'status':'connected','receivedAt':'2026-10-10T00:00:00Z','snapshot':{'sampledAt':'2026-10-10T00:00:00Z','complete':True,'active':[]}}
    path.write_text(json.dumps(expected))
    assert read_cards(root)==expected
    path.write_text('{broken')
    assert read_cards(root)['snapshot'] is None
    path.write_text('x'*(4*1024*1024+1))
    assert read_cards(root)['status']=='unavailable'
    print('PASS 4 desktop cache checks; no credentials or upstream calls')

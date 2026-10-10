"""Read the existing credential-free card cache; never poll the upstream here."""
import json
from pathlib import Path

def read_cards(directory):
    try:
        with (Path(directory)/'basispulse.json').open('rb') as stream:
            body=stream.read(4*1024*1024+1)
        if len(body)>4*1024*1024: raise ValueError('limit')
        envelope=json.loads(body,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
        if not isinstance(envelope,dict) or not isinstance(envelope.get('snapshot'),dict): raise ValueError('schema')
        snapshot=envelope['snapshot']
        if not isinstance(snapshot.get('active'),list) or len(snapshot['active'])>1000: raise ValueError('cards')
        return envelope
    except (OSError,ValueError,TypeError):
        return {'status':'unavailable','receivedAt':None,'snapshot':None}

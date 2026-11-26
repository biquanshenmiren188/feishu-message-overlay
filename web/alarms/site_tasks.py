"""Read the administrator's persistent switches. Existing installations default to on."""
import math
from pathlib import Path

ROOT = Path('/var/lib/radar-features')
SOURCES = {'tbtc-price': ('alarm-price', 'quotes'), 'tbtc-large-sale': ('alarm-sale', 'sellers'),
           'tbtc-btc-deposit': ('alarm-deposit', 'deposits'), 'tbtc-mint': ('alarm-mint', 'supply'),
           'tbtc-backed-mint': ('alarm-mint', 'supply')}


def since(rule):
    start = 0.0
    for key in SOURCES[rule]:
        try:
            if (ROOT / (key + '.off')).exists():
                return math.inf
            start = max(start, (ROOT / key).stat().st_mtime)
        except FileNotFoundError:
            continue
        except OSError:
            return math.inf
    return start


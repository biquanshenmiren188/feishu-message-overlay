"""Read the administrator's persistent switches. Existing installations default to on."""
import math
from pathlib import Path

ROOT = Path('/var/lib/radar-features')
SOURCES = {'tbtc-price': ('alarm-price',), 'tbtc-large-sale': ('alarm-sale',),
           'tbtc-btc-deposit': ('alarm-deposit',), 'tbtc-mint': ('alarm-mint',),
           'tbtc-backed-mint': ('alarm-mint',)}


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


def enabled_since(key):
    if (ROOT / (key + '.off')).exists():
        return math.inf
    try:
        return (ROOT / key).stat().st_mtime
    except FileNotFoundError:
        return math.inf if key == 'bot-bark' else 0


def bark_mode(rule_id):
    key = 'bot-bark' if rule_id == 'bot-bark' else SOURCES.get(rule_id, ('price-alerts',))[0]
    try:
        mode = (ROOT / (key + '.mode')).read_text().strip()
        return 'critical' if mode == 'critical' else 'active'
    except FileNotFoundError:
        return 'active' if key == 'bot-bark' else 'critical'

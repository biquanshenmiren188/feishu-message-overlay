"""Bounded, persistent pin archive. Reading history never enters the live feed."""
import json

LIMIT = 5

class PinHistory:
    def __init__(self, db):
        self.db = db
        db.execute('CREATE TABLE IF NOT EXISTS pin_history (id TEXT PRIMARY KEY, group_id TEXT NOT NULL, sent REAL NOT NULL, payload TEXT NOT NULL)')
        db.commit()

    def remember(self, message, stamp):
        if message is None:
            return
        payload = json.dumps(message, ensure_ascii=False, separators=(',', ':'))
        with self.db:
            self.db.execute('INSERT INTO pin_history VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, sent=excluded.sent, group_id=excluded.group_id WHERE pin_history.payload != excluded.payload',
                            (message['id'], message['groupId'], stamp, payload))
            self.db.execute('DELETE FROM pin_history WHERE id NOT IN (SELECT id FROM pin_history ORDER BY sent DESC, id DESC LIMIT ?)', (LIMIT,))

    def rows(self, group):
        return [json.loads(row[0]) for row in self.db.execute('SELECT payload FROM pin_history WHERE group_id=? ORDER BY sent DESC, id DESC LIMIT ?', (group, LIMIT))]

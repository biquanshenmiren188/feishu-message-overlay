export const number = v => typeof v === 'number' && Number.isFinite(v);
export const percent = (v, divisor = 100, digits = 2) => number(v) ? `${v >= 0 ? '+' : ''}${(v / divisor).toFixed(digits)}%` : '—';
export const money = v => !number(v) ? '—' : v >= 1e9 ? `${(v/1e9).toFixed(2)}B` : v >= 1e6 ? `${(v/1e6).toFixed(2)}M` : v >= 1e3 ? `${(v/1e3).toFixed(2)}K` : v.toFixed(2);
export const assetName = c => String(c.asset || '').split(':').at(-1) || '未知';
export function safeRadar(value) {
  try { const u = new URL(value); return u.origin === 'https://leida.shenmiren.work' && u.pathname === '/radar/' && !u.username && !u.password ? u.href : null; } catch { return null; }
}
export class Opportunities {
  constructor() { this.cards = new Map(); this.lastSample = -Infinity; this.nextSort = 0; this.order = []; }
  ingest(envelope, now = Date.now()) {
    const s = envelope?.snapshot, stamp = Date.parse(s?.sampledAt);
    if (!s || !Array.isArray(s.active) || !Number.isFinite(stamp) || stamp <= this.lastSample) return;
    this.lastSample = stamp;
    const present = new Set();
    for (const data of s.active) {
      if (!data || typeof data.id !== 'string') continue;
      // A re-entered span replaces the same market pair's grey card.
      const key = data.pair || (data.longMarketKey && data.shortMarketKey ? `${data.longMarketKey}>${data.shortMarketKey}` : data.id);
      present.add(key);
      const old = this.cards.get(key), level = data.v2Residual?.level;
      this.cards.set(key, { data, missingAt: null, level, levelSince: old?.level === level ? old.levelSince : now, stableLevel: old?.stableLevel ?? level });
      if (!old) this.order.push(key);
    }
    if (s.complete === true) for (const [id, c] of this.cards) if (!present.has(id)) c.missingAt ??= now;
    this.tick(now);
  }
  tick(now = Date.now()) {
    for (const [id, c] of this.cards) {
      const expires = Date.parse(c.data.validUntil);
      c.expiredAt = Math.min(c.missingAt ?? Infinity, Number.isFinite(expires) ? expires : now);
      if (now >= c.expiredAt + 30_000) this.cards.delete(id);
      if (now - c.levelSince >= 15_000) c.stableLevel = c.level;
    }
    this.order = this.order.filter(id => this.cards.has(id));
    if (now >= this.nextSort) {
      this.order.sort((a,b) => {
        const x=this.cards.get(a), y=this.cards.get(b);
        return assetName(x.data).localeCompare(assetName(y.data), 'en') || (y.stableLevel ?? -1)-(x.stableLevel ?? -1) || Date.parse(y.data.enteredAt)-Date.parse(x.data.enteredAt);
      });
      this.nextSort = now + 15_000;
    }
    return this.order.map(id => this.cards.get(id));
  }
}

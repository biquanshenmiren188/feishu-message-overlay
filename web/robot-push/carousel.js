/**
 * Clock-injected web batch reader; desktop reading behavior is independent.
 * Supply only normal-message IDs, oldest first; keep the independent pin outside.
 * All times and delays are milliseconds. No timers, DOM, storage, or network.
 */
export class CarouselReader {
  constructor({ enabled = true, seconds = 5, now = 0, capacity = 3 } = {}) {
    this.ids = [];
    this.capacity = capacity === 5 ? 5 : 3;
    this.enabled = Boolean(enabled);
    this.seconds = secondsValue(seconds);
    this.current = null;
    this.rangeStart = null;
    this.displayEnd = null;
    this.deadline = timeValue(now) + this.seconds * 1000;
    this.idleUntil = null;
    this.paused = false;
    this.visible = true;
    this._manualId = null;
  }

  get rangeIndex() {
    return this.ids.length ? this.ids.indexOf(this.rangeStart) : -1;
  }

  /** Refreshes preserve current ID, window anchor, and dwell deadline. */
  synchronize(ids, now) {
    now = timeValue(now);
    const hadPending = this.pendingCount > 0;
    const unique = new Set();
    for (const id of ids) {
      if (typeof id !== 'string' || id.length === 0 || unique.has(id)) continue;
      unique.add(id);
      if (unique.size === 100) break;
    }
    this.ids = [...unique];
    if (this.current === null || !unique.has(this.current)) {
      this.current = this.ids[0] ?? null;
      this.deadline = now + this.seconds * 1000;
    }
    if (this.rangeStart === null || !unique.has(this.rangeStart)) {
      this.rangeStart = this.current;
    }
    if (!unique.has(this.displayEnd) || !unique.has(this.rangeStart)) this.show(this.rangeStart);
    // Skip empty clock boundaries without scheduling idle ticks or resetting on every poll.
    if (!hadPending && !this.paused && this.deadline < now) {
      this.deadline += Math.ceil((now - this.deadline) / (this.seconds * 1000)) * this.seconds * 1000;
    }
    return this.window();
  }

  /** UI configuration restarts a full dwell and cancels manual recovery. */
  configure(enabled, seconds, now) {
    now = timeValue(now);
    const wasPaused = this.paused;
    const enableChanged = this.enabled !== Boolean(enabled);
    this.enabled = Boolean(enabled);
    this.seconds = secondsValue(seconds);
    if (wasPaused || enableChanged) this._focusVisible(now);
    this._cancelManual();
    this.deadline = now + this.seconds * 1000;
    return this.window();
  }

  /** Focus alone does not change the displayed range, matching desktop. */
  focus(id, now) {
    now = timeValue(now);
    if (id != null && this.ids.includes(id)) this.current = id;
    this.deadline = now + this.seconds * 1000;
    return this.current;
  }

  /** Display exactly min(capacity, N) unique IDs, including at the queue tail. */
  show(id) {
    const requested = this.ids.indexOf(id);
    const start = Math.max(0, Math.min(requested, Math.max(0, this.ids.length - this.capacity)));
    this.rangeStart = this.ids[start] ?? null;
    this.displayEnd = this.ids[Math.min(start + this.capacity - 1, this.ids.length - 1)] ?? null;
    return this.window();
  }

  setCapacity(capacity, anchor = this.rangeStart) {
    const next = capacity === 5 ? 5 : 3;
    if (next === this.capacity) return this.window();
    const atTail = this.displayEnd === this.ids.at(-1);
    this.capacity = next;
    this.show(atTail ? this.ids.at(-1) : anchor);
    if (!this.window().includes(this.current)) this.current = this.window()[0] ?? null;
    return this.window();
  }

  window() {
    const start = this.rangeIndex;
    return start < 0 ? [] : this.ids.slice(start, Math.min(start + this.capacity, this.ids.indexOf(this.displayEnd) + 1));
  }

  get pendingCount() {
    return this.displayEnd === null ? 0 : Math.max(0, this.ids.length - 1 - this.ids.indexOf(this.displayEnd));
  }

  /** Every actual manual scroll restarts the 10s idle deadline without disabling auto. */
  manual(firstVisibleId, now) {
    now = timeValue(now);
    if (!this.enabled || !this.visible) return this.window();
    this._manualId = this.ids.includes(firstVisibleId)
      ? firstVisibleId : this.window()[0] ?? null;
    this.paused = true;
    this.idleUntil = now + 10_000;
    return this.window();
  }

  /** Call at a manual scroll boundary; direction is -1 or +1. */
  move(delta, now) {
    now = timeValue(now);
    const step = Math.sign(delta);
    if (step && this.ids.length) {
      const index = Math.max(0, Math.min(this.rangeIndex + step, this.ids.length - 1));
      this.show(this.ids[index]);
      this.focus(this.rangeStart, now);
    }
    this.manual(this.window()[0] ?? null, now);
    return this.window();
  }

  /**
   * Admits at most two pending IDs and returns the first admitted ID, or null. At manual idle recovery, the pending batch is admitted immediately.
   * Pass document visibility; hidden transitions cancel manual recovery.
   */
  tick(now, visible = true) {
    now = timeValue(now);
    if (this.visible !== Boolean(visible)) this.setVisible(visible, now);
    if (!this.visible || !this.enabled) return null;
    if (this.paused) {
      if (this.idleUntil === null || now < this.idleUntil) return null;
      const recoveryAt = this.idleUntil;
      this._focusVisible(now);
      this._cancelManual();
      if (!this.pendingCount) {
        this.deadline = now + this.seconds * 1000;
        return null;
      }
      // The manual idle interval already supplied the wait. Admit this batch now.
      this.deadline = recoveryAt;
    }
    if (this.current === null || now < this.deadline) return null;
    const index = this.ids.indexOf(this.displayEnd);
    if (index < 0 || !this.pendingCount) return null;
    const end = Math.min(index + 2, this.ids.length - 1);
    this.current = this.ids[index + 1]; // First new card, not the last: do not obscure the first of a pair.
    this.displayEnd = this.ids[end];
    this.rangeStart = this.ids[Math.max(0, end - this.capacity + 1)];
    this.deadline = now + this.seconds * 1000;
    return this.current;
  }

  /** No timer at tail. The stored deadline is deliberately never cleared. */
  nextDelay(now) {
    now = timeValue(now);
    if (!this.enabled || !this.visible) return null;
    if (this.paused) return this.idleUntil === null ? null : Math.max(0, this.idleUntil - now);
    return !this.pendingCount
      ? null : Math.max(0, this.deadline - now);
  }

  setVisible(visible, now, firstVisibleId = this.window()[0] ?? null) {
    now = timeValue(now);
    visible = Boolean(visible);
    if (visible !== this.visible) {
      this.visible = visible;
      this.focus(firstVisibleId, now);
      this._cancelManual();
    }
    return this.window();
  }

  _focusVisible(now) {
    const id = this.ids.includes(this._manualId) ? this._manualId : this.window()[0];
    this.focus(id ?? null, now);
  }

  _cancelManual() {
    this.paused = false;
    this.idleUntil = null;
    this._manualId = null;
  }
}

function secondsValue(seconds) {
  if (!Number.isFinite(seconds)) throw new TypeError('seconds must be finite');
  return Math.max(1, Math.min(300, Math.trunc(seconds)));
}

function timeValue(now) {
  if (!Number.isFinite(now)) throw new TypeError('now must be a finite millisecond timestamp');
  return now;
}

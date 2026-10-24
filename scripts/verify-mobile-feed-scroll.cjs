#!/usr/bin/env node
// Exercise real deployed HTML/CSS/JS on an isolated loopback origin. All feed,
// card, and settings API traffic is synthetic; no production request is made.
// Usage: node scripts/verify-mobile-feed-scroll.cjs --baseline ../mobile-live-baseline
//        [--overlay ../mobile-candidate] [--engine chromium|webkit|all]
//        [--out artifacts/mobile-scroll.json] [--case feed-arrival,card-data-refresh]
//        [--width 390 --height 844] [--jobs 2]
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');

const options = {};
for (let i = 2; i < process.argv.length; i += 2) {
  assert.ok(process.argv[i].startsWith('--') && process.argv[i + 1], 'Expected --name value');
  options[process.argv[i].slice(2)] = process.argv[i + 1];
}
const baseline = path.resolve(options.baseline || '../mobile-live-baseline');
const overlay = options.overlay && path.resolve(options.overlay);
const bundledModules = path.join(process.env.USERPROFILE || '', '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules');
const playwright = require(require.resolve('playwright', {paths: [process.cwd(), bundledModules]}));
const engines = options.engine === 'all' ? ['chromium', 'webkit'] : [options.engine || 'chromium'];
const viewport = {width: Number(options.width) || 390, height: Number(options.height) || 844};
const mime = {'.js': 'application/javascript', '.mjs': 'application/javascript', '.css': 'text/css', '.html': 'text/html', '.svg': 'image/svg+xml', '.png': 'image/png', '.json': 'application/json'};
const roots = [overlay, baseline].filter(Boolean);
const metadata = (root, name) => root && fs.existsSync(path.join(root, name)) ? JSON.parse(fs.readFileSync(path.join(root, name), 'utf8')) : null;
const provenance = {baseline: metadata(baseline, 'manifest.json'), candidate: metadata(overlay, 'candidate.json')};
function findFile(relative) {
  for (const root of roots) {
    const file = path.resolve(root, relative);
    if (file.startsWith(root + path.sep) && fs.existsSync(file) && fs.statSync(file).isFile()) return file;
  }
}
const server = http.createServer((request, response) => {
  const url = new URL(request.url, 'http://127.0.0.1');
  let relative = url.pathname.replace(/^\/radar\//, '');
  if (relative === 'robot-push/' || relative === 'robot-push') relative = 'robot-push/index.html';
  const file = findFile(relative);
  if (!file) { response.writeHead(404); response.end('Fixture resource not present'); return; }
  response.writeHead(200, {'Content-Type': (mime[path.extname(file)] || 'application/octet-stream') + '; charset=utf-8', 'Cache-Control': 'no-store'});
  response.end(fs.readFileSync(file));
});

function createFixture() {
  const fixture = {count: 12, pin: 1, cards: Array.from({length: 8}, (_, i) => i), revision: 0, requests: {feed: 0, cards: 0}, now: Date.now()};
  fixture.message = index => ({id: 'message-' + index, groupId: 'regular', senderType: 'bot', sentAt: new Date(fixture.now - 120000 + index * 1000).toISOString(), title: `R0 +0.40% | SYNTH${index} | FF | P75 +0.43% | GT→BN`, body: '盘口差 +0.402%\n仅用于本地滚动回归，合成数据。', actions: []});
  fixture.feed = () => ({sourceConnected: true, updatedAt: new Date(fixture.now).toISOString(), messages: Array.from({length: fixture.count}, (_, i) => fixture.message(i)), pinned: {id: 'pin-' + fixture.pin, groupId: 'pin', senderType: 'bot', sentAt: new Date(fixture.now - 1000).toISOString(), title: 'Synthetic pinned message', body: Array.from({length: fixture.pin}, (_, i) => '本地合成置顶说明 ' + i).join('\n'), actions: []}});
  fixture.card = index => ({id: 'card-' + index + (fixture.renewed === index ? '-renewed' : ''), pair: 'pair-' + index, asset: fixture.renameTop && index === 0 ? 'ZZZ' : 'SYNTH' + index, strategy: 'FF', trigger: 'v2_price_window', enteredAt: new Date(fixture.now - 60000).toISOString(), validUntil: new Date(fixture.now + 300000).toISOString(), v2Residual: {level: 1, bps: 40 + fixture.revision}, details: {netBps: 15, marketBps: 23, p75Bps: 25, indexBps: -13, newsWarnings: fixture.tallTop && index === 0 ? [{exchange: 'gate', summary: '仅用于本地测试的多行卡片说明。'.repeat(30)}] : [], legs: [{exchange: 'gate', symbol: 'SYNTH' + index + 'USDT', spot: false, rate: 0.0001, hours: 4, volume: 721000, oi: 882900}, {exchange: 'binance', symbol: 'SYNTH' + index + 'USDT', spot: false, rate: 0.0001, hours: 4, volume: 8620000, oi: 11450000}]}});
  fixture.snapshot = () => ({status: 'connected', receivedAt: new Date(fixture.now).toISOString(), snapshot: {sampledAt: new Date(fixture.now).toISOString(), complete: true, active: fixture.cards.map(fixture.card)}});
  return fixture;
}

async function sample(page, target) {
  return page.evaluate(id => {
    const card = document.querySelector('.bp-card[data-id="' + id + '"], .bp-card[data-id="' + id + '-renewed"]');
    const rect = card?.getBoundingClientRect();
    const board = document.querySelector('#board');
    const pin = document.querySelector('#pinned');
    const feedTop = board.getBoundingClientRect().top + (getComputedStyle(pin).position === 'sticky' ? pin.offsetHeight : 0);
    const reading = [...document.querySelectorAll('#feed .message')].find(el => el.getBoundingClientRect().bottom > feedTop + 1);
    return {scrollY, maxScrollY: document.documentElement.scrollHeight - innerHeight, target: id, targetTop: rect?.top ?? null, targetBottom: rect?.bottom ?? null, targetLevel: card?.querySelector('.bp-level')?.textContent, documentHeight: document.documentElement.scrollHeight, paneScroll: document.querySelector('#basis-pane').scrollTop, boardScroll: board.scrollTop, boardHeight: board.getBoundingClientRect().height, readingMessage: reading ? {id: reading.dataset.id, top: reading.getBoundingClientRect().top} : null, cardIds: [...document.querySelectorAll('.bp-card')].map(el => el.dataset.id), feedIds: [...document.querySelectorAll('#feed .message')].map(el => el.dataset.id), pinnedId: document.querySelector('#pinned .message')?.dataset.id, activeElement: document.activeElement?.tagName};
  }, target);
}
async function advance(page, fixture, milliseconds) {
  // Advance in small steps so the real fetch/promise chain settles between
  // successive scheduled polls. Never skip repeated expiry/render callbacks.
  for (let left = milliseconds; left > 0; left -= 500) {
    const step = Math.min(500, left);
    fixture.now += step;
    await page.clock.runFor(step);
    await page.evaluate(() => Promise.resolve());
  }
}

const cases = [
  {name: 'feed-arrival', target: 'card-4', change(f) {f.count += 2;}, duration: 6500, expected: f => f.feedIds.includes('message-13')},
  {name: 'feed-arrival-at-bottom', target: 'card-7', bottom: true, change(f) {f.count += 2;}, duration: 6500, expected: f => f.feedIds.includes('message-13')},
  {name: 'feed-arrival-while-reading-history', target: 'card-4', history: true, change(f) {f.count += 2;}, duration: 6500, expected: f => f.feedIds.includes('message-13'), verify: (a, b) => a.readingMessage?.id === b.readingMessage?.id && Math.abs(a.readingMessage.top - b.readingMessage.top) <= 2},
  {name: 'feed-history-trim', target: 'card-4', change(f) {f.count = 34;}, duration: 6500, expected: f => f.feedIds.length === 30 && f.feedIds.at(-1) === 'message-33'},
  {name: 'pinned-message-grows', target: 'card-4', change(f) {f.pin = 18;}, duration: 6500, expected: f => f.pinnedId === 'pin-18'},
  {name: 'card-data-refresh', target: 'card-4', change(f) {f.revision++;}, duration: 11500, expected: f => f.targetLevel?.includes('+0.41%')},
  {name: 'new-card-sorts-above', target: 'card-4', change(f) {f.cards.unshift(-1);}, duration: 16500, expected: f => f.cardIds[0] === 'card--1'},
  {name: 'upper-card-reorders-below', target: 'card-4', change(f) {f.renameTop = true;}, duration: 16500, expected: f => f.cardIds.at(-1) === 'card-0'},
  {name: 'visible-pair-renews-id', target: 'card-4', change(f) {f.renewed = 4;}, duration: 11500, expected: f => f.cardIds.includes('card-4-renewed') && !f.cardIds.includes('card-4')},
  {name: 'upper-card-grows-tall', target: 'card-4', change(f) {f.tallTop = true;}, duration: 11500, verify: (a, b) => viewport.width > 900 || b.documentHeight - a.documentHeight > 200},
  {name: 'upper-card-expires', target: 'card-4', change(f) {f.cards = f.cards.filter(id => id !== 0);}, duration: 36500, expected: f => !f.cardIds.includes('card-0')},
  {name: 'upper-card-expires-at-bottom', target: 'card-7', bottom: true, change(f) {f.cards = f.cards.filter(id => id !== 0);}, duration: 36500, expected: f => !f.cardIds.includes('card-0')},
  {name: 'visible-anchor-expires', target: 'card-4', sampleTarget: 'card-5', readAtTop: true, change(f) {f.cards = f.cards.filter(id => id !== 4);}, duration: 36500, expected: f => !f.cardIds.includes('card-4')},
];

async function runCase(browser, engine, test, origin) {
  const context = await browser.newContext({viewport, deviceScaleFactor: 1, isMobile: viewport.width <= 900, hasTouch: viewport.width <= 900, serviceWorkers: 'block'});
  const fixture = createFixture();
  const errors = [], forbidden = [], missing = [];
  await context.addInitScript(() => {
    // Shared-worker scripts are outside the captured entry dependency graph.
    // Use the app's real, supported page-local polling fallback.
    Object.defineProperty(window, 'SharedWorker', {value: undefined, configurable: true});
    localStorage.setItem('robot-push-ui', JSON.stringify({enabled: true, seconds: 5, sound: false}));
  });
  await context.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url());
    if (url.origin !== origin) { forbidden.push(url.origin + url.pathname); await route.abort(); return; }
    const respond = body => route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(body)});
    if (url.pathname.endsWith('/feed.json')) {fixture.requests.feed++; await respond(fixture.feed()); return;}
    if (url.pathname.endsWith('/basispulse.json')) {fixture.requests.cards++; await respond(fixture.snapshot()); return;}
    if (url.pathname.startsWith('/radar/push-test/api/')) {await route.fulfill({status: 401, contentType: 'application/json', body: '{"error":"Synthetic unauthenticated fixture"}'}); return;}
    await route.continue();
  });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  page.on('response', response => {const pathname = new URL(response.url()).pathname; if (response.status() === 404 && !pathname.endsWith('.webmanifest')) missing.push(pathname);});
  await page.clock.install({time: new Date(fixture.now)});
  await page.clock.pauseAt(new Date(fixture.now + 100));
  fixture.now += 100;
  try {
    await page.goto(origin + '/radar/robot-push/', {waitUntil: 'load'});
    await advance(page, fixture, 1500);
    await page.locator('.bp-card').last().waitFor();
    assert.equal(await page.locator('.bp-card').count(), 8, 'fixture must render all opportunity cards');
    if (test.history) {
      const bounds = await page.locator('#board').boundingBox();
      await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
      await page.mouse.wheel(0, -200);
      await advance(page, fixture, 100);
    }
    await page.evaluate(({target, bottom, readAtTop}) => {
      const card = document.querySelector('.bp-card[data-id="' + target + '"]');
      if (innerWidth > 900) {
        const pane = document.querySelector('#basis-pane');
        pane.scrollTop = bottom ? pane.scrollHeight : pane.scrollTop + card.getBoundingClientRect().top - 160;
      } else window.scrollTo(0, bottom ? document.documentElement.scrollHeight : window.scrollY + card.getBoundingClientRect().top - (readAtTop ? 0 : 160));
    }, {target: test.target, bottom: !!test.bottom, readAtTop: !!test.readAtTop});
    await advance(page, fixture, 600); // includes existing 240 ms quiet period
    const target = test.sampleTarget || test.target;
    const before = await sample(page, target);
    assert.ok((viewport.width > 900 ? before.paneScroll > 0 : before.scrollY > 500) && before.targetBottom > 0 && before.targetTop < viewport.height, 'card must be on screen after scrolling into card list: ' + JSON.stringify(before));
    const frames = [];
    // rAF sampling catches a visible transient jump that a final-only assertion
    // could miss (e.g. remove -> scroll clamp -> reinsert).
    await page.evaluate(target => {
      window.__scrollSamples = [];
      window.__scrollSampling = true;
      function record() {
        const card = document.querySelector('.bp-card[data-id="' + target + '"], .bp-card[data-id="' + target + '-renewed"]');
        if (card) window.__scrollSamples.push({y: scrollY, top: card.getBoundingClientRect().top});
        if (window.__scrollSampling) requestAnimationFrame(record);
      }
      requestAnimationFrame(record);
    }, target);
    test.change(fixture);
    await advance(page, fixture, test.duration);
    const after = await sample(page, target);
    frames.push(...await page.evaluate(() => {window.__scrollSampling = false; return window.__scrollSamples;}));
    const expectedMutation = (!test.expected || test.expected(after)) && (!test.verify || test.verify(before, after));
    const largestShift = Math.max(0, ...frames.map(frame => Math.abs(frame.top - before.targetTop)));
    return {engine, name: test.name, viewport, passed: expectedMutation && errors.length === 0 && missing.length === 0 && Math.abs(after.targetTop - before.targetTop) <= 2 && largestShift <= 2 && (viewport.width <= 900 || before.scrollY === 0 && after.scrollY === 0), expectedMutation, before, after, targetShift: after.targetTop - before.targetTop, scrollDelta: after.scrollY - before.scrollY, largestFrameShift: largestShift, frames: frames.length, requests: fixture.requests, errors, forbidden, missing};
  } finally {await context.close();}
}

(async () => {
  const results = [];
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = 'http://127.0.0.1:' + server.address().port;
  try {
    for (const engine of engines) {
      assert.ok(playwright[engine], 'Unknown browser engine ' + engine);
      if (!fs.existsSync(playwright[engine].executablePath())) {results.push({engine, skipped: true, reason: 'Browser binary not installed', executable: playwright[engine].executablePath()}); continue;}
      const browser = await playwright[engine].launch({headless: true});
      try {
        const selected = options.case?.split(',');
        if (selected) assert.ok(selected.every(name => cases.some(test => test.name === name)), 'Unknown test case');
        const queue = cases.filter(test => !selected || selected.includes(test.name));
        await Promise.all(Array.from({length: Math.min(Number(options.jobs) || 2, queue.length)}, async () => {
          while (queue.length) {
            const result = await runCase(browser, engine, queue.shift(), origin);
            results.push(result);
            console.log(JSON.stringify({engine, name: result.name, passed: result.passed, targetShift: result.targetShift, scrollDelta: result.scrollDelta, largestFrameShift: result.largestFrameShift, missing: result.missing, errors: result.errors}));
          }
        }));
      } finally {await browser.close();}
    }
  } finally {await new Promise(resolve => server.close(resolve));}
  const report = {baseline, overlay: overlay || null, provenance, generatedAt: new Date().toISOString(), results, passed: results.length > 0 && results.every(item => item.passed)};
  if (options.out) {const out = path.resolve(options.out); fs.mkdirSync(path.dirname(out), {recursive: true}); fs.writeFileSync(out, JSON.stringify(report, null, 2) + '\n');}
  console.log(JSON.stringify({passed: report.passed, cases: results.length, report: options.out || null}));
  process.exitCode = report.passed ? 0 : 1;
})().catch(error => {console.error(error.stack); server.close(); process.exitCode = 2;});

/* Home Screen navigation stays in the installed app; external links stay external. */
(function () {
  function installed() { return navigator.standalone === true || matchMedia('(display-mode: standalone)').matches; }
  document.addEventListener('click', function (event) {
    if (!installed() || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    var link = event.target.closest && event.target.closest('a[href]');
    if (!link || link.hasAttribute('download') || link.target.toLowerCase() !== '_blank') return;
    var url;
    try { url = new URL(link.href, location.href); } catch (_) { return; }
    if (url.origin !== location.origin || !url.pathname.startsWith('/radar/')) return;
    link.target = '_self';
  }, true);
  if (!/^\/radar\/push-test\/?$/.test(location.pathname) || !installed()) return;
  if (!matchMedia('(min-width:720px) and (max-width:1199px) and (hover:none) and (pointer:coarse)').matches) return;
  var target = new URL('/radar/robot-push/', location.origin);
  target.search = location.search;
  target.hash = location.hash;
  location.replace(target.href);
})();

/* Temporary geometry-only probe, expires 2026-11-16 00:00 UTC. No identifiers or page content. */
(function () {
  if (typeof window === 'undefined' || Date.now() >= Date.UTC(2026, 10, 16)) return;
  // Some large/folded Apple viewports retain the small outer screen dimensions.
  // Do not use screen size to decide whether geometry can be diagnosed.
  if (!matchMedia('(pointer:coarse)').matches && !(navigator.maxTouchPoints > 0)) return;
  var src = document.currentScript && document.currentScript.src;
  if (!src) return;
  var endpoint = new URL(src, location.href);
  if (endpoint.origin !== location.origin) return;
  endpoint.search = ''; endpoint.hash = '';
  var key = 'radar-geometry-20261114', sent = 0;
  function n(value) { return Number.isFinite(value) ? Math.round(value * 100) / 100 : -1; }
  function report(phase) {
    if (sent >= 3 || Date.now() >= Date.UTC(2026, 10, 16) || !document.body) return;
    try {
      var total = Number(sessionStorage.getItem(key) || 0);
      if (!Number.isFinite(total) || total >= 18) return;
      sessionStorage.setItem(key, String(total + 1));
      sent++;
      var safe = document.createElement('div');
      safe.style.cssText = 'position:fixed;visibility:hidden;pointer-events:none;width:0;height:0;padding:env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left);';
      document.body.appendChild(safe);
      var st = getComputedStyle(safe);
      var inset = ['Top','Right','Bottom','Left'].map(function (side) { return n(parseFloat(st['padding' + side])); });
      safe.remove();
      var root = document.documentElement, body = document.body, main = document.querySelector('main') || body;
      var b = body.getBoundingClientRect(), m = main.getBoundingClientRect(), v = window.visualViewport;
      var path = location.pathname;
      var page = /push-test/.test(path) ? 'legacy' : /alarms/.test(path) ? 'alarms' : /settings/.test(path) ? 'settings' : /robot-push/.test(path) ? 'bot' : /position-limits/.test(path) ? 'limits' : /push-center/.test(path) ? 'push' : 'main';
      var data = {
        phase:phase,page:page,installed:navigator.standalone === true,standalone:matchMedia('(display-mode: standalone)').matches,
        coarse:matchMedia('(pointer:coarse)').matches,touch:n(navigator.maxTouchPoints),
        screen:[n(screen.width),n(screen.height),n(screen.availWidth),n(screen.availHeight)],
        window:[n(innerWidth),n(innerHeight),n(outerWidth),n(outerHeight),n(devicePixelRatio)],
        viewport:v ? [n(v.width),n(v.height),n(v.offsetLeft),n(v.offsetTop),n(v.scale)] : [],
        document:[n(root.clientWidth),n(root.scrollWidth),n(body.scrollWidth)],
        body:[n(b.left),n(b.width)],main:[n(m.left),n(m.width)],safe:inset
      };
      var url = new URL(endpoint.href);
      url.searchParams.set('radar_geometry_v1', JSON.stringify(data));
      url.searchParams.set('sample', String(Date.now()));
      fetch(url.href, {credentials:'same-origin',cache:'no-store',referrerPolicy:'no-referrer'}).catch(function () {});
    } catch (_) { /* Diagnostic failure must not affect the page. */ }
  }
  function start() { report('ready'); setTimeout(function () { report('settled'); }, 1500); setTimeout(function () { report('late'); }, 5000); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once:true}); else start();
})();

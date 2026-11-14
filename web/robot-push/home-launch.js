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

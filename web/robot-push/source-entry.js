const basis = new URLSearchParams(location.search).get('source') === 'basispulse';
const modes = document.createElement('nav');
modes.className = 'source-modes'; modes.setAttribute('aria-label', '推送数据来源');
for (const [label, url, selected] of [['机器人消息', './', !basis], ['BasisPulse 机会', './?source=basispulse', basis]]) {
  const a = document.createElement('a'); a.textContent = label; a.href = url;
  if (selected) a.setAttribute('aria-current', 'page'); modes.append(a);
}
document.querySelector('main').prepend(modes);
if (basis) await import('./basispulse.js?v=20261004d');
else await import('./page.js?v=20261003m');

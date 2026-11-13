// Mobile-only layout adapter. Moves existing elements without replacing handlers or saving rules.
(() => {
  const settings = document.querySelector('.settings');
  if (!settings || document.getElementById('mobile-batch-toggle')) return;
  document.body.classList.add('mobile-settings');
  const heading = document.createElement('div');
  heading.className = 'mobile-settings-heading';
  heading.innerHTML = '<h2>消息设置</h2><details class="mobile-more"><summary>更多 ···</summary><div class="mobile-more-content"></div></details>';
  settings.before(heading);
  const content = heading.querySelector('.mobile-more-content');
  const moved = [...document.querySelectorAll('.settings-intro,#panel-coins>.section>.section-heading>div>p,#panel-coins>.section>p.helper:not(#coin-sync-status)')].map(node => {
    const anchor = document.createComment('mobile-layout-origin');
    node.before(anchor);
    return {node, anchor};
  });
  const media = matchMedia('(max-width:700px)');
  function apply() {
    for (const {node, anchor} of moved) {
      if (media.matches) content.append(node);
      else anchor.after(node);
    }
    if (!media.matches) heading.querySelector('details').open = false;
  }
  media.addEventListener('change', apply);
  apply();
  const batch = document.createElement('button');
  batch.id = 'mobile-batch-toggle';
  batch.type = 'button';
  batch.textContent = '批量管理';
  batch.setAttribute('aria-expanded', 'false');
  batch.addEventListener('click', () => {
    const open = document.body.classList.toggle('is-batch');
    batch.setAttribute('aria-expanded', String(open));
    batch.textContent = open ? '完成' : '批量管理';
    if (!open) document.getElementById('clear-selected')?.click();
  });
  document.getElementById('refresh-coins').before(batch);
})();

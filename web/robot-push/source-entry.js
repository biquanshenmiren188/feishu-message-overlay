const main=document.querySelector('main');
document.body.classList.add('split-mode');
document.documentElement.classList.add('split-layout');
const feedPane=document.createElement('section');feedPane.className='feed-pane';feedPane.setAttribute('aria-label','机器人推送');
const title=document.createElement('h1');title.className='feed-pane-title';title.textContent='机器人推送';
feedPane.append(title,...main.children);
const basisPane=document.createElement('section');basisPane.id='basis-pane';basisPane.setAttribute('aria-label','BasisPulse 机会卡片');
main.append(feedPane,basisPane);
await Promise.all([import('./page.js?v=20261005split1'),import('./basispulse.js?v=20261005ui2')]);

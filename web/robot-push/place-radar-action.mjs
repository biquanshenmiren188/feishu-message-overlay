// Move existing anchors; keep their original URLs and click behavior.
export function placeRadarAction(article) {
 const spread=article.querySelector('.summary-spread');
 const footer=article.querySelector(':scope > .actions');
 if(!spread||!footer)return;
 const links=[...footer.querySelectorAll('a')].filter(a=>a.textContent.trim()==='查看雷达');
 if(!links.length)return;
 const row=document.createElement('div');row.className='summary-spread-row';
 const actions=document.createElement('div');actions.className='actions inline-radar-actions';
 spread.replaceWith(row);row.append(spread,actions);actions.append(...links);
 if(!footer.children.length)footer.remove();
}

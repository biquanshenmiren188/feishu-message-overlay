export function clusterCard(message,pinned,detail,openOriginal){
 if(!message.title.includes('强信号聚集')||detail)return null;
 const el=(tag,cls,text)=>{const n=document.createElement(tag);n.className=cls;if(text)n.textContent=text;return n;};
 const root=el('article','message cluster-card'+(pinned?' pin':''));root.dataset.id=message.id;
 const head=el('div','message-head');head.append(el('h2','message-title',(pinned?'置顶 · ':'')+message.title.replace(/🚨/gu,'').trim()),el('time','',new Date(Date.parse(message.sentAt)+28800000).toISOString().slice(11,16)));root.append(head);
 const lines=message.body.split(/\r?\n/).map(s=>s.trim()).filter(Boolean),intro=lines.filter(s=>/^(涉及|各组合)/u.test(s));
 root.append(el('p','cluster-intro',intro.join(' · ')));
 const groups=[];for(let i=0;i<lines.length;i++)if(/^R\d+\+?\s*[|｜]/u.test(lines[i]))groups.push([lines[i],lines[i+1]||'']);
 const details=el('details','cluster-groups');details.open=pinned&&!matchMedia('(max-width:700px)').matches;
 const summary=el('summary','',`查看 ${groups.length} 组组合`);details.append(summary);
 groups.forEach(([route,value],i)=>{const row=el('div','cluster-group');row.append(el('strong','',route),el('p','',value));if(message.groupOutcomes?.[i]==='hide')row.append(el('span','cluster-blocked','此组已屏蔽'));details.append(row);});root.append(details);
 const actions=el('div','actions');for(const a of message.actions||[]){try{const u=new URL(a.url);if(!['https:','http:'].includes(u.protocol)||u.username||u.password)continue;const link=el('a','',a.label);link.href=a.url;link.target='_blank';link.rel='noopener noreferrer';actions.append(link);}catch{}}
 const original=el('button','cluster-original','完整原文');original.type='button';original.onclick=()=>openOriginal(message,pinned);actions.append(original);root.append(actions);return root;
}

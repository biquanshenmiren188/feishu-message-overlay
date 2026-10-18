// Presentation only: move the existing rank/value pair, preserving its precision.
export function rankFirstTitle(title) {
 const text=String(title??'');
 const parts=text.split(/[｜|]/u).map(part=>part.trim());
 const index=parts.findIndex(part=>/^R\d+\+?\s+[+−-]?\d+(?:\.\d+)?\s*%$/iu.test(part));
 if(index<=0)return text;
 return [parts[index],...parts.filter((_,i)=>i!==index)].join('｜');
}

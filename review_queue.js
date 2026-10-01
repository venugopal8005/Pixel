(function(root){
  function rank(segment){
    if(segment.category==='unrecognized')return 0;
    if((segment.reason||'').startsWith('Readings disagree'))return 1;
    return segment.category==='single'?3:2;
  }
  function buildQueue(state,all=false){
    const items=[];let pending=0,total=0;
    for(const record of state.records)for(const line of record.lines)for(const segment of line.segments){
      const confirmed=Object.hasOwn(state.decisions,segment.id);
      if(segment.category!=='single'){total++;if(!confirmed)pending++;}
      if(all||(!confirmed&&segment.category!=='single'))items.push({record,line,segment});
    }
    if(!all)items.sort((a,b)=>rank(a.segment)-rank(b.segment)||(a.segment.score??0)-(b.segment.score??0));
    return {items,pending,total};
  }
  function focus(queue,record,line,segment){
    const index=queue.findIndex(item=>item.segment.id===segment.id);
    if(index>=0)return index;
    queue.unshift({record,line,segment});return 0;
  }
  const api={buildQueue,focus};
  if(typeof module!=='undefined')module.exports=api;else root.PixelQueue=api;
})(typeof window!=='undefined'?window:globalThis);

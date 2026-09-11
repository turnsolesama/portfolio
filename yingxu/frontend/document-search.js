/* Literal, bounded document search over the current draft; never edits content. */
(function(scope){
  'use strict';
  const MAX_MATCHES=10000,MAX_CHARACTERS=2000000,MAX_QUERY=256;
  function findMatches(segments,query){
    query=String(query??'').slice(0,MAX_QUERY);
    const matches=[];let scanned=0,limited=false;
    if(!query)return {matches,limited,scanned};
    const regex=new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'giu');
    for(let segmentIndex=0;segmentIndex<(segments||[]).length;segmentIndex++){
      const segment=segments[segmentIndex],source=String(segment.text??''),remaining=MAX_CHARACTERS-scanned;
      if(remaining<=0){limited=true;break;}
      const text=source.slice(0,remaining);scanned+=text.length;if(text.length<source.length)limited=true;
      regex.lastIndex=0;let match;
      while((match=regex.exec(text))){
        if(matches.length===MAX_MATCHES){limited=true;break;}
        matches.push({segmentId:String(segment.id??segmentIndex),segmentIndex,from:match.index,to:match.index+match[0].length});
      }
      if(matches.length===MAX_MATCHES&&limited)break;
    }
    return {matches,limited,scanned};
  }
  function install({parent,getDocument,onReveal=()=>{},onClear=()=>{}}){
    const doc=parent.ownerDocument,win=doc.defaultView;
    const bar=doc.createElement('div');bar.className='document-search';bar.hidden=true;bar.setAttribute('role','search');bar.setAttribute('aria-label','当前文档查找');
    bar.innerHTML='<label><span class="sr-only">查找正文</span><input type="search" maxlength="256" placeholder="查找当前正文…" data-document-query autocomplete="off" spellcheck="false"></label><span class="document-search-count" data-document-count aria-live="polite"></span><button type="button" data-document-prev title="上一个（Shift+Enter）" aria-label="上一个匹配">↑</button><button type="button" data-document-next title="下一个（Enter）" aria-label="下一个匹配">↓</button><button type="button" data-document-close title="关闭查找（Esc）" aria-label="关闭文档查找">×</button><small data-document-notice></small>';
    parent.appendChild(bar);
    const input=bar.querySelector('[data-document-query]'),count=bar.querySelector('[data-document-count]'),notice=bar.querySelector('[data-document-notice]');
    const prev=bar.querySelector('[data-document-prev]'),next=bar.querySelector('[data-document-next]');
    let key=null,result={matches:[],limited:false},active=-1,timer=0,ticket=0,disposed=false,prior=null;
    function draw(){count.textContent=input.value?(result.matches.length?`${active+1} / ${result.matches.length}${result.limited?'+':''}`:'0 / 0'):'输入查找词';prev.disabled=next.disabled=!result.matches.length;notice.textContent=result.limited?'文稿或匹配数量较多，当前仅显示限额内结果；可缩短查找范围。':'';}
    function current(){const value=getDocument();return value&&String(value.key)===key?value:null;}
    function cancel(){if(timer)win.clearTimeout(timer);timer=0;ticket++;}
    function close(restore=true){if(bar.hidden)return;cancel();bar.hidden=true;key=null;result={matches:[],limited:false};active=-1;onClear();if(restore&&prior?.isConnected)prior.focus();}
    async function reveal(focus=false){
      if(active<0||!result.matches.length||!current())return;
      const selected=result.matches[active],stamp=ticket,keepInput=doc.activeElement===input,from=input.selectionStart,to=input.selectionEnd;
      try{await onReveal(selected,{focus});}catch(error){if(stamp===ticket&&!bar.hidden)notice.textContent=error.message||'暂时无法定位此处。';}
      if(stamp===ticket&&!bar.hidden&&keepInput){input.focus();if(input.type!=='search')input.setSelectionRange(from,to);}
    }
    function search(preserve=false,revealResult=true){
      timer=0;if(disposed||bar.hidden)return;
      const snapshot=current();if(!snapshot){close(false);return;}
      const previous=preserve?result.matches[active]:null;result=findMatches(snapshot.segments,input.value);
      active=result.matches.length?0:-1;
      if(previous){const index=result.matches.findIndex(m=>m.segmentId===previous.segmentId&&m.from===previous.from);if(index>=0)active=index;}
      onClear();draw();if(revealResult)reveal(false);
    }
    function refresh(){if(bar.hidden||disposed)return;cancel();timer=win.setTimeout(()=>search(true),100);}
    function move(direction){if(bar.hidden||disposed)return;cancel();const old=result.matches[active];search(true,false);if(!result.matches.length)return;if(old&&result.matches.some(m=>m.segmentId===old.segmentId&&m.from===old.from))active=(active+direction+result.matches.length)%result.matches.length;draw();reveal(true);}
    function open(seed){
      if(disposed)return false;const snapshot=getDocument();if(!snapshot||!Array.isArray(snapshot.segments))return false;
      if(bar.hidden){prior=doc.activeElement;key=String(snapshot.key);bar.hidden=false;}else if(key!==String(snapshot.key)){onClear();key=String(snapshot.key);}
      if(seed!==undefined)input.value=String(seed).slice(0,MAX_QUERY);
      cancel();search();input.focus();input.select();return true;
    }
    function changed(event){if(event.isComposing)return;refresh();}
    function keydown(event){if(event.isComposing)return;if(event.key==='Escape'){event.preventDefault();event.stopPropagation();close();}else if(event.key==='Enter'){event.preventDefault();event.stopPropagation();move(event.shiftKey?-1:1);}}
    const click=event=>{if(event.target.closest('[data-document-close]'))close();else if(event.target.closest('[data-document-prev]'))move(-1);else if(event.target.closest('[data-document-next]'))move(1);};
    input.addEventListener('input',changed);input.addEventListener('compositionend',refresh);bar.addEventListener('keydown',keydown);bar.addEventListener('click',click);draw();
    return {open,close,refresh,next:()=>move(1),previous:()=>move(-1),isOpen:()=>!bar.hidden,element:bar,
      getState:()=>({query:input.value,count:result.matches.length,active,limited:result.limited,key}),
      destroy(){if(disposed)return;close(false);disposed=true;input.removeEventListener('input',changed);input.removeEventListener('compositionend',refresh);bar.removeEventListener('keydown',keydown);bar.removeEventListener('click',click);bar.remove();}};
  }
  scope.YingXuDocumentSearch={install,findMatches,MAX_MATCHES,MAX_CHARACTERS,MAX_QUERY};
  if(typeof module!=='undefined')module.exports=scope.YingXuDocumentSearch;
})(typeof window!=='undefined'?window:globalThis);

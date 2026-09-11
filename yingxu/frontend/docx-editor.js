/* Bounded Word text editor: only one page of paragraph controls is mounted. */
(function(scope){
  'use strict';
  const PAGE_SIZE=40;
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function mount({parent,paragraphs=[],editable=false,page=0,onChange=()=>{},onPageChange=()=>{},onBlocked=()=>{}}){
    const win=parent.ownerDocument.defaultView;
    let current=Math.max(0,Math.min(Math.max(0,Math.ceil(paragraphs.length/PAGE_SIZE)-1),Math.floor(Number(page)||0)));
    let composing=false,disposed=false,frame=0,pending=null;
    const totalPages=Math.max(1,Math.ceil(paragraphs.length/PAGE_SIZE));
    const height=editor=>Math.min(1000,Math.max(56,editor.scrollHeight+2));
    function cancelResize(){if(frame)win.cancelAnimationFrame(frame);frame=0;pending=null;}
    function resize(editor){pending=editor;if(frame)return;frame=win.requestAnimationFrame(()=>{frame=0;const target=pending;pending=null;if(disposed||!target?.isConnected||!parent.contains(target))return;target.style.height='auto';const pixels=height(target);target.style.height=`${pixels}px`;});}
    function controls(){const prev=parent.querySelector('[data-docx-prev]'),next=parent.querySelector('[data-docx-next]');if(prev)prev.disabled=composing||current===0;if(next)next.disabled=composing||current>=totalPages-1;for(const node of parent.querySelectorAll('[data-docx-page-input],[data-docx-go]'))node.disabled=composing;}
    function draw(){
      cancelResize();
      const start=current*PAGE_SIZE,end=Math.min(start+PAGE_SIZE,paragraphs.length);
      const rows=paragraphs.slice(start,end).map((p,i)=>`<div class="docx-paragraph"><span class="paragraph-number">${start+i+1}</span><div class="docx-paragraph-field"><textarea data-paragraph="${esc(p.id)}" data-docx-index="${start+i}" aria-label="第 ${start+i+1} 段" ${!editable||p.editable===false?'readonly':''}>${esc(p.text)}</textarea>${p.readonly_reason?`<p class="field-hint">${esc(p.readonly_reason)}</p>`:''}</div></div>`).join('');
      parent.innerHTML=`<div class="docx-editor-pagination" role="navigation" aria-label="Word 段落分页"><span class="docx-page-range" aria-live="polite">${paragraphs.length?`第 ${start+1}–${end} 段 · 共 ${paragraphs.length} 段`:'暂无正文段落'}</span><div class="docx-page-controls"><button type="button" class="button button-secondary button-small" data-docx-prev>上一页</button><label>第 <input type="number" min="1" max="${totalPages}" value="${current+1}" data-docx-page-input aria-label="Word 页码"> / ${totalPages} 页</label><button type="button" class="button button-secondary button-small" data-docx-go>前往</button><button type="button" class="button button-secondary button-small" data-docx-next>下一页</button></div></div><p class="docx-page-hint">每页最多 40 段，翻页保留全部未保存修改。</p><div class="docx-page-paragraphs">${rows||'<p class="relation-empty">此文件没有可编辑的正文段落。</p>'}</div>`;
      // All controls are inserted before geometry reads, then all heights are
      // written together: no write/read alternation over thousands of nodes.
      const editors=[...parent.querySelectorAll('[data-docx-index]')];
      const heights=editors.map(height);
      editors.forEach((editor,i)=>{editor.style.height=`${heights[i]}px`;});
      controls();
    }
    function goTo(next){
      if(disposed)return false;
      if(composing){onBlocked();return false;}
      const index=Math.max(0,Math.min(totalPages-1,Math.floor(Number(next)||0)));
      if(index===current)return true;
      current=index;draw();onPageChange(current);const scroller=parent.closest('.docx-editor');if(scroller)scroller.scrollTop=0;return true;
    }
    function targetParagraph(target){const index=Number(target?.dataset?.docxIndex);if(!Number.isInteger(index)||index<current*PAGE_SIZE||index>=Math.min((current+1)*PAGE_SIZE,paragraphs.length))return null;const p=paragraphs[index];return target.matches('textarea[data-docx-index]')&&parent.contains(target)&&String(p.id)===target.dataset.paragraph?p:null;}
    function update(target){const p=targetParagraph(target);if(!p||!editable||p.editable===false)return;if(p.text!==target.value){p.text=target.value;onChange(p);}resize(target);}
    const input=event=>update(event.target);
    const start=event=>{if(targetParagraph(event.target)){composing=true;controls();}};
    const end=event=>{if(targetParagraph(event.target)){composing=false;update(event.target);controls();}};
    const click=event=>{const button=event.target.closest('[data-docx-prev],[data-docx-next],[data-docx-go]');if(!button||!parent.contains(button))return;event.preventDefault();if(button.hasAttribute('data-docx-prev'))goTo(current-1);else if(button.hasAttribute('data-docx-next'))goTo(current+1);else goTo(Number(parent.querySelector('[data-docx-page-input]').value)-1);};
    const key=event=>{if(event.key==='Enter'&&event.target.matches('[data-docx-page-input]')){event.preventDefault();goTo(Number(event.target.value)-1);}};
    for(const [type,listener] of [['input',input],['compositionstart',start],['compositionend',end],['click',click],['keydown',key]])parent.addEventListener(type,listener);
    draw();
    function clearSearch(){for(const node of parent.querySelectorAll('.docx-search-current'))node.classList.remove('docx-search-current');}
    function revealMatch({segmentIndex,from,to},{focus=true}={}){
      if(!Number.isInteger(segmentIndex)||segmentIndex<0||segmentIndex>=paragraphs.length)return false;
      if(!goTo(Math.floor(segmentIndex/PAGE_SIZE)))return false;
      const editor=parent.querySelector(`[data-docx-index="${segmentIndex}"]`);if(!editor)return false;
      clearSearch();editor.closest('.docx-paragraph').classList.add('docx-search-current');
      if(focus)editor.focus();editor.setSelectionRange(Math.max(0,from),Math.min(editor.value.length,to));editor.scrollIntoView({block:'center'});return true;
    }
    return {getPage:()=>current,isComposing:()=>composing,goTo,revealMatch,clearSearch,destroy(){if(disposed)return;disposed=true;cancelResize();for(const [type,listener] of [['input',input],['compositionstart',start],['compositionend',end],['click',click],['keydown',key]])parent.removeEventListener(type,listener);}};
  }
  scope.YingXuDocxEditor={mount,PAGE_SIZE};
  if(typeof module!=='undefined')module.exports={mount,PAGE_SIZE};
})(typeof window!=='undefined'?window:globalThis);

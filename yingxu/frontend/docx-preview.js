(function (scope) {
  'use strict';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const PAGE_SIZE=40;
  function render(content, paragraphs, options={}) {
    paragraphs=paragraphs||[];
    const page=Math.max(0,Math.min(Math.max(0,Math.ceil(paragraphs.length/PAGE_SIZE)-1),Math.floor(Number(options.page)||0)));
    const indexes=new Map(paragraphs.map((value,index)=>[String(value.id),index]));
    const visible=new Set(paragraphs.slice(page*PAGE_SIZE,(page+1)*PAGE_SIZE).map(value=>String(value.id)));
    let unavailableCount=0;
    const byId = new Map((paragraphs || []).map(value => [String(value.id),value]));
    const paragraph = id => {
      const p = byId.get(String(id)); if (!p||!visible.has(String(id))) return '';
      const heading = Math.max(0,Math.min(6,Number(p.heading_level) || 0));
      const tag = heading ? `h${heading}` : 'p';
      const align = ['left','center','right','justify'].includes(p.alignment) ? p.alignment : 'left';
      const runs = Array.isArray(p.runs) && p.runs.map(run => run.text).join('') === p.text ? p.runs : [{text:p.text}];
      const text = runs.map(run => {
        const css = [];
        if (run.bold) css.push('font-weight:700'); if (run.italic) css.push('font-style:italic'); if (run.underline) css.push('text-decoration:underline');
        if (/^#[a-f\d]{6}$/i.test(run.color || '')) css.push(`color:${run.color}`);
        if (Number.isFinite(run.font_size) && run.font_size >= 6 && run.font_size <= 96) css.push(`font-size:${run.font_size}pt`);
        return `<span style="${css.join(';')}">${escape(run.text)}</span>`;
      }).join('');
      const images = (p.images || []).map(image => /^data:image\/(png|jpeg|gif|webp);base64,[a-z\d+/=]+$/i.test(image.src || '')
        ? `<img class="docx-image" src="${escape(image.src)}" alt="${escape(image.alt || '文档图片')}" loading="lazy" decoding="async">${image.note ? `<small class="docx-image-note">${escape(image.note)}</small>` : ''}`
        : `<span class="docx-unavailable">${escape(image.reason || '此图片暂不能预览')}${image.alt ? `：${escape(image.alt)}` : ''}</span>`).join('');
      return `<${tag} class="docx-preview-paragraph" data-docx-preview-index="${indexes.get(String(id))}" style="text-align:${align}">${text || (images ? '' : '<br>')}${images}</${tag}>`;
    };
    const blocks = (values,depth = 0) => {
      if (depth > 16) return '<p class="docx-unavailable">表格嵌套较深，请在 Word 中查看。</p>';
      return (values || []).map(block => {
        if (block.kind === 'paragraph') return paragraph(block.id);
        if (block.kind !== 'table') return page===0&&unavailableCount++<20?`<p class="docx-unavailable">${escape(block.text || '此内容暂不能预览')}</p>`:'';
        const rows = (block.rows || []).map(row => { let column = 0; return row.map(cell => { const colspan = Math.max(1,Math.min(64,Number(cell.colspan) || 1)); const result = {...cell,colspan,column,html:blocks(cell.blocks,depth+1)}; column += colspan; return result; }); }).filter(row=>row.some(cell=>cell.html));
        if(!rows.length)return '';
        return `<div class="docx-table-wrap"><table class="docx-preview-table"><tbody>${rows.map((row,index) => {const compact=[];for(const cell of row){const last=compact.at(-1);if(!cell.html&&last&&!last.html)last.colspan=Math.min(64,last.colspan+cell.colspan);else compact.push({...cell,vmerge:cell.html?cell.vmerge:''});}return `<tr>${compact.map(cell => {
          if (cell.vmerge === 'continue') {
            let merged = false;
            for (let prior = index-1; prior >= 0; prior--) {
              const above = rows[prior].find(value => value.column === cell.column && value.colspan === cell.colspan);
              if (above?.vmerge === 'restart') { merged = true; break; }
              if (above?.vmerge !== 'continue') break;
            }
            if (merged) return '';
          }
          let rowspan = 1;
          if (cell.vmerge === 'restart') for (let next = index+1; next < rows.length; next++) { const follow = rows[next].find(value => value.column === cell.column && value.colspan === cell.colspan); if (follow?.vmerge !== 'continue') break; rowspan++; }
          return `<td colspan="${cell.colspan}" rowspan="${rowspan}">${cell.html}</td>`;
        }).join('')}</tr>`;}).join('')}</tbody></table></div>`;
      }).join('');
    };
    return `<article class="docx-preview">${blocks(content?.blocks || (paragraphs || []).map(p => ({kind:'paragraph',id:p.id})))}</article>`;
  }
  function mount({parent,content,paragraphs=[],page=0,onPageChange=()=>{}}){
    const doc=parent.ownerDocument,win=doc.defaultView,total=Math.max(1,Math.ceil(paragraphs.length/PAGE_SIZE));
    let current=Math.max(0,Math.min(total-1,Math.floor(Number(page)||0))),disposed=false;
    function clearSearch(){for(const node of parent.querySelectorAll('.docx-search-current'))node.classList.remove('docx-search-current');win.CSS?.highlights?.delete('yingxu-document-match');}
    function draw(){clearSearch();parent.innerHTML=`<div class="docx-editor-pagination"><span class="docx-page-range">第 ${paragraphs.length?current*PAGE_SIZE+1:0}–${Math.min((current+1)*PAGE_SIZE,paragraphs.length)} 段 · 共 ${paragraphs.length} 段</span><div class="docx-page-controls"><button type="button" class="button button-secondary button-small" data-docx-preview-prev ${current===0?'disabled':''}>上一段</button><span>${current+1} / ${total}</span><button type="button" class="button button-secondary button-small" data-docx-preview-next ${current===total-1?'disabled':''}>下一段</button></div></div>${total>1?'<p class="docx-page-hint">分段预览，每次最多 40 段；表格可能跨段显示，可查找全文定位。</p>':''}${render(content,paragraphs,{page:current})}`;}
    function goTo(next){if(disposed)return false;const index=Math.max(0,Math.min(total-1,Math.floor(Number(next)||0)));if(index!==current){current=index;draw();onPageChange(current);}return true;}
    function revealMatch({segmentIndex,from,to}){
      if(!Number.isInteger(segmentIndex)||segmentIndex<0||segmentIndex>=paragraphs.length||!goTo(Math.floor(segmentIndex/PAGE_SIZE)))return false;
      clearSearch();const node=parent.querySelector(`[data-docx-preview-index="${segmentIndex}"]`);if(!node)return false;
      node.classList.add('docx-search-current');const walker=doc.createTreeWalker(node,win.NodeFilter.SHOW_TEXT);let cursor=0,start=null,end=null;
      for(let text=walker.nextNode();text;text=walker.nextNode()){const length=text.textContent.length;if(!start&&from>=cursor&&from<cursor+length)start=[text,from-cursor];if(to>cursor&&to<=cursor+length){end=[text,to-cursor];break;}cursor+=length;}
      if(start&&end){const range=doc.createRange();range.setStart(...start);range.setEnd(...end);if(win.CSS?.highlights&&win.Highlight)win.CSS.highlights.set('yingxu-document-match',new win.Highlight(range));else{const selection=win.getSelection();selection.removeAllRanges();selection.addRange(range);}}
      node.scrollIntoView({block:'center'});return true;
    }
    const click=event=>{if(event.target.closest('[data-docx-preview-prev]'))goTo(current-1);else if(event.target.closest('[data-docx-preview-next]'))goTo(current+1);};
    parent.addEventListener('click',click);draw();
    return {goTo,getPage:()=>current,revealMatch,clearSearch,destroy(){if(disposed)return;disposed=true;clearSearch();parent.removeEventListener('click',click);}};
  }
  scope.YingXuDocx = {render,mount,PAGE_SIZE};
  if (typeof module !== 'undefined') module.exports = {render,mount,PAGE_SIZE};
})(typeof window !== 'undefined' ? window : globalThis);

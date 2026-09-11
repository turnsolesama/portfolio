(function (scope) {
  'use strict';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  function render(content, paragraphs) {
    const byId = new Map((paragraphs || []).map(value => [String(value.id),value]));
    const paragraph = id => {
      const p = byId.get(String(id)); if (!p) return '';
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
      return `<${tag} class="docx-preview-paragraph" style="text-align:${align}">${text || (images ? '' : '<br>')}${images}</${tag}>`;
    };
    const blocks = (values,depth = 0) => {
      if (depth > 16) return '<p class="docx-unavailable">表格嵌套较深，请在 Word 中查看。</p>';
      return (values || []).map(block => {
        if (block.kind === 'paragraph') return paragraph(block.id);
        if (block.kind !== 'table') return `<p class="docx-unavailable">${escape(block.text || '此内容暂不能预览')}</p>`;
        const rows = (block.rows || []).map(row => { let column = 0; return row.map(cell => { const colspan = Math.max(1,Math.min(64,Number(cell.colspan) || 1)); const result = {...cell,colspan,column}; column += colspan; return result; }); });
        return `<div class="docx-table-wrap"><table class="docx-preview-table"><tbody>${rows.map((row,index) => `<tr>${row.map(cell => {
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
          return `<td colspan="${cell.colspan}" rowspan="${rowspan}">${blocks(cell.blocks,depth+1)}</td>`;
        }).join('')}</tr>`).join('')}</tbody></table></div>`;
      }).join('');
    };
    return `<article class="docx-preview">${blocks(content?.blocks || (paragraphs || []).map(p => ({kind:'paragraph',id:p.id})))}</article>`;
  }
  scope.YingXuDocx = {render};
  if (typeof module !== 'undefined') module.exports = {render};
})(typeof window !== 'undefined' ? window : globalThis);

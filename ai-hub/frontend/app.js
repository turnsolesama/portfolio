/* AI Hub 前端 —— 零依赖单页应用 */
(() => {
  "use strict";

  // ---------- 基础 ----------
  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtSize = n => {
    if (n == null) return "-";
    const u = ["B", "KiB", "MiB", "GiB", "TiB"]; let i = 0;
    while (Math.abs(n) >= 1024 && i < 4) { n /= 1024; i++; }
    return (i === 0 ? n : n.toFixed(1)) + " " + u[i];
  };
  const fmtDate = ts => ts ? new Date(ts * 1000).toLocaleDateString("sv") : "-";
  const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

  async function api(path, opts = {}) {
    const res = await fetch(path, opts.body ? {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(opts.body)
    } : undefined);
    const ct = res.headers.get("content-type") || "";
    const data = ct.includes("json") ? await res.json() : await res.text();
    if (!res.ok) throw new Error((data && data.error) || res.status);
    return data;
  }
  const fileURL = p => "/api/file?path=" + encodeURIComponent(p);
  const thumbURL = p => "/api/thumb?path=" + encodeURIComponent(p);

  function toast(msg, kind = "") {
    const t = document.createElement("div");
    t.className = "t " + kind; t.textContent = msg;
    $("#toast").appendChild(t);
    setTimeout(() => t.remove(), 4200);
  }

  // ---------- 徽章 ----------
  const stateBadge = st => {
    const map = { ok: ["已是最新", "b-green"], available: ["有新版本", "b-yellow"], maybe: ["疑似更新", "b-yellow"],
      error: ["检查失败", "b-red"], unknown: ["无法检查", ""], unchecked: ["未检查", ""] };
    const [txt, cls] = map[st] || [st, ""];
    return `<span class="badge ${cls}">${txt}</span>`;
  };
  const tagBadge = tag => {
    const map = { "高频核心": "b-purple", "常用": "b-blue", "低频": "b-cyan", "暂无引用": "", "新入库": "b-green" };
    return `<span class="badge ${map[tag] || ""}">${tag}</span>`;
  };
  const typeBadge = t => {
    const map = { Checkpoint: "b-blue", LoRA: "b-purple", Diffusion: "b-cyan", VAE: "b-green",
      ControlNet: "b-yellow", TextEncoder: "b-cyan", Embedding: "b-green", LLM: "b-red", TTS: "b-red",
      VideoAI: "b-red", Package: "", Private: "", Vision: "b-cyan", IPAdapter: "b-purple", Upscaler: "b-green" };
    return `<span class="badge ${map[t] || ""}">${esc(t || "未分类")}</span>`;
  };

  const ICONS = {
    layers:'<path d="m3 7 9-5 9 5-9 5zM3 12l9 5 9-5M3 17l9 5 9-5"/>',
    overview:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    cpu:'<rect x="6" y="6" width="12" height="12" rx="3"/><path d="M9 1v5m6-5v5M9 18v5m6-5v5M1 9h5m-5 6h5m12-6h5m-5 6h5"/><path d="M10 10h4v4h-4z"/>',
    workflow:'<rect x="2" y="3" width="6" height="5" rx="1"/><rect x="16" y="3" width="6" height="5" rx="1"/><rect x="9" y="16" width="6" height="5" rx="1"/><path d="M5 8v4h14V8m-7 4v4"/>',
    folder:'<path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM3 9h18"/>',
    chart:'<path d="M4 3v17h17M8 15l4-5 4 2 5-7"/>',
    image:'<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 5-5 4 4 4-6 5 7"/>',
    refresh:'<path d="M20 7a9 9 0 0 0-15-2L2 8m0-5v5h5M4 17a9 9 0 0 0 15 2l3-3m0 5v-5h-5"/>',
    document:'<path d="M13 2H5a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V10zM13 2v8h8M7 15h10M7 18h6"/>',
    settings:'<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="8" cy="6" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="9" cy="18" r="2"/>',
    scan:'<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5M7 12h10"/>',
    menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',
    arrow:'<path d="M5 12h14m-5-5 5 5-5 5"/>',
    back:'<path d="M19 12H5m5-7-7 7 7 7"/>',
    video:'<rect x="3" y="5" width="13" height="14" rx="3"/><path d="m16 10 5-3v10l-5-3z"/>',
    audio:'<path d="M12 3v18M4 9v6m4-9v12m8-12v12m4-9v6"/>',
    message:'<path d="M21 11a8 8 0 0 1-8 8H7l-4 3V11a9 9 0 0 1 18 0Z"/><path d="M7 10h10M7 14h7"/>',
    check:'<path d="m5 12 4 4 10-10"/>',
    shield:'<path d="m12 2 8 3v7c0 6-8 10-8 10S4 18 4 12V5z"/><path d="m8 12 3 3 5-6"/>',
    disk:'<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="12" cy="10" r="4"/><path d="M6 18h5m6 0h1"/>',
    clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    search:'<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
    copy:'<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 5V3H3v13h2"/>',
    info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.1"/>',
    bookmark:'<path d="M6 3h12v19l-6-4-6 4z"/>',
    trash:'<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
    grid:'<rect x="3" y="3" width="4" height="4" rx=".5"/><rect x="10" y="3" width="4" height="4" rx=".5"/><rect x="17" y="3" width="4" height="4" rx=".5"/><rect x="3" y="10" width="4" height="4" rx=".5"/><rect x="10" y="10" width="4" height="4" rx=".5"/><rect x="17" y="10" width="4" height="4" rx=".5"/><path d="M3 17h4v4H3zM10 17h4v4h-4zM17 17h4v4h-4z"/>',
    expand:'<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',
    close:'<path d="m6 6 12 12M6 18 18 6"/>'
  };
  const icon = (name,size=18) => `<svg class="ico" width="${size}" height="${size}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ICONS.layers}</svg>`;
  const scopes = {central:'中央模型库',training:'训练产物',archive:'历史归档','app-private':'应用私有',unknown:'范围待确认'};
  const heading = (title,sub,eyebrow='ASSET WORKSPACE') => `<div class="page-heading"><div><div class="eyebrow">${eyebrow}</div><h2>${esc(title)}</h2><p>${esc(sub)}</p></div><div class="toolbar-note">${icon('shield',15)} 本地资产 · 按需检索</div></div>`;
  const skeleton = () => `<div class="loading-skeleton"><div class="skeleton hero-skeleton"></div><div class="metric-grid">${'<div class="skeleton"></div>'.repeat(4)}</div></div>`;
  const empty = (title,detail='试试调整筛选条件，或刷新本地索引。') => `<div class="results-empty">${icon('search',32)}<h3>${esc(title)}</h3><p>${esc(detail)}</p></div>`;
  function failPage(el,error){el.innerHTML=`<div class="page-error"><h3>暂时无法读取数据</h3><p>${esc(error.message)}</p><button class="btn">重试</button></div>`;$('button',el).onclick=route;}
  function readFavorites(){try{return new Set(JSON.parse(localStorage.getItem('aihub.favorites')||'[]').filter(Number.isInteger));}catch{return new Set();}}
  const favorites=readFavorites();
  async function copyPath(value){try{await navigator.clipboard.writeText(value);toast('路径已复制','ok');}catch{toast('浏览器未允许复制，请从详情中选中路径复制。','err');}}
  function bindNavigation(el){$$('[data-nav]',el).forEach(b=>b.onclick=()=>nav(b.dataset.nav,b.dataset.query?Object.fromEntries(new URLSearchParams(b.dataset.query)):undefined));}
  function triggerInfo(m){
    const candidates=m.audit?.trigger_candidates;
    let source=Array.isArray(candidates)&&candidates.length?candidates:m.trigger_words;
    if(typeof source==='string'&&/^[\[{]/.test(source.trim())){try{source=JSON.parse(source);}catch{}}
    const words=[],evidence=[];
    for(const item of Array.isArray(source)?source:[source]){
      const word=typeof item==='string'?item:item?.value||item?.word||item?.name||item?.text;
      if(typeof word!=='string'||!word.trim())continue;
      words.push(word.trim());
      if(typeof item?.evidence==='string')evidence.push(item.evidence.replace(/^training tag frequency (\d+); candidate, not validated$/,(_,count)=>`训练标签中出现 ${Number(count).toLocaleString('zh-CN')} 次；仅为候选，尚未验证`));
    }
    return {words:[...new Set(words)].join('，'),evidence:[...new Set(evidence)].join('；')};
  }
  function loraIntro(m){
    if((m.classification?.model_role||m.mtype)!=='LoRA')return '';
    const a=m.audit||{}, family=m.classification?.architecture||a.family||m.family||'尚未确认', md={...(m.header_meta||{}),...(a.metadata||{})};
    const base=m.training_base||md.ss_sd_model_name;
    const authorDescription=md['modelspec.description'];
    const trigger=triggerInfo(m);
    const descriptions={Acceleration:['采样加速','用于缩短采样过程。采样步数、CFG 与调度器应按该版本的作者说明配套。'],Detail_Light:['细节与光照','侧重细节、光照或材质表现；具体改善方向需通过对照样张判断。'],Character_Identity:['角色与外观','用于加强特定角色或外观特征；触发词与底模版本会影响表现。'],Style_Other:['风格与概念','用于调整画面风格或概念表现；分类依据来自文件与元数据，尚未逐份验证效果。']};
    const [oldRole,oldDescription]=descriptions[a.role]||['用途待补充','现有元数据不足以确认具体用途，可以在下方备注中补充作者说明或实际使用结论。'];
    const role=m.classification?.purpose_labels?.join(' / ')||oldRole;
    const description=m.classification?'用途根据已有记录或你的分类整理；具体效果与兼容性仍需结合模型说明和实际样张判断。':oldDescription;
    return `<section class="intro"><h3>${icon('layers',16)} 关于这份 LoRA · ${esc(role)}</h3><p>${esc(description)}</p>${authorDescription?`<p>文件内嵌介绍：${esc(String(authorDescription).slice(0,1500))}</p>`:''}<p>记录架构：<b>${esc(family)}</b>。${base?`记录的训练底模为 <b>${esc(base)}</b>，优先用这一底模检查表现。`:'尚未记录训练底模，使用前需核对作者的兼容说明。'}</p><p>${trigger.words?`触发词候选：<b>${esc(trigger.words)}</b>。`:'没有可确认的触发词记录，不等于无需触发词。'}</p>${trigger.evidence?`<p class="muted">候选依据：${esc(trigger.evidence)}。</p>`:''}<div class="intro-evidence">介绍依据：${a.family_confidence==='confirmed'?'已有架构证据':'包含分类推断'} · 用途标签不代表效果评级 · 本次终端更新未做推理验证</div></section>`;
  }
  function mdRender(src,basePath=''){
    const inline=text=>{
      const codes=[];
      let out=esc(text).replace(/`([^`]+)`/g,(_,code)=>{codes.push(`<code>${code}</code>`);return `\u0000${codes.length-1}\u0000`;});
      out=out.replace(/\[([^\]]+)\]\(([^)]+)\)/g,(_,label,href)=>{
        const decoded=href.replace(/&amp;/g,'&');
        if(/^https?:\/\//i.test(decoded))return `<a href="${esc(decoded)}" target="_blank" rel="noopener noreferrer">${label}</a>`;
        if(!basePath||/^[a-z]+:/i.test(decoded)&&! /^[a-z]:[\\/]/i.test(decoded)||decoded.startsWith('#'))return label;
        const target=/^[a-z]:[\\/]/i.test(decoded)?decoded:basePath.replace(/[\\/][^\\/]+$/,'')+'\\'+decoded.replace(/\//g,'\\');
        return `<a href="#/reports?path=${encodeURIComponent(target)}">${label}</a>`;
      }).replace(/\*\*([^*]+)\*\*/g,'<b>$1</b>');
      return out.replace(/\u0000(\d+)\u0000/g,(_,i)=>codes[+i]);
    };
    const lines=src.replace(/\r/g,'').split('\n');let result='',i=0;
    while(i<lines.length){const line=lines[i];
      if(/^\s*```/.test(line)){const block=[];i++;while(i<lines.length&&!/^\s*```/.test(lines[i]))block.push(lines[i++]);i++;result+=`<pre><code>${esc(block.join('\n'))}</code></pre>`;continue;}
      if(!line.trim()){i++;continue;}
      const h=line.match(/^(#{1,6})\s+(.+)/);if(h){result+=`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`;i++;continue;}
      if(/^\s*([-*_])\1{2,}\s*$/.test(line)){result+='<hr>';i++;continue;}
      if(line.trim().startsWith('|')&&i+1<lines.length&&/^\s*\|?\s*:?-{3,}/.test(lines[i+1])){
        const row=(s,tag)=>'<tr>'+s.trim().replace(/^\||\|$/g,'').split('|').map(c=>`<${tag}>${inline(c.trim())}</${tag}>`).join('')+'</tr>';
        result+='<div class="table-wrap"><table><thead>'+row(line,'th')+'</thead><tbody>';i+=2;
        while(i<lines.length&&lines[i].trim().startsWith('|'))result+=row(lines[i++],'td');result+='</tbody></table></div>';continue;
      }
      const list=line.match(/^\s*(?:[-*]|\d+\.)\s+(.*)/);if(list){const tag=/^\s*\d+\./.test(line)?'ol':'ul';result+=`<${tag}>`;while(i<lines.length){const m=lines[i].match(/^\s*(?:[-*]|\d+\.)\s+(.*)/);if(!m)break;result+=`<li>${inline(m[1])}</li>`;i++;}result+=`</${tag}>`;continue;}
      result+=`<p>${inline(line)}</p>`;i++;
    }
    return `<div class="md">${result}</div>`;
  }

  function classificationSummary(c) {
    if(!c)return '<span class="muted">用途待确认</span>';
    return `<span class="classification-domain">${esc(c.domain_label)}</span><div class="classification-tags">${c.purpose_labels.map(label=>`<span>${esc(label)}</span>`).join('')}</div><small class="classification-source">${c.domain_source==='manual'||c.purpose_source==='manual'?'已手动分类':'自动建议'}</small>`;
  }
  function classificationSection(m) {
    const c=m.classification;if(!c)return '';
    return `<section class="classification-card"><div class="classification-head"><h3>${icon('folder',16)} 功能与用途</h3><button class="btn small" id="edit-classification">调整分类</button></div>${classificationSummary(c)}<dl class="classification-dimensions"><dt>所属范围</dt><dd>${esc(c.scope_label)}</dd><dt>模型角色</dt><dd>${esc(c.model_role_label)}</dd><dt>兼容架构</dt><dd>${esc(c.architecture||'待确认')} · ${c.architecture_source==='manual'?'人工记录，未代表结构验证':'已有记录'}</dd><dt>入库状态</dt><dd>${c.registered?'已登记':'已索引'}${c.classification_pending?' · 分类待确认':''}</dd></dl>${c.compatibility_paths?.length?`<details><summary>${c.compatibility_paths.length} 个兼容 / 同一文件入口</summary>${c.compatibility_paths.map(p=>`<p class="pathline">${esc(p)}</p>`).join('')}</details>`:''}<details class="classification-evidence"><summary>查看分类依据</summary><p>${esc(c.domain_evidence)}</p>${Object.entries(c.purpose_evidence).map(([id,reason])=>`<p>${esc(m.classification_options.purposes[id])}：${esc(reason)}</p>`).join('')}</details></section>`;
  }
  function openCategoryEditor(ids,options,current,onSaved) {
    if(!ids.length||!options)return;
    const bulk=!current,domain=current?.manual_domain||'auto',mode=current?.manual_purposes!==null&&current?.manual_purposes!==undefined?'set':'auto';
    const chosen=new Set(current?.purposes||[]),showPurposes=bulk||current?.purpose_source!=='none';
    openModal(`<div class="category-editor"><div class="eyebrow">ORGANIZE ASSETS</div><h2>${bulk?'批量分类 · '+ids.length+' 个模型':'调整模型分类'}</h2><p class="muted">保存后会优先使用你的分类。模型文件仍在原来的位置。</p><label class="category-field">创作用途<select id="category-domain">${bulk?'<option value="keep">保持原分类</option>':''}<option value="auto" ${!bulk&&domain==='auto'?'selected':''}>自动识别</option>${Object.entries(options.domains).map(([id,d])=>`<option value="${esc(id)}" ${!bulk&&domain===id?'selected':''}>${esc(d.label)}</option>`).join('')}</select></label><label class="category-field">LoRA 用途<select id="category-mode">${bulk?'<option value="keep">保持原用途</option>':''}<option value="auto" ${!bulk&&mode==='auto'?'selected':''}>使用自动建议</option><option value="set" ${!bulk&&mode==='set'?'selected':''}>手动指定（可多选）</option></select></label><div class="category-checks">${Object.entries(options.purposes).map(([id,label])=>`<label><input type="checkbox" data-category-purpose="${esc(id)}" ${chosen.has(id)?'checked':''}><span>${esc(label)}</span></label>`).join('')}</div><p class="caption-note">LoRA 用途只应用于所选的 LoRA；勾选用途后会切换为手动指定。</p><p class="dialog-error" id="category-error" role="alert"></p><div class="dialog-actions"><button class="btn ghost" id="category-reset">恢复自动分类</button><button class="btn" id="category-cancel">取消</button><button class="btn primary" id="category-save">保存分类</button></div></div>`);
    const editor=$('.category-editor'),error=$('#category-error',editor);
    const dimension=(key,label,values)=>`<label class="category-field">${label}<select id="category-${key}">${bulk?'<option value="keep">保持原值</option>':''}<option value="auto">使用已有记录</option>${Object.entries(values||{}).map(([id,text])=>`<option value="${esc(id)}" ${current?.['manual_'+key]===id?'selected':''}>${esc(text)}</option>`).join('')}</select></label>`;
    error.insertAdjacentHTML('beforebegin',dimension('scope','所属范围',options.scopes)+dimension('model_role','模型角色',options.roles)+`<label class="category-field">兼容架构（人工记录）<input id="category-architecture" value="${esc(current?.manual_architecture||'')}" placeholder="${bulk?'留空保持原值':'留空使用已有记录'}"></label>`);
    if(!showPurposes){$('#category-mode',editor).closest('label').hidden=true;$('.category-checks',editor).hidden=true;$('.caption-note',editor).hidden=true;}
    $$('[data-category-purpose]',editor).forEach(check=>check.onchange=()=>{
      $('#category-mode',editor).value='set';
      if(check.checked)$$('[data-category-purpose]',editor).forEach(other=>{if(other!==check&&(check.dataset.categoryPurpose==='uncategorized'||other.dataset.categoryPurpose==='uncategorized'))other.checked=false;});
    });
    $('#category-cancel',editor).onclick=closeModal;
    const save=async reset=>{
      const body={ids};
      if(reset)body.reset=true;
      else{
        const domain=$('#category-domain',editor).value,mode=$('#category-mode',editor).value;
        if(domain!=='keep')body.domain=domain==='auto'?null:domain;
        if(showPurposes&&mode!=='keep')body.purposes=mode==='auto'?null:$$('[data-category-purpose]:checked',editor).map(c=>c.dataset.categoryPurpose);
        for(const key of ['scope','model_role']) {const value=$('#category-'+key,editor).value;if(value!=='keep')body[key]=value==='auto'?null:value;}
        const architecture=$('#category-architecture',editor).value.trim();if(architecture||!bulk)body.architecture=architecture||null;
        if(Object.keys(body).length===1){error.textContent='请选择要调整的分类。';return;}
      }
      $$('button',editor).forEach(b=>b.disabled=true);error.textContent='';
      try{
        const result=await api('/api/models/classify',{body:{...body,preview:true}});if(!editor.isConnected)return;
        openModal(`<h2>确认分类预览</h2><p>以下只更新人工分类记录，原文件保持原位置。</p>${result.items.map(item=>`<section class="intro"><h3>${esc(item.name)}</h3><p>原分类：${esc([item.before.scope_label,item.before.model_role_label,item.before.domain_label,item.before.architecture].filter(Boolean).join(' · '))}</p><p>新分类：${esc([item.after.scope_label,item.after.model_role_label,item.after.domain_label,item.after.architecture].filter(Boolean).join(' · '))}</p><p>LoRA 用途：${esc(item.after.purpose_labels.join(' / '))}</p></section>`).join('')}<p class="dialog-error" id="category-preview-error"></p><div class="dialog-actions"><button class="btn" id="category-preview-back">返回修改</button><button class="btn primary" id="category-confirm">保存人工分类</button></div>`);
        $('#category-preview-back').onclick=()=>{
          if(ids.length===1)openCategoryEditor(ids,options,result.items[0].after,onSaved);
          else {
            openCategoryEditor(ids,options,null,onSaved);
            for(const key of ['domain','scope','model_role'])if(key in body)$('#category-'+key).value=body[key]||'auto';
            if('architecture' in body)$('#category-architecture').value=body.architecture||'';
            if('purposes' in body){$('#category-mode').value=body.purposes===null?'auto':'set';$$('[data-category-purpose]').forEach(c=>c.checked=(body.purposes||[]).includes(c.dataset.categoryPurpose));}
          }
        };
        const confirm=$('#category-confirm');confirm.onclick=async()=>{confirm.disabled=true;try{const r=await api('/api/models/classify',{body});if(confirm.isConnected){closeModal();onSaved?.();toast(`已更新 ${r.updated} 个模型的分类`,'ok');}}catch(e){if(confirm.isConnected){$('#category-preview-error').textContent=e.message;confirm.disabled=false;}}};
      }
      catch(e){if(editor.isConnected){error.textContent=e.message;$$('button',editor).forEach(b=>b.disabled=false);}}
    };
    $('#category-save',editor).onclick=()=>save(false);$('#category-reset',editor).onclick=()=>save(true);
    $('#category-domain',editor).focus();
  }

  // ---------- 抽屉 / 模态 / 灯箱 ----------
  let activeDrawerId = null, drawerRequest = 0;
  function openDrawer(html) { $("#drawer").innerHTML = html; $("#drawer").classList.remove("hidden"); $("#drawer-mask").classList.remove("hidden"); }
  function closeDrawer() { activeDrawerId = null; drawerRequest++; $("#drawer").classList.add("hidden"); $("#drawer-mask").classList.add("hidden"); }
  $("#drawer-mask").onclick = closeDrawer;
  function openModal(html) { $("#modal").innerHTML = `<button class="btn small close">✕ 关闭</button>` + html; $("#modal-mask").classList.remove("hidden"); $(".close", $("#modal")).onclick = closeModal; }
  function closeModal() { $("#modal-mask").classList.add("hidden"); }
  $("#modal-mask").onclick = e => { if (e.target.id === "modal-mask") closeModal(); };
  function openLightbox(imgPath,metaHTML,onDelete=null){
    $('#lightbox').innerHTML=`<div class="lightbox-toolbar"><span>${icon('image',17)} 图片预览</span><div>${onDelete?`<button class="btn small danger-ghost" id="lightbox-delete">${icon('trash',15)} 删除图片</button>`:''}<button class="btn small" id="lightbox-close">${icon('close',16)} 关闭</button></div></div><div class="lightbox-canvas"><img class="main" src="${fileURL(imgPath)}" alt="图片大图预览"></div><div class="meta">${metaHTML||''}</div>`;
    $('#lightbox').classList.remove('hidden');
    $('#lightbox-close').onclick=closeLightbox;
    if(onDelete)$('#lightbox-delete').onclick=onDelete;
    $('#lightbox-close').focus();
  }

  function closeLightbox() { $("#lightbox").classList.add("hidden"); $("#lightbox").innerHTML = ""; }
  $("#lightbox").onclick = e => { if (e.target.id === "lightbox") closeLightbox(); };
  document.addEventListener("keydown", e => { if (e.key === "Escape") { closeLightbox(); closeModal(); closeDrawer(); } });

  // ---------- 任务轮询 ----------
  let polling = null;
  function pollJobs() {
    api("/api/jobs").then(({ jobs }) => {
      const running = jobs.filter(j => j.status === "running");
      const bar = $("#jobbar");
      if (running.length) {
        bar.classList.remove("hidden");
        $("#jobbar-text").textContent = running.map(j => `${j.name}: ${j.progress || "运行中"}`).join(" · ");
      } else {
        if (!bar.classList.contains("hidden")) { bar.classList.add("hidden"); route(); }
      }
      const last = jobs[0];
      $("#sidebar-status").innerHTML =
        `<div>状态 <b>${running.length ? "扫描中" : "空闲"}</b></div>` +
        (last ? `<div>${esc(last.name)} · ${last.status}</div>` : "");
    }).catch(() => { $("#sidebar-status").textContent="本地服务暂时未连接"; });
  }
  setInterval(pollJobs, 2500);

  // ---------- 路由 ----------
  const titles = { overview: "工作总览", models: "模型资产", workflows: "工作流", updates: "更新中心", analysis: "使用分析",
    images: "出图图库", llm: "大模型", files: "文件总览", reports: "知识与报告", projects:"项目与运行", settings: "设置", organizer: "安全区整理" };
  function parseHash(hash = location.hash) {
    const h = hash.slice(2) || "overview";
    const [page, qs] = h.split("?");
    return { page: page || "overview", params: new URLSearchParams(qs || "") };
  }
  let activePage = '', routeRequest = 0;
  const scrollSelectors = ['.table-wrap', '.report-list', '.report-reader', '#fs-results .panel'];
  function capturePage() {
    const host = $('#page'), view = host.firstElementChild, drawer = $('#drawer');
    const value = id => $('#' + id, host)?.value || '';
    let state = {};
    if (activePage === 'models') state = { ...modelState };
    if (activePage === 'images') state = { ...imgState };
    if (activePage === 'analysis') state = { type: value('an-type') || pages.analysis._type };
    if (activePage === 'workflows') state = { state: value('wf-state'), query: value('wf-query') };
    if (activePage === 'reports') state = { path: view?.dataset.report, query: value('report-search'), group:value('report-group-filter') };
    if (activePage === 'files') state = { path: fileState.path, query: value('fs-q') };
    if (activePage === 'organizer') state = AIHubOrganizer.capture(view);
    if (activePage === 'projects') state = AIHubRegistry.capture(view);
    return {
      state, top: host.scrollTop, left: host.scrollLeft, search: $('#global-search').value,
      scrolls: scrollSelectors.map(selector => $$(selector, host).map(el => [el.scrollLeft, el.scrollTop])),
      drawer: activeDrawerId === null ? null : {
        id: activeDrawerId, top: drawer.scrollTop,
        expanded: $$('details', drawer).map(el => el.open),
        notes: $('#notes', drawer)?.value, source: $('#src-input', drawer)?.value,
        rating: $('#stars', drawer) ? $$('#stars .on', drawer).length : undefined,
      },
    };
  }
  async function renderRoute(hash, snapshot) {
    const request = ++routeRequest;
    const { page, params } = parseHash(hash);
    activePage = page;
    closeDrawer(); closeLightbox(); closeModal();
    document.body.classList.remove('nav-open');
    $('#menu-toggle').setAttribute('aria-expanded','false');
    $$('#nav a').forEach(a => { a.classList.toggle('active',a.dataset.page===page); if(a.dataset.page===page)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current'); });
    $('#page-title').textContent=titles[page]||page;
    const container=document.createElement('div');container.className='page-view';
    $('#page').replaceChildren(container);$('#page').scrollTop=0;
    if (snapshot) $('#global-search').value = snapshot.search;
    await (pages[page] || pages.overview)(container, params, snapshot?.state);
    if (request !== routeRequest || !container.isConnected) return;
    if (snapshot?.drawer) await openModelDrawer(snapshot.drawer.id, snapshot.drawer);
    if (request !== routeRequest || !container.isConnected || !snapshot) return;
    requestAnimationFrame(() => {
      if (request !== routeRequest || !container.isConnected) return;
      $('#page').scrollTop = snapshot.top; $('#page').scrollLeft = snapshot.left;
      scrollSelectors.forEach((selector, i) => $$(selector, container).forEach((el, j) => {
        const position = snapshot.scrolls?.[i]?.[j];
        if (position) { el.scrollLeft = position[0]; el.scrollTop = position[1]; }
      }));
    });
  }

  const navigation = AIHubNavigation.create({
    history, location, capture: capturePage, render: renderRoute,
    update: ({ canBack, previous }) => {
      const label = previous ? '返回' + (previous.snapshot?.drawer ? '模型详情' : titles[parseHash(previous.hash).page] || '上一页') : '返回';
      const button = $('#nav-back');
      button.disabled = !canBack;
      $('#nav-back-label').textContent = label;
      button.setAttribute('aria-label', canBack ? label : '暂无上一页');
      button.title = canBack ? label + '（Alt + ←）' : '暂无上一页';
    },
  });
  function route() { return navigation.refresh(); }
  const nav = (page, params, options) => navigation.navigate(`#/${page}` + (params ? '?' + new URLSearchParams(params) : ''), options);
  window.addEventListener('popstate', navigation.sync);
  window.addEventListener('hashchange', navigation.sync);
  $('#nav-back').onclick = navigation.back;
  document.addEventListener('click', e => {
    if (e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    const link = e.target.closest('a[href^="#/"]');
    if (!link || link.hasAttribute('download') || (link.target && link.target !== '_self')) return;
    e.preventDefault(); navigation.navigate(link.getAttribute('href'));
  });
  document.addEventListener('keydown', e => {
    if (!e.altKey || e.ctrlKey || e.metaKey || e.shiftKey || !['ArrowLeft', 'ArrowRight'].includes(e.key)) return;
    e.preventDefault();
    if (e.key === 'ArrowLeft') navigation.back(); else navigation.forward();
  });

  // ---------- 通用分页表格 ----------
  function pager(total, page, size, onPage) {
    const pagesN = Math.max(1, Math.ceil(total / size));
    const d = document.createElement("div");
    d.className = "pager";
    d.innerHTML = `共 ${total} 条 · 第 ${page}/${pagesN} 页
      <button class="btn small" ${page <= 1 ? "disabled" : ""}>‹ 上一页</button>
      <button class="btn small" ${page >= pagesN ? "disabled" : ""}>下一页 ›</button>`;
    const [prev, next] = $$("button", d);
    prev.onclick = () => onPage(page - 1);
    next.onclick = () => onPage(page + 1);
    return d;
  }

  const pages = {};
  pages.organizer = AIHubOrganizer.createPage({api, icon, heading, toast, pollJobs, openModal, closeModal, refresh: route});
  const registryEnv={api,heading,toast,openModal,closeModal,refresh:route,nav,copyPath};
  pages.projects=AIHubRegistry.createProjects(registryEnv);

  pages.overview = async el => {
    el.classList.add('overview-page');
    el.innerHTML=skeleton();
    try{
      const [ov,mg,organizer]=await Promise.all([api('/api/overview'),api('/api/management'),api('/api/organizer/status')]);
      if(!el.isConnected)return;
      const palette=['#9daedd','#7688b0','#a7b8d2','#7b9dab','#c0b3d5','#928cab','#709296','#647d9e'];
      const parts=ov.parts.filter(p=>p.size>0).sort((a,b)=>b.size-a.size),total=parts.reduce((s,p)=>s+p.size,0)||1;
      const labels={AI_Models:'模型仓库',AI_Apps:'应用与环境',AI_Agent:'自动化工具','50_Training':'训练资产','70_Output':'输出文件','30_Assets':'素材资源','40_Projects':'创作项目','80_Knowledge':'知识资料','90_Archive':'归档'};
      const functional=ov.functional_categories||[];
      const metric=(label,value,foot,ic)=>`<div class="metric"><div class="metric-top">${label}<span class="metric-icon">${icon(ic,17)}</span></div><div class="metric-value">${String(value).replace(/ ([KMGT]iB|B)$/,'<small>$1</small>')}</div><div class="metric-foot">${foot}</div></div>`;
      const action=(ic,title,detail,page,query,tone='')=>`<div class="attention-row"><span class="attention-icon ${tone}">${icon(ic,17)}</span><div class="attention-content"><strong>${title}</strong><p>${detail}</p></div><button class="action" data-nav="${page}" data-query="${esc(query||'')}">查看 ${icon('arrow',13)}</button></div>`;
      el.innerHTML=heading('工作空间','模型、出图与资料，在同一处管理。','WORKSPACE OVERVIEW')+`
      ${AIHubOrganizer.workspaceBanner(organizer)}
      <section class="workspace-banner" aria-label="常用工作入口"><div class="workspace-copy"><div class="workspace-caption">${icon('layers',14)} 创作资产工作台</div><h3>让每一次创作，都有迹可循。</h3><p>从合适的模型开始，连接工作流，回看你的出图记录。</p><div class="workspace-context">${icon('folder',15)}<b>${esc(ov.ai_root)}</b><span>本机工作空间</span></div></div><div class="workspace-actions"><button class="btn primary" data-nav="models">${icon('layers',15)} 浏览模型 ${icon('arrow',14)}</button><button class="btn" data-nav="images">${icon('image',15)} 打开图库</button><button class="btn ghost" data-nav="workflows">${icon('workflow',15)} 进入工作流</button></div></section>
      <div class="metric-grid">${metric('中央主模型',(ov.central_counts.Checkpoint||0)+(ov.central_counts.Diffusion||0),'当前索引 · Checkpoint / Diffusion','layers')}${metric('中央 LoRA',ov.central_counts.LoRA||0,'当前索引 · 架构、用途与训练信息','cpu')}${metric('文件占用',fmtSize(ov.unique_size),`扫描范围去重 · 可用 ${fmtSize(ov.disk.free)}`,'disk')}${metric('出图记录',ov.image_count.toLocaleString(),`其中 <em>${ov.image_with_meta}</em> 张包含生成元数据`,'image')}</div>
      <section class="panel purpose-launcher"><div class="panel-head"><h3>从创作用途开始</h3><span class="caption-note">全部已索引资产 · 含配套组件</span></div><div class="body"><div class="domain-grid">${functional.map(c=>`<button class="domain-card" data-nav="models" data-query="domain=${encodeURIComponent(c.id)}&scope=&kind=&view=all"><span class="domain-icon">${icon(c.icon,20)}</span><span class="domain-name">${esc(c.label)}</span><b>${c.count.toLocaleString()}</b></button>`).join('')}</div></div></section>
      <div class="content-grid"><section class="panel"><div class="panel-head"><h3>资产维护</h3><span class="health-score">${mg.check.status==='passed'?'最近检查通过':'尚无检查记录'}</span></div><div class="body">
      ${action('workflow',mg.workflow_pending?`${mg.workflow_pending} 份工作流需核对模型引用`:'工作流路径记录',`${mg.workflow_reviewed} 份独立路径修正版 · 尚未执行生成验收`,'workflows', 'state=needs_review')}
      ${action('refresh',ov.pending_updates?`${ov.pending_updates} 个模型有版本变化`:'模型版本检查',ov.pending_updates?'查看来源与版本差异后再决定更新':`${ov.state_counts.unchecked||0} 个模型尚未检查更新`,'updates','','green')}
      ${action('copy',`${mg.duplicate_groups} 组文件待确认重复`,`${fmtSize(mg.duplicate_candidate_bytes)} 候选额外占用 · 未做完整哈希确认`,'reports','path='+encodeURIComponent(mg.verification_report))}
      </div></section><section class="panel"><div class="panel-head"><h3>存储分布</h3><a class="link" href="#/files">文件空间 ${icon('arrow',13)}</a></div><div class="body"><div class="storage-summary"><b>${fmtSize(ov.unique_size)}</b><span>扫描范围 · 文件去重后</span></div><div class="segment-bar" aria-label="目录逻辑体积分布">${parts.map((p,i)=>`<span style="width:${100*p.size/total}%;background:${palette[i%palette.length]}" title="${esc(p.name)} ${fmtSize(p.size)}"></span>`).join('')}</div><div class="storage-list">${parts.slice(0,8).map((p,i)=>`<div class="storage-item"><span class="dot" style="background:${palette[i%palette.length]}"></span><button data-nav="files" data-query="path=${encodeURIComponent(p.path)}" title="${esc(p.path)}">${esc(labels[p.name]||p.name.replace(/^\d+_/,''))}</button><b>${fmtSize(p.size)}</b></div>`).join('')}</div><p class="footnote">分区显示逻辑体积，共享硬链接会重复计入；实际文件占用参考上方去重值。</p></div></section></div>

      <section class="panel"><div class="panel-head"><h3>最近修改的模型</h3><a href="#/models" class="link">查看全部 ${icon('arrow',13)}</a></div><div class="table-wrap"><table class="tbl recent-table"><thead><tr><th>模型名称</th><th>类型</th><th>架构</th><th>大小</th><th class="hide-small">文件修改</th></tr></thead><tbody>${ov.recent_models.slice(0,5).map(m=>`<tr><td><div class="file-label"><span class="type-icon">${icon('layers',15)}</span><button class="model-link" data-id="${m.rowid_pk}" title="${esc(m.filename)}">${esc(m.filename)}</button></div></td><td>${typeBadge(m.classification?.model_role||m.mtype)}</td><td class="muted">${esc(m.classification?.architecture||m.family||'未确认')}</td><td class="muted">${fmtSize(m.size)}</td><td class="muted hide-small">${fmtDate(m.mtime)}</td></tr>`).join('')}</tbody></table></div></section>
      <div class="caption-note">稳定台账 ${mg.catalog_records.toLocaleString()} 条（${esc(mg.updated_at||'时间未记录')}） · 当前索引 ${(ov.indexed_records??ov.model_count).toLocaleString()} 条 / ${(ov.unique_model_files??ov.model_count).toLocaleString()} 个文件身份（含现场发现、训练产物及应用私有文件）。<br>最近扫描 ${esc(ov.scan_at||'尚未扫描')} · ${ov.total_files.toLocaleString()} 个文件；扫描排除环境缓存等目录，与全量整理盘点的范围不同。</div>`;
      bindNavigation(el);bindModelLinks(el);
    }catch(e){failPage(el,e);}
  };

  function bindModelLinks(el) { $$(".model-link", el).forEach(n => n.onclick = () => openModelDrawer(+n.dataset.id)); }

  const modelState={page:1,size:40,type:'',family:'',state:'',usage:'',q:'',sort:'name',scope:'central',kind:'',view:'all',domain:'image',purpose:'',intake:''};
  pages.models=(el,params=new URLSearchParams(),restored)=>{
    if(restored)Object.assign(modelState,restored);
    else if(params.size){Object.assign(modelState,{page:1,type:'',family:'',state:'',usage:'',q:'',scope:'central',kind:'',view:'all',domain:'',purpose:'',intake:''});for(const key of Object.keys(modelState))if(params.has(key))modelState[key]=['page','size'].includes(key)?Math.max(1,+params.get(key)||1):params.get(key);}
    const tabs=[['all','全部类型',{kind:'',type:''}],['base','主模型',{kind:'base',type:''}],['lora','LoRA',{kind:'',type:'LoRA'}],['components','配套组件',{kind:'components',type:''}],['favorites','我的收藏',{kind:'',type:''}]];
    el.innerHTML=heading('模型资产','先选择创作用途，再查找模型与适合的 LoRA。','MODEL LIBRARY')+`
      <div class="catalog-section-label"><span>按创作用途</span><small id="domain-scope">当前范围 · 全部类型</small></div>
      <div class="domain-grid" id="model-domains" role="group" aria-label="模型功能分类"></div>
      <div class="catalog-tools"><div class="segmented" role="group" aria-label="模型快捷筛选">${tabs.map(([id,label])=>`<button data-tab="${id}" class="${modelState.view===id?'active':''}">${label}</button>`).join('')}</div><span class="caption-note">架构作为兼容条件保留</span></div>
      <section class="purpose-section hidden" id="lora-purposes"><div class="catalog-section-label"><span>LoRA 用途</span><small>同一模型可以有多个用途</small></div><div class="purpose-chips" id="purpose-chips" role="group" aria-label="LoRA 用途筛选"></div></section>
      <div class="filterbar" id="model-filters"><input id="f-q" type="search" aria-label="搜索模型" placeholder="搜索名称、训练底模或触发词…" value="${esc(modelState.q)}"></div>
      <section class="panel"><div class="table-heading"><span id="model-results">正在读取模型…</span><button class="btn small" id="batch-classify" disabled>${icon('folder',14)} 批量分类 <span id="selected-count"></span></button></div>
      <div class="table-wrap"><table class="tbl catalog-table"><thead><tr><th><input type="checkbox" id="models-select-all" aria-label="选择本页所有模型"></th><th>模型 / 类型</th><th>功能与用途</th><th>兼容架构 / 训练底模</th><th>已有引用</th><th>大小</th><th>入库 / 版本状态</th></tr></thead><tbody id="model-rows"></tbody></table></div><div id="models-empty"></div></section><div id="models-pager"></div>
      <p class="caption-note">自动分类参考架构记录、原目录与模型描述；用途建议可以在详情或批量分类中调整。分类不会移动模型文件。</p>`;
    let sequence=0,filtersReady=false,options=null;
    const selected=new Set();
    const updateSelection=()=>{
      $('#selected-count',el).textContent=selected.size?`· 已选 ${selected.size} 项`:'';
      $('#batch-classify',el).disabled=!selected.size;
      const checks=$$('[data-select]',el),all=$('#models-select-all',el);
      all.checked=checks.length>0&&selected.size===checks.length;all.indeterminate=selected.size>0&&selected.size<checks.length;
    };
    const load=async()=>{
      const request=++sequence;
      const query=new URLSearchParams();for(const [key,value]of Object.entries(modelState))if(key!=='view'&&value!=='')query.set(key,value);
      if(modelState.view==='favorites')query.set('ids',[...favorites].join(','));
      try{
        const d=await api('/api/models?'+query);if(request!==sequence||!el.isConnected)return;
        modelState.page=d.page;options=d.facets.options;
        selected.clear();$('#models-select-all',el).checked=false;
        const domains=d.facets.domains||[];
        $('#domain-scope',el).textContent=(scopes[modelState.scope]||'全部位置')+' · 全部类型';
        $('#model-domains',el).innerHTML=[{id:'',label:'全部功能',description:'浏览当前范围内的所有资产',icon:'layers',count:domains.reduce((n,c)=>n+c.count,0)},...domains].map(c=>`<button class="domain-card ${modelState.domain===c.id?'active':''}" data-domain="${esc(c.id)}" aria-pressed="${modelState.domain===c.id}" title="${esc(c.description)}"><span class="domain-icon">${icon(c.icon,20)}</span><span class="domain-name">${esc(c.label)}</span><b>${c.count.toLocaleString()}</b></button>`).join('');
        $$('[data-domain]',el).forEach(b=>b.onclick=()=>nav('models',{...modelState,domain:b.dataset.domain,purpose:'',page:1,type:'',kind:'',family:'',q:'',view:'all'},{force:true}));
        const purposes=d.facets.purposes||[],loraCount=purposes.reduce((n,p)=>n+p.count,0);
        $('#lora-purposes',el).classList.toggle('hidden',!loraCount&&modelState.type!=='LoRA'&&!modelState.purpose);
        $('#purpose-chips',el).innerHTML=`<button data-purpose="" class="${!modelState.purpose?'active':''}" aria-pressed="${!modelState.purpose}">全部用途</button>`+purposes.map(p=>`<button data-purpose="${esc(p.id)}" class="${modelState.purpose===p.id?'active':''}" aria-pressed="${modelState.purpose===p.id}">${esc(p.label)} <span>${p.count}</span></button>`).join('');
        $$('[data-purpose]',el).forEach(b=>b.onclick=()=>nav('models',{...modelState,purpose:b.dataset.purpose,type:'LoRA',kind:'',view:'lora',page:1},{force:true}));
        if(!filtersReady){
          const select=(id,label,values,value)=>`<select id="${id}" aria-label="${label}">${values.map(([v,t])=>`<option value="${esc(v)}" ${v===value?'selected':''}>${esc(t)}</option>`).join('')}</select>`;
          $('#model-filters',el).insertAdjacentHTML('beforeend',select('f-type','模型类型',[['','所有类型'],...d.facets.types.map(t=>[t,t])],modelState.type)+select('f-family','兼容架构',[['','所有兼容架构'],...[...new Set([...d.facets.families,'未确认'])].sort().map(f=>[f,f==='未确认'?'架构待确认':f])],modelState.family)+select('f-scope','资产范围',[['','所有位置'],...Object.entries(scopes)],modelState.scope)+select('f-sort','排序方式',[['name','按名称'],['mtime','最近修改'],['size','按体积'],['usage','按引用次数']],modelState.sort)+select('f-intake','入库状态',[['','所有入库状态'],['indexed','已索引'],['registered','已登记'],['pending','分类待确认']],modelState.intake));
          for(const key of ['type','family','scope','sort','intake'])$('#f-'+key,el).onchange=e=>{modelState[key]=e.target.value;modelState.page=1;if(key==='type'){modelState.kind='';if(modelState.type!=='LoRA')modelState.purpose='';}modelState.view='custom';$$('[data-tab]',el).forEach(b=>b.classList.remove('active'));load();};
          filtersReady=true;
        }
        $('#model-results',el).textContent=`找到 ${d.total.toLocaleString()} 个资产 · ${scopes[modelState.scope]||'全部位置'} · 按文件身份去重`;
        $('#model-rows',el).innerHTML=d.items.map(m=>`<tr><td><input type="checkbox" data-select="${m.rowid_pk}" aria-label="选择 ${esc(m.filename)}"></td><td class="model-name"><div class="catalog-model-name"><button class="star-btn ${favorites.has(m.rowid_pk)?'active':''}" data-favorite="${m.rowid_pk}" aria-label="${favorites.has(m.rowid_pk)?'取消收藏':'收藏'} ${esc(m.filename)}" aria-pressed="${favorites.has(m.rowid_pk)}">${favorites.has(m.rowid_pk)?'★':'☆'}</button><button class="model-link" data-id="${m.rowid_pk}">${esc(m.filename)}</button></div><span class="file-sub">${typeBadge(m.classification?.model_role||m.mtype)} ${esc(m.classification?.scope_label||scopes[m.scope]||'范围待确认')}</span></td><td>${classificationSummary(m.classification)}</td><td class="training-base">${esc(m.classification?.architecture||m.family||'架构待确认')}<span class="file-sub" title="${esc(m.training_base||'')}">${esc(m.training_base||'训练底模未记录')}</span>${m.lrank?`<span class="file-sub">rank ${esc(m.lrank)} · alpha ${esc(m.lalpha??'—')}</span>`:''}</td><td class="num">${m.img_count||0}<span class="file-sub">张图片</span></td><td class="num">${fmtSize(m.size)}</td><td><span class="badge">${m.classification?.registered?'已登记':'已索引'}</span>${m.classification?.classification_pending?'<span class="badge b-yellow">分类待确认</span>':''}<span class="file-sub">${stateBadge(m.update_state)}</span>${m.missing?'<span class="badge b-red">文件缺失</span>':''}</td></tr>`).join('');
        $('#models-empty',el).innerHTML=d.items.length?'':empty(modelState.view==='favorites'?'还没有匹配的收藏':'没有找到匹配的资产','试试其他用途、兼容架构，或把位置切换为“所有位置”。');
        $('#models-pager',el).replaceChildren(pager(d.total,d.page,d.size,p=>{modelState.page=p;load();}));
        bindModelLinks(el);
        $$('[data-select]',el).forEach(check=>check.onchange=()=>{const id=+check.dataset.select;check.checked?selected.add(id):selected.delete(id);updateSelection();});
        $('#models-select-all',el).onchange=e=>{$$('[data-select]',el).forEach(check=>{check.checked=e.target.checked;check.checked?selected.add(+check.dataset.select):selected.delete(+check.dataset.select);});updateSelection();};
        updateSelection();
        $$('[data-favorite]',el).forEach(b=>b.onclick=()=>{const id=+b.dataset.favorite;favorites.has(id)?favorites.delete(id):favorites.add(id);try{localStorage.setItem('aihub.favorites',JSON.stringify([...favorites]));}catch{toast('收藏仅在本次页面中保留','err');}b.classList.toggle('active',favorites.has(id));b.textContent=favorites.has(id)?'★':'☆';b.setAttribute('aria-pressed',String(favorites.has(id)));b.setAttribute('aria-label',(favorites.has(id)?'取消收藏 ':'收藏 ')+d.items.find(m=>m.rowid_pk===id).filename);if(modelState.view==='favorites')load();});
      }catch(e){if(request===sequence&&el.isConnected)$('#models-empty',el).innerHTML=empty('读取失败',e.message);}
    };
    $('#batch-classify',el).onclick=()=>openCategoryEditor([...selected],options,null,()=>{if(el.isConnected)load();});
    const search=debounce(()=>{if(el.isConnected)load();},250);
    $('#f-q',el).oninput=e=>{modelState.q=e.target.value.trim();modelState.page=1;search();};
    $$('[data-tab]',el).forEach(b=>b.onclick=()=>{const tab=tabs.find(t=>t[0]===b.dataset.tab);nav('models',{...modelState,page:1,purpose:'',view:tab[0],...tab[2]},{force:true});});
    return load();
  };

  // ---------- 模型详情抽屉 ----------
  async function openModelDrawer(id, restored) {
    const request = ++drawerRequest;
    activeDrawerId = id;
    const isCurrent = () => request === drawerRequest && activeDrawerId === id;
    openDrawer(`<div class="muted">加载中…</div>`);
    $('#drawer').scrollTop = 0;
    let m;
    try { m = await api("/api/model/" + id); } catch (e) { if(isCurrent())openDrawer(`<button class="btn small" id="drawer-error-close">关闭详情</button><div class="badge b-red">${esc(e.message)}</div>`); if(isCurrent())$('#drawer-error-close').onclick=closeDrawer; return; }
    if (!isCurrent()) return;
    const hm = m.header_meta || {};
    const kv = (k, v) => v !== null && v !== undefined && v !== "" ? `<div class="k">${k}</div><div class="v">${esc(v)}</div>` : "";
    const previewSrc = m.preview_path ? thumbURL(m.preview_path)
      : (m.preview_url ? m.preview_url : (m.images[0] ? thumbURL(m.images[0].path) : null));
    openDrawer(`
      <button class="btn small close" aria-label="关闭详情">${icon("close",16)}</button>
      <h2>${esc(m.filename)}</h2>
      <div>${typeBadge(m.classification?.model_role||m.mtype)} <span class="badge">${esc(m.classification?.architecture || m.family || "架构待确认")}</span>
        ${`<span class="badge">${esc(m.classification?.scope_label||scopes[m.scope]||m.scope||"范围待确认")}</span>`}
        ${m.missing ? '<span class="badge b-red">文件缺失</span>' : ""} ${stateBadge(m.update_state)}</div>
      ${loraIntro(m)}
      ${classificationSection(m)}
      ${previewSrc ? `<details class="sample-fold"><summary>查看已有预览图</summary><img class="drawer-preview" src="${esc(previewSrc)}" loading="lazy" onerror="this.style.display='none'"></details>` : ""}
      <div class="dsec"><div class="t">${icon("folder",15)} 位置（${esc(m.partition || "")}）</div><div class="c">
        <div class="kv">
          <div class="k">规范路径</div><div class="v pathline">${esc(m.path)}</div>
          ${(m.alt_paths || []).map(p => `<div class="k">兼容入口</div><div class="v pathline">${esc(p)}</div>`).join("")}
          ${kv("大小", m.size_h)} ${kv("修改时间", m.mtime ? new Date(m.mtime * 1000).toLocaleString() : "-")}
          ${kv("重复候选", (m.duplicates || []).length ? m.duplicates.map(d => d.filename + (d.same_name ? "（同名）" : "")).join("；") : "无")}
        </div>
        <div style="margin-top:8px"><button class="btn small" id="btn-reveal">${icon("folder",14)} 打开所在文件夹</button><button class="btn small" id="btn-copy-model" style="margin-left:8px">复制运行路径</button></div>
      </div></div>
      <div class="dsec"><div class="t">${icon("refresh",15)} 下载来源与更新</div><div class="c">
        <div class="kv">
          ${kv("来源", m.source_url || "未绑定")}
          ${kv("来源方式", m.source_conf === "header" ? "模型内嵌元数据" : m.source_conf === "sidecar" ? "伴随文件" : m.source_conf === "registry" ? "手动登记" : m.source_conf === "search" ? "文件名搜索（低置信）" : "-")}
          ${kv("最新版本", m.latest_version_name ? m.latest_version_name + (m.latest_version_date ? `（${m.latest_version_date.slice(0, 10)}）` : "") : "-")}
          ${kv("远端底模", m.latest_base_model)}
          ${kv("检查时间", m.last_checked || "-")} ${kv("备注", m.check_error)}
        </div>
        <div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn small" id="btn-resolve">${icon("search",14)} 识别来源</button>
          <button class="btn small" id="btn-check">${icon("refresh",14)} 检查更新</button>
          <input class="inp" id="src-input" placeholder="粘贴 Civitai / HuggingFace 链接" style="flex:1;min-width:200px">
          <button class="btn small primary" id="btn-save-src">绑定来源</button>
        </div>
      </div></div>
      <div class="dsec"><div class="t">${icon("chart",15)} 出图引用与使用记录</div><div class="c">
        <div class="kv">
          ${kv("出图次数", m.img_count || 0)} ${kv("活跃天数", m.days_used || 0)}
          ${kv("最近使用", m.last_used_h || "暂无记录")} ${kv("使用参考分", m.value_score + " / 100")} ${kv("标签", m.value_tag)}
        </div>
        <div style="margin-top:8px" class="thumb-strip">${(m.images || []).slice(0, 12).map(im =>
          `<img src="${thumbURL(im.path)}" data-path="${esc(im.path)}" title="${esc(im.role)}">`).join("")}</div>
        ${m.image_total > 12 ? `<div class="muted" style="margin-top:6px">共 ${m.image_total} 张 · <a class="link" href="#/images?model=${encodeURIComponent(m.path)}">在画廊中查看 →</a></div>` : ""}
      </div></div>
      ${(Object.keys(hm).length || m.trigger_words || m.training_base) ? `<div class="dsec"><div class="t">${icon("cpu",15)} 元数据</div><div class="c"><div class="kv">
        ${kv("触发词候选", triggerInfo(m).words)} ${kv("候选依据", triggerInfo(m).evidence)} ${kv("训练底模", m.training_base)}
        ${kv("Rank/Alpha", (m.lrank || "-") + " / " + (m.lalpha || "-"))} ${kv("训练方法", m.method)} ${kv("保存段步数", hm.ss_steps)} ${kv("训练图片数", hm.ss_num_train_images)}
        ${Object.entries(hm).slice(0, 14).map(([k, v]) => kv(k, String(v).slice(0, 160))).join("")}
      </div></div></div>` : ""}
      <div class="dsec"><div class="t">${icon("bookmark",15)} 我的评价</div><div class="c">
        <div class="stars" id="stars">${[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(i =>
          `<span data-i="${i}" class="${i <= (m.rating || 0) ? "on" : ""}">★</span>`).join("")}</div>
        <textarea class="ta" id="notes" placeholder="备注：用途、效果、待办…" style="margin-top:8px">${esc(m.notes || "")}</textarea>
        <button class="btn small primary" id="btn-save-note" style="margin-top:8px">保存评价</button>
      </div></div>`);

    $(".close", $("#drawer")).onclick = closeDrawer;
    if(m.classification)$('#edit-classification').onclick=()=>openCategoryEditor([id],m.classification_options,m.classification,()=>{if(isCurrent())route();});
    $("#btn-copy-model").onclick = () => copyPath(m.audit?.runtime_path || m.path);
    $("#btn-reveal").onclick = () => api(`/api/model/${id}/reveal`, { body: {} }).then(() => toast("已在资源管理器中打开", "ok")).catch(e => toast(e.message, "err"));
    $("#btn-resolve").onclick = async () => {
      toast("正在识别来源…");
      const r = await api(`/api/model/${id}/resolve-source`, { body: {} }).catch(e => ({ note: e.message }));
      toast(r.url ? `识别到来源（${r.note}）：${r.url}` : `未识别：${r.note}`, r.url ? "ok" : "err");
      if (r.url && isCurrent()) { $("#src-input").value = r.url; openModelDrawer(id); }
    };
    $("#btn-check").onclick = async () => {
      toast("正在检查更新…");
      const r = await api(`/api/model/${id}/check`, { body: {} }).catch(e => ({ result: { message: e.message } }));
      toast(r.result.message, r.result.state === "ok" ? "ok" : r.result.state === "error" ? "err" : "");
      if (isCurrent()) openModelDrawer(id);
    };
    $("#btn-save-src").onclick = async () => {
      const url = $("#src-input").value.trim();
      await api(`/api/model/${id}/source`, { body: { url } });
      toast("来源已绑定", "ok"); if (isCurrent()) openModelDrawer(id);
    };
    $$(".thumb-strip img", $("#drawer")).forEach(im => im.onclick = () => openLightbox(im.dataset.path, ""));
    $("#stars").onclick = e => {
      if (e.target.dataset.i) $$("#stars span").forEach(s => s.classList.toggle("on", +s.dataset.i <= +e.target.dataset.i));
    };
    $("#btn-save-note").onclick = async () => {
      const rating = $$("#stars span").filter(s => s.classList.contains("on")).length;
      await api(`/api/model/${id}/edit`, { body: { rating, notes: $("#notes").value } });
      toast("已保存", "ok");
    };
    if (restored) {
      if (restored.notes !== undefined) $('#notes').value = restored.notes;
      if (restored.source !== undefined) $('#src-input').value = restored.source;
      if (restored.rating !== undefined) $$('#stars span').forEach(s => s.classList.toggle('on', +s.dataset.i <= restored.rating));
      $$('details', $('#drawer')).forEach((el, i) => el.open = !!restored.expanded?.[i]);
      $('.close', $('#drawer')).focus({ preventScroll: true });
      $('#drawer').scrollTop = restored.top;
    }
  }

  // ================= 更新中心 =================
  pages.updates = (el) => {
    el.innerHTML = `<div class="muted">加载中…</div>`;
    return Promise.all([api("/api/overview"), api("/api/models?state=pending&size=200")]).then(([ov, lst]) => {
      const s = ov.state_counts;
      el.innerHTML = `
        <div class="grid-cards">
          <div class="card"><div class="k">有新版本</div><div class="v upd-avail">${(s.available || 0) + (s.maybe || 0)}</div><div class="s">可考虑升级（黄色待确认）</div></div>
          <div class="card"><div class="k">已是最新</div><div class="v" style="color:var(--green)">${s.ok || 0}</div><div class="s">远端无更新</div></div>
          <div class="card"><div class="k">未检查</div><div class="v">${(s.unchecked || 0) + (s.unknown || 0) + (s.error || 0)}</div><div class="s">点击右上角“检查更新”</div></div>
          <div class="card"><div class="k">上次检查</div><div class="v" style="font-size:14px">${esc(ov.update_check_at || "暂无记录")}</div><div class="s">限流间隔见设置</div></div>
        </div>
        <div class="panel" style="overflow-x:auto"><h3>⬆️ 待更新列表</h3><div class="body" style="padding:0">
        <table class="tbl"><thead><tr><th>文件名</th><th>类型</th><th>本地时间</th><th>远端最新</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>${lst.items.length ? lst.items.map(m => `<tr>
          <td title="${esc(m.path)}">${esc(m.filename)}</td><td>${typeBadge(m.classification?.model_role||m.mtype)}</td>
          <td class="muted">${fmtDate(m.mtime)}</td>
          <td class="upd-${esc(m.update_state)}">${esc(m.latest_version_name || "-")}${m.latest_version_date ? `<div class="muted" style="font-size:11px">${esc(m.latest_version_date.slice(0, 10))}</div>` : ""}</td>
          <td>${stateBadge(m.update_state)}${m.source_conf === "search" ? '<span class="badge">低置信</span>' : ""}</td>
          <td><button class="btn small model-link" data-id="${m.rowid_pk}">详情</button>
              ${m.source_url ? `<a class="btn small" href="${esc(m.source_url)}" target="_blank">打开来源</a>` : ""}</td>
        </tr>`).join("") : `<tr><td colspan="6" class="muted" style="padding:20px;text-align:center">当前没有待更新的模型。点击右上角“检查更新”开始全面检查。</td></tr>`}</tbody>
        </table></div></div>
        <div class="muted" style="font-size:12px">更新检查通过 Civitai / HuggingFace 公共 API，逐个间隔请求防止限流；大列表会在后台任务中运行，完成后自动刷新。</div>`;
      bindModelLinks(el);
    }).catch(e => el.innerHTML = `<div class="badge b-red">${esc(e.message)}</div>`);
  };

  // ================= 出图分析 =================
  pages.analysis = (el, params, restored) => {
    el.innerHTML = `<div class="muted">加载中…</div>`;
    const type = restored?.type || pages.analysis._type || "LoRA";
    pages.analysis._type = type;
    return api("/api/usage/ranking?limit=40&type=" + encodeURIComponent(type)).then(d => {
      const max = Math.max(1, ...d.ranking.map(m => m.img_count || 0));
      const maxScore = Math.max(1, ...d.ranking.map(m => m.value_score || 0));
      el.innerHTML = `
        <div class="filterbar">
          <select id="an-type">${["LoRA", "Checkpoint", "Diffusion", "TextEncoder"].map(t =>
            `<option ${t === type ? "selected" : ""}>${t}</option>`).join("")}</select>
          <span class="muted">仅表示已扫描图片的引用记录，不代表质量；价值分 = 出图量 45% + 近期使用 25% + 活跃天数 15% + 主观评分 15%</span>
        </div>
        <div class="panel"><h3>🏆 使用参考排行（${esc(type)}）</h3><div class="body">${d.ranking.map(m => `
          <div class="bar-row">
            <span class="nm model-link" data-id="${m.rowid_pk}" title="${esc(m.path)}">${esc(m.filename)}</span>
            <div class="bar-track"><div class="bar-fill" style="width:${100 * (m.value_score || 0) / maxScore}%"></div></div>
            <span class="num">${m.value_score}</span>
            <span class="muted">${m.img_count || 0} 张 · ${m.last_used_h || "暂无记录"}</span>
          </div>`).join("") || "暂无数据"}</div></div>
        <div class="panel"><h3>💤 当前索引未发现引用（${esc(type)}，含新入库）</h3><div class="body">${d.unused.map(m => `
          <div class="flat-row"><span class="nm model-link" data-id="${m.rowid_pk}" title="${esc(m.path)}">${esc(m.filename)}</span>
          ${tagBadge(m.value_tag)}<span class="sub">${esc(m.classification?.architecture||m.family || "")}</span>
          <span class="num">${m.size_h}</span><span class="sub">${fmtDate(m.mtime)}</span></div>`).join("") || "当前筛选中的模型均有引用记录"}</div></div>`;
      $("#an-type", el).onchange = e => { pages.analysis._type = e.target.value; route(); };
      bindModelLinks(el);
    }).catch(e => el.innerHTML = `<div class="badge b-red">${esc(e.message)}</div>`);
  };

  const imgState={page:1,size:36,q:'',model:'',dir:'',sort:'newest',density:'comfortable'};
  function requestImageDeletion(im,onDeleted){
    openModal(`<div class="delete-dialog"><span class="dialog-icon">${icon('trash',24)}</span><h2>将这张图片移到回收站？</h2><p class="muted">可以从 Windows 回收站还原。图库和模型引用记录会同步更新。</p><div class="delete-file"><img src="${thumbURL(im.path)}" alt=""><div><strong>${esc(im.name)}</strong><span>${fmtSize(im.size)}${im.width&&im.height?` · ${im.width} × ${im.height}`:''}</span></div></div><p class="dialog-error" id="delete-error" role="alert"></p><div class="dialog-actions"><button class="btn" id="delete-cancel">保留图片</button><button class="btn danger" id="delete-confirm">${icon('trash',15)} 移到回收站</button></div></div>`);
    const button=$('#delete-confirm'),cancel=$('#delete-cancel'),error=$('#delete-error');
    cancel.onclick=closeModal;
    button.onclick=async()=>{
      button.disabled=true;cancel.disabled=true;button.textContent='正在移到回收站…';error.textContent='';
      try{
        await api('/api/image/delete',{body:{path:im.path,size:im.size,mtime:im.mtime}});
        closeModal();closeLightbox();toast('已移到 Windows 回收站','ok');onDeleted();
      }catch(e){error.textContent=e.message;button.disabled=false;cancel.disabled=false;button.innerHTML=icon('trash',15)+' 重试';}
    };
    cancel.focus();
  }
  pages.images=(el,params=new URLSearchParams(),restored)=>{
    if(restored)Object.assign(imgState,restored);
    else if(params.has('model')||params.has('dir'))Object.assign(imgState,{model:params.get('model')||'',dir:params.get('dir')||'',q:'',page:1});
    el.innerHTML=heading('出图图库','浏览作品、检查生成记录，整理不再需要的图片。','GALLERY')+`<div class="gallery-toolbar"><div class="gallery-title"><b id="image-total">读取图库…</b><span>本地出图</span></div><div class="gallery-density" role="group" aria-label="预览大小"><button data-density="comfortable" aria-label="大图预览" title="大图预览" class="${imgState.density==='comfortable'?'active':''}">${icon('overview',16)}</button><button data-density="compact" aria-label="紧凑预览" title="紧凑预览" class="${imgState.density==='compact'?'active':''}">${icon('grid',16)}</button></div></div><div class="filterbar gallery-filters"><input id="im-q" type="search" aria-label="搜索图片" placeholder="搜索文件名或提示词…" value="${esc(imgState.q)}"><input id="im-model" aria-label="按引用模型筛选" placeholder="筛选模型名称或路径" value="${esc(imgState.model)}"><select id="im-dir" aria-label="图片目录"><option value="">所有出图目录</option></select><select id="im-sort" aria-label="图片排序"><option value="newest" ${imgState.sort==='newest'?'selected':''}>最新在前</option><option value="oldest" ${imgState.sort==='oldest'?'selected':''}>最早在前</option></select><button class="btn ghost" id="im-clear">重置</button></div><div class="gallery ${imgState.density==='compact'?'compact':''}" id="image-grid"></div><div id="images-empty"></div><div id="images-pager"></div>`;
    let sequence=0,dirsReady=false;
    const load=async()=>{
      const request=++sequence;
      const query=new URLSearchParams();for(const key of ['page','size','q','model','dir','sort'])if(imgState[key]!== '')query.set(key,imgState[key]);
      try{
        const d=await api('/api/images?'+query);if(request!==sequence||!el.isConnected)return;
        const maxPage=Math.max(1,Math.ceil(d.total/d.size));if(imgState.page>maxPage){imgState.page=maxPage;return load();}
        $('#image-total',el).textContent=d.total.toLocaleString()+' 张图片';
        if(!dirsReady){const select=$('#im-dir',el);select.innerHTML='<option value="">所有出图目录</option>'+d.dirs.map(path=>`<option value="${esc(path)}">${esc(path)}</option>`).join('');select.value=imgState.dir;dirsReady=true;}
        $('#image-grid',el).innerHTML=d.items.map((im,index)=>`<article class="gitem"><button class="g-preview" data-image="${index}" aria-label="查看 ${esc(im.name)}"><img src="${thumbURL(im.path)}" alt="${esc(im.name)}" loading="lazy"><span class="preview-hint">${icon('expand',15)} 查看大图</span>${im.width&&im.height?`<span class="image-resolution">${im.width} × ${im.height}</span>`:''}</button><div class="gitem-body"><div class="gitem-heading"><button class="gallery-filename" data-image="${index}" title="${esc(im.name)}">${esc(im.name)}</button><button class="gallery-delete" data-delete="${index}" title="移到回收站" aria-label="删除 ${esc(im.name)}">${icon('trash',15)}</button></div><div class="gitem-meta"><span>${im.engine==='comfyui'?'ComfyUI':im.engine==='a1111'?'Stable Diffusion':'本地图片'}</span><span>${fmtDate(im.mtime)} · ${fmtSize(im.size)}</span></div></div></article>`).join('');
        $('#images-empty',el).innerHTML=d.items.length?'':empty('当前没有匹配的图片','调整筛选条件，或刷新索引读取最新出图。');
        $('#images-pager',el).replaceChildren(pager(d.total,d.page,d.size,p=>{imgState.page=p;load();}));
        const afterDelete=()=>{if(el.isConnected){dirsReady=false;load();}};
        $$('[data-image]',el).forEach(button=>button.onclick=()=>{const im=d.items[+button.dataset.image];openLightbox(im.path,`<strong>${esc(im.name)}</strong><span>${fmtSize(im.size)} · ${esc(im.engine||'本地图片')}</span>`,()=>requestImageDeletion(im,afterDelete));});
        $$('[data-delete]',el).forEach(button=>button.onclick=()=>requestImageDeletion(d.items[+button.dataset.delete],afterDelete));
      }catch(e){if(request===sequence)$('#images-empty',el).innerHTML=empty('图库读取失败',e.message);}
    };
    const search=debounce(()=>{if(el.isConnected)load();},300);
    for(const [id,key]of [['im-q','q'],['im-model','model']])$('#'+id,el).oninput=e=>{imgState[key]=e.target.value.trim();imgState.page=1;search();};
    for(const key of ['dir','sort'])$('#im-'+key,el).onchange=e=>{imgState[key]=e.target.value;imgState.page=1;load();};
    $('#im-clear',el).onclick=()=>{Object.assign(imgState,{q:'',model:'',dir:'',page:1,sort:'newest'});$('#im-q',el).value='';$('#im-model',el).value='';$('#im-dir',el).value='';$('#im-sort',el).value='newest';load();};
    $$('[data-density]',el).forEach(button=>button.onclick=()=>{imgState.density=button.dataset.density;$('#image-grid',el).classList.toggle('compact',imgState.density==='compact');$$('[data-density]',el).forEach(b=>b.classList.toggle('active',b===button));});
    return load();
  };

  // ================= 大模型 =================
  pages.llm = (el) => {
    el.innerHTML = `<div class="muted">加载中…</div>`;
    return api("/api/llm").then(d => {
      const groups = {};
      d.items.forEach(it => { (groups[it.mtype] = groups[it.mtype] || []).push(it); });
      el.innerHTML = Object.entries(groups).map(([t, items]) => `
        <div class="panel" style="overflow-x:auto"><h3>${t === "LLM" ? "🧠 大语言模型" : t === "TTS" ? "🗣️ 语音模型" : "📦 模型包"}（${items.length}）</h3>
        <div class="body" style="padding:0"><table class="tbl">
          <thead><tr><th>文件</th><th>家族</th><th>量化</th><th>参数量</th><th>大小</th><th>位置</th><th>修改时间</th></tr></thead>
          <tbody>${items.map(m => `<tr class="rowbtn model-link" data-id="${m.rowid_pk}">
            <td>${esc(m.filename)}</td><td><span class="badge b-blue">${esc(m.classification?.architecture||m.family || "其他")}</span></td>
            <td>${esc(m.quant || "-")}</td><td>${esc(m.params || "-")}</td>
            <td class="num">${m.size_h}</td><td class="muted mono" title="${esc(m.path)}" style="max-width:340px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(m.path)}</td>
            <td class="muted">${fmtDate(m.mtime)}</td></tr>`).join("")}</tbody></table></div></div>`).join("")
        || `<div class="muted">未发现大模型文件</div>`;
      bindModelLinks(el);
    }).catch(e => el.innerHTML = `<div class="badge b-red">${esc(e.message)}</div>`);
  };

  // ================= 文件总览 =================
  const fileState = { path: "" };
  pages.files = (el, params, restored) => {
    const path = restored?.path ?? params.get("path") ?? fileState.path ?? "";
    el.innerHTML = `<div class="muted">加载中…</div>`;
    return api("/api/tree?path=" + encodeURIComponent(path)).then(async d => {
      if (!el.isConnected) return;
      fileState.path = d.path;
      const catIcon = { image: "🖼️", video: "🎬", audio: "🎵", model: "🧩", workflow: "🔀", doc: "📄", code: "💻", archive: "🗜️" };
      el.innerHTML = `
        <div class="filterbar"><input id="fs-q" placeholder="全盘搜索文件名…" style="width:280px"><span id="fs-results"></span></div>
        <div class="crumbs">${(d.crumb || []).map((c, i) =>
          `<a data-path="${esc(c.path)}">${esc(c.name)}</a>${i < d.crumb.length - 1 ? " › " : ""}`).join("")}</div>
        ${d.dir ? `<div class="muted" style="margin-bottom:10px">本目录 ${d.dir.file_count} 文件 · ${fmtSize(d.dir.size)} · ${d.dir.dir_count} 子目录</div>` : ""}
        <div class="dirgrid">${d.subdirs.map(s => `
          <div class="dircell" data-path="${esc(s.path)}">
            <span class="ic">${s.ignored ? "🚫" : "📁"}</span>
            <span class="nm" title="${esc(s.path)}">${esc(s.name)}</span>
            <span class="sz">${s.ignored ? "已忽略" : fmtSize(s.size) + " · " + s.file_count + " 文件"}</span>
          </div>`).join("")}</div>
        ${d.files.length ? `<div class="panel" style="overflow-x:auto"><h3>文件</h3><div class="body" style="padding:0">
          <table class="tbl"><thead><tr><th>名称</th><th>类别</th><th>大小</th><th>修改时间</th></tr></thead>
          <tbody>${d.files.map(f => `<tr>
            <td>${f.category === "image" ? `<a class="link" href="#" data-view="${esc(f.path)}">${esc(f.name)}</a>` : esc(f.name)}</td>
            <td>${catIcon[f.category] || "📄"} ${esc(f.mtype || f.category || "")}</td>
            <td class="num">${fmtSize(f.size)}</td><td class="muted">${fmtDate(f.mtime)}</td></tr>`).join("")}</tbody></table></div></div>` : ""}`;
      $$(".dircell", el).forEach(c => c.onclick = () => nav("files", { path: c.dataset.path }));
      $$(".crumbs a", el).forEach(c => c.onclick = () => nav("files", { path: c.dataset.path }));
      $$("[data-view]", el).forEach(a => a.onclick = ev => { ev.preventDefault(); openLightbox(a.dataset.view, ""); });
      const search = async () => {
        if (!el.isConnected) return;
        const term = $("#fs-q", el).value.trim();
        if (term.length < 2) { $("#fs-results", el).innerHTML = ""; return; }
        const r = await api("/api/files/search?q=" + encodeURIComponent(term));
        if (!el.isConnected || $("#fs-q", el).value.trim() !== term) return;
        $("#fs-results", el).innerHTML = `<div class="panel" style="margin:0;width:100%;max-height:420px;overflow-y:auto"><div class="body" style="padding:0">
          <table class="tbl"><tbody>${r.items.map(f => `<tr class="rowbtn" data-path="${esc(f.path)}">
            <td>${esc(f.name)}</td><td class="num">${fmtSize(f.size)}</td>
            <td class="muted mono" style="max-width:380px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(f.path)}</td></tr>`).join("") || '<tr><td class="muted">无结果</td></tr>'}</tbody></table></div></div>`;
        $$("#fs-results .rowbtn", el).forEach(row => row.onclick = () => {
          const p = row.dataset.path;
          if (/\.(png|jpg|jpeg|webp)$/i.test(p)) openLightbox(p, ""); else nav("files", { path: p.replace(/\\[^\\]+$/, "") });
        });
      };
      $("#fs-q", el).oninput = debounce(search, 400);
      if (restored?.query) { $("#fs-q", el).value = restored.query; await search(); }
    }).catch(e => el.innerHTML = `<div class="badge b-red">${esc(e.message)}（路径可能不存在）</div>`);
  };

  pages.reports=async(el,params=new URLSearchParams(),restored)=>{
    el.innerHTML=skeleton();
    try{
      const data=await api('/api/reports');
      if(!el.isConnected)return;
      let selected=restored?.path||params.get('path')||data.items.find(r=>r.name==='START_HERE.md')?.path||data.items[0]?.path;
      const groups={};data.items.forEach(r=>(groups[r.group]??=[]).push(r));
      el.innerHTML=heading('知识与报告','目录规则、模型说明与项目档案，在这里统一查阅。','KNOWLEDGE BASE')+`<div class="report-layout"><aside class="report-list" aria-label="报告列表"><input class="inp" id="report-search" aria-label="搜索报告" placeholder="搜索报告标题…"><select class="inp" id="report-group-filter" aria-label="知识分组"><option value="">所有资料分组</option>${Object.keys(groups).map(g=>`<option value="${esc(g)}">${esc(g)}</option>`).join('')}</select><button class="btn small" id="knowledge-register">登记知识入口</button>${Object.entries(groups).map(([group,items])=>`<div class="report-group">${esc(group)}</div>${items.map(r=>`<button class="report-item" data-report="${esc(r.path)}" data-report-group="${esc(r.group)}" title="${esc(r.path)}">${icon('document',15)}<span>${esc(r.name.replace(/\.md$/,''))}</span></button>`).join('')}`).join('')}<button class="btn small" id="rep-gen" style="margin:15px 10px">生成索引报告</button></aside><article class="report-reader" id="report-reader"></article></div>`;
      let request=0;
      const show=async path=>{
        selected=path;el.dataset.report=path;const serial=++request,reader=$('#report-reader',el),record=data.items.find(r=>r.path===path);
        $$('.report-item',el).forEach(b=>b.classList.toggle('active',b.dataset.report===path));
        reader.innerHTML='<div class="reader-body">正在读取报告…</div>';
        try{
          if(record?.kind==='html'){reader.innerHTML=`<div class="reader-header">${esc(record.name)}</div><div class="reader-body">${empty('交互式模型手册','这份报告为独立 HTML 页面，可在浏览器新标签页打开。')}<a class="btn" href="${fileURL(path)}" target="_blank" rel="noopener noreferrer">打开 HTML 手册 ${icon('arrow',14)}</a></div>`;return;}
          const r=await api('/api/report/content?path='+encodeURIComponent(path));if(serial!==request)return;
          reader.innerHTML=`<div class="reader-header"><span>${icon('document',16)} ${esc(r.name)}</span><button class="btn small" id="copy-report-path">${icon('copy',12)} 复制路径</button></div><div class="reader-body">${mdRender(r.content,path)}</div>`;
          $('#copy-report-path',reader).onclick=()=>copyPath(path);
        }catch(e){reader.innerHTML=empty('这份报告暂时无法读取',e.message);}
      };
      $$('[data-report]',el).forEach(b=>b.onclick=()=>nav('reports',{path:b.dataset.report,q:$('#report-search',el).value}));
      const filter=()=>{const q=$('#report-search',el).value.trim().toLowerCase();$$('[data-report]',el).forEach(b=>b.hidden=!b.textContent.toLowerCase().includes(q)||!!$('#report-group-filter',el).value&&b.dataset.reportGroup!==$('#report-group-filter',el).value);};
      $('#report-search',el).value=restored?.query??params.get('q')??'';
      $('#report-group-filter',el).value=restored?.group??params.get('group')??'';
      $('#report-group-filter',el).onchange=filter;
      $('#knowledge-register',el).onclick=async()=>{try{const snapshot=await api('/api/registry');if(el.isConnected)AIHubRegistry.editor(registryEnv,'knowledge',{},snapshot,route);}catch(e){toast(e.message,'err');}};
      $('#report-search',el).oninput=filter;filter();
      $('#rep-gen',el).onclick=async()=>{try{const r=await api('/api/report/generate',{body:{}});toast('索引报告已生成','ok');nav('reports',{path:r.path});}catch(e){toast(e.message,'err');}};
      if(selected)await show(selected);else $('#report-reader',el).innerHTML=empty('尚未发现管理报告');
    }catch(e){failPage(el,e);}
  };

  pages.workflows=async(el,params=new URLSearchParams(),restored)=>{
    el.innerHTML=skeleton();
    try{
      const d=await api('/api/workflows');if(!el.isConnected)return;let state=restored?.state??params.get('state')??'',query=restored?.query?.trim().toLowerCase()||'';
      const labels=AIHubRegistry.STATES;const verificationState=w=>w.verification_state||'pending';if(state==='needs_review')state='pending';
      el.innerHTML=heading('工作流','查看模型依赖与路径记录，定位可用副本。','WORKFLOW LIBRARY')+`<div class="filterbar"><input id="wf-query" aria-label="搜索工作流" placeholder="搜索工作流名称或模型…"><select id="wf-state" aria-label="工作流状态"><option value="">所有状态 · ${d.items.length}</option>${Object.entries(labels).map(([value,label])=>`<option value="${value}" ${state===value?'selected':''}>${label} · ${d.verification_counts?.[value]||0}</option>`).join('')}</select></div><p class="warning-note">验证结论按版本、日期和证据分别记录。仅路径检查与历史执行均不代表当前可运行。</p><section class="panel table-wrap"><table class="tbl"><thead><tr><th>工作流</th><th>验证状态 / 日期</th><th>证据与待核对</th><th>操作</th></tr></thead><tbody id="workflow-rows"></tbody></table><div id="workflow-empty"></div></section>`;
      const render=()=>{
        const filtered=d.items.filter(w=>(!state||verificationState(w)===state)&&(!query||JSON.stringify([w.name,w.missing,w.dependencies]).toLowerCase().includes(query)));
        $('#workflow-rows',el).innerHTML=filtered.map(w=>`<tr><td class="workflow-name">${esc(w.name)}<span class="file-sub">${w.dependencies.length} 个模型引用</span></td><td>${AIHubRegistry.verificationBadge(verificationState(w))}<span class="file-sub">${esc(w.validation?.date||'无验证日期')}</span></td><td class="workflow-missing"><span class="file-sub">${esc(w.verification_reason||'暂无执行证据')}</span>${w.status==='reviewed_copy'?`${w.changes.length} 处路径修正 · ${w.copy_exists?'副本可访问':'副本当前不可访问'}`:esc(w.missing.join('；')||'记录中未发现缺失模型')}</td><td><button class="btn small" data-workflow="${esc(w.path)}">依赖详情</button></td></tr>`).join('');
        $('#workflow-empty',el).innerHTML=filtered.length?'':empty('没有匹配的工作流');
        $$('[data-workflow]',el).forEach(b=>b.onclick=()=>{
          const w=d.items.find(x=>x.path===b.dataset.workflow);
          openModal(`<h2>${esc(w.name)}</h2><div class="warning-note">${d.coverage}</div><div class="kv"><div class="k">原稿</div><div class="pathline">${esc(w.path)}</div>${w.copy?`<div class="k">修正版</div><div class="pathline">${esc(w.copy)}</div>`:''}</div>${AIHubRegistry.verificationBadge(verificationState(w))}<p>${esc(w.verification_reason||'暂无执行证据')}</p><div class="copy-paths"><button class="btn small" id="workflow-register">登记验证证据</button><button class="btn small" id="copy-wf-original">复制原稿路径</button>${w.copy?'<button class="btn small primary" id="copy-wf-reviewed">复制修正版路径</button>':''}</div><div class="workflow-details">${w.dependencies.map(p=>`<div class="dependency"><span class="badge ${p.exists?'b-green':'b-yellow'}">${p.exists?'原路径有记录':'原路径需核对'}</span><div>${esc(p.name)}<span class="file-sub">${esc(p.type)}</span></div></div>`).join('')}</div>${w.changes.length?`<div class="intro"><h3>路径修正记录</h3>${w.changes.map(c=>`<p>${esc(c.from)}<br>→ ${esc(c.to)}</p>`).join('')}</div>`:''}`);
          $('#workflow-register').onclick=async()=>{try{const snapshot=await api('/api/registry');if(!el.isConnected)return;AIHubRegistry.editor(registryEnv,'workflow',(snapshot.workflows||[]).find(r=>r.path===w.path)||{path:w.path},snapshot,route);}catch(e){toast(e.message,'err');}};
          $('#copy-wf-original').onclick=()=>copyPath(w.path);if(w.copy)$('#copy-wf-reviewed').onclick=()=>copyPath(w.copy);
        });
      };
      $('#wf-query',el).value=restored?.query||'';
      $('#wf-state',el).onchange=e=>{state=e.target.value;render();};$('#wf-query',el).oninput=debounce(e=>{if(!el.isConnected)return;query=e.target.value.trim().toLowerCase();render();},200);render();
    }catch(e){failPage(el,e);}
  };

  // ================= 设置 =================
  pages.settings = (el) => {
    el.innerHTML = `<div class="muted">加载中…</div>`;
    return api("/api/settings").then(c => {
      el.innerHTML = `
        <section class="setup-banner organizer-settings-entry"><div><h3>安全区与自动分类</h3><p>换电脑后，从这里选择本机目录、预览分类入口并设置启动整理。</p></div><a class="btn" href="#/organizer">管理安全区 ${icon('arrow',14)}</a></section>
        <div class="panel"><h3>🌐 网络与更新源</h3><div class="body">
          <div class="form-row"><div class="k">Civitai API 地址</div><input class="inp" id="s-cbase" value="${esc(c.network.civitai_base)}"></div>
          <div class="form-row"><div class="k">Civitai Token（可选）</div><input class="inp" id="s-token" type="password" autocomplete="off" value="${esc(c.network.civitai_token || "")}" placeholder="用于提高限流额度"></div>
          <div class="form-row"><div class="k">HuggingFace 地址</div><input class="inp" id="s-hbase" value="${esc(c.network.hf_base)}"></div>
          <div class="form-row"><div class="k">代理</div><input class="inp" id="s-proxy" value="${esc(c.network.proxy || "")}" placeholder="http://127.0.0.1:7890（访问 Civitai 困难时设置）"></div>
          <div class="form-row"><div class="k">请求间隔（秒）</div><input class="inp" id="s-interval" value="${esc(c.network.request_interval)}"></div>
        </div></div>
        <div class="panel"><h3>📁 扫描范围（JSON）</h3><div class="body">
          <div class="form-row"><div class="k">AI 根目录</div><input class="inp" id="s-root" value="${esc(c.ai_root)}" placeholder="填写存放模型和出图的文件夹"></div>
          <div class="form-row"><div class="k"></div><button class="btn" id="s-detect">探测目录</button><span class="caption-note">自动填充下方扫描范围，保存后可刷新索引。</span></div>
          <div class="form-row"><div class="k">扫描根分区</div><textarea class="ta" id="s-roots" style="min-height:110px">${esc(JSON.stringify(c.scan_roots, null, 1))}</textarea></div>
          <div class="form-row"><div class="k">输出目录</div><textarea class="ta" id="s-outputs" style="min-height:80px">${esc(JSON.stringify(c.output_roots, null, 1))}</textarea></div>
          <div class="form-row"><div class="k">忽略目录</div><input class="inp" id="s-ignore" value="${esc((c.ignore_dirs || []).join(", "))}"></div>
          <div class="muted" style="font-size:12px">扫描根会自动跳过 junction/符号链接防止环路；修改后保存并重新扫描生效。</div>
        </div></div>
        <button class="btn primary" id="s-save">💾 保存设置</button>
        <div class="section-gap"></div>
        <div class="panel"><h3>🧹 数据</h3><div class="body">
          <button class="btn" id="s-rescan">⟳ 立即重新扫描（文件 + 出图分析）</button>
          <span class="muted" style="margin-left:10px">SQLite 数据库位于 ai-hub/data/aihub.db</span>
        </div></div>`;
      let detected=null;
      $('#s-root',el).oninput=()=>{detected=null;};
      $('#s-detect',el).onclick=async()=>{
        const button=$('#s-detect',el);button.disabled=true;
        try{detected=await api('/api/settings/detect',{body:{ai_root:$('#s-root',el).value.trim()}});if(!el.isConnected)return;$('#s-root',el).value=detected.ai_root;$('#s-roots',el).value=JSON.stringify(detected.scan_roots,null,1);$('#s-outputs',el).value=JSON.stringify(detected.output_roots,null,1);toast('已填充扫描范围，保存设置后生效','ok');}
        catch(e){toast(e.message,'err');}finally{button.disabled=false;}
      };
      $("#s-save", el).onclick = async () => {
        let roots, outputs;
        try { roots = JSON.parse($("#s-roots").value); } catch { return toast("扫描根不是合法 JSON", "err"); }
        try { outputs = JSON.parse($("#s-outputs").value); } catch { return toast("输出目录不是合法 JSON", "err"); }
        await api("/api/settings", { body: {
          ai_root: $("#s-root").value.trim(),
          scan_roots: roots, output_roots: outputs,
          ...(detected?{aliases:detected.aliases,catalog_dir:detected.catalog_dir}:{}),
          ignore_dirs: $("#s-ignore").value.split(",").map(s => s.trim()).filter(Boolean),
          network: { civitai_base: $("#s-cbase").value.trim(), civitai_token: $("#s-token").value.trim(),
                     hf_base: $("#s-hbase").value.trim(), proxy: $("#s-proxy").value.trim(),
                     request_interval: parseFloat($("#s-interval").value) || 1.2 },
        }});
        toast("设置已保存，可以刷新索引读取资产", "ok");
      };
      $("#s-rescan", el).onclick = async () => {
        try { await api("/api/scan/start", { body: {} }); toast("扫描已开始，可看左上角进度", "ok"); }
        catch (e) { toast(e.message, "err"); }
      };
    }).catch(e => el.innerHTML = `<div class="badge b-red">${esc(e.message)}</div>`);
  };

  // ---------- 全局动作 ----------
  $("#btn-rescan").onclick = async () => {
    try { await api("/api/scan/start", { body: {} }); toast("重新扫描已开始", "ok"); }
    catch (e) { toast(e.message, "err"); }
  };
  $("#btn-check-updates").onclick = async () => {
    try { await api("/api/models/check-updates", { body: { scope: "all" } }); toast("更新检查已开始（后台逐个进行）", "ok"); }
    catch (e) { toast(e.message, "err"); }
  };
  $("#global-search").addEventListener("keydown", e => {
    if (e.key === "Enter") { nav("models", {q:e.target.value.trim(),scope:"",kind:"",view:"all"}); }
  });

  $$('[data-icon]').forEach(el=>el.innerHTML=icon(el.dataset.icon));
  $('#menu-toggle').onclick=()=>{const open=document.body.classList.toggle('nav-open');$('#menu-toggle').setAttribute('aria-expanded',String(open));};
  document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();$('#global-search').focus();$('#global-search').select();}});
  pollJobs();
  navigation.start();
})();

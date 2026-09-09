/* Project mappings and evidence registration. No file relocation or model execution. */
(function(root, factory) {
  const moduleAPI = factory();
  if (typeof module === 'object' && module.exports) module.exports = moduleAPI;
  else root.AIHubRegistry = moduleAPI;
})(typeof globalThis === 'object' ? globalThis : this, function() {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const TYPES = {creative:'创作项目',training:'模型训练',tool:'工具开发'};
  const STATES = {pending:'待验证',path_checked:'仅路径检查',historical_passed:'历史执行通过',current_passed:'当前复验通过'};
  const lines = text => text.split('\n').map(s=>s.trim()).filter(Boolean);
  function capture(el) {
    return {query:el.querySelector('#project-search')?.value || '', type:el.querySelector('#project-type')?.value || ''};
  }
  function verificationBadge(state) {
    return `<span class="badge ${state==='current_passed'?'b-green':state==='pending'?'b-yellow':''}">${esc(STATES[state] || STATES.pending)}</span>`;
  }
  function editor(env, kind, record, snapshot, done) {
    const {api,openModal,closeModal,toast} = env;
    const input=(id,label,value='',type='text')=>`<label class="registry-field">${label}<input id="reg-${id}" type="${type}" value="${esc(value)}" autocomplete="off"></label>`;
    const area=(id,label,value='')=>`<label class="registry-field wide">${label}<textarea id="reg-${id}" rows="3" spellcheck="false">${esc(value)}</textarea></label>`;
    const select=(id,label,options,value)=>`<label class="registry-field">${label}<select id="reg-${id}">${options.map(([key,text])=>`<option value="${esc(key)}" ${key===value?'selected':''}>${esc(text)}</option>`).join('')}</select></label>`;
    const title={project:'登记项目位置',run:'登记一次运行',workflow:'登记验证证据',knowledge:'登记知识入口'}[kind];
    let fields=input('id','记录编号（字母、数字、短横线）',record.id || 'entry-'+Date.now());
    if(kind==='project') {
      fields+=input('name','项目名称',record.name)+select('type','项目类型',Object.entries(TYPES),record.type || 'creative')+
        select('template','适用模板',(snapshot.templates || []).map(t=>[t.id,t.name||t.label||t.id]),record.template?.id||'external')+
        input('root','现有项目目录',record.root||record.path)+input('current_doc','当前项目说明',record.current_doc||record.report)+
        area('description','当前说明',record.description)+area('assets','资产位置（每行一个）',(record.assets||[]).join('\n'))+
        area('outputs','输出位置（每行一个）',(record.outputs||[]).join('\n'))+input('delivery','唯一正式交付位置',record.delivery)+area('mapping','内部结构映射（可选 JSON，例如 {"脚本":"01_script"}）',JSON.stringify(record.mapping||{},null,2));
    } else if(kind==='run') {
      fields+=select('project_id','所属项目',[['','无项目测试'],...(snapshot.projects||[]).map(p=>[p.id,p.name])],record.project_id||'')+
        input('output_dir','本次输出目录',record.output_dir)+input('workflow_path','工作流位置',record.workflow_path)+
        input('workflow_sha256','工作流 SHA-256',record.workflow_sha256)+input('seed','Seed',record.seed)+
        area('models','模型位置（每行一个）',(record.models||[]).join('\n'));
      fields+='<p class="caption-note wide">运行登记默认为待验证。推荐输出位置：70_Output/Projects/项目编号/运行编号；无项目测试：Tests/Unassigned/运行。正式交付以项目登记为准。</p>';
      fields+='<button class="btn wide" type="button" id="registry-evidence">读取工作流版本</button>';
    } else if(kind==='workflow') {
      const v=record.validation||{};
      fields+=input('path','工作流位置',record.path)+select('state','验证结论',Object.entries(STATES),record.state||'pending')+
        input('date','验证日期',v.date,'date')+input('workflow_sha256','验证版本 SHA-256',v.workflow_sha256)+
        area('dependency_paths','依赖文件位置（每行一个）',(v.dependencies||[]).map(r=>r.path).join('\n'))+
        area('output_paths','输出证据位置（每行一个）',(v.outputs||[]).map(r=>r.path).join('\n'))+
        '<button class="btn wide" type="button" id="registry-evidence">读取文件信息，生成证据快照</button>'+
        area('dependencies','依赖快照（可由上方按钮填写）',JSON.stringify(v.dependencies||[],null,2))+
        area('outputs','输出证据（可由上方按钮填写）',JSON.stringify(v.outputs||[],null,2));
      fields+='<p class="caption-note wide">只有版本、日期、依赖和输出证据完整时才能登记执行通过。当前复验还会核对文件是否仍匹配；路径检查不能代替生成测试。</p>';
    } else {
      fields+=input('title','知识标题',record.title)+input('path','教程正文路径',record.path);
    }
    openModal(`<div class="registry-editor"><div class="eyebrow">REGISTER & REVIEW</div><h2>${title}</h2><p class="muted">保存位置与证据映射。预览不会移动文件或执行工作流。</p><form id="registry-form"><div class="registry-fields">${fields}</div><p id="registry-error" class="dialog-error" role="alert"></p><div class="dialog-actions"><button type="button" class="btn" id="registry-cancel">取消</button><button type="submit" class="btn primary">检查并预览</button></div></form></div>`);
    const form=document.querySelector('#registry-form'),get=id=>form.querySelector('#reg-'+id)?.value.trim()||'';
    document.querySelector('#registry-cancel').onclick=closeModal;
    const evidenceButton=form.querySelector('#registry-evidence');
    if(evidenceButton)evidenceButton.onclick=async()=>{
      evidenceButton.disabled=true;const error=form.querySelector('#registry-error');error.textContent='';
      try {
        const evidence=await api('/api/registry/evidence',{body:{workflow_path:get(kind==='run'?'workflow_path':'path'),dependencies:kind==='workflow'?lines(get('dependency_paths')):[],outputs:kind==='workflow'?lines(get('output_paths')):[]}});
        if(!form.isConnected)return;
        form.querySelector('#reg-workflow_sha256').value=evidence.workflow_sha256;
        if(kind==='workflow'){form.querySelector('#reg-dependencies').value=JSON.stringify(evidence.dependencies,null,2);form.querySelector('#reg-outputs').value=JSON.stringify(evidence.outputs,null,2);}
        toast('已读取文件信息；验证结论与日期仍需根据实际执行记录填写','ok');
      }catch(e){if(form.isConnected)error.textContent=e.message;}
      finally{if(evidenceButton.isConnected)evidenceButton.disabled=false;}
    };
    if(kind==='run') {
      let lastSuggestion='';
      const suggest=()=>{const input=form.querySelector('#reg-output_dir');if(input.value&&input.value!==lastSuggestion)return;const base=String(snapshot.workspace||'').replace(/[\\/]$/,'');if(!base)return;lastSuggestion=base+'/70_Output/'+(get('project_id')?'Projects/'+get('project_id'):'Tests/Unassigned')+'/'+get('id');input.value=lastSuggestion;};
      form.querySelector('#reg-project_id').onchange=suggest;form.querySelector('#reg-id').oninput=suggest;suggest();
    }
    form.onsubmit=async event=>{
      event.preventDefault();const error=form.querySelector('#registry-error');error.textContent='';
      try {
        let next={id:get('id')};
        if(kind==='project') {
          const template=(snapshot.templates||[]).find(t=>t.id===get('template'));
          next={...next,name:get('name'),type:get('type'),root:get('root'),current_doc:get('current_doc'),description:get('description'),assets:lines(get('assets')),outputs:lines(get('outputs')),delivery:get('delivery'),template:{id:get('template'),version:template?.version||'1',applicable:get('template')!=='external'},mapping:JSON.parse(get('mapping')||'{}')};
        } else if(kind==='run') {
          const seed=get('seed');
          if(seed && !Number.isSafeInteger(Number(seed)))throw new Error('Seed 请填写安全范围内的整数，或留空。');
          next={...next,project_id:get('project_id')||null,output_dir:get('output_dir'),workflow_path:get('workflow_path'),workflow_sha256:get('workflow_sha256'),models:lines(get('models')),seed:seed?Number(seed):null,validation_status:'pending'};
        }
        else if(kind==='workflow') next={...next,path:get('path'),state:get('state'),validation:{date:get('date'),workflow_sha256:get('workflow_sha256'),dependencies:JSON.parse(get('dependencies')),outputs:JSON.parse(get('outputs')),note:record.validation?.note||''}};
        else next={...next,title:get('title'),path:get('path')};
        const preview=await api('/api/registry/preview',{body:{kind,record:next}});
        if(!form.isConnected)return;
        showPreview(env,preview,()=>editor(env,kind,next,snapshot,done),done);
      } catch(e) {if(form.isConnected)error.textContent=e.message;}
    };
  }
  function showPreview(env,preview,back,done) {
    const {api,openModal,closeModal,toast}=env;
    openModal(`<div class="registry-review"><h2>确认登记预览</h2><p>检查下面的位置与结论后保存。原资产和应用目录保持原位。</p>${(preview.warnings||[]).map(w=>`<p class="warning-note">${esc(w)}</p>`).join('')}<pre class="registry-json">${esc(JSON.stringify(preview.record || preview,null,2))}</pre><p id="registry-error" class="dialog-error" role="alert"></p><div class="dialog-actions"><button class="btn" id="registry-back">返回修改</button><button class="btn primary" id="registry-save">保存登记</button></div></div>`);
    document.querySelector('#registry-back').onclick=back || closeModal;
    const button=document.querySelector('#registry-save');
    button.onclick=async()=>{
      button.disabled=true;
      try {await api('/api/registry/save',{body:{token:preview.token}});if(button.isConnected){closeModal();toast('登记已保存，原资产未改动','ok');done?.();}}
      catch(e){if(button.isConnected){document.querySelector('#registry-error').textContent=e.message;button.disabled=false;}}
    };
  }
  function createProjects(env) {
    const {api,heading,openModal,closeModal,toast,refresh,nav,copyPath}=env;
    return async(el,params=new URLSearchParams(),restored)=>{
      try {
        const [data,snapshot]=await Promise.all([api('/api/projects'),api('/api/registry')]);
        if(!el.isConnected)return;
        const $=s=>el.querySelector(s),$$=s=>[...el.querySelectorAll(s)];
        el.innerHTML=heading('项目与运行','创作、训练和工具开发，共用一份位置登记。','PROJECT REGISTRY')+`<div class="filterbar"><input id="project-search" type="search" aria-label="搜索项目" placeholder="搜索项目、说明或位置"><select id="project-type" aria-label="项目类型"><option value="">所有项目类型</option>${Object.entries(TYPES).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select><button class="btn primary" id="project-add">登记项目</button><button class="btn" id="project-run">登记运行</button><button class="btn ghost" id="registry-backups">登记回退</button></div><p class="caption-note">${esc(data.coverage)}</p><div class="project-grid" id="project-list"></div><section class="panel"><div class="panel-head"><h3>运行与输出归属</h3></div><div class="table-wrap"><table class="tbl"><thead><tr><th>运行</th><th>所属项目</th><th>输出位置</th><th>登记状态</th></tr></thead><tbody>${(snapshot.runs||[]).map(r=>`<tr><td>${esc(r.id)}</td><td>${esc((snapshot.projects||[]).find(p=>p.id===r.project_id)?.name||'无项目测试')}</td><td class="pathline">${esc(r.output_dir)}</td><td>${verificationBadge(r.effective_validation_status||r.validation_status)}</td></tr>`).join('')||'<tr><td colspan="4">尚无运行登记。历史散图不会按文件名自动认领。</td></tr>'}</tbody></table></div></section><details class="panel project-templates"><summary>项目模板与位置规则</summary>${(snapshot.templates||[]).map(t=>`<p><b>${esc(t.name||t.label||t.id)} · ${esc(t.version)}</b> ${esc(t.description||'')}<span class="file-sub">${esc((t.types||[]).map(k=>TYPES[k]||k).join(' / '))}</span></p>`).join('')}<p>通用素材保留在 30_Assets；训练归 50_Training/Projects；内部项目结构通过位置映射接入。正式交付只认项目登记的一个位置。</p></details>`;
        const render=()=>{
          const query=$('#project-search').value.toLowerCase(),type=$('#project-type').value;
          const items=data.items.filter(p=>(!type||p.type===type)&&(!query||[p.name,p.description,p.path].join(' ').toLowerCase().includes(query)));
          $('#project-list').innerHTML=items.map(p=>`<article class="panel project-card"><div class="project-card-heading"><span class="badge">${esc(TYPES[p.type]||'类型待登记')}</span><span class="badge ${p.registered?'':'b-yellow'}">${esc(p.status||(p.registered?'已登记':'未登记'))}</span></div><h3>${esc(p.name)}</h3><p>${esc(p.description||'尚未补充当前说明')}</p><dl><dt>项目位置</dt><dd>${esc(p.root||p.path)}</dd><dt>当前说明</dt><dd>${esc(p.current_doc||p.report||'未登记')}</dd><dt>资产位置</dt><dd>${esc((p.assets?.length?p.assets:p.datasets||[]).join('\n')||'未登记')}</dd><dt>输出位置</dt><dd>${esc((p.outputs?.length?p.outputs:p.runs||[]).join('\n')||'未登记')}</dd><dt>正式交付</dt><dd>${esc(p.delivery||'未登记')}</dd></dl><div class="project-card-actions">${p.current_doc||p.report?`<button class="btn small" data-doc="${esc(p.current_doc||p.report)}">阅读项目说明</button>`:''}<button class="btn small" data-edit="${esc(p.id||p.path)}">${p.registered?'编辑登记':'补齐登记'}</button><button class="btn small ghost" data-copy="${esc(p.root||p.path)}">复制位置</button></div></article>`).join('')||'<p class="results-empty">没有匹配的项目。</p>';
          $$('[data-doc]').forEach(b=>b.onclick=()=>nav('reports',{path:b.dataset.doc}));
          $$('[data-copy]').forEach(b=>b.onclick=()=>copyPath(b.dataset.copy));
          $$('[data-edit]').forEach(b=>b.onclick=()=>{
            const p=data.items.find(p=>(p.id||p.path)===b.dataset.edit);
            const existing=(snapshot.projects||[]).find(r=>r.id===p.id);
            editor(env,'project',existing||{...p,id:''},snapshot,refresh);
          });
        };
        $('#project-search').value=restored?.query??params.get('q')??'';
        $('#project-type').value=restored?.type??params.get('type')??'';
        $('#project-search').oninput=render;$('#project-type').onchange=render;render();
        $('#project-add').onclick=()=>editor(env,'project',{},snapshot,refresh);
        $('#project-run').onclick=()=>editor(env,'run',{},snapshot,refresh);
        $('#registry-backups').onclick=async()=>{
          try {
            const backups=await api('/api/registry/backups');if(!el.isConnected)return;
            openModal(`<h2>登记回退</h2><p>只恢复项目、运行和验证登记。不会改变原资产或模型评分。</p><div class="registry-backups">${backups.items.map(b=>`<button class="btn" data-backup="${esc(b.id)}">${esc(b.name||b.id)}</button>`).join('')||'<p>尚无登记备份。</p>'}</div><p id="registry-error" class="dialog-error"></p>`);
            document.querySelectorAll('[data-backup]').forEach(b=>b.onclick=async()=>{
              try {const preview=await api('/api/registry/restore-preview',{body:{backup_id:b.dataset.backup}});if(b.isConnected)showPreview(env,preview,closeModal,refresh);}
              catch(e){if(b.isConnected)document.querySelector('#registry-error').textContent=e.message;}
            });
          }catch(e){toast(e.message,'err');}
        };
      }catch(e){if(el.isConnected)el.innerHTML=`<div class="page-error"><h3>项目登记暂不可用</h3><p>${esc(e.message)}</p></div>`;}
    };
  }
  return {TYPES,STATES,capture,verificationBadge,createProjects,editor,showPreview};
});

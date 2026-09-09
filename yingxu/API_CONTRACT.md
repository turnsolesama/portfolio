# 映序 API v1

Base http://127.0.0.1:8791。JSON；错误 {error:"中文信息"} 配相应状态码。GET /api/bootstrap 返回 {app:"yingxu",version,token,project_root,data_root,categories:[{key,label}],statuses:[...],capabilities:{...}}。写请求头 X-YingXu-Token=token，Content-Type:application/json。

Categories: scripts 剧本与文档 / shots 分镜 / characters 角色 / scenes 场景 / props 道具 / previs 白模预演 / generated 生成素材 / delivery 成片交付 / references 参考资料。Statuses: 待开始, 进行中, 待审核, 已完成。

GET /api/projects -> {projects:[{id,name,description,color,root,created,updated,counts:{total,shots,completed,documents}}]}
POST /api/projects {name,description} -> project object，创建标准目录。
GET /api/items?project=ID&category=KEY&q=QUERY&status=STATUS&kind=KIND&limit=60&offset=0&sort=updated|name|order -> {items,total,limit,offset,categories:[{key,label,count}],elapsed_ms}。q 支持普通中文文本、tag:夜景、type:video、status:已完成、category:scenes，多个条件 AND。服务端优先分页；前端每页最大60，不无限累积DOM。
Item object: {id,project_id,name,category,kind,ext,path,size,mtime,status,tags:[...],notes,metadata:{...},sort_order,created,updated,thumbnail_url,media_url}. kinds markdown,text,docx,image,video,audio,pdf,model,file。新分镜本体是 category=shots 的 markdown。图片/视频 thumb 用 /api/thumbnail/ID（202 尚未就绪，稍后有限重试）。media_url=/api/media/ID。列表不含全文。
GET /api/items/ID -> item + {relations:[{id,source_id,target_id,relation,item:relatedItem}],versions:[{id,created,size}],content_preview}
POST /api/items {project_id,category,name,content?,status?,tags?,metadata?} -> item；创建 .md，本体是本地文件。metadata 支持 shot_number, duration, shot_size, camera, prompt, negative_prompt, seed, model, version 等。
PATCH /api/items/ID {name?,category?,status?,tags?,notes?,metadata?,sort_order?} -> item。name 只改显示名，不移动文件。
DELETE /api/items/ID -> {ok:true,batch_id,project_id,kind,count} 移入映序回收站（磁盘文件保留），可恢复。
GET /api/content/ID -> {format:"markdown"|"text"|"docx"|"binary",content,etag,editable,paragraphs?:[{id,text,editable}],notice?}。
PUT /api/content/ID {etag,content} 或 DOCX {etag,paragraphs:[{id,text}]} -> 同 GET，保存前备份；冲突409，前端保留编辑内容并提示刷新。
POST /api/import {project_id,category,paths:[absolutePath,...]} -> {job_id}，引用原文件，扫描异步增量，忽略链接，不复制/移动原资产。新增项目自己文件可编辑，引用文件同样保存时备份且用户明确点击保存才写。GET /api/jobs/ID -> {id,state:"queued"|"running"|"done"|"error",done,skipped,errors:[...],message}。
POST /api/pick {kind:"files"|"folder"} -> {paths:[...]} 打开 Windows 选择对话框。取消为空。
POST /api/rescan {project_id} -> {job_id} 重扫已注册源和项目文件，保留分类/标签/状态。
POST /api/relations {source_id,target_id,relation} -> {id}，同项目；relation 自由中文，如角色/场景/道具/生成版本/白模参考。
DELETE /api/relations/ID -> {ok:true}
POST /api/open {id,action:"open"|"reveal"} -> {ok:true}，系统关联打开（仅允许已索引安全文档媒体），或定位文件。
POST /api/demo {} -> project object，创建明确标注“示例项目”的合成可编辑示例；默认全新应用先空项目状态，由用户按钮导入示例，安装验收可以创建示例供用户体验。
GET /api/health -> {app:"yingxu",ok:true,version}，供桌面验证服务身份。

前端：fetch 读请求使用 AbortController/序号避免过时响应覆盖；输入搜索250ms debounce；多标签内容在页内保存未提交稿，关闭脏标签确认；Ctrl+S 保存/Ctrl+K搜索。编辑 Markdown 为 textarea+安全预览（禁止原始HTML脚本）；DOCX显示段落编辑与格式说明。3D文件首版系统应用打开，白模视频用播放器。所有占位内容显式示例，不用伪按钮。

## 追加：SKILL 与项目交接

GET /api/skills?q=&project= -> {skills:[{id,name,description,path,source,source_label,editable,bound}],total}。
POST /api/skills/refresh {}。GET /api/skills/ID -> {...,content,etag,editable}；PUT /api/skills/ID {content,etag} 只允许映序自建技能，外部库只读。POST /api/skills {name,description,content} 新建本地 SKILL。POST /api/skills/bind {project_id,skill_id,bound:bool}。
GET /api/context?project=ID 与 POST /api/context/refresh {project_id} 返回 {markdown,path,json_path,index_path,updated,stale,pending,error,...}。项目导出是文本供AI读取，不会自动执行技能。

## 追加：拖放与文件名

POST /api/upload?project=ID&category=KEY&name=URLENCODED_FILENAME 原始File请求体，X-YingXu-Token；响应item。文件流分块写，复制进项目，不移动原文件。
POST /api/rename {id,name} 真实文件改名，保留后缀，遇同名409；更新工作台中全部指向原路径的引用。
GET /api/native-file/ID 返回 {path}，仍检查本地来源、索引及当前路径，仅供受限桌面拖出桥。
桌面拖出手柄 pointerdown 发送 window.chrome.webview.postMessage({action:'drag-file',id})，需真实左键仍按下。桌面提供 FileDrop+Copy；普通浏览器用定位文件。
PNG提取元数据为 source_prompt/source_parameters/source_workflow，width,height；用户手动 prompt 独立。列表不返回全文和完整元数据，完整属性在 GET /api/items/ID。

## 0.2 追加：文件夹、移动、回收站

- GET /api/folders?project=ID&category=KEY -> {folders:[{id,project_id,category,parent_id,name,path,relative_path,folder_path,count}],total}。
- POST /api/folders {project_id,category,name,parent_id?} -> folder，创建实际项目子目录。
- PATCH /api/folders/ID {name} -> folder；DELETE /api/folders/ID -> 删除批次。
- GET /api/items 增加 folder 参数：不传/空串为当前分类递归全部；root 为分类直属；ID 为子文件夹直属。列表与详情带 folder_id/folder_path。
- POST /api/items、POST /api/import 与 POST /api/upload query 均支持 folder_id；空/root 表示分类目录。
- POST /api/move {ids:[...],category,folder_id:null|ID} -> {ok,project_id,items,stats:{moved,referenced,unchanged,copied}}，最多200条同项目。项目内文件实际移动，外部引用只改组织归属；不覆盖同名文件。
- PATCH /api/projects/ID {name?,description?} -> project，仅改显示资料，项目根路径不动。
- DELETE /api/projects/ID、DELETE /api/folders/ID、POST /api/trash/items {ids} -> {ok,batch_id,project_id,kind,count}。
- DELETE /api/skills/ID -> {ok,kind:'skill',batch_id:ID,count:1}。自建技能可恢复删除；外部来源仅在映序隐藏，源文件不卸载。绑定关系保留但回收期间不参与项目交接。
- GET /api/trash?project=ID&q=关键词&limit=48&offset=0 -> {entries:[{id,batch_id,kind,target_id,project_id,name,created,count}],total,limit,offset,truncated}，名称搜索在数据库分页前执行；省略project时列所有项目，始终合并全局技能回收条目。
- POST /api/trash/ID/restore {kind?:'skill'} -> {ok,project_id?,kind,count}。技能必须传kind=skill，其他类型按组织批次恢复。恢复目录/项目仅恢复该删除批次带走的条目，不复活更早删除的文件。
- 进度快照增加folders树和folder_id；项目在回收站时 PROJECT_CONTEXT.md/progress.json 明确标记已回收，恢复后重新生成。

## 0.2.1 追加：本地目录与公开版启动隔离

- POST /api/open-folder {project_id,category?,folder_id?} 在 Windows 资源管理器打开已验证的项目根目录、分类目录或子目录；客户端不能传入任意路径。文件通过原有 POST /api/open {id,action:'reveal'} 定位。
- GET /api/health -> {app:'yingxu',ok:true,version,instance_id}。公开版启动器通过数据目录规范路径的 SHA-256 指纹确认后台；拒绝旧版缺少指纹或指纹不符的服务，避免错误复用其他数据目录。
- 默认数据路径与环境变量见 RUNNING.md；server.py 的 --data 与 --projects-root 参数优先于有效的环境变量默认值。

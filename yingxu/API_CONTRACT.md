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

前端：fetch 读请求使用 AbortController/序号避免过时响应覆盖；输入搜索250ms debounce；多标签内容在页内保存未提交稿，关闭脏标签确认；Ctrl+S 保存，Ctrl+F 聚焦当前页面搜索，Ctrl+K 打开独立全局搜索窗口。编辑 Markdown 为 textarea+安全预览（禁止原始HTML脚本）；DOCX显示段落编辑与格式说明。3D文件首版系统应用打开，白模视频用播放器。所有占位内容显式示例，不用伪按钮。

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
- POST /api/open-folder {skill_id} 打开已登记且未移除的 SKILL.md 所在目录；本地与外部只读技能均可定位，不读取或改写正文。此目标与 project_id/category/folder_id 互斥，拒绝任意 path、未知 ID、已移除/缺失文件及联接或符号链接路径；同样需要当前会话令牌与同源校验。
- GET /api/health -> {app:'yingxu',ok:true,version,instance_id}。公开版启动器通过数据目录规范路径的 SHA-256 指纹确认后台；拒绝旧版缺少指纹或指纹不符的服务，避免错误复用其他数据目录。
- 默认数据路径与环境变量见 RUNNING.md；server.py 的 --data 与 --projects-root 参数优先于有效的环境变量默认值。

## 回收站清理（0.3.1）

- `POST /api/trash/delete-preview {entries:[{id,kind}]}` 预览所选批次；`{all:true}` 预览全部回收条目，不受列表搜索和分页影响。
- 返回 `{token,total,entries:[{id,kind,name,paths,warnings,error?}],paths,warnings,expires_in}`。存在 `error` 的条目不执行；默认展示实际文件位置与外部引用说明并确认；用户可在设置显式关闭确认。关闭确认不跳过后台预览校验，存在阻挡项仍展示原因。
- `POST /api/trash/delete {token}` 执行已确认快照，返回 `{deleted,failed:[{id,kind,name,error}],remaining}`。客户端不能自行提交磁盘路径。令牌有期限、仅使用一次；实际实体状态和磁盘内容变化时拒绝旧预览。
- 只有确认进入 Windows 回收站的文件才算成功，不提供永久删除后备。外部引用和外部 SKILL 保留原文件。失败批次保留回收记录；已清理批次不能通过旧恢复请求、刷新或同步自动复活。


## 0.3.1：设置、临时预览与项目库

- `GET /api/settings` 与 `PATCH /api/settings` 读取/更新六项设置：`confirm_delete`、`confirm_trash_delete`、`close_to_tray`、`autoplay_media`（布尔）；`default_view`（grid/list/board）、`default_sort`（updated/name/order）。默认确认删除、关闭到托盘、画廊/最近更新、不自动播放；未知键及类型错误拒绝，原子保存。bootstrap 附带 settings。
- `POST /api/external-open {paths:[绝对路径]}` 受会话令牌保护，返回 `{entries}`，仅注册会话临时 ID。`GET /api/external/ID` 返回元数据及只读 content；`GET /api/external-media/ID` 通过已验证文件句柄流式读取并支持 Range。仅受支持文件可读，不增加项目或复制文件，不提供写接口。预览 ID 会在后台重启或过期后失效。
- `GET /api/project-library` 返回 `{folders,projects,recent_ids,total}`；项目带 folder_id 和 last_opened。`POST /api/project-folders {name,parent_id?}` 创建逻辑分类；`PATCH /api/project-folders/ID {name?,parent_id?}` 改名或移动，拒绝循环及同级重名；`DELETE /api/project-folders/ID` 仅删除可见项目与子分类均为空的分类，历史归属置为未分类。
- `PATCH /api/project-library/PROJECT_ID {folder_id}` 归类（null 为未分类）；`POST /api/project-library/PROJECT_ID/visit {}` 记录最近打开，不改写项目磁盘目录。以上写接口沿用同源及会话令牌验证。

## 0.3.4 全局搜索交互边界

- `GET /api/search?q=关键词&limit=30&offset=0` 返回下表字段。仅接受 `q`、`limit`、`offset`，不接收磁盘路径、项目或分类参数；沿用 Host、Origin 和跨站请求校验。bootstrap 的 `capabilities.global_search` 为 `true`。
- `q` 最多 200 字符，禁止 NUL；按空白分隔最多 12 个关键词。空查询返回空结果且不扫描。`limit` 默认为 30，必须为正整数，最大按 50 处理；`offset` 默认为 0，范围为 0–100000。无效参数返回 400，不可信来源返回 403。
- 各类结果统一使用 Unicode casefold 后的字面子串匹配；全部关键词都必须命中，可分布在不同可搜索字段中。`night` 可以命中 `midnight`，`café` 可以命中 `CAFÉ`；不把关键词解释为 FTS 表达式、SQL 或通配符。

| 返回字段 | 含义 |
| --- | --- |
| `q` | 去除首尾空白的查询 |
| `results` | 当前页结果数组；每项结构见下文 |
| `total`、`total_exact` | 本次已找到的结果数量、是否可视为完整数量；不完整时 `total` 只是已找到的数量 |
| `limit`、`offset`、`has_more` | 实际页大小、偏移、已找到的结果中是否还有下一页 |
| `truncated`、`warnings` | 是否未完成全部扫描及说明；正常非空查询也会提示索引时效，因此不能仅凭 `warnings` 非空判断失败 |
| `scope` | `projects`、`items`、`skills`、`content_source` 四项范围与索引时效说明 |
| `scanned` | `projects`、`items`、`skills` 候选检查计数，以及实际读取的 `skill_bytes`；不是底层数据库扫描行数 |
| `elapsed_ms` | 本次搜索耗时，单位毫秒 |

结果共有 `type`（`project` / `item` / `skill`）、`id`、`project_id`、`project_name`、`name`、`category`、`folder_id`、`snippet`。文件结果额外有 `kind`；技能结果额外有 `source`，且项目字段为 null；项目结果的 `project_id` 等于自身 `id`，分类与文件夹字段为 null。结果不返回磁盘路径或完整正文。排序优先名称精确匹配，其次名称包含全部关键词，随后其他命中；同级按名称、类型、ID 排序。分页针对本次结果排序后切片，跨请求不提供冻结快照。

- 项目与文件候选每类最多 5000 个，SKILL 候选最多 2000 个；SKILL 单文件正文最多 1 MiB、单次累计最多 32 MiB。另有时间、数据库工作量和锁等待预算；触限、路径失效或记录变更时返回部分结果与原因，`truncated=true`、`total_exact=false`。
- 全局搜索跨所有项目名称/简介、文件名称/标签/备注及已索引正文（含提取的 DOCX 正文），以及已注册 SKILL 名称/描述和限额正文；不继承当前项目或分类过滤。
- 返回结果需显示来源、命中摘要和分页信息；超过扫描限额必须明确标记部分结果。未保存草稿不纳入索引，外部项目文件变化需要同步索引。
- 独立搜索窗口支持上/下选择、Enter 打开及 Esc 关闭；当前页面 Ctrl+F 行为保留。顶栏另提供全局搜索按钮，帮助位于设置左侧、设置最右。

## 0.3.5：截图、Markdown 图片与逻辑素材组

- 设置新增 `capture_enabled`（默认 true）与 `capture_hotkey`（默认 `Ctrl+Alt+Shift+S`）。快捷键需要至少两个不同的 Ctrl/Alt/Shift 修饰键和大写字母、数字或 F1–F24，排除 F12；关闭后台快捷键不关闭主动截图按钮。
- 原生桥接 `capture-context-request {requestId}` → `capture-context {requestId,projectId,itemId}` 锁定目标；仅接受同源页面、匹配 ID 与严格字段。5 秒未取得上下文时只尝试剪贴板。截图只在主动触发时读取鼠标所在单屏，最大 40000000 像素，无持续截图或剪贴板轮询。
- 原生 PNG 通过原有 `POST /api/upload?project=ID&category=references&name=文件名` 上传二进制，带新取得的会话令牌与同源头。`capture-result` 返回 `requestId,item,clipboardCopied,cancelled,error,clipboardError,saveError`；复制与保存独立报告。前端只在原项目/笔记/草稿及可编辑模式仍匹配、且没有保存中或输入法组合时插入 Markdown 草稿，不自动保存笔记。
- `GET /api/markdown-assets/link?note=ID&image=ID` 返回 `{relative_path,markdown,preview_url}`；仅为同项目已登记的独立 Markdown 与光栅图片生成相对引用，不改文稿。`GET /api/markdown-assets/image?note=ID&path=编码相对路径` 按安全文件句柄流式读取、支持 Range；拒绝越界、网络协议、UNC、回收对象、硬/软链接及超过 32 MiB 的图片。
- 编辑器 `create({imageResolver})` 只对普通相对路径图片调用回调，默认不加载图片；返回值必须是同源相对路由。`getSelection()` 返回原文 UTF-16 的 `{from,to}`（CRLF 计两个字符）；`insertText(text,from?,to?)` 是一次可撤销文本事务，保留原文换行。输入法组合拒绝插入，非法范围或超过实时编辑限额抛出错误。
- `GET /api/resource-groups?project=ID` 返回 `{groups,total}`，组摘要含 `id,project_id,name,revision,count,member_ids,categories,preview` 等字段。`GET /api/resource-groups/ID` 追加完整 `members`。`POST /api/resource-groups {project_id,name?,item_ids}` 创建组，至少两个同项目成员。
- `PATCH /api/resource-groups/ID {name,revision}` 改名；`POST` / `DELETE /api/resource-groups/ID/members {item_ids,revision}` 加入/移出；`DELETE /api/resource-groups/ID {revision}` 解散。写接口要求同源与令牌，修订号冲突返回 409。一素材只属于一组，每组最多 200 成员、每项目最多 500 组；组变更不搬动/删除文件或修改原分类与制作信息。

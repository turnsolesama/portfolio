# 项目、知识、运行与工作流登记

登记只建立导航和引用，不创建项目、运行或交付目录，不移动资产，不改 SQLite。登记须显式预览保存；开发验证使用临时目录。

## 读取与保存

Python 接口位于 `aihub.management`：

- `registry_snapshot(cfg)`：返回 `version/revision/projects/runs/workflows/knowledge/templates/warnings`。
- `registration_preview(cfg, kind, record)`：`kind` 为 `project/run/workflow/knowledge`；返回规范化 `record`、被替代的 `previous`、`revision`、10 分钟有效的 `token/expires_at/warnings`。预览不写盘。
- `registration_save(cfg, token)`：只能保存同进程预览，重新检查路径和当前证据，返回 `saved/kind/record/revision`。令牌绑定根目录、存储位置和 revision，成功后不可复用；配置改变或过期需重新预览。
- `registration_backups(cfg)`：列出上一份有效登记的摘要 ID、修改时间和记录数量，不接收路径。
- `registration_restore_preview(cfg, backup_id)`：选择上述 ID 生成恢复预览，仍由 `registration_save` 执行。恢复重新校验全部引用，不能用任意文件作为备份。
- `evidence_preview(cfg, {workflow_path, dependencies: [绝对文件路径], outputs: [绝对文件路径]})`：只计算工作流 SHA-256，并获取依赖/输出 `path,size,mtime_ns`。清单各最多 100 项，可为空用于先获取工作流哈希。不自动补日期或通过结论，不读取/解码依赖与出图内容。
- `read_report(cfg, generated_dir, path)`：白名单与打开句柄身份检查后读取正文；原 API 应使用此接口，不在授权路径检查后自行裸读文件。

存储固定在程序 `config.DATA_DIR/registry.json`，不接受网页提供其他写入路径；每次成功保存前将有效原文件原子备份到 `registry.previous.json`。JSON 临时文件写入、flush/fsync 后替换，写前再次比对 revision。主文件损坏时只读有效备份并提示，不自动覆盖损坏文件；下一次经预览保存可恢复主文件。文件上限 4 MiB，各类上限 2000 项，读写使用相同结构校验。

登记绑定选定 AI 根目录；换电脑或换根目录后须重新核对路径，不将旧根目录登记直接套用。

## 项目

必填：`id/name/type/root/current_doc/delivery`。ID 为 1–80 位英文字母、数字、下划线或连字符，首位须字母/数字。类型为 `creative/training/tool`。

可选：`description`（当前说明）、`assets`（引用目录列表）、`outputs`（输出目录列表）、`mapping`（角色到项目内相对目录）、`template`。`delivery` 为唯一正式交付目录，可以尚未创建；同一目录不能归属两个项目。同一项目根也不能重复登记。

- 允许项目根：`40_Projects`、`50_Training/Projects`、`10_Apps` 下的具体项目。应用专用目录可明确登记，保留其内部结构。
- `current_doc` 须为项目根内已有的 `.md/.txt/.html` 正文，作为唯一当前说明。
- `assets` 可引用项目内部、`30_Assets`、`20_Models` 或训练项目；`outputs` 可引用项目内或 `70_Output`，不改变文件归属。
- `mapping` 只接入已有相对结构，不把影视专用结构改排成训练 Runs。

模板由 snapshot 返回：`generic` 通用项目（创作/工具）、`film` 影视创作、`training` 模型训练、`external` 已有应用结构。当前模板版本为 `1`；未选择时使用 `external/applicable=false`。选择模板代表登记其适用性，不自动创建结构。

项目导航发现 `40_Projects` 与 `50_Training/Projects` 的直接子目录；工具只发现带 `项目说明.md/README_项目.md/PROJECT.md` 的直接子目录、同时含安全 `AGENTS.md + README.md` 的一级开发候选，或明确登记的目录。仅有普通 README 的安装应用不会列为开发项目；嵌套依赖/环境中的 marker 不扫描。创作与训练兼容原 `README_训练项目.md` 和 `README.md`。未登记项明确显示“未登记”，不推断项目完成度或套用模板。原 `report/datasets/runs/weights/families/weight_count` 字段保留；`current_doc` 优先作为项目说明，专项历史报告继续可查。

## 运行与输出归属

运行记录：`id`、`project_id`（可空）、`output_dir`、`workflow_path`、`workflow_sha256`、`models`（模型标识列表）、`seed`（整数或 null）、`validation_status`。

有项目的运行进入 `70_Output/Projects/<项目ID>/<运行>`、项目内部或该项目明确登记的输出映射；无项目测试进入 `70_Output/Tests/Unassigned/<日期_任务>`。必须指定具体运行目录，同一输出目录不能被多个运行重复认领。登记不创建目录；`pending` 可登记计划位置。正式交付位置仍以项目记录为准。

`path_checked` 要求运行目录和工作流文件实际存在、类型正确，工作流哈希相符。通过状态必须引用相同工作流版本的验证登记，而且输出证据必须在此次运行目录中。

读取时保留原 `validation_status`，使用 `effective_validation_status/validation_label/validation_reason` 展示现场有效状态。工作流或输出失配后，原当前通过记录降为历史，不继续显示当前通过；项目页 `output_runs` 同步重算。

## 工作流四种状态

登记记录：`{id,path,state,validation}`。

| state | 含义 |
|---|---|
| `pending` | 尚未验证，不推断路径或执行结果 |
| `path_checked` | 文件路径已检查，不代表执行过 |
| `historical_passed` | 保留有明确版本和日期的历史执行证据 |
| `current_passed` | 用户登记了执行通过，且当前文件与依赖/输出证据匹配 |

两种通过状态必须提供 `validation.date`（非未来 YYYY-MM-DD）、`workflow_sha256`、非空 `dependencies` 与 `outputs`、可选 `note`。依赖和输出每条为 `{path,size,mtime_ns,sha256?}`；mtime_ns 使用十进制字符串传输和保存，避免 JavaScript 数值精度丢失（兼容旧整数输入）；工作流必须是工作流区或已登记项目内的 JSON。依赖限定模型、工作流、应用或已登记项目范围；输出限定 `70_Output` 或项目范围。

path_checked 可不填执行证据；若用户已填写检查日期、工作流哈希、说明或快照，保存时保留。对应哈希发生变化时显示待验证并保留原路径检查记录，不提升为执行通过。

工作流哈希绑定版本；依赖/输出默认以大小和修改时间快照核对，避免读取大型权重或解码图片。这是统计快照，不宣称等价于完整内容哈希；小文件可显式提供 SHA-256，单次哈希限 64 MiB。系统只核对证据，不自动运行工作流，也不把文件夹名称、旧 README 口号或路径修正版当成执行成功。

当前工作流哈希、依赖或输出失配时，`verification_state` 降为历史；证据结构不完整则为待验证。原日期和证据不被改写。旧 `status/copy/changes/generation_status/counts` 字段保留兼容用途；新版 UI 必须用 `verification_state/verification_label/current_match/verification_reason/validation` 和汇总 `verification_counts`。旧 `reviewed_copy` 仅是历史静态路径记录。

## 知识与正文索引

保留管理区顶层、管理报告、原专项项目报告和终端生成报告；增加项目当前说明、`80_Knowledge/Guides` 顶层正文。深层知识文件只通过显式知识登记 `{id,path,title,description}` 或 `80_Knowledge/manifest.json` 白名单进入：

```json
{"version":1,"documents":[{"path":"Guides/Topic/lesson.md","title":"教程标题"}]}
```

manifest 路径必须为知识区内相对路径，不接受 `..` 或绝对路径。默认不递归遍历教程构建材料。正文仅允许 md/txt/html、单文件最多 2 MiB；API 默认返回前 400 KiB。

所有路径先检查原始拼写、上级路径、Windows reparse point、符号链接和范围再访问；私密配置、环境文件、缓存、依赖和构建材料不能进入文本索引，硬链接正文也不进入。打开正文后再次核对句柄与路径身份。登记文件和备份不接受链接，不读任意指定的私人 JSON。

## 验证

`python -B -m unittest discover -s tests -p test_management_registry.py -q`

覆盖只读预览、保存并发与过期、项目发现/类型/唯一交付/结构映射、知识白名单、硬链接与实际 Windows junction 逃逸、reparse 标志、损坏备份回退与预览恢复、2000 项读写一致限制、完整验证证据、文件变化降级、运行归属和前后状态一致、证据收集只 stat 依赖/输出。所有文件均为临时虚构数据，不操作正式模型或图片。

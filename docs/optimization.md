# 多渠道长任务、身份、记忆与 MCP 改造

## 已定位的问题

- handler 原先直接运行主 Agent，没有调用 dispatcher；06/07 脚本是独立入口，所以行为不同。
- 飞书接收端只处理 text，富文本 post 被忽略，坏内容被静默吞掉。现在统一解析并增加接收、入队、阶段、完成和失败日志。
- 长连接进程自行执行 Agent；Webhook 使用进程内后台任务，都未接现有 arq 队列。同步发送 SDK 还会阻塞事件循环。现在接收进程入队，worker 执行并主动回复，HTTP 回调只等待入队。
- arq 默认 300 秒超时改为可配置的 1800 秒。同会话通过 Redis 锁串行执行。完成的回复缓存后再投递，发送失败重试不再执行 Agent。投递采用至少一次语义，部分发送后失败可能重复已发送片段。
- seed_project 循环缩进导致只复制最后一个目录。现在上传必要源码、测试、技能、约定与锁文件，排除隐藏文件和缓存，不复制 .env。沙箱镜像预装完整依赖，测试只使用占位凭据。
- Compose 的 worker/feishu 未统一内部 Redis 地址，现在已补齐；接收端不再创建数据库池和沙箱。
- Web 原先匿名调用且信任客户端 source/user_id。现在普通 /issues、/jobs、/webhook/generic 要求登录，写请求校验 CSRF。/issues/secure 保留 API Key 方式，使用独立集成命名空间；默认演示 Key 已移除。

这些代码问题可以解释任务丢失、调度差异和超时。2026-10-11 已在真实容器中复现 512 MB 沙箱 OOM，详见下文；历史任务仍不能仅凭退出码 137 判定原因。

## 调度与身份

所有生产渠道通过 handle_message 进入 dispatcher：聊天直接回答，不创建开发沙箱；研究按需 planner → researcher；开发按需 planner/researcher，固定 coder → tester → reviewer。审查不通过最多再修复一轮。每个角色由代码直接调用，阶段独立线程，共享沙箱，仅交接有界摘要。角色不能再次调用 task；只读角色在模型工具绑定与实际执行两处受限。Docker reviewer 使用移除写权限的副本，Daytona reviewer 使用工具层只读约束。

Web 首页分别提供注册和登录界面，注册成功后返回登录界面。用户名 3–64 位，密码 6–128 字符。通过 Docker 启动时请打开 http://localhost:18700/；直接打开 web/index.html 会显示服务入口提示，需要进入 HTTP 服务后使用账户。Postgres 的 ivyclaw_users 表使用独立盐的 scrypt 验证值；Redis 保存随机会话令牌哈希对应的记录。Cookie 为 HttpOnly、SameSite=Lax，可退出撤销，默认有效期 7 天。登录/注册限制尝试频率。

页面本地记录按服务端用户 ID 分开。登录时同步服务端会话索引，切换时按需读取全文；当前浏览器的未完成 job_id 保留，刷新后继续查询。Web 使用 /jobs，避免同步长请求超过 Gunicorn 的 120 秒超时。任务结果只允许提交者查询。/webhook/generic 保留同步兼容能力，长任务应改用 /jobs。

接口：POST /auth/register、POST /auth/login，JSON 为 username/password；GET /auth/me 返回 userId/username/csrfToken；POST /auth/logout 撤销会话。任务/偏好写请求带 Cookie 与 X-CSRF-Token。原有 API 字段保留兼容。

CLI 使用已有 Web 账户，密码交互输入：

```powershell
uv run python -m channels.cli --username alice --session work "任务描述"
```

## 记忆

app/memory.py 复用已有 LangGraph Store，生产使用 Postgres。命名空间包含租户、身份来源和用户 ID；Web/API 登录账户共享记忆，飞书 open_id 和 API Key 集成不会自动绑定 Web 账户。

- 短期：同会话最近六轮，有界注入；聊天 checkpoint 仅保留本轮。
- episodic：每轮请求、结果和时间单独保存。召回索引为最近 100 轮的有界摘要，Web 单会话显示最近 200 轮，旧 episodic 完整记录仍在 Store。列表与召回读取独立小索引，避免每次加载所有对话全文。
- semantic：稳定事实的 key/value、原文证据和时间，同 key 更新。
- preferences：语言、回复风格、协作习惯、技术栈、时区、是否提取事实。

每轮先保存历史和经历，再尽力提取稳定信息。模型提取失败不会丢失完成的对话。提取只读取当前用户原文，验证 evidence 为原文片段，不把密码/密钥/令牌存为 semantic 事实。关闭 rememberFacts 会停止自动事实和偏好提取，仍保存历史与经历。完整对话可能包含用户主动输入的敏感文本，聊天不能当作凭据保险库。

当前召回是有界关键词匹配与时间排序，尚未配置 embedding/向量索引。semantic 指事实类型，不表示已有向量检索。自动提取取决于模型判断，用户可在 Web“偏好与记忆”查看并直接修正偏好。

账户接口：GET/PATCH /me/preferences、GET /me/memory、GET /conversations、GET /conversations/{id}。新字段使用 camelCase。没有跨渠道自动身份绑定，不能仅凭客户端声明的 ID 合并账户。

## 八个 MCP 工具

| 工具 | 能力 |
| --- | --- |
| inspect_workspace | 查看当前沙箱目录与初始化结果 |
| read_project_file | 有界读取项目文本，拦截越界和隐藏路径 |
| search_workspace | 检索已有实现，返回文件与行号 |
| run_project_tests | 仅在沙箱 tests 目录执行 pytest，保留退出码 |
| check_python_syntax | AST 检查，不执行源码 |
| recall_user_memory | 当前用户事实、经历和偏好召回 |
| remember_user_fact | 根据当前用户原文保存事实 |
| set_user_preference | 根据当前用户原文更新偏好 |

tools/project_mcp.py 使用 [官方 MCP Python SDK](https://py.sdk.modelcontextprotocol.io/v1/)。运行时建立请求专属双向内存协议会话，通过 initialize/list_tools/call_tool 和 LangChain MCP adapter 加载工具。工具参数不能切换用户或沙箱；realpath 校验在沙箱内执行。会话覆盖角色执行并在结束时关闭。IVC_MCP_SERVERS 中的外部工具也已实际传给 Agent。

独立受信任的本地客户端可用 stdio：

```powershell
uv run python -m tools.project_mcp --user-id local-owner --user-text "我使用 Python，偏好详细解释"
```

stdio 创建独立沙箱与 CLI 记忆命名空间。user-text 固定本次记忆写入的证据来源，省略时写入不能通过证据检查。user-id 是可信本地启动配置，不是公开多用户认证方式。本次未暴露匿名 HTTP MCP 服务。

## 配置与启用

现有 .env 可设置：

```dotenv
IVC_TASK_TIMEOUT_SECONDS=1800
IVC_STAGE_MODEL_CALL_LIMIT=40
IVC_WORKER_MAX_JOBS=1
IVC_SANDBOX_MEM_LIMIT=1g
IVC_WEB_WORKERS=2
IVC_JOB_RESULT_TTL_SECONDS=604800
IVC_SESSION_TTL_SECONDS=604800
IVC_SESSION_COOKIE_SECURE=true
IVC_ALLOWED_ORIGINS=[]
```

本地 HTTP 开发用 session_cookie_secure=false；HTTPS 生产用 true。同源无需 CORS，跨域域名须加入 allowed origins。旧匿名客户端须登录，集成端可配置 IVC_GATEWAY_API_KEYS 并使用 /issues/secure。

飞书长连接需要 App 凭据和运行中的 worker。Webhook 明文事件需要 verification token；当前未增加 encrypted 事件解密，使用加密回调需另行接入 SDK 解密验证。长连接无需 Webhook token。Redis 必须配置可靠持久化；已入队不等于已开始执行。

Docker 服务和沙箱按 uv.lock 安装依赖。**旧沙箱镜像需要重建**，否则没有完整项目测试依赖：

```powershell
docker build -f sandbox/Dockerfile -t ivy-sandbox:latest .
docker compose -f docker-compose.prod.yml up -d --build web worker feishu
```

两份 Dockerfile 的依赖安装步骤使用 BuildKit 缓存挂载、120 秒下载超时、5 次 HTTP 重试和最多 4 个并发下载，适用于依赖下载慢或不稳定的环境。缓存挂载可在构建重试时复用已完成的下载，UV_LINK_MODE=copy 避免跨文件系统硬链接。仍无法下载时，应检查服务器对 uv.lock 中 files.pythonhosted.org 地址的连通性；运行容器的 .env 不会自动成为镜像构建参数。不要使用 --no-cache 或清理构建缓存来处理下载超时。

2026-10-11 按用户要求已构建镜像并启动本地 Docker Compose 服务进行联调，未发布到远程环境。账户表使用事务 advisory lock 串行创建，避免 Gunicorn 多进程首次建表冲突；记忆复用已有 Store 表。

## 验证与限制

```powershell
uv run python -m compileall -q app agent middleware scripts tools channels api gateway tasks sandbox
uv run pytest -q
```

回归覆盖长消息、Unicode 分片、五角色顺序、只读工具拦截、认证/CSRF、任务归属、记忆隔离/恢复/提取失败、真实 MCP 调用/路径越界/pytest 成败、队列幂等与投递重试。Web JavaScript 用 Node --check 验证。

## 2026-10-11 真实联调记录

- 历史 Web 与沙箱退出码 137，但 OOMKilled=false，且 Postgres、Redis 在前一秒停机。不能将这批历史退出直接归因为 OOM。
- 真实 512 MB 沙箱跑 pytest 时达到 536870912 字节，memory.events 中 oom=1、oom_kill=1，pytest 子进程返回 -9，Docker 记录 oom 事件。常驻 sleep 仍存活，说明只检查容器 OOMKilled 会漏掉子进程 OOM。
- 最终 1 GB 沙箱完成全部 59 项测试，峰值 719261696 字节（约 686 MiB），oom_kill=0；真实 MCP initialize/list_tools/call_tool、长文件读取、语法检查和只读 reviewer 副本均通过。报告位于 logs/live_container_check_512m.json 与 logs/live_container_check_final.json。
- DockerSandbox 原先截断 execute 的底层输出，破坏大文件的 JSON 协议，引发 read_file 的 unexpected server response 和模型循环。现在保持文件协议完整，在命令工具交付模型时限制输出；阶段最多调用模型 40 次。sh -lc 还会覆盖镜像 PATH，改为 sh -c 保留预装虚拟环境。
- 审查角色猜测调用 execute 时，工具被拒绝且返回可恢复错误，角色继续用只读工具审查。禁止的命令与文件修改不会执行。
- 长任务中的“不修改宿主机、在沙箱开发”曾被模型误判成纯研究，已明确分类优先级；用真实 2175 字消息验证分类为 development、complex、need_research=true。分类保留超长输入的首尾，避免末尾交付要求丢失。
- 实际 HTTP 联调完成两账户注册、匿名 401、CSRF 拒绝、Postgres 记忆隔离与退出撤销。临时联调账户未用于真实用户数据。
- Windows 当时只余约 0.9 GB 物理内存和 1.3 GB 可用虚拟内存，与飞书截图告警一致。WSL/Docker 最大内存约 8 GB。Web 改为默认 2 个进程减少约 0.6 GB 占用；并发任务须结合宿主机内存配置，不能只提高单沙箱额度。
- worker 默认同时执行一个任务（与 sandbox_pool_size 取较小值），避免四个任务与 reviewer 副本叠加超过宿主机预算；有更大内存的部署可显式提高 IVC_WORKER_MAX_JOBS。

飞书 150 字任务已通过真实长连接接收、入队、五角色调用及失败通知链路。2175 字任务从真实飞书消息 API 读取并显式重放，完整执行五角色和一轮返工，约 237 秒后将 4290 字结果真实投递回飞书。该任务生成的示例代码最终 approved=false，不能称为开发验收通过；流程和投递通过且没有 OOM，沙箱峰值 581304320 字节。**重放不能等同新长连接入站验证**。新的长入站结果仍需以实际任务日志为准。上线验收应检查：长 post 有接收与 job 日志；复杂开发任务出现各阶段日志；长回复完整分片；重新登录能恢复历史；不同账户无法读取彼此的 job_id/conversation_id。

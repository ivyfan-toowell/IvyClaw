# IvyClaw

IvyClaw 是一个面向软件研发任务的多智能体 AI Agent 工程系统。

项目基于 DeepAgents / LangGraph 构建多智能体协作流程，并结合 FastAPI、PostgreSQL、Redis、ARQ、Docker 等组件，实现从任务接入、智能体协作、工具调用、沙箱执行，到异步任务、人工审批、可观测性和生产部署的一套完整工程链路。

项目重点不是单纯调用大模型，而是探索如何将 AI Agent 从“能够对话”进一步工程化为一个具备任务编排、状态持久化、工具执行、安全隔离和生产运行能力的系统。

---

## ✨ 核心能力

### 多智能体协作

IvyClaw 将复杂研发任务拆分给不同角色的 Agent：

- **Planner**：分析需求并制定任务计划
- **Researcher**：搜索资料、补充外部信息
- **Coder**：实现和修改代码
- **Tester**：执行测试并反馈问题
- **Reviewer**：进行最终代码审查

通过 Dispatcher 对任务复杂度进行判断，并组织不同 Agent 完成研发闭环。

典型流程：

```text
用户任务
   ↓
主 Agent / Dispatcher
   ↓
Planner
   ↓
Researcher（按需）
   ↓
Coder
   ↓
Tester
   ↓
Reviewer
   ↓
最终结果
🧠 多模型路由

项目支持根据不同 Agent 的任务特点选择不同能力等级的模型。

例如：

Planner / 主 Agent
        ↓
   Strong Model

Researcher
        ↓
    Cheap Model

Coder / Reviewer
        ↓
   Strong Model

Tester
        ↓
 Standard Model

模型通过统一的 LLM Router 管理，使 Agent 与具体模型供应商解耦。

当前主要使用 OpenAI Compatible API，可接入 Qwen 等兼容模型。

🛠️ 工具系统

Agent 可以通过工具完成真实的软件研发任务，包括：

Git 操作
pytest 测试
Python 命令执行
Web 搜索
Tavily / Exa
MCP Tool
文件操作
沙箱代码执行

不同 Agent 只获得完成自身任务所需的最小工具集，降低工具误用风险。

🧩 Skills 能力

项目支持通过 skills/ 为 Agent 提供可复用的软件工程能力，例如：

skills/
├── fastapi-endpoint/
├── requirements-clarification/
├── systematic-debugging/
├── test-driven-development/
├── unit-test/
└── verification-before-completion/

Skills 用于向 Agent 提供稳定的工程流程和任务规范。

🏗️ 沙箱执行

IvyClaw 为 Agent 提供隔离的代码执行环境。

当前支持：

Docker Sandbox
Daytona Sandbox

主要能力包括：

独立工作目录
Python / pytest / Git 执行
沙箱复用
TTL 生命周期管理
资源限制
沙箱池
运行时切换

生产环境默认使用 Docker Sandbox，并支持进一步接入 gVisor / Kata 等隔离运行时。

💾 状态持久化

项目使用：

PostgreSQL：持久化 Agent 会话、任务状态等数据
Redis：缓存、队列、限流及异步任务基础设施

通过 LangGraph Checkpointer / Store 保留 Agent 执行上下文，使任务能够跨请求持续运行。

⚡ 长任务异步化

对于耗时较长的 Agent 任务，IvyClaw 使用 ARQ + Redis 实现异步任务队列。

基本流程：

客户端
   ↓
FastAPI
   ↓
创建 Job
   ↓
Redis Queue
   ↓
ARQ Worker
   ↓
Agent 执行任务
   ↓
保存结果
   ↓
客户端查询 Job 状态

支持：

Job ID
queued / running / completed 等任务状态
后台 Worker
异步结果查询
Job 幂等
👤 Human-in-the-Loop

针对高风险操作，项目支持 Human-in-the-Loop（HITL）。

例如：

Agent 请求执行高风险操作
        ↓
interrupt
        ↓
等待人工确认
        ↓
approve / reject
        ↓
Command(resume)
        ↓
Agent 继续执行

避免 Agent 在无人确认的情况下直接执行危险操作。

🌐 多渠道接入

IvyClaw 将用户请求统一抽象为 InboundMessage，从而支持多个入口接入同一套 Agent 系统。

当前实现：

CLI
Web API
Feishu
Feishu WebSocket
Feishu Webhook
Generic Webhook

整体结构：

CLI
Web
Feishu
Webhook
   ↓
Channel Adapter
   ↓
InboundMessage
   ↓
handle_message()
   ↓
IvyClaw Agent
🔐 API 网关与多租户

项目实现基础的 API Gateway 机制，包括：

API Key 鉴权
Tenant 识别
多租户隔离
Rate Limit
Idempotency
请求上下文
Audit Log

请求首先通过网关鉴权，再进入 Agent 服务。

Client
   ↓
API Key
   ↓
Gateway
   ↓
Tenant
   ↓
Rate Limit / Context
   ↓
Agent Service

当前仓库中的 Key / Tenant 为演示配置，生产环境应使用数据库或专门的身份认证系统管理。

🔄 容错与稳定性

IvyClaw 在基础设施层实现了多种稳定性机制：

Retry
Timeout
Fallback
Idempotency
Concurrency Control
Rate Limit
Redis Connection Pool
PostgreSQL Connection Pool
Sandbox Pool

用于提升 Agent 系统在高并发和外部服务异常情况下的可靠性。

📊 可观测性

项目集成：

LangSmith
Prometheus
Grafana
Structured Logging
Metrics
Audit Log

用于观察：

Agent 调用链
模型调用情况
请求量
延迟
并发
错误
Token / Cost
Worker 状态
🧪 Evaluation & Testing

项目包含 Agent 评估与测试能力：

eval/
tests/
loadtest/

包括：

pytest
Agent Runtime Test
Code Cases
Execution Scorer
LLM Judge
Baseline Evaluation
Locust Load Test

通过测试、评估和压测形成从开发到生产验证的闭环。

🐳 部署

项目支持 Docker 化部署。

生产环境主要服务包括：

Web
Worker
Feishu
PostgreSQL
Redis
Prometheus
Grafana

整体结构：

                ┌──────────────┐
                │    Client    │
                └──────┬───────┘
                       │
                ┌──────▼───────┐
                │   FastAPI    │
                └──────┬───────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
   PostgreSQL        Redis         ARQ Worker
        │              │              │
        └──────────────┼──────────────┘
                       │
                ┌──────▼───────┐
                │ IvyClaw Agent│
                └──────┬───────┘
                       │
                 Docker Sandbox
📁 项目结构
IvyClaw/
├── agent/              # 主 Agent 与 Dispatcher
├── api/                # FastAPI API
├── app/                # Web 应用
├── channels/           # CLI / Feishu / Webhook
├── concurrency/        # 并发控制
├── deploy/             # 部署与 Prometheus 配置
├── eval/               # Agent 评估
├── gateway/            # API 鉴权与限流
├── infra/              # 数据库、Redis、模型路由等基础设施
├── loadtest/           # Locust 压测
├── middleware/         # 请求中间件
├── obs/                # Metrics 与可观测性
├── profiles/           # 模型与 Agent Profile
├── resilience/         # 稳定性与容错
├── sandbox/            # Docker / Daytona 沙箱
├── scripts/            # 测试与演示脚本
├── skills/             # Agent Skills
├── subagents/          # 子 Agent 定义
├── tasks/              # ARQ 异步任务
├── tests/              # 自动化测试
├── tools/              # Agent 工具
├── web/                # Web UI
├── Dockerfile
├── docker-compose.prod.yml
├── pyproject.toml
└── .env.example
🚀 Quick Start
克隆项目
git clone https://github.com/ivyfan-toowell/IvyClaw.git
cd IvyClaw
配置环境变量

复制示例配置：

cp .env.example .env

Windows PowerShell：

Copy-Item .env.example .env

然后根据自己的环境填写：

IVC_API_KEY=your_api_key_here
IVC_POSTGRES_URL=postgresql://user:password@localhost:5432/ivyclaw
IVC_DATABASE_URL=postgresql://user:password@localhost:5432/ivyclaw
IVC_REDIS_URL=redis://localhost:6379/0

不要将真实 .env 上传至 GitHub。

安装依赖

项目使用 uv 管理 Python 环境：

uv sync
启动 API
uv run uvicorn api.app:app --reload --port 8000

启动后访问：

http://localhost:8000/docs

查看 FastAPI Swagger API 文档。

启动 ARQ Worker
uv run arq tasks.worker.WorkerSettings
启动飞书长连接
uv run python -m channels.feishu_ws
Docker 部署
docker compose -f docker-compose.prod.yml up -d --build
🔒 Security

本项目不会将真实密钥写入代码仓库。

敏感配置统一通过 .env 管理，例如：

LLM API Key
LangSmith API Key
Feishu App Secret
PostgreSQL Password
Gateway API Key

仓库只保留 .env.example 作为配置示例。

🎯 项目目标

IvyClaw 主要用于探索 AI Agent 的工程化实践，包括：

LLM
 ↓
Agent
 ↓
Multi-Agent
 ↓
Tools
 ↓
Sandbox
 ↓
Persistence
 ↓
Async Task
 ↓
Gateway
 ↓
Observability
 ↓
Evaluation
 ↓
Production Deployment

希望通过这个项目，将 AI Agent 从 Demo 逐步推进到具备完整软件工程能力的服务系统。

📌 Status

IvyClaw 仍在持续迭代中。

目前已完成多智能体协作、工具系统、模型路由、沙箱执行、持久化、多渠道接入、异步任务、HITL、API 网关、可观测性、评估、压测与 Docker 化部署等核心模块。

后续将继续优化：

Agent 调度策略
RAG / Knowledge Base
更完善的 Tenant 管理
CI/CD
Agent Evaluation
Production Security
Web UI
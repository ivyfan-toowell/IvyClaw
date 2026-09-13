# 🦞 IvyClaw

> **面向软件研发任务的多智能体 AI Agent 工程系统**

IvyClaw 是一个基于 **DeepAgents / LangGraph** 构建的软件研发智能体系统。  
项目围绕 AI Agent 的工程化落地，实现了多智能体协作、工具调用、代码沙箱、状态持久化、异步任务、Human-in-the-Loop、多渠道接入、网关鉴权、可观测与生产部署等能力。

它的目标不只是让大模型“能够对话”，而是让 Agent 真正具备：

**任务规划 → 资料检索 → 代码实现 → 自动测试 → 代码审查 → 安全执行 → 持续运行**

的完整软件研发能力。

---

## 🧰 Tech Stack

`Python` · `DeepAgents` · `LangGraph` · `FastAPI` · `PostgreSQL` · `Redis` · `ARQ` · `Docker` · `Prometheus` · `Grafana`

---

## ✨ Highlights

- 🤖 **多智能体协作**：Planner / Researcher / Coder / Tester / Reviewer 分工完成研发任务
- 🧠 **多模型路由**：根据 Agent 角色和任务复杂度选择不同模型档位
- 🛠️ **真实工具调用**：支持 Git、pytest、Web Search、MCP 等工具
- 📦 **安全沙箱执行**：通过 Docker / Daytona 隔离运行 Agent 生成的代码
- 💾 **状态持久化**：PostgreSQL + LangGraph Checkpointer / Store 保存任务上下文
- ⚡ **长任务异步化**：Redis + ARQ Worker 处理耗时 Agent 任务
- 👤 **Human-in-the-Loop**：高风险工具调用支持人工审批与恢复执行
- 🌐 **多渠道接入**：CLI、Web API、飞书 WebSocket、Webhook 等统一接入
- 🔐 **网关与多租户**：API Key、Tenant、限流、幂等、审计等基础治理能力
- 📊 **可观测与评估**：LangSmith、Prometheus、Grafana、自动化测试与 Agent Evaluation

---

## 🏗️ Architecture
下图展示了 IvyClaw 从用户接入、网关治理、多智能体编排、工具调用、沙箱执行、状态持久化、异步任务到可观测与部署的整体架构。

![IvyClaw Architecture](docs/images/ivyclaw-architecture.png)

```mermaid
flowchart TD
    U[User / Client] --> G[API Gateway]

    G --> C[Channel / FastAPI]
    C --> D[Dispatcher]

    D --> P[Planner]
    P --> Q{Need Research?}

    Q -->|Yes| R[Researcher]
    Q -->|No| CO[Coder]
    R --> CO

    CO --> T[Tester]
    T --> RV[Reviewer]
    RV --> O[Final Response]

    D <--> PG[(PostgreSQL)]
    D <--> RD[(Redis)]

    CO --> SB[Docker / Daytona Sandbox]

    RD --> W[ARQ Worker]
    W --> D

    D --> OBS[LangSmith / Prometheus / Grafana]
```

### Agent Workflow

```text
User Request
      ↓
   Gateway
      ↓
  Dispatcher
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
Final Response
```

---

## 🚀 What IvyClaw Solves

传统 LLM 应用通常只完成一次模型调用，而 IvyClaw 将研发任务拆解为一个可以持续执行的 Agent Workflow：

```text
理解需求
   ↓
任务规划
   ↓
信息检索
   ↓
代码实现
   ↓
沙箱执行
   ↓
自动测试
   ↓
代码审查
   ↓
结果返回
```

同时通过持久化、异步任务、HITL、限流、监控和容错机制，使整个 Agent 系统具备进一步走向生产环境的基础能力。

---


⚡ Quick Start

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

## 🧠 Agent Core Capabilities

### Multi-Agent & Model Routing

IvyClaw 根据不同 Agent 的职责和任务复杂度进行模型路由：

| Agent | 主要职责 | 模型档位 |
| --- | --- | --- |
| Main Agent / Planner | 任务理解、规划与决策 | Strong |
| Researcher | 信息检索与资料整理 | Cheap |
| Coder | 代码实现与修改 | Strong |
| Tester | 测试执行与问题定位 | Standard |
| Reviewer | 最终代码审查 | Strong |

模型由统一的 LLM Router 管理，使 Agent 与具体模型供应商解耦，并支持 OpenAI Compatible API。

### Tool Calling

不同 Agent 按职责获得最小工具集，可调用真实的软件工程工具：

- Git：查看和操作代码版本
- pytest：执行自动化测试
- Python / Shell：运行开发命令
- Web Search：Tavily / Exa 信息检索
- MCP：接入外部工具与服务
- File Tools：读取和修改工作区文件
- Sandbox：隔离执行 Agent 生成的代码

这种最小工具授权方式可以减少不必要的工具调用和误操作风险。

### Skills

项目通过 `skills/` 为 Agent 提供可复用的软件工程流程：

```text
skills/
├── fastapi-endpoint/
├── requirements-clarification/
├── systematic-debugging/
├── test-driven-development/
├── unit-test/
└── verification-before-completion/
```

Skills 用于沉淀需求澄清、调试、测试驱动开发和任务完成前验证等工程规范。

## ⚙️ Agent Runtime & Execution

### Sandbox Execution

IvyClaw 为 Agent 提供隔离的代码执行环境，支持：

- Docker Sandbox
- Daytona Sandbox
- Python / pytest / Git 命令执行
- 独立工作目录
- 沙箱复用与生命周期管理
- CPU / Memory / PID 等资源限制
- Sandbox Pool 并发管理

生产环境默认使用 Docker Sandbox，并预留 gVisor / Kata 等更强隔离运行时的扩展能力。

### Persistence

项目使用 PostgreSQL 与 Redis 作为 Agent 运行基础设施：

- **PostgreSQL**：保存 Checkpointer / Store、会话状态及持久化数据
- **Redis**：缓存、限流、任务队列及运行时状态

LangGraph Checkpointer / Store 用于保存 Agent 执行上下文，使任务能够跨请求持续运行。

### Async Jobs

耗时较长的 Agent 任务通过 Redis + ARQ 异步执行：

```text
Client
  ↓
FastAPI
  ↓
Create Job
  ↓
Redis Queue
  ↓
ARQ Worker
  ↓
Agent Runtime
  ↓
Persist Result
  ↓
Query Job Status
```

支持 Job ID、任务状态查询、后台 Worker、幂等提交与结果获取。

### Human-in-the-Loop

对于删除、破坏性修改等高风险操作，IvyClaw 支持人工审批：

```text
Agent requests risky action
          ↓
       Interrupt
          ↓
    Human Approval
       ↓       ↓
    Approve   Reject
       ↓
 Command(resume)
       ↓
Agent continues
```

通过 HITL 将高风险工具调用从全自动执行转为可人工控制的执行流程。

## 🌐 Service Access & Gateway

### Multi-Channel Access

IvyClaw 将不同入口统一抽象为 `InboundMessage`，使多个渠道可以复用同一套 Agent 处理逻辑。

当前支持：

- CLI
- Web API
- Feishu WebSocket
- Feishu Webhook
- Generic Webhook

整体流程：

```text
CLI / Web / Feishu / Webhook
            ↓
      Channel Adapter
            ↓
      InboundMessage
            ↓
      handle_message()
            ↓
       IvyClaw Agent
```

### API Gateway & Multi-Tenant

项目实现了基础的服务治理能力：

- API Key 鉴权
- Tenant 识别与隔离
- Rate Limit
- Idempotency
- Request Context
- Audit Log

请求在进入 Agent Runtime 之前，会先经过网关层完成身份识别和基础治理。

```text
Client
  ↓
API Key
  ↓
Gateway
  ↓
Tenant Context
  ↓
Rate Limit / Idempotency / Audit
  ↓
Agent Service
```

当前仓库中的 Key / Tenant 仅作为演示配置，生产环境应接入数据库或专门的身份认证系统。

### Resilience

IvyClaw 在基础设施层实现了多种稳定性机制：

- Retry
- Timeout
- Fallback
- Idempotency
- Concurrency Control
- Rate Limit
- PostgreSQL Connection Pool
- Redis Connection Pool
- Sandbox Pool

这些机制用于提高 Agent 服务在高并发、外部模型异常或基础设施抖动情况下的稳定性。

## 📊 Production, Observability & Evaluation

### Observability

IvyClaw 集成多种可观测能力，用于追踪 Agent 从请求进入到任务完成的完整运行过程。

主要组件包括：

- **LangSmith**：Agent / LLM 调用链追踪
- **Prometheus**：服务指标采集
- **Grafana**：监控指标可视化
- **Structured Logging**：结构化运行日志
- **Audit Log**：关键请求与操作审计

重点关注的运行指标包括：

```text
Request
Latency
Error Rate
Concurrency
LLM Calls
Token / Cost
Worker Status
Sandbox Status
```

### Evaluation & Testing

项目包含测试、Agent Evaluation 与压测能力：

```text
tests/
eval/
loadtest/
```

主要包括：

- pytest 自动化测试
- Agent Runtime 测试
- Code Cases
- Execution Scorer
- LLM Judge
- Baseline Evaluation
- Reviewer Flow Test
- Locust Load Test

通过：

```text
开发
 ↓
自动化测试
 ↓
Agent Evaluation
 ↓
压力测试
 ↓
指标观测
 ↓
问题优化
```

形成从开发到生产验证的工程闭环。

### Production Deployment

IvyClaw 支持 Docker 化部署，生产环境主要服务包括：

```text
Web / FastAPI
ARQ Worker
Feishu Service
PostgreSQL
Redis
Prometheus
Grafana
```

整体部署关系：

```mermaid
flowchart TD
    U[Client] --> API[FastAPI Service]

    API --> PG[(PostgreSQL)]
    API --> RD[(Redis)]

    RD --> W[ARQ Worker]
    W --> AG[Agent Runtime]

    API --> AG
    AG --> SB[Docker Sandbox]

    API --> PM[Prometheus]
    W --> PM
    PM --> GF[Grafana]
```

生产环境可通过：

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

启动完整服务栈。


## 📁 Project Structure

```text
IvyClaw/
├── agent/          # 主 Agent 与任务调度
├── api/            # FastAPI API
├── channels/       # CLI / Feishu / Webhook 等接入渠道
├── gateway/        # API 鉴权、Tenant、限流
├── infra/          # PostgreSQL、Redis、LLM Router 等基础设施
├── middleware/     # 请求上下文、并发、审计、成本统计
├── obs/            # Metrics 与可观测性
├── profiles/       # 模型与 Agent Profile
├── sandbox/        # Docker / Daytona 沙箱
├── skills/         # Agent Skills
├── subagents/      # Planner / Researcher / Coder / Tester / Reviewer
├── tasks/          # ARQ 异步任务
├── tools/          # Git / pytest / Search / MCP 等工具
├── eval/           # Agent Evaluation
├── loadtest/       # Locust 压测
├── tests/          # 自动化测试
├── scripts/        # 开发、测试与演示脚本
├── web/            # Web UI
├── Dockerfile
├── docker-compose.prod.yml
├── pyproject.toml
└── .env.example
```

---

## 🔒 Security

敏感配置统一通过本地 `.env` 管理，仓库中只保留 `.env.example` 作为配置模板。

不应提交到 GitHub 的内容包括：

- LLM API Key
- LangSmith API Key
- Feishu App Secret
- PostgreSQL Password
- 真实 Gateway API Key
- 其他 Token / Secret

`.env`、虚拟环境、IDE 配置及运行时临时文件均通过 `.gitignore` 排除。

---

## 🗺️ Roadmap

IvyClaw 仍在持续迭代，后续计划包括：

- [ ] 优化 Multi-Agent 调度策略
- [ ] 引入 RAG / Knowledge Base
- [ ] 完善 Tenant 与权限管理
- [ ] 建立 CI/CD Pipeline
- [ ] 完善 Agent Evaluation 数据集
- [ ] 加强 Production Security
- [ ] 优化 Web UI
- [ ] 增加更多 MCP / External Tools

---

## 📌 Project Status

当前已实现：

- [x] Multi-Agent Workflow
- [x] Role-based Model Routing
- [x] Tool Calling
- [x] Docker / Daytona Sandbox
- [x] PostgreSQL / Redis Persistence
- [x] ARQ Async Jobs
- [x] Human-in-the-Loop
- [x] Multi-Channel Access
- [x] API Gateway & Multi-Tenant Demo
- [x] Rate Limit / Idempotency / Audit
- [x] LangSmith / Prometheus / Grafana
- [x] Agent Evaluation
- [x] Load Testing
- [x] Docker Production Deployment

---

## 📌 Note

IvyClaw 目前主要用于 AI Agent 工程化实践、学习与研究。

项目仍在持续完善中，部分能力为工程原型或演示实现，生产环境使用时仍需进一步完善身份认证、权限控制、安全隔离和基础设施配置。
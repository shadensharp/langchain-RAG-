# chat-langchain-study

基于 LangChain 官方 `chat-langchain` 改造的学习与实验项目。

当前版本采用前后端分离架构：

- 后端：FastAPI + LangChain + LangServe
- 前端：Next.js 13 + React + Chakra UI
- 向量库：Weaviate
- 默认模型：阿里云 DashScope 兼容接口下的 `qwen-turbo`
- 默认向量化模型：`text-embedding-v4`
- 当前知识库来源：LangChain / LangGraph 官方 Python 文档与 `common-errors`

这个仓库适合用于：

- 本地运行一个 LangChain / LangGraph 文档问答机器人
- 学习 LangChain / RAG / LangServe 的基础工程结构
- 在现有项目上继续做二次开发

## 项目特点

- 支持 LangChain / LangGraph 文档检索问答
- 后端支持从本地 `.env` 自动加载环境变量
- `ingest` 默认可使用本地 SQLite 作为 record manager
- 提供适合 Windows 的 PowerShell 启动脚本
- 支持会话、消息、`Good/Bad` 反馈和响应风格偏好持久化
- 支持来源摘录与 `Trace` 展示
- 前后端目录清晰，便于继续修改

## 目录结构

```text
.
|-- backend/          # FastAPI + LangChain backend
|-- frontend/         # Next.js frontend
|-- _scripts/         # PowerShell helper scripts
|-- assets/           # images and static assets
|-- terraform/        # deployment infra
|-- README.md
|-- pyproject.toml
|-- package.json
```

## 运行环境

- Python 3.10+
- Poetry
- Node.js 18+
- Yarn 1.x
- 可用的 Weaviate 实例
- DashScope API Key

## 快速开始

### 1. 安装后端依赖

项目内脚本默认使用仓库根目录下的 `.venv`，建议先执行：

```powershell
poetry config virtualenvs.in-project true
poetry install
```

### 2. 安装前端依赖

```powershell
cd frontend
yarn
cd ..
```

### 3. 配置环境变量

复制一份示例文件：

```powershell
Copy-Item .env.example .env
```

然后按实际情况填写 `.env`。

最少需要配置：

- `DASHSCOPE_API_KEY`
- `WEAVIATE_URL`
- `WEAVIATE_API_KEY`

可选配置：

- `RECORD_MANAGER_DB_URL`
- `APP_PERSISTENCE_DB_URL`
- `BACKEND_CORS_ORIGINS`
- `LANGCHAIN_API_KEY`
- `LANGCHAIN_PROJECT`
- `LANGCHAIN_TRACING_V2`
- `NEXT_PUBLIC_API_BASE_URL`

### 4. 采集并写入向量库

```powershell
powershell -File _scripts/run_ingest.ps1
```

当前 `ingest` 会抓取：

- `https://docs.langchain.com/oss/python/langchain/`
- `https://docs.langchain.com/oss/python/langgraph/`
- `https://docs.langchain.com/oss/python/common-errors`

默认情况下会使用本地 SQLite 作为 record manager：

```text
sqlite:///record_manager_local.db
```

如果你明确要使用环境变量里的 `RECORD_MANAGER_DB_URL`，可以执行：

```powershell
powershell -File _scripts/run_ingest.ps1 -UseConfiguredRecordManager
```

如果你更换了 Weaviate 集群，建议重新指定一份新的本地 record-manager 文件，避免旧集群状态干扰新集群：

```powershell
powershell -File _scripts/run_ingest.ps1 -UseLocalRecordManager -LocalRecordManagerUrl sqlite:///record_manager_rebuild.db
```

### 5. 启动后端

```powershell
powershell -File _scripts/run_backend.ps1 -Reload
```

默认监听：

- backend: `http://127.0.0.1:8080`

### 6. 启动前端

```powershell
powershell -File _scripts/run_frontend_dev.ps1
```

默认访问地址：

- frontend: `http://localhost:3000`

## 常用命令

```powershell
# backend
powershell -File _scripts/run_ingest.ps1
powershell -File _scripts/run_backend.ps1 -Reload

# frontend
powershell -File _scripts/run_frontend_dev.ps1
powershell -File _scripts/build_frontend.ps1
```

## 环境变量说明

```dotenv
# Required
DASHSCOPE_API_KEY=
WEAVIATE_URL=
WEAVIATE_API_KEY=

# Optional local/default settings
RECORD_MANAGER_DB_URL=sqlite:///record_manager_local.db
USE_CONFIGURED_RECORD_MANAGER=false
FORCE_UPDATE=false
APP_PERSISTENCE_DB_URL=sqlite:///chat_state.db
BACKEND_CORS_ORIGINS=http://localhost:3000

# Optional LangSmith tracing
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_API_KEY=
LANGCHAIN_PROJECT=chat-langchain-study

# Optional frontend override
NEXT_PUBLIC_API_BASE_URL=http://localhost:8080
```

## 反馈与 Trace

- `Good`
  - 将当前回答标记为正向反馈
  - 后端会保存这条回答，并抽取其风格备注，作为后续回答的风格参考
- `Bad`
  - 将用户写下的调整意见与被否定的回答一起保存
  - 后续回答会把这些内容作为风格指导，而不是事实证据
- `Trace`
  - 展示当前回答命中的来源页面、位置和摘录
  - 只有当前回答带有 `sources` 时可点击；如果向量库为空或未完成 ingest，就不会显示可用 trace

## 当前改造点

相对原始 `chat-langchain`，当前仓库包含这些本地化改动：

- 默认聊天模型切换为 DashScope 兼容接口下的 Qwen
- 默认 embedding 改为 DashScope `text-embedding-v4`
- 增加 `.env` 本地加载逻辑
- 增加 Windows PowerShell 启动脚本
- 本地启动脚本会清理残留的 `WEAVIATE_*` 等环境变量，避免旧 shell 环境覆盖仓库 `.env`
- `ingest` 切换到当前官方文档站点 `docs.langchain.com`
- 当前知识库已覆盖 LangChain、LangGraph 和 `common-errors`
- 后端新增会话、反馈和响应风格偏好的持久化能力

## 参考来源

- 原始项目：<https://github.com/langchain-ai/chat-langchain>
- 当前仓库基于原项目做学习和运行适配

## License

本仓库沿用 [MIT License](./LICENSE)。

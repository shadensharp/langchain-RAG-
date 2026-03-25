# chat-langchain-study

基于 LangChain 官方 `chat-langchain` 改造的学习与实验项目。

当前版本采用前后端分离架构：

- 后端：FastAPI + LangChain + LangServe
- 前端：Next.js 13 + React + Chakra UI
- 向量库：Weaviate
- 默认模型：阿里云 DashScope 兼容接口下的 `qwen-turbo`
- 默认向量化模型：`text-embedding-v4`

这个仓库适合用于：

- 本地运行一个 LangChain 文档问答机器人
- 学习 LangChain / RAG / LangServe 的基础工程结构
- 在现有项目上继续做二次开发

## 项目特点

- 支持 LangChain 文档检索问答
- 后端支持从本地 `.env` 自动加载环境变量
- `ingest` 默认可使用本地 SQLite 作为 record manager
- 提供适合 Windows 的 PowerShell 启动脚本
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
- `LANGCHAIN_API_KEY`
- `LANGCHAIN_PROJECT`
- `LANGCHAIN_TRACING_V2`
- `NEXT_PUBLIC_API_BASE_URL`

### 4. 采集并写入向量库

```powershell
powershell -File _scripts/run_ingest.ps1
```

默认情况下会优先使用本地 SQLite：

```text
sqlite:///record_manager_local.db
```

如果你明确要使用环境变量里的 `RECORD_MANAGER_DB_URL`，可以执行：

```powershell
powershell -File _scripts/run_ingest.ps1 -UseConfiguredRecordManager
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

# Optional
RECORD_MANAGER_DB_URL=sqlite:///record_manager_local.db
USE_CONFIGURED_RECORD_MANAGER=false
FORCE_UPDATE=false

# LangSmith
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_API_KEY=
LANGCHAIN_PROJECT=chat-langchain-study

# Frontend
NEXT_PUBLIC_API_BASE_URL=http://localhost:8080
```

## 当前改造点

相对原始 `chat-langchain`，当前仓库包含这些本地化改动：

- 默认聊天模型切换为 DashScope 兼容接口下的 Qwen
- 默认 embedding 改为 DashScope `text-embedding-v4`
- 增加 `.env` 本地加载逻辑
- 增加 Windows PowerShell 启动脚本
- `ingest` 默认使用本地 SQLite record manager，便于本地调试

## 参考来源

- 原始项目：<https://github.com/langchain-ai/chat-langchain>
- 当前仓库基于原项目做学习和运行适配

## License

本仓库沿用 [MIT License](./LICENSE)。

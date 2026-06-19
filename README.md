# 明日方舟剧情史学家（非构史学家）

基于 RAG（检索增强生成）的《明日方舟》剧情问答 AI 助手。使用本地知识库检索 + 大语言模型，回答关于游戏剧情、角色、世界观的问题。

> **免责声明**：本项目是由《明日方舟》游戏爱好者制作的非官方交流学习工具。项目内使用的游戏文本、角色名称等，版权属于上海鹰角网络科技有限公司及其关联公司。本项目严禁用于任何形式的盈利服务。AI 生成内容仅供参考，不构成官方解释。

## 版本

当前版本：**v1.0.0**

## 功能特性

- **剧情问答**：覆盖主线（第零章~第十七章）、50+ 活动/支线剧情
- **角色档案**：428 位干员的档案、密录、模组故事、皮肤描述、干员语音
- **双时间线**：
  - **泰拉历**（游戏世界时间）：从结晶纪元前到泰拉历 1103 年的完整编年史（来源：PRTS Wiki）
  - **现实时间**：每个活动剧情块标注中国服现实开放时间（如"2026年6月"），可回答"最新活动"、"某年某月活动"等版本相关问题
- **多模型支持**：兼容任何 OpenAI API 格式的大模型（DeepSeek、Kimi、通义千问、Ollama 等）
- **多轮对话**：保持上下文连贯
- **一键更新知识库**：前端点击即可完成 git pull → 数据解析 → 增量重建向量库全流程
- **增量向量更新**：只对变更的文本块重新计算 embedding，小活动更新从 5 分钟降至秒级
- **数据更新检查**：自动检测 ArknightsGameData 仓库是否有新版本
- **BGM 播放器**：内置游戏音乐播放器，支持播放/暂停/切歌/音量调节
- **一键启动**：自动检查环境、安装依赖、启动服务

## 知识库规模（以2026.6.20为例）

| 数据类型 | 文本块数量 |
|---------|-----------|
| 剧情 | 12,864 |
| 干员档案/密录/语音 | 15,522 |
| 模组故事 | 864 |
| 皮肤描述 | 1,302 |
| 集成战略 | 25 |
| 泰拉年表 | 160 |
| **合计** | **30,737** |

---

## 技术栈

**后端（Python）**
- FastAPI + Uvicorn（Web 框架与 ASGI 服务器）
- OpenAI SDK（兼容任何 OpenAI 格式的 LLM API，支持 Function Calling + 流式输出）
- ChromaDB（向量数据库，持久化存储）
- sentence-transformers + bge-large-zh-v1.5（中文文本嵌入模型）

**前端**
- React 19 + Vite 8（构建工具与开发服务器）
- TailwindCSS 4（原子化 CSS）
- Zustand（轻量状态管理）
- react-markdown + remark-gfm（Markdown 渲染，支持表格）
- lucide-react（图标库）

---

## 模块说明

### 后端模块

| 模块 | 核心技术 | 职责 |
|------|---------|------|
| [start.py](start.py) | subprocess / urllib / webbrowser | 一键启动入口：环境检查 → 启动后端 → 启动前端 → 打开浏览器；Ctrl+C 停止所有子进程 |
| [check_deps.py](check_deps.py) | pip / npm / winget | 独立依赖检查与自动安装（Python 包、Node 模块、Git），使用国内镜像源 |
| [server.py](server.py) | FastAPI / Uvicorn / SSE | 后端 API 服务：会话管理（线程安全）、流式聊天（SSE）、配置接口、更新检查、一键更新知识库（SSE 进度推送） |
| [agent.py](agent.py) | OpenAI SDK / sentence-transformers / ChromaDB | RAG Agent 核心：System Prompt 驱动、Function Calling 自主检索、多轮工具调用（最多 8 轮）、真流式输出、BGE 模型单例共享 |
| [vector_store.py](vector_store.py) | sentence-transformers / ChromaDB | 向量库构建器：读取 chunks → bge-large-zh 计算 embedding → 写入 ChromaDB；支持增量更新（对比文本 hash 跳过未变更块）和全量重建 |
| [github_crawler.py](github_crawler.py) | json / os | 游戏数据解析器：遍历 ArknightsGameData 仓库，解析 6 类数据（剧情/模组/档案/语音/皮肤/集成战略），附加现实时间标签和覆盖范围摘要 |
| [import_timeline.py](import_timeline.py) | ChromaDB | 泰拉年表导入：解析 timeline_raw.txt（来源 PRTS Wiki），写入向量库 |
| [auto_test.py](auto_test.py) | OpenAI SDK | 多 Agent 自动测试流水线（开发工具，非运行必需）：出题人 → 被测 Agent → 审核员，覆盖 6 类测试场景 |

### 前端模块

| 模块 | 核心技术 | 职责 |
|------|---------|------|
| [App.jsx](web/src/App.jsx) | React | 主布局：侧边栏 + 聊天区 + 音乐播放器 |
| [chatStore.js](web/src/store/chatStore.js) | Zustand | 全局状态管理：消息列表、加载状态、配置、数据更新状态；集成 AbortController 取消流 |
| [client.js](web/src/api/client.js) | fetch + ReadableStream | API 请求封装：SSE 流式聊天、统计、配置、更新检查、一键更新进度监听 |
| [Sidebar.jsx](web/src/components/Sidebar.jsx) | React + Tailwind | 侧边栏：知识库统计、更新检查、一键更新知识库、模型设置入口 |
| [MessageList.jsx](web/src/components/MessageList.jsx) | React | 消息列表 + 欢迎页（预设问题）+ 加载动画 |
| [MessageBubble.jsx](web/src/components/MessageBubble.jsx) | react-markdown | 消息气泡：Markdown 渲染 + token 用量统计 |
| [InputArea.jsx](web/src/components/InputArea.jsx) | React | 输入框 + 发送/重置按钮 |
| [SettingsPanel.jsx](web/src/components/SettingsPanel.jsx) | React | 模型设置弹窗：API Key / Base URL / 模型名称 |
| [UpdateOverlay.jsx](web/src/components/UpdateOverlay.jsx) | React | 全屏更新覆盖层：进度条 + 步骤提示 + 完成刷新 |
| [MusicBox.jsx](web/src/components/MusicBox.jsx) | HTML5 Audio API | BGM 播放器：播放控制 / 进度条 / 音量 / 曲目列表 |
| [ErrorBoundary.jsx](web/src/components/ErrorBoundary.jsx) | React Error Boundary | 全局错误边界：白屏降级 UI + 刷新按钮 |

---

## 架构概览

### RAG 检索流程

```
用户问题
    │
    ▼
LLM Function Calling（规划检索策略）
    │
    ├─ search_stories(query, type, top_k)  ──▶  ChromaDB 向量检索
    │                                                (bge-large-zh-v1.5)
    └─ get_stats()                        ──▶  meta.json 统计信息
    │
    ▼
LLM 综合检索结果 → 生成回答（附带出处标注）
```

Agent 通过 LLM 的 Function Calling 机制自主决定检索策略：根据问题类型（角色/剧情/事实/现实时间/创意）自动选择数据类型过滤和关键词，多轮检索直到覆盖全面，最多 8 轮工具调用。

### 数据处理流水线

```
ArknightsGameData (GitHub)          PRTS Wiki
    │                                    │
    ▼                                    ▼
github_crawler.py                  import_timeline.py
    │  解析 6 类数据:                       │  解析年表原始文本
    │  ├─ story_txt → 剧情文本块           │  (泰拉历时间线)
    │  ├─ uniequip_table → 模组故事       │
    │  ├─ handbook_info_table → 档案/密录 │
    │  ├─ charword_table → 干员语音       │
    │  ├─ skin_table → 皮肤描述          │
    │  └─ roguelike → 集成战略剧情        │
    │  + activity_table → 现实时间标签    │
    ▼                                    ▼
data/chunks/*.json  ◄──────────────────┘
    │
    ▼
vector_store.py
    │  bge-large-zh-v1.5 嵌入 + ChromaDB 存储
    │  （增量更新：只计算变更块的 embedding）
    ▼
data/vectorstore/  (ChromaDB 持久化)
```

### 一键更新知识库流程

```
前端点击"一键更新知识库"
    │
    ▼
POST /api/update-data (SSE)
    │
    ├─ [1] 检查/安装 Git (winget)
    ├─ [2] git pull（已存在）/ git clone --sparse（首次）
    ├─ [3] github_crawler.py 解析数据
    ├─ [4] vector_store.py 增量重建向量库
    ├─ [5] import_timeline.py 导入年表（如存在）
    └─ [6] 检查应用版本 + 清除旧会话
    │
    ▼  全程 SSE 推送进度
前端 UpdateOverlay 显示进度条 + 步骤
```

---

## 从零开始：完整操作指南

### 方式一：下载完整版（推荐新手）

这是最简单的方式，不需要任何编程基础。

#### 第 1 步：下载项目

从 [Releases](../../releases) 页面下载最新完整版 zip 文件，解压到任意目录。

> zip 包含预构建的知识库数据（约 1 GB），开箱即用。

#### 第 2 步：安装系统环境

本项目需要以下两个系统环境，请确认已安装：

**Python 3.10+**

1. 访问 https://www.python.org/downloads/
2. 下载 Python 3.12（推荐）或更高版本
3. 运行安装程序，**务必勾选 "Add Python to PATH"**
4. 安装完成后，打开 cmd 输入 `python -V` 验证

**Node.js 18+**

1. 访问 https://nodejs.org
2. 下载 LTS 版本（推荐 20.x）
3. 运行 MSI 安装程序，保持默认选项
4. 安装完成后，打开 cmd 输入 `node -v` 验证

#### 第 3 步：配置 API Key

你需要一个大语言模型的 API Key，用于驱动 AI 回答。支持以下服务：

| 服务 | 获取地址 | Base URL | 推荐模型 |
|-----|---------|----------|---------|
| DeepSeek | https://platform.deepseek.com | https://api.deepseek.com | deepseek-chat |
| Kimi | https://platform.moonshot.cn | https://api.moonshot.cn/v1 | moonshot-v1-32k |
| 通义千问 | https://dashscope.console.aliyun.com | https://dashscope.aliyuncs.com/compatible-mode/v1 | qwen-plus |
| Ollama（本地） | https://ollama.com | http://localhost:11434/v1 | qwen2.5 |

> **推荐 DeepSeek**：价格低、中文能力强、兼容性好。

配置方式（二选一）：

- **方式 A**：可以稍后进入前端界面，点击"模型设置"实时配置模型。（每次启动服务时，需重新在前端界面配置模型）
- **方式 B**（推荐）：手动编辑项目根目录下的 `.env` 文件（用记事本打开）：
  ```env
  DEEPSEEK_API_KEY=你的API Key
  DEEPSEEK_BASE_URL=https://api.deepseek.com
  DEEPSEEK_MODEL=deepseek-chat
  ```

#### 第 4 步：一键启动

双击项目根目录下的 **`start.bat`**，或在项目根目录打开 cmd 执行：

```
python start.py
```

启动流程：
```
=============================================
  明日方舟剧情史学家 - 一键启动
=============================================

[1/4] 检查环境...
[✓] 环境检查通过
[2/4] 启动后端 (端口 8000)...
      等待后端就绪.... ✓
[3/4] 启动前端 (端口 36888)...
[4/4] 就绪

=============================================
  后端: http://localhost:8000
  前端: http://localhost:36888
=============================================

按 Enter 键打开浏览器，按 Ctrl+C 停止所有服务...
```

**首次运行注意事项**：
- 如果缺少 Python 包或前端依赖，`start.py` 会自动检测并提示安装（使用国内镜像源，无需科学上网）
- sentence-transformers（含 PyTorch）较大（约 2.5 GB），首次安装需要几分钟
- 嵌入模型（bge-large-zh-v1.5）首次使用时自动下载（通过 hf-mirror.com 国内镜像，约 1.3 GB）
- 安装完成后关闭窗口，重新运行即可

#### 第 5 步：开始使用

按 Enter 键后浏览器会自动打开 `http://localhost:36888/`。

- 在输入框输入问题即可对话
- 侧边栏可查看知识库概况、检查更新、一键更新知识库、切换模型
- 支持多轮对话，上下文自动保持

#### 停止服务

- 在启动窗口按 `Ctrl+C` 停止所有服务
- 或直接关闭弹出的窗口

---

### 方式二：从源码构建（进阶用户）

适用于想自行构建知识库或修改代码的开发者。

#### 第 1 步：克隆项目

```bash
git clone https://github.com/你的用户名/mrfz_history_project.git
cd mrfz_history_project
```

#### 第 2 步：安装 Python 依赖

```bash
pip install -r requirements.txt
```

> 国内用户建议使用镜像源加速：
> ```bash
> pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
> ```

#### 第 3 步：安装前端依赖

```bash
cd web
npm install --registry=https://registry.npmmirror.com
cd ..
```

#### 第 4 步：配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的 API Key：
```env
DEEPSEEK_API_KEY=你的API Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
HF_ENDPOINT=https://hf-mirror.com
```

#### 第 5 步：构建知识库

首次使用需要拉取游戏数据并构建向量库：

```bash
# 一键更新（自动 git clone + 解析 + 构建向量库）
python start.py
# 启动后在前端点击"一键更新知识库"

# 或手动构建：
python github_crawler.py    # 解析游戏数据（需先 clone ArknightsGameData）
python vector_store.py      # 构建向量库
python import_timeline.py   # 导入泰拉年表
```

#### 第 6 步：启动服务

```bash
python start.py
```

启动后访问 **http://localhost:36888/**

---

## 使用指南

### 试试这些问题

点击欢迎页的预设问题快速体验：

| 问题 | 类型 |
|------|------|
| 四皇会战发生在哪一年？ | 事实检索（泰拉历） |
| 2024年有哪些活动？ | 版本检索（现实时间） |
| 最新活动是什么？ | 版本检索（现实时间） |
| 乌萨斯学生自治团和整合运动的关系是什么？ | 关系分析 |
| 分析莫斯提马的人格特点 | 人物画像 |
| 凯尔希的几次复活与死亡 | 事件梳理 |
| 以年和夕为主角写个小故事 | 创意生成 |

### 模型设置

点击侧边栏底部的"模型设置"按钮，可以实时切换：
- API Key
- API Base URL
- 模型名称

切换后立即生效，无需重启。

### 更新知识库

- **检查更新**：点击侧边栏"检查更新"，检测 ArknightsGameData 仓库是否有新版本
- **一键更新**：点击"一键更新知识库"，自动完成 git pull → 数据解析 → 增量重建向量库全流程，前端实时显示进度

---

## 项目结构

```
├── start.py              # 一键启动脚本（环境检查 + 自动安装 + 启动服务）
├── check_deps.py         # 独立依赖检查与自动安装
├── server.py             # FastAPI 后端服务（API 路由 + 会话管理 + SSE 流式输出）
├── agent.py              # RAG Agent 核心（VectorSearcher + Function Calling + 流式输出）
├── vector_store.py       # 向量索引构建器（增量更新 + 全量重建）
├── github_crawler.py     # 游戏数据解析器（剧情/模组/档案/语音/皮肤/集成战略 + 现实时间）
├── import_timeline.py    # 泰拉年表导入脚本（PRTS Wiki 数据 → ChromaDB）
├── auto_test.py          # 多 Agent 自动测试流水线（开发工具）
├── requirements.txt      # Python 依赖清单
├── .env.example          # 环境变量模板
├── .gitignore            # Git 忽略配置
│
├── data/
│   ├── chunks/           # 数据分块（JSON，按类型分文件）
│   │   ├── meta.json         # 元信息与统计
│   │   ├── story.json        # 剧情文本块
│   │   ├── character.json    # 干员档案/密录/语音
│   │   ├── module.json       # 模组故事
│   │   ├── skin.json         # 皮肤描述
│   │   └── roguelike.json    # 集成战略剧情
│   ├── vectorstore/      # ChromaDB 向量库（持久化存储）
│   └── timeline_raw.txt  # 泰拉年表原始文本（来源 PRTS Wiki）
│
└── web/                  # React 前端
    ├── public/
    │   └── music/            # BGM 音乐文件 + tracks.json 播放列表
    ├── src/
    │   ├── App.jsx           # 主布局
    │   ├── main.jsx          # 入口
    │   ├── index.css         # 全局样式
    │   ├── api/client.js     # API 请求封装（SSE 流式/统计/配置/更新）
    │   ├── store/chatStore.js # Zustand 全局状态管理
    │   └── components/       # UI 组件
    │       ├── Sidebar.jsx       # 侧边栏
    │       ├── MessageList.jsx   # 消息列表 + 欢迎页
    │       ├── MessageBubble.jsx # 消息气泡（Markdown 渲染）
    │       ├── InputArea.jsx     # 输入框
    │       ├── SettingsPanel.jsx # 模型设置弹窗
    │       ├── MusicBox.jsx     # BGM 播放器
    │       ├── UpdateOverlay.jsx # 更新覆盖层
    │       └── ErrorBoundary.jsx # 错误边界
    ├── vite.config.js       # Vite 配置（端口 36888 + API 代理）
    └── package.json
```

---

## 常见问题

### Q: 启动时报错？
A: 打开 cmd，手动运行 `python start.py` 查看具体错误信息。最常见原因是 Python/Node.js 未加入 PATH。

### Q: 首次运行很慢？
A: 首次运行需要下载嵌入模型（约 1.3 GB），通过 hf-mirror.com 国内镜像下载。下载完成后后续启动会很快。

### Q: 回答错误或不准确？
A: 尝试切换更强大的模型，或更换为 Kimi、通义千问等其他服务。也可以在提问时提供更多上下文信息。

### Q: 如何更新知识库？
A: 启动服务后，在前端侧边栏点击"一键更新知识库"即可，会自动拉取最新数据并增量重建向量库。

### Q: 检查更新提示超时？
A: 这是国内访问 GitHub API 不稳定导致，稍后重试即可，不影响正常对话功能。

### Q: 可以离线使用吗？
A: 不行。知识库和嵌入模型是本地的，但 AI 推理需要在线调用大语言模型 API。

### Q: 支持哪些大模型？
A: 任何兼容 OpenAI API 格式的模型服务都可以，包括 DeepSeek、Kimi、通义千问、Ollama（本地部署）等。

---

## 致谢与数据来源

本项目基于以下开放项目构建，在此表示感谢：

- **[ArknightsGameData](https://github.com/Kengxxiao/ArknightsGameData)**（by Kengxxiao）— 《明日方舟》中文游戏数据仓库，本项目的主要数据来源
- **[PRTS Wiki](https://prts.wiki/)** — 明日方舟中文 Wiki，泰拉年表数据来源

---


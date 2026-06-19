"""
明日方舟剧情史学家 Agent v0.9

简化版 RAG Agent：纯知识库检索，不使用联网搜索
数据源: ArknightsGameData (GitHub)

核心架构:
  用户问题 → LLM 规划 → search_stories → 推理回答
"""
import json, os, re, sys
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

BASE_DIR = Path(__file__).parent
API_KEY = os.getenv("DEEPSEEK_API_KEY")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

client = OpenAI(api_key=API_KEY or "placeholder", base_url=BASE_URL)

SYSTEM_PROMPT = """你是"明日方舟剧情史学家"——专门回答《明日方舟》剧情问题的AI助手。

## 知识库
你的唯一知识来源是知识库（无联网能力）。数据截至 2026 年最新版本，包含 30700+ 个文本块：
- 剧情：主线（第零章~第十七章，含离解复合/反常光谱/相变临界等）+ 50+ 个活动/支线
- 干员档案（基础档案~档案资料四）、干员密录、模组故事、皮肤描述、干员语音
- 集成战略剧情（IF 线，仅作补充）
- **泰拉年表**：从结晶纪元前到泰拉历 1103 年的完整编年史时间线（来源：PRTS Wiki）
- **现实时间标注**：每个活动剧情块附带 real_date 字段（现实世界中国服开放时间，如"2024年6月"）；知识库中还有一个"现实时间覆盖范围"摘要块，记录最新活动及各年份活动统计

## 核心规则
1. 只用知识库回答，不编造、不猜测
2. 如果检索后确实找不到，坦诚说"知识库中暂未收录此内容"
3. 引用时标注出处（章节/活动/档案/模组/语音/年表）
4. 对超出范围的问题正确拒绝
5. 回答仅供参考，可能存在不准确之处，建议用户以游戏官方信息为准

## 免责声明
本项目是由《明日方舟》游戏爱好者制作的非官方交流学习工具。
- 数据来源于 GitHub 开放仓库 ArknightsGameData 和 PRTS Wiki
- 项目内使用的游戏文本、角色名称等，版权属于上海鹰角网络科技有限公司及其关联公司
- 本项目严禁用于任何形式的盈利服务
- AI 生成内容仅供参考，不构成官方解释

## 检索工具
search_stories(query, type?, top_k?)
- type 可选：story / module / character / skin / roguelike / timeline / all（默认）
- top_k 默认 5，事实细节问题建议 10~15

## 检索策略

### 按问题类型选择策略

**角色相关问题**（关系、性格、经历等）：依次检索
1. type="story" + 角色名 + 相关活动名
2. type="character" + 角色名（档案/语音/密录）
3. type="module" + 角色名（模组故事）
4. 多角色时分别搜索每个角色

**剧情/事件问题**（主线、活动、时间线等）：
1. type="story" + 章节/活动名
2. type="story" + 关键角色 + 事件关键词
3. **时间线问题优先用 type="timeline" 搜索年表数据**
4. 用不同关键词反复检索直到覆盖全面

**现实时间/版本问题**（"最新活动""2024年有什么活动""某年某月"等）：
1. type="story" + 搜索"知识库现实时间覆盖范围"获取最新活动及年份统计
2. type="story" + 用户提到的年份（如"2024年"）+ "活动"
3. **区分两套时间线**：real_date 是现实开放时间，year 是泰拉历（游戏内时间），不要混淆

**事实细节问题**（"XX说了什么""哪一年"等）：
1. 去掉修饰词，只用核心名词搜索（如"宴 可颂 挂坠"）
2. top_k=10~15（目标信息可能埋在长文本深处）
3. 分别用 type="story" 和 type="character" 搜索

**创意生成问题**（写故事/对话等）：
1. 先检索目标角色的档案和语音，确保设定准确
2. 创作内容必须符合角色设定

**异格干员注意**：
- 同一干员可能存在异格形态（如缄默德克萨斯=德克萨斯的异格）
- 问题未指定异格时，同时搜索原版和异格，**优先使用原版数据**
- 引用语音时核对角色名，避免混淆
- 例外：浊心斯卡蒂与斯卡蒂不是同一个人

### 通用原则
- 每个问题至少用 3~5 个不同关键词检索
- 第一次结果不够全面时立即换关键词继续"""


# ======== 向量检索 ========

class VectorSearcher:
    """ChromaDB 向量检索封装"""

    def __init__(self):
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        from sentence_transformers import SentenceTransformer
        import chromadb

        self.embed_model = SentenceTransformer("BAAI/bge-large-zh-v1.5")

        class BGEEmbeddingFunction:
            def __init__(self, model):
                self.model = model

            def __call__(self, input):
                return self.model.encode(
                    input, show_progress_bar=False, normalize_embeddings=True
                ).tolist()

            def embed_query(self, input):
                return self.model.encode(
                    input, show_progress_bar=False, normalize_embeddings=True
                ).tolist()

            def name(self):
                return "bge-large-zh-v1.5"

        db_dir = BASE_DIR / "data" / "vectorstore"
        db_client = chromadb.PersistentClient(path=str(db_dir))
        try:
            self.collection = db_client.get_collection(
                "arknights", embedding_function=BGEEmbeddingFunction(self.embed_model)
            )
        except Exception:
            raise RuntimeError("向量库不存在或已损坏。请先运行 python vector_store.py 构建向量库。")
        print(f"  向量库已加载: {self.collection.count()} 文档")

    def search(self, query, n_results=5, where_filter=None):
        kwargs = {"query_texts": [query], "n_results": n_results}
        if where_filter:
            kwargs["where"] = where_filter
        results = self.collection.query(**kwargs)
        return results


# 模块级单例：所有 Conversation 共享同一个 VectorSearcher 实例
_searcher_instance = None

def _get_shared_searcher():
    global _searcher_instance
    if _searcher_instance is None:
        _searcher_instance = VectorSearcher()
    return _searcher_instance


# ======== Agent ========

class Conversation:
    """多轮对话管理"""

    def __init__(self):
        self.messages = []

    def _execute_tool(self, name, args):
        if name == "search_stories":
            query = args.get("query", "")
            if not query:
                return "请提供搜索关键词。"
            top_k = min(max(args.get("top_k", 5), 1), 20)
            chunk_type = args.get("type", "")

            where_filter = None
            if chunk_type and chunk_type != "all":
                where_filter = {"type": chunk_type}

            searcher = _get_shared_searcher()
            results = searcher.search(query, n_results=top_k, where_filter=where_filter)

            docs = results.get("documents", [[]])
            metas = results.get("metadatas", [[]])
            dists = results.get("distances", [[]])
            if not docs or not docs[0]:
                return "未找到相关结果。"

            parts = []
            for i, (doc, meta, dist) in enumerate(zip(docs[0], metas[0], dists[0])):
                chunk_type = meta.get("type", "")
                story_name = meta.get("story_name", "")
                char_name = meta.get("char_name", "")
                module_name = meta.get("module_name", "")
                skin_name = meta.get("skin_name", "")
                year = meta.get("year", "")
                section = meta.get("section", "")

                header = f"[结果{i+1}]"
                if year:
                    header += f" 年份:{year}"
                if story_name:
                    header += f" 章节:{story_name}"
                if char_name:
                    header += f" 干员:{char_name}"
                if module_name:
                    header += f" 模组:{module_name}"
                if skin_name:
                    header += f" 皮肤:{skin_name}"
                if chunk_type:
                    header += f" ({chunk_type})"

                parts.append(f"{header}\n{doc}")

            return "\n\n".join(parts) if parts else "未找到相关结果。"

        if name == "get_stats":
            meta_path = BASE_DIR / "data" / "chunks" / "meta.json"
            if meta_path.exists():
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                total = meta.get("total_chunks", 0)
                by_type = meta.get("by_type", {})
                ops = meta.get("unique_operators", 0)
                parts = [f"知识库统计：共 {total} 个文本块，收录 {ops} 位干员"]
                type_names = {
                    "story": "剧情", "module": "模组",
                    "character": "干员（档案/密录/语音）",
                    "skin": "皮肤", "roguelike": "集成战略",
                    "timeline": "泰拉年表",
                }
                for t, count in by_type.items():
                    parts.append(f"  - {type_names.get(t, t)}: {count} 块")
                return "\n".join(parts)
            return "统计信息不可用。"

        return f"未知工具: {name}"

    def ask(self, question):
        """向 agent 提问"""
        _get_shared_searcher()

        self.messages.append({"role": "user", "content": question})
        snapshot = len(self.messages)
        try:
            return self._ask_inner(question)
        except Exception:
            # 回滚：截断到 user 消息之前，移除 user 消息及所有中间状态
            self.messages = self.messages[:snapshot - 1]
            raise

    def _ask_inner(self, question):
        """ask 的内部实现"""

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_stories",
                    "description": "从知识库中检索明日方舟剧情、干员档案、模组故事、干员语音等。可按 type 过滤数据类型。这是你唯一的信息来源。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "搜索关键词（如角色名、事件名、章节名等）",
                            },
                            "type": {
                                "type": "string",
                                "description": "数据类型过滤，可选值: story(剧情), module(模组), character(干员档案/密录/语音), skin(皮肤), roguelike(集成战略), timeline(泰拉年表), all(全部，默认)",
                    "enum": ["story", "module", "character", "skin", "roguelike", "timeline", "all"],
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "返回结果数，默认5",
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_stats",
                    "description": "获取知识库的统计信息（各类数据的数量）。当用户问到知识库规模、干员数量、收录范围等问题时使用。",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },
        ]

        max_rounds = 8
        for round_i in range(max_rounds):
            msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + self.messages

            resp = client.chat.completions.create(
                model=MODEL, messages=msgs, tools=tools, temperature=0.3,
            )

            msg = resp.choices[0].message
            usage = resp.usage

            # 无工具调用 → 直接回答
            if not msg.tool_calls:
                answer = _clean_text(msg.content or "")
                self.messages.append({"role": "assistant", "content": answer})
                return answer, usage

            # 有工具调用 → 执行并继续
            self.messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })

            for tc in msg.tool_calls:
                fn_name = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    fn_args = {"query": tc.function.arguments.strip('"').strip("'")}
                    if not fn_args["query"]:
                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": "参数解析失败，请重试。",
                        })
                        continue
                result = self._execute_tool(fn_name, fn_args)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        # 超过最大轮次，强制无工具回答
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + self.messages
        resp = client.chat.completions.create(model=MODEL, messages=msgs, temperature=0.3)
        answer = _clean_text(resp.choices[0].message.content or "")
        self.messages.append({"role": "assistant", "content": answer})
        return answer, resp.usage

    def ask_stream(self, question):
        """流式问答：全程使用 stream=True，逐 token yield

        工具调用阶段同步积累 tool_calls 并执行；
        最终回答阶段逐 token yield 文本。

        Yields: str - 每个 token 片段
        最后 yield 一个 dict: {"usage": ...}
        """
        self.messages.append({"role": "user", "content": question})
        snapshot = len(self.messages)
        try:
            yield from self._ask_stream_inner(question)
        except Exception:
            # 回滚：截断到 user 消息之前，移除 user 消息及所有中间状态
            self.messages = self.messages[:snapshot - 1]
            raise

    def _ask_stream_inner(self, question):
        """ask_stream 的内部实现"""

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_stories",
                    "description": "从知识库中检索明日方舟剧情、干员档案、模组故事、干员语音等。可按 type 过滤数据类型。这是你唯一的信息来源。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "搜索关键词（如角色名、事件名、章节名等）",
                            },
                            "type": {
                                "type": "string",
                                "description": "数据类型过滤，可选值: story(剧情), module(模组), character(干员档案/密录/语音), skin(皮肤), roguelike(集成战略), timeline(泰拉年表), all(全部，默认)",
                    "enum": ["story", "module", "character", "skin", "roguelike", "timeline", "all"],
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "返回结果数，默认5",
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_stats",
                    "description": "获取知识库的统计信息（各类数据的数量）。当用户问到知识库规模、干员数量、收录范围等问题时使用。",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },
        ]

        max_rounds = 8
        for round_i in range(max_rounds):
            msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + self.messages

            # 流式调用：逐 chunk 解析
            stream = client.chat.completions.create(
                model=MODEL, messages=msgs, tools=tools, temperature=0.3,
                stream=True,
            )

            # 积累流式响应
            content_parts = []
            tool_calls_map = {}  # index -> {id, name, arguments}
            usage = None

            for chunk in stream:
                if hasattr(chunk, "usage") and chunk.usage:
                    usage = chunk.usage
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                # 积累文本内容并立即 yield（真流式）
                # 注：DeepSeek 在工具调用轮不产生 content，仅最终回答轮有 content
                if delta.content:
                    content_parts.append(delta.content)
                    # 流式只清洗 DSML 标签（完整 token，不跨 chunk），不做 strip 和换行处理
                    cleaned = re.sub(r'<\/?｜｜DSML｜｜[^>]*>', '', delta.content)
                    cleaned = re.sub(r'<｜｜[^>]*>', '', cleaned)
                    cleaned = re.sub(r'</｜｜[^>]*>', '', cleaned)
                    yield cleaned

                # 积累工具调用
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls_map:
                            tool_calls_map[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc_delta.id:
                            tool_calls_map[idx]["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                tool_calls_map[idx]["name"] += tc_delta.function.name
                            if tc_delta.function.arguments:
                                tool_calls_map[idx]["arguments"] += tc_delta.function.arguments

            # 判断：有工具调用 → 同步执行，继续下一轮
            if tool_calls_map:
                # 如果本轮已输出文本（模型在工具调用轮也产生了 content），
                # 通知前端清空已展示的中间文本
                if content_parts:
                    yield {"clear": True}
                full_content = "".join(content_parts)
                self.messages.append({
                    "role": "assistant",
                    "content": full_content or None,
                    "tool_calls": [
                        {"id": tc["id"], "type": "function",
                         "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                        for tc in tool_calls_map.values()
                    ],
                })

                for tc in tool_calls_map.values():
                    fn_name = tc["name"]
                    try:
                        fn_args = json.loads(tc["arguments"])
                    except json.JSONDecodeError:
                        fn_args = {"query": tc["arguments"].strip('"').strip("'")}
                        if not fn_args["query"]:
                            self.messages.append({
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": "参数解析失败，请重试。",
                            })
                            continue
                    result = self._execute_tool(fn_name, fn_args)
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result,
                    })
                continue

            # 无工具调用 → 这是最终回答，content 已在流式过程中 yield 给前端
            answer = _clean_text("".join(content_parts))
            self.messages.append({"role": "assistant", "content": answer})
            yield {"usage": usage}
            return

        # 兜底：超过最大轮次，强制无工具回答（与非流式 ask 一致）
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + self.messages
        stream = client.chat.completions.create(
            model=MODEL, messages=msgs, temperature=0.3, stream=True,
        )
        full_text = ""
        fallback_usage = None
        for chunk in stream:
            if hasattr(chunk, "usage") and chunk.usage:
                fallback_usage = chunk.usage
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                full_text += delta.content
                cleaned = re.sub(r'<\/?｜｜DSML｜｜[^>]*>', '', delta.content)
                cleaned = re.sub(r'<｜｜[^>]*>', '', cleaned)
                cleaned = re.sub(r'</｜｜[^>]*>', '', cleaned)
                yield cleaned
        answer = _clean_text(full_text)
        self.messages.append({"role": "assistant", "content": answer})
        yield {"usage": fallback_usage}

    def reset(self):
        self.messages = []


def _clean_text(text):
    """清理 DSML 标签和多余空白"""
    # 匹配所有 DSML 标签: <｜｜DSML｜｜...> 和 </｜｜DSML｜｜...>
    text = re.sub(r'<\/?｜｜DSML｜｜[^>]*>', '', text)
    # 匹配其他可能的工具调用残留
    text = re.sub(r'<｜｜[^>]*>', '', text)
    text = re.sub(r'</｜｜[^>]*>', '', text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ======== 兼容接口 ========

def answer_question(question):
    """单次问答（向后兼容）"""
    conv = Conversation()
    result = conv.ask(question)
    if isinstance(result, tuple):
        return result[0]
    return result


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "罗德岛是什么组织？"
    print(f"问题: {q}")
    answer = answer_question(q)
    print(f"\n回答:\n{answer}")

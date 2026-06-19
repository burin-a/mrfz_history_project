"""
自动测试流水线：出题人 → 被测 Agent → 审核员

用法:
    python auto_test.py                    # 完整流水线（生成 + 回答 + 评分）
    python auto_test.py --generate-only    # 只生成测试题
    python auto_test.py --review-only      # 只评分已有结果
    python auto_test.py --count 10         # 每类生成 10 题（默认 5）
    python auto_test.py --types T1 T6      # 只生成指定类型
"""
import json, os, random, time, sys, argparse, re
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

BASE_DIR = Path(__file__).parent
API_KEY = os.getenv("DEEPSEEK_API_KEY")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
TEST_DIR = BASE_DIR / "data" / "tests"


# ======== 向量检索（用于 Examiner 出题） ========

def _get_searcher():
    """延迟加载向量检索器"""
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
    from sentence_transformers import SentenceTransformer
    import chromadb

    embed_model = SentenceTransformer("BAAI/bge-large-zh-v1.5")

    class BGEEmbeddingFunction:
        def __init__(self, model):
            self.model = model
        def __call__(self, input):
            return self.model.encode(input, show_progress_bar=False, normalize_embeddings=True).tolist()
        def embed_query(self, input):
            return self.model.encode(input, show_progress_bar=False, normalize_embeddings=True).tolist()
        def name(self):
            return "bge-large-zh-v1.5"

    db_dir = BASE_DIR / "data" / "vectorstore"
    db_client = chromadb.PersistentClient(path=str(db_dir))
    collection = db_client.get_collection("arknights", embedding_function=BGEEmbeddingFunction(embed_model))
    return collection


def kb_search(query, n_results=5, where_filter=None):
    """从知识库检索"""
    collection = _get_searcher()
    kwargs = {"query_texts": [query], "n_results": n_results}
    if where_filter:
        kwargs["where"] = where_filter
    results = collection.query(**kwargs)
    return results


# ======== Examiner: 出题人 ========

TYPE_PROMPTS = {
    "T1": {
        "name": "事实检索",
        "desc": "精确事实查找",
        "prompt": """你是一个明日方舟剧情知识测试出题人。根据提供的知识库片段，生成一个**事实检索**类问题。

要求:
- 问题必须有明确的、唯一的答案
- 答案必须能从提供的片段中直接找到
- 问题应该涉及具体的剧情事件、时间、地点、人物行动等

输出 JSON 格式:
```json
{
  "question": "问题文本",
  "answer": "标准答案（精确）",
  "evidence": "知识库中的原文引用",
  "source": "出处描述"
}
```""",
    },
    "T2": {
        "name": "关系分析",
        "desc": "跨章节实体关系聚合",
        "prompt": """你是一个明日方舟剧情知识测试出题人。根据提供的知识库片段，生成一个**关系分析**类问题。

要求:
- 问题涉及两个或多个角色/组织之间的关系
- 需要综合多个片段才能完整回答
- 可以是敌对、同盟、师徒、亲情、友情等各种关系

输出 JSON 格式:
```json
{
  "question": "问题文本",
  "answer": "标准答案（详细说明关系）",
  "evidence": "知识库中的原文引用",
  "source": "出处描述"
}
```""",
    },
    "T3": {
        "name": "人物画像",
        "desc": "多场景综合归纳",
        "prompt": """你是一个明日方舟剧情知识测试出题人。根据提供的知识库片段，生成一个**人物画像**类问题。

要求:
- 问题要求分析某个角色的性格特点、动机、信念等
- 需要从多个角度综合分析
- 答案应体现深度理解

输出 JSON 格式:
```json
{
  "question": "问题文本",
  "answer": "标准答案（多维度分析）",
  "evidence": "知识库中的原文引用",
  "source": "出处描述"
}
```""",
    },
    "T4": {
        "name": "事件梳理",
        "desc": "时间线串联 + 因果推理",
        "prompt": """你是一个明日方舟剧情知识测试出题人。根据提供的知识库片段，生成一个**事件梳理**类问题。

要求:
- 问题涉及一个事件或一系列事件的来龙去脉
- 需要按时间线或因果关系梳理
- 可以涉及主线剧情、大型活动等

输出 JSON 格式:
```json
{
  "question": "问题文本",
  "answer": "标准答案（按时间/因果梳理）",
  "evidence": "知识库中的原文引用",
  "source": "出处描述"
}
```""",
    },
    "T5": {
        "name": "创意生成",
        "desc": "角色设定检索 + 生成",
        "prompt": """你是一个明日方舟剧情知识测试出题人。根据提供的知识库片段，生成一个**创意生成**类问题。

要求:
- 问题要求基于角色设定创作内容（小故事、对话、场景描写等）
- 需要准确把握角色的性格、背景、说话方式
- 创作内容必须符合角色设定

输出 JSON 格式:
```json
{
  "question": "问题文本",
  "answer": "标准答案（基于角色设定的创作范例）",
  "evidence": "用于参考的角色设定原文",
  "source": "出处描述"
}
```""",
    },
    "T6": {
        "name": "反幻觉/拒绝",
        "desc": "知识边界判断",
        "prompt": """你是一个明日方舟剧情知识测试出题人。请生成一个**反幻觉/拒绝**类问题。

这类问题专门测试 Agent 是否会编造不存在的内容。有两种出题方式:

方式 A: 问一个知识库中**不存在**的内容
- 例如问完全不存在的角色、事件、设定
- 预期回答应该是"知识库中暂未收录"

方式 B: 问一个存在但容易被混淆的内容
- 例如把两个不同角色混为一谈
- 预期回答应该能正确区分

请直接生成，不需要知识库片段。输出 JSON:
```json
{
  "question": "问题文本",
  "answer": "预期回答描述（应该怎么答）",
  "evidence": "无（幻觉测试题）",
  "source": "幻觉测试"
}
```""",
    },
}

# 用于 T6 幻觉测试的种子问题
HALLUCINATION_SEEDS = [
    "阿米娅是萨卡兹的女王吗？",
    "陈晖洁是龙门近卫局局长的女儿吗？",
    "W的真名是温蒂吗？",
    "塔露拉最终加入了罗德岛吗？",
    "博士就是特蕾西娅吗？",
    "凯尔希是萨卡兹人吗？",
    "德克萨斯和拉普兰德是亲姐妹吗？",
    "阿米娅的种族是萨卡兹吗？",
    "银灰是谢拉格的执政官吗？",
    "斯卡蒂是深海猎人队的队长吗？",
    "明日方舟中的'天灾'是一种自然现象吗？",
    "罗德岛的舰长是博士吗？",
    "年酱和夕是亲姐妹关系吗？",
    "迷迭香是凯尔希的女儿吗？",
    "能天使和德克萨斯在剧情中是恋人关系吗？",
    "整合运动最终被罗德岛彻底消灭了吗？",
    "博士在巴别塔时期是凯尔希的上级吗？",
    "普瑞赛斯是泰拉的原始居民吗？",
    "源石是泰拉上的天然矿物吗？",
    "霜叶是乌萨斯帝国的贵族吗？",
]


def _sample_kb_content(type_filter=None, n=5):
    """从知识库随机采样内容片段"""
    # 随机关键词采样
    keywords_pool = [
        "凯尔希", "阿米娅", "博士", "塔露拉", "W", "陈", "德克萨斯",
        "拉普兰德", "星熊", "斯卡蒂", "银灰", "年", "夕", "令",
        "迷迭香", "Logos", "特蕾西娅", "普瑞赛斯", "罗德岛",
        "萨卡兹", "乌萨斯", "维多利亚", "龙门", "切尔诺伯格",
        "叙拉古", "莱塔尼亚", "卡西米尔", "谢拉格", "伊比利亚",
        "整合运动", "巴别塔", "源石", "矿石病", "天灾",
        "离解复合", "相变临界", "反常光谱", "慈悲灯塔",
        "风暴瞭望", "破碎日冕", "惊霆无声", "恶兆湍流",
        "叙拉古人", "遗尘漫步", "水晶旅人", "巴别塔",
    ]
    random.shuffle(keywords_pool)
    chunks = []
    seen = set()
    for kw in keywords_pool[:10]:
        try:
            where = {"type": type_filter} if type_filter else None
            results = kb_search(kw, n_results=3, where_filter=where)
            for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
                # 用前50字去重
                key = doc[:50]
                if key not in seen:
                    seen.add(key)
                    chunks.append({
                        "text": doc[:800],
                        "type": meta.get("type", ""),
                        "source": meta.get("story_name", "") or meta.get("char_name", "") or meta.get("module_name", ""),
                    })
        except Exception:
            continue
        if len(chunks) >= n:
            break
    return chunks[:n]


def generate_question(type_key, index):
    """生成一道测试题"""
    info = TYPE_PROMPTS[type_key]

    if type_key == "T6":
        # 幻觉测试：直接用种子问题或让 LLM 生成
        seed = HALLUCINATION_SEEDS[index % len(HALLUCINATION_SEEDS)]
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": info["prompt"]},
                {"role": "user", "content": f"请基于以下种子问题，生成一道类似的幻觉测试题（不要和种子问题完全相同）：\n种子：{seed}\n\n请生成一道新的幻觉测试题。"},
            ],
            temperature=0.7,
        )
        text = resp.choices[0].message.content
    else:
        # 从知识库采样内容
        type_filter_map = {
            "T1": "story", "T2": "story", "T3": "character",
            "T4": "story", "T5": "character",
        }
        chunks = _sample_kb_content(type_filter_map.get(type_key), n=3)
        if not chunks:
            # fallback: 不过滤类型
            chunks = _sample_kb_content(n=3)

        context = "\n\n---\n\n".join(
            f"[片段{i+1}] 来源: {c['source']}\n{c['text']}"
            for i, c in enumerate(chunks)
        )
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": info["prompt"]},
                {"role": "user", "content": f"基于以下知识库片段，生成一道{info['name']}类测试题：\n\n{context}"},
            ],
            temperature=0.7,
        )
        text = resp.choices[0].message.content

    # 解析 JSON
    q_data = _extract_json(text)
    if q_data:
        q_data["type"] = type_key
        q_data["type_name"] = info["name"]
        q_data["index"] = index
        return q_data

    return None


def generate_test_suite(types=None, count=5):
    """生成完整测试套件"""
    if types is None:
        types = list(TYPE_PROMPTS.keys())

    suite = {}
    for t in types:
        info = TYPE_PROMPTS[t]
        print(f"  生成 {t} ({info['name']}) × {count} ...")
        questions = []
        for i in range(count):
            q = generate_question(t, i)
            if q:
                questions.append(q)
                print(f"    [{len(questions)}/{count}] {q['question'][:40]}...")
            else:
                print(f"    [{i+1}/{count}] 生成失败，跳过")
            time.sleep(0.5)
        suite[t] = questions
    return suite


# ======== Target: 被测 Agent ========

def run_target(question):
    """调用被测 Agent 回答问题"""
    from agent import Conversation
    conv = Conversation()
    result = conv.ask(question)
    if isinstance(result, tuple):
        answer, usage = result
        tokens = (usage.prompt_tokens or 0) + (usage.completion_tokens or 0)
    else:
        answer = result
        tokens = 0
    return answer, tokens


# ======== Reviewer: 审核员 ========

REVIEWER_PROMPT = """你是一个严格的测试审核员，负责评估 AI Agent 回答明日方舟剧情问题的质量。

## 评分维度（每项 0-10 分）

1. **事实准确率**：核心事实是否与标准答案一致？有无事实错误？
2. **幻觉检测**：是否编造了不存在的内容？（发现任何编造直接 0 分）
3. **引用正确性**：引用的对话、事件、章节名是否真实存在？
4. **完整性**：是否充分回答了问题？有无遗漏关键信息？
5. **拒绝能力**（仅 T6）：对超出知识范围的问题是否正确拒绝？

## 评分标准
- 9-10: 优秀，几乎无瑕疵
- 7-8: 良好，有小瑕疵但核心正确
- 5-6: 及格，有部分错误或遗漏
- 3-4: 不及格，有明显错误或幻觉
- 0-2: 严重错误，大量编造

## 输出格式

严格输出 JSON:
```json
{
  "scores": {
    "accuracy": 0,
    "hallucination": 0,
    "citation": 0,
    "completeness": 0
  },
  "overall": 0,
  "verdict": "PASS/FAIL",
  "strengths": ["优点1", "优点2"],
  "weaknesses": ["不足1", "不足2"],
  "details": "简要评语"
}
```

注意:
- T6 题目重点评估拒绝能力：如果 Agent 正确拒绝回答不存在的内容，所有分数应较高
- T5 题目（创意生成）允许合理的创作发挥，但角色设定必须准确
- overall = 各维度加权平均
- 总分 >= 7 为 PASS，< 7 为 FAIL"""


def _extract_json(text):
    """从 LLM 输出中提取 JSON（支持嵌套）"""
    # 方法1: 找到 ```json ... ``` 代码块
    code_match = re.search(r'```json\s*\n(.*?)```', text, re.DOTALL)
    if code_match:
        try:
            return json.loads(code_match.group(1))
        except json.JSONDecodeError:
            pass

    # 方法2: 找到最外层的 { ... } 配对
    start = text.find('{')
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i+1])
                except json.JSONDecodeError:
                    return None
    return None


def review_answer(question, expected, actual, type_key):
    """审核员评估回答"""
    type_info = TYPE_PROMPTS[type_key]

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": REVIEWER_PROMPT},
            {"role": "user", "content": f"""请评估以下回答的质量。

## 题目类型: {type_key} ({type_info['name']})

## 问题
{question}

## 标准答案
{expected}

## Agent 的回答
{actual}

请严格评分并输出 JSON。"""},
        ],
        temperature=0.3,
    )
    text = resp.choices[0].message.content

    review = _extract_json(text)
    if review:
        return review

    return {
        "scores": {"accuracy": 5, "hallucination": 5, "citation": 5, "completeness": 5},
        "overall": 5,
        "verdict": "FAIL",
        "strengths": [],
        "weaknesses": ["审核结果解析失败"],
        "details": text[:200],
    }


# ======== 流水线 ========

def _get_all_operator_names():
    """从 chunks 中提取所有干员名"""
    char_path = BASE_DIR / "data" / "chunks" / "character.json"
    names = set()
    if char_path.exists():
        with open(char_path, "r", encoding="utf-8") as f:
            chunks = json.load(f)
        for c in chunks:
            cn = c.get("char_name", "")
            if cn:
                names.add(cn)
    return names

def run_pipeline(types=None, count=5, generate_only=False, review_only=False, skip_review=False):
    """运行完整测试流水线"""
    TEST_DIR.mkdir(parents=True, exist_ok=True)

    if types is None:
        types = list(TYPE_PROMPTS.keys())

    # Step 1: 生成测试题
    suite_path = TEST_DIR / "test_suite.json"
    if not review_only:
        print("=" * 60)
        print("Step 1: 生成测试题")
        print("=" * 60)
        suite = generate_test_suite(types=types, count=count)
        # T5 筛选：随机选 10 道，角色不重复
        if "T5" in suite and len(suite["T5"]) > 10:
            import random as _rng
            _rng.shuffle(suite["T5"])
            seen_chars = set()
            filtered = []
            for q in suite["T5"]:
                # 提取角色名（从问题中找中文名字）
                chars_in_q = set()
                for name in _get_all_operator_names():
                    if name in q.get("question", ""):
                        chars_in_q.add(name)
                if not chars_in_q or chars_in_q.isdisjoint(seen_chars):
                    filtered.append(q)
                    seen_chars.update(chars_in_q)
                if len(filtered) >= 10:
                    break
            suite["T5"] = filtered
            print(f"  T5 筛选: {len(filtered)} 道（角色不重复）")
        with open(suite_path, "w", encoding="utf-8") as f:
            json.dump(suite, f, ensure_ascii=False, indent=2)
        total = sum(len(qs) for qs in suite.values())
        print(f"\n  共生成 {total} 道测试题 → {suite_path}")
    else:
        with open(suite_path, "r", encoding="utf-8") as f:
            suite = json.load(f)
        print(f"  加载已有测试题: {suite_path}")

    if generate_only:
        return suite

    # Step 2: 被测 Agent 回答
    results_path = TEST_DIR / "test_results.json"
    if review_only and results_path.exists():
        with open(results_path, "r", encoding="utf-8") as f:
            results = json.load(f)
        print(f"  加载已有结果: {results_path}")
    else:
        if review_only:
            print("  未找到 test_results.json，将重新运行被测 Agent")
        # 断点续传：加载已有结果
        if results_path.exists():
            with open(results_path, "r", encoding="utf-8") as f:
                results = json.load(f)
            print(f"  断点续传: 已有 {sum(len(r) for r in results.values())} 条结果")
        else:
            results = {}
        print("\n" + "=" * 60)
        print("Step 2: 被测 Agent 回答")
        print("=" * 60)
        total_tokens = 0
        for t, questions in suite.items():
            if t not in results:
                results[t] = []
            done_count = len(results[t])
            for i, q in enumerate(questions):
                if i < done_count:
                    print(f"  [{t}-{i+1}] 跳过（已有结果）")
                    continue
                q_text = q["question"]
                print(f"  [{t}-{i+1}/{len(questions)}] {q_text[:50]}...")
                start = time.time()
                try:
                    answer, tokens = run_target(q_text)
                    total_tokens += tokens
                except Exception as e:
                    answer = f"[错误] {e}"
                    tokens = 0
                elapsed = time.time() - start
                print(f"    → {elapsed:.1f}s, {tokens} tokens")
                results[t].append({
                    "question": q_text,
                    "expected_answer": q.get("answer", ""),
                    "agent_answer": answer,
                    "tokens": tokens,
                    "elapsed": round(elapsed, 1),
                })
                # 每题保存（支持断点续传）
                with open(results_path, "w", encoding="utf-8") as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)
                time.sleep(1)
        print(f"\n  总 tokens: {total_tokens} → {results_path}")

    # Step 3: 审核员评分（可跳过）
    if skip_review:
        reviews = {}
    else:
        print("\n" + "=" * 60)
        print("Step 3: 审核员评分")
        print("=" * 60)
        reviews = {}
        for t, questions in suite.items():
            reviews[t] = []
            r_list = results.get(t, [])
            for i, q in enumerate(questions):
                if i >= len(r_list):
                    break
                print(f"  评分 [{t}-{i+1}] ...")
                try:
                    review = review_answer(
                        q["question"],
                        q.get("answer", ""),
                        r_list[i]["agent_answer"],
                        t,
                    )
                    review["question"] = q["question"][:60]
                    reviews[t].append(review)
                    verdict = review.get("verdict", "?")
                    overall = review.get("overall", 0)
                    print(f"    → {verdict} ({overall}/10)")
                except Exception as e:
                    reviews[t].append({"verdict": "ERROR", "overall": 0, "details": str(e)})
                    print(f"    → ERROR: {e}")
                time.sleep(0.5)

    # Step 4: 生成报告 + MD 文档
    print("\n" + "=" * 60)
    print("Step 4: 生成报告")
    print("=" * 60)

    if reviews:
        report = _build_report(suite, results, reviews)
        report_path = TEST_DIR / "test_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        _print_report(report)
        print(f"\n  报告已保存: {report_path}")

    # 生成人工审查 MD 文档
    md_path = BASE_DIR / "test_review.md"
    _generate_review_md(suite, results, reviews, md_path)
    print(f"  人工审查文档: {md_path}")

    return report if reviews else None


def _build_report(suite, results, reviews):
    """构建结构化测试报告"""
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {},
        "by_type": {},
    }

    total_questions = 0
    total_pass = 0
    total_scores = {"accuracy": [], "hallucination": [], "citation": [], "completeness": []}

    for t in suite:
        r_list = reviews.get(t, [])
        q_list = suite[t]

        type_scores = {"accuracy": [], "hallucination": [], "citation": [], "completeness": []}
        pass_count = 0
        type_details = []

        for i, q in enumerate(q_list):
            if i >= len(r_list):
                break
            rev = r_list[i]
            scores = rev.get("scores", {})
            for dim in type_scores:
                type_scores[dim].append(scores.get(dim, 0))
            if rev.get("verdict") == "PASS":
                pass_count += 1

            type_details.append({
                "question": q["question"][:80],
                "verdict": rev.get("verdict", "?"),
                "overall": rev.get("overall", 0),
                "strengths": rev.get("strengths", []),
                "weaknesses": rev.get("weaknesses", []),
            })

        n = len(r_list)
        avg_scores = {dim: round(sum(vals)/n, 1) if n else 0 for dim, vals in type_scores.items()}
        pass_rate = round(pass_count / n * 100, 1) if n else 0

        report["by_type"][t] = {
            "name": TYPE_PROMPTS[t]["name"],
            "total": n,
            "pass": pass_count,
            "fail": n - pass_count,
            "pass_rate": pass_rate,
            "avg_scores": avg_scores,
            "details": type_details,
        }

        total_questions += n
        total_pass += pass_count
        for dim in total_scores:
            total_scores[dim].extend(type_scores[dim])

    n_total = total_questions or 1
    report["summary"] = {
        "total_questions": total_questions,
        "total_pass": total_pass,
        "total_fail": total_questions - total_pass,
        "overall_pass_rate": round(total_pass / n_total * 100, 1),
        "avg_scores": {dim: round(sum(vals)/len(vals), 1) if vals else 0 for dim, vals in total_scores.items()},
    }

    return report


def _print_report(report):
    """打印测试报告摘要"""
    s = report["summary"]
    print(f"\n{'='*60}")
    print(f"  测试报告  {report['timestamp']}")
    print(f"{'='*60}")
    print(f"  总题数: {s['total_questions']}")
    print(f"  通过:   {s['total_pass']}")
    print(f"  失败:   {s['total_fail']}")
    print(f"  通过率: {s['overall_pass_rate']}%")
    print(f"\n  平均分数:")
    dim_names = {"accuracy": "事实准确率", "hallucination": "幻觉检测", "citation": "引用正确性", "completeness": "完整性"}
    for dim, name in dim_names.items():
        score = s["avg_scores"].get(dim, 0)
        bar = "█" * int(score) + "░" * (10 - int(score))
        print(f"    {name}: {score}/10 [{bar}]")

    print(f"\n  各类型详情:")
    print(f"  {'类型':<6} {'名称':<10} {'题数':<5} {'通过':<5} {'通过率':<8} {'准确':<6} {'幻觉':<6} {'引用':<6} {'完整':<6}")
    print(f"  {'-'*62}")
    for t, data in report["by_type"].items():
        avg = data["avg_scores"]
        print(f"  {t:<6} {data['name']:<10} {data['total']:<5} {data['pass']:<5} {data['pass_rate']:<8} {avg.get('accuracy',0):<6} {avg.get('hallucination',0):<6} {avg.get('citation',0):<6} {avg.get('completeness',0):<6}")

    print(f"\n  失败题目详情:")
    has_failure = False
    for t, data in report["by_type"].items():
        for d in data["details"]:
            if d["verdict"] != "PASS":
                has_failure = True
                print(f"    [{t}] {d['question']}")
                if d.get("weaknesses"):
                    for w in d["weaknesses"]:
                        print(f"      ✗ {w}")
    if not has_failure:
        print(f"    全部通过！")


def _generate_review_md(suite, results, reviews, md_path):
    """生成人工审查用的 Markdown 文档"""
    lines = []
    lines.append("# 明日方舟剧情 Agent 测试 - 人工审查文档\n")
    lines.append(f"> 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append("---\n")

    for t in suite:
        type_info = TYPE_PROMPTS[t]
        questions = suite[t]
        r_list = results.get(t, [])
        rev_list = reviews.get(t, [])

        lines.append(f"## {t} - {type_info['name']} ({type_info['desc']})\n")

        for i, q in enumerate(questions):
            lines.append(f"### 题目 {i+1}\n")
            lines.append(f"**问题:** {q['question']}\n")
            lines.append(f"**标准答案:** {q.get('answer', '无')}\n")
            lines.append(f"**证据来源:** {q.get('evidence', '无')}\n")

            if i < len(r_list):
                r = r_list[i]
                lines.append(f"**Agent 回答:** {r.get('agent_answer', '无')}\n")
                lines.append(f"**耗时:** {r.get('elapsed', '?')}s | **Tokens:** {r.get('tokens', '?')}\n")

            if i < len(rev_list):
                rev = rev_list[i]
                scores = rev.get("scores", {})
                verdict = rev.get("verdict", "?")
                overall = rev.get("overall", 0)
                lines.append(f"**评分:** {verdict} ({overall}/10)\n")
                lines.append(f"- 事实准确率: {scores.get('accuracy', '?')}/10\n")
                lines.append(f"- 幻觉检测: {scores.get('hallucination', '?')}/10\n")
                lines.append(f"- 引用正确性: {scores.get('citation', '?')}/10\n")
                lines.append(f"- 完整性: {scores.get('completeness', '?')}/10\n")
                if rev.get("strengths"):
                    lines.append(f"**优点:**\n")
                    for s in rev["strengths"]:
                        lines.append(f"- {s}\n")
                if rev.get("weaknesses"):
                    lines.append(f"**不足:**\n")
                    for w in rev["weaknesses"]:
                        lines.append(f"- {w}\n")
                lines.append(f"**评语:** {rev.get('details', '无')}\n")
            else:
                lines.append("**评分:** 未评分\n")

            lines.append("---\n")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ======== CLI ========

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="明日方舟剧情 Agent 自动测试")
    parser.add_argument("--generate-only", action="store_true", help="只生成测试题")
    parser.add_argument("--review-only", action="store_true", help="只评分已有结果")
    parser.add_argument("--skip-review", action="store_true", help="跳过审核员评分")
    parser.add_argument("--count", type=int, default=5, help="每类生成题数（默认5）")
    parser.add_argument("--types", nargs="+", help="指定测试类型（如 T1 T2 T6）")
    args = parser.parse_args()

    print("╔══════════════════════════════════════════╗")
    print("║  明日方舟剧情 Agent 自动测试系统 v1.0    ║")
    print("╚══════════════════════════════════════════╝")

    run_pipeline(
        types=args.types,
        count=args.count,
        generate_only=args.generate_only,
        review_only=args.review_only,
        skip_review=args.skip_review,
    )

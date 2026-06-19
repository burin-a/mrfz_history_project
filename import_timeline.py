"""
将 PRTS 泰拉年表导入 ChromaDB 向量库
用法: python import_timeline.py
"""
import re
import json
import hashlib
from pathlib import Path
from sentence_transformers import SentenceTransformer
import chromadb

BASE_DIR = Path(__file__).parent
VECTOR_DB_DIR = BASE_DIR / "data" / "vectorstore"
TIMELINE_FILE = BASE_DIR / "data" / "timeline_raw.txt"
BATCH_SIZE = 50


def parse_timeline(text: str) -> list[dict]:
    """解析年表原始文本，返回结构化条目列表"""
    lines = text.strip().split("\n")

    # 移除空行和标题行（如"可确认的大致时间点"）
    lines = [l.strip() for l in lines if l.strip()]

    entries = []
    current_section = ""
    current_year = ""
    buffer = []

    def flush():
        nonlocal buffer
        if not buffer:
            return
        content = "\n".join(buffer).strip()
        if not content:
            buffer = []
            return
        # 生成唯一 id
        raw = f"{current_section}|{current_year}|{content[:50]}"
        uid = hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]
        entries.append({
            "id": f"timeline_{uid}",
            "text": content,
            "type": "timeline",
            "section": current_section,
            "year": current_year,
        })
        buffer = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # 跳过"可确认的大致时间点"等尾部注释
        if "可确认的大致时间点" in line or line.startswith("以下事件"):
            break

        # 检测年份行：匹配 "XXXX 年"、"约前 XXXX 年"、"前 XXXX 年" 等
        # 也匹配范围格式 "XXXX 年 ~ XXXX 年"、"XX 世纪 XX 年代"
        year_match = re.match(
            r"^("
            r"(约\s*)?(前\s*)?\d{3,5}\s*年"           # 1097 年、前 9000 年、约前 8000 年
            r"|结晶纪元之前"                            # 特殊纪元
            r"|前文明时期"                              # 特殊纪元
            r"|泰拉纪元前"                              # 特殊纪元
            r"|\d{1,2}\s*世纪\s*\d{2}\s*年代"          # 11 世纪 80 年代
            r"|12世纪"                                   # 12世纪
            r")",
            line
        )

        # 检测范围行
        range_match = re.match(
            r"^(约\s*)?(前\s*)?\d{3,5}\s*年\s*(~|－|—|–|-)\s*(前\s*)?\d{3,5}\s*年",
            line
        )

        # 检测具体日期行 (X月 X日)
        date_match = re.match(r"^(\d{1,2}\s*月\s*\d{1,2}\s*日)", line)

        if year_match:
            flush()
            current_year = line.strip()
            current_section = ""
            i += 1
            continue
        elif range_match:
            flush()
            current_year = line.strip()
            current_section = ""
            i += 1
            continue
        elif date_match:
            # 日期行通常属于当前年份段落，作为内容
            buffer.append(line)
            i += 1
            continue
        elif re.match(r"^(~|－|—|–|-)$", line.strip()):
            # 纯分隔符行，跳过
            i += 1
            continue
        else:
            buffer.append(line)
            i += 1
            continue

    flush()
    return entries


def main():
    print("读取年表原始文本...")
    raw = TIMELINE_FILE.read_text(encoding="utf-8")
    print(f"原始文本: {len(raw)} 字符, {len(raw.splitlines())} 行")

    print("解析年表...")
    entries = parse_timeline(raw)
    print(f"解析出 {len(entries)} 个时间线条目")

    if not entries:
        print("未解析出任何条目，退出")
        return

    # 找出最新年份（只看结晶纪元后的年份，排除"前"和"TT"日期）
    latest = ""
    for e in entries:
        y = e["year"]
        if "前" in y or "TT" in y:
            continue
        m = re.search(r"(\d{3,5})\s*年", y)
        if m:
            num = int(m.group(1))
            if 100 <= num <= 2000:  # 合理的泰拉纪元年份范围
                if num > int(latest or "0"):
                    latest = str(num)

    print(f"知识库截止到泰拉历 {latest} 年")

    # 加载 embedding 模型
    print("加载 embedding 模型 (bge-large-zh-v1.5)...")
    model = SentenceTransformer("BAAI/bge-large-zh-v1.5", local_files_only=True)

    # 生成 embeddings
    print("生成向量...")
    texts = [e["text"] for e in entries]
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)

    # 连接 ChromaDB
    print("连接向量库...")
    client = chromadb.PersistentClient(path=str(VECTOR_DB_DIR))
    collection = client.get_or_create_collection(
        name="arknights",
        metadata={"description": "明日方舟剧情向量库 v1.0"},
    )

    # 分批 upsert
    print("导入向量库...")
    for i in range(0, len(entries), BATCH_SIZE):
        batch = entries[i:i + BATCH_SIZE]
        batch_embeddings = embeddings[i:i + BATCH_SIZE].tolist()
        collection.upsert(
            documents=[e["text"] for e in batch],
            ids=[e["id"] for e in batch],
            embeddings=batch_embeddings,
            metadatas=[{k: v for k, v in e.items() if k not in ("id", "text")} for e in batch],
        )
        print(f"  已导入 {min(i + BATCH_SIZE, len(entries))}/{len(entries)}")

    # 更新 meta.json 中的 timeline 统计
    meta_path = BASE_DIR / "data" / "chunks" / "meta.json"
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        meta["timeline_entries"] = len(entries)
        meta["timeline_latest_year"] = latest
        meta["by_type"]["timeline"] = len(entries)
        meta["total_chunks"] = sum(meta["by_type"].values())
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print(f"已更新 meta.json")

    print(f"完成! 共导入 {len(entries)} 条年表数据，截止泰拉历 {latest} 年")


if __name__ == "__main__":
    main()

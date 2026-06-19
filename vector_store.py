"""
向量索引构建器（支持增量更新）

从 data/chunks/ 读取纯文本块，构建/更新 ChromaDB 向量索引

用法:
    python vector_store.py          # 增量更新（默认，只对变更块计算向量）
    python vector_store.py --full   # 全量重建（删除旧库重新计算全部向量）
"""
import json, os, argparse
from pathlib import Path

BASE_DIR = Path(__file__).parent
CHUNKS_DIR = BASE_DIR / "data" / "chunks"
VECTOR_DB_DIR = BASE_DIR / "data" / "vectorstore"
BATCH_SIZE = 100


def load_chunks():
    """加载所有数据块"""
    documents = []
    metadatas = []
    ids = []

    if not CHUNKS_DIR.exists():
        return documents, metadatas, ids

    for fname in sorted(os.listdir(CHUNKS_DIR)):
        if not fname.endswith(".json") or fname == "meta.json":
            continue
        fpath = CHUNKS_DIR / fname
        with open(fpath, "r", encoding="utf-8") as f:
            chunks = json.load(f)

        for chunk in chunks:
            text = chunk.pop("text", "")
            chunk_id = chunk.pop("id", "")
            if not text.strip():
                continue
            documents.append(text)
            metadatas.append(chunk)
            ids.append(chunk_id)

    return documents, metadatas, ids


def main():
    parser = argparse.ArgumentParser(description="向量索引构建器")
    parser.add_argument("--full", action="store_true", help="全量重建（删除旧库后重新计算全部）")
    args = parser.parse_args()

    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    from sentence_transformers import SentenceTransformer
    import chromadb

    print("=" * 60)
    print("向量索引构建器 (bge-large-zh-v1.5 + ChromaDB)")
    print("=" * 60)

    print("\n[1/3] 加载数据块...")
    documents, metadatas, ids = load_chunks()
    print(f"  总块数: {len(documents)}")

    if not documents:
        print("[ERROR] 无数据块。请先运行 python github_crawler.py")
        return

    avg_len = sum(len(d) for d in documents) / len(documents)
    print(f"  平均长度: {avg_len:.0f} 字符")

    # 类型分布
    type_counts = {}
    for m in metadatas:
        t = m.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
    for t, c in sorted(type_counts.items()):
        print(f"  {t}: {c}")

    print("\n[2/3] 加载嵌入模型...")
    print("  bge-large-zh-v1.5 ...")
    embed_model = SentenceTransformer("BAAI/bge-large-zh-v1.5")
    print("  模型加载完成")

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

    embedding_fn = BGEEmbeddingFunction(embed_model)

    client = chromadb.PersistentClient(path=str(VECTOR_DB_DIR))

    # 全量重建模式
    if args.full:
        return _full_rebuild(client, embedding_fn, documents, metadatas, ids)

    # 尝试增量更新
    existing = _load_existing(client, embedding_fn)

    if existing is None:
        # 库不存在，走全量
        print("\n  未检测到已有向量库，执行全量构建...")
        return _full_rebuild(client, embedding_fn, documents, metadatas, ids)

    existing_map, existing_meta_map = existing

    # 对比差异
    print("\n[3/3] 对比已有数据，计算增量...")
    new_id_set = set(ids)

    to_upsert_ids = []
    to_upsert_docs = []
    to_upsert_meta = []
    unchanged = 0

    for i, cid in enumerate(ids):
        existing_meta = existing_meta_map.get(cid, {})
        if cid in existing_map and existing_map[cid] == documents[i] and existing_meta == metadatas[i]:
            unchanged += 1
        else:
            to_upsert_ids.append(cid)
            to_upsert_docs.append(documents[i])
            to_upsert_meta.append(metadatas[i])

    deleted_ids = [eid for eid in existing_map if eid not in new_id_set]

    print(f"  未变化（跳过）: {unchanged}")
    print(f"  新增/变更: {len(to_upsert_ids)}")
    print(f"  待删除: {len(deleted_ids)}")

    collection = client.get_or_create_collection(
        name="arknights",
        embedding_function=embedding_fn,
        metadata={"description": "明日方舟剧情向量库 v1.0"},
    )

    # 无变更
    if not to_upsert_ids and not deleted_ids:
        print(f"\n  向量库已是最新，无需更新。当前 {collection.count()} 文档。")
        return

    # 仅对变更/新增块计算向量并写入
    if to_upsert_ids:
        print(f"\n  正在对 {len(to_upsert_ids)} 个变更块计算向量...")
        total = len(to_upsert_ids)
        for i in range(0, total, BATCH_SIZE):
            batch_docs = to_upsert_docs[i : i + BATCH_SIZE]
            batch_meta = to_upsert_meta[i : i + BATCH_SIZE]
            batch_ids = to_upsert_ids[i : i + BATCH_SIZE]
            collection.upsert(
                documents=batch_docs,
                metadatas=batch_meta,
                ids=batch_ids,
            )
            done = min(i + BATCH_SIZE, total)
            if done % 500 == 0 or done >= total:
                print(f"  进度: {done}/{total}")

    # 删除废弃文档
    if deleted_ids:
        print(f"\n  删除 {len(deleted_ids)} 个废弃文档...")
        for i in range(0, len(deleted_ids), BATCH_SIZE):
            collection.delete(ids=deleted_ids[i : i + BATCH_SIZE])

    print(f"\n{'=' * 60}")
    print("增量更新完成!")
    print(f"  总文档: {collection.count()}")
    print(f"  本次计算: {len(to_upsert_ids)} 块")
    print(f"  存储: {VECTOR_DB_DIR}")
    print(f"{'=' * 60}")

    _run_test(collection)


def _load_existing(client, embedding_fn):
    """读取已有向量库中所有文档，返回 ({id: text}, {id: metadata}) 元组；库不存在返回 None"""
    try:
        collection = client.get_collection(
            name="arknights", embedding_function=embedding_fn,
        )
        if collection.count() == 0:
            return {}, {}
        print(f"\n[2.5/3] 读取已有向量库 ({collection.count()} 文档)...")
        existing = collection.get(include=["documents", "metadatas"])
        existing_map = dict(zip(existing["ids"], existing["documents"]))
        existing_meta_map = dict(zip(existing["ids"], existing["metadatas"]))
        print(f"  已有文档: {len(existing_map)}")
        return existing_map, existing_meta_map
    except Exception:
        return None


def _full_rebuild(client, embedding_fn, documents, metadatas, ids):
    """全量重建：删除旧库 → 重新计算全部向量"""
    print("\n[3/3] 全量重建向量库...")

    try:
        client.delete_collection("arknights")
        print("  已清除旧 collection")
    except Exception:
        pass

    collection = client.get_or_create_collection(
        name="arknights",
        embedding_function=embedding_fn,
        metadata={"description": "明日方舟剧情向量库 v1.0"},
    )

    total = len(documents)
    for i in range(0, total, BATCH_SIZE):
        batch_docs = documents[i : i + BATCH_SIZE]
        batch_meta = metadatas[i : i + BATCH_SIZE]
        batch_ids = ids[i : i + BATCH_SIZE]
        collection.upsert(
            documents=batch_docs,
            metadatas=batch_meta,
            ids=batch_ids,
        )
        done = min(i + BATCH_SIZE, total)
        if done % 500 == 0 or done >= total:
            print(f"  进度: {done}/{total}")

    print(f"\n{'=' * 60}")
    print("全量重建完成!")
    print(f"  总文档: {collection.count()}")
    print(f"  存储: {VECTOR_DB_DIR}")
    print(f"{'=' * 60}")

    _run_test(collection)


def _run_test(collection):
    """语义检索测试"""
    print("\n[测试] 语义检索...")
    test_queries = ["凯尔希和萨卡兹的关系", "罗德岛是什么组织"]
    for q in test_queries:
        results = collection.query(query_texts=[q], n_results=3)
        print(f"\n  查询: {q}")
        for i, (doc, meta, dist) in enumerate(
            zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ):
            name = (
                meta.get("story_name")
                or meta.get("char_name")
                or meta.get("module_name")
                or meta.get("skin_name")
                or ""
            )
            src = meta.get("source", "")
            print(f"    [{i+1}] {name} ({src}) 相关度={1-dist:.2f}")
            print(f"        {doc[:120]}...")


if __name__ == "__main__":
    main()

"""
从本地 ArknightsGameData 仓库解析明日方舟剧情数据

数据源: https://github.com/Kengxxiao/ArknightsGameData (需先 git clone 到上级目录)

用法:
    python github_crawler.py          # 全量解析
    python github_crawler.py --check  # 只检查状态
"""
import json, os, re, sys, argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CHUNKS_DIR = DATA_DIR / "chunks"
REPO_DIR = BASE_DIR.parent / "ArknightsGameData" / "zh_CN" / "gamedata"
REPO_GIT_DIR = BASE_DIR.parent / "ArknightsGameData"

STORY_TABLE = REPO_DIR / "excel" / "story_table.json"
ACTIVITY_TABLE = REPO_DIR / "excel" / "activity_table.json"
UNIEQUIP_TABLE = REPO_DIR / "excel" / "uniequip_table.json"
CHARACTER_TABLE = REPO_DIR / "excel" / "character_table.json"
HANDBOOK_TABLE = REPO_DIR / "excel" / "handbook_info_table.json"
SKIN_TABLE = REPO_DIR / "excel" / "skin_table.json"
CHARWORD_TABLE = REPO_DIR / "excel" / "charword_table.json"
STORY_DIR = REPO_DIR / "story"

MAX_CHUNK_CHARS = 800

# 主线章节名映射（chapter_table 中的数据）
MAIN_CHAPTER_NAMES = {
    # Act initium 觉醒
    "level_main_00": "第零章 黑暗时代（上）",
    "level_main_01": "第一章 黑暗时代（下）",
    # Act initium 觉醒（续）
    "level_main_02": "第二章 异卵同生",
    "level_main_03": "第三章 二次呼吸",
    "level_main_04": "第四章 急性衰竭",
    # Act I 幻灭
    "level_main_05": "第五章 靶向药物",
    "level_main_06": "第六章 局部坏死",
    "level_main_07": "第七章 苦难摇篮",
    "level_main_08": "第八章 怒号光明",
    # Act II 残阳
    "level_main_09": "第九章 风暴瞭望",
    "level_main_10": "第十章 破碎日冕",
    "level_main_11": "第十一章 淬火尘霾",
    "level_main_12": "第十二章 惊霆无声",
    "level_main_13": "第十三章 恶兆湍流",
    "level_main_14": "第十四章 慈悲灯塔",
    # Act III 裂变
    "level_main_15": "第十五章 离解复合",
    "level_main_16": "第十六章 反常光谱",
    "level_main_17": "第十七章 相变临界",
}


def _safe_load_json(path, default=None):
    """安全加载 JSON 文件，损坏时返回默认值而非崩溃"""
    if default is None:
        default = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [警告] 加载 {path.name} 失败: {e}，跳过此数据源")
        return default


# ======== .txt 剧本解析 ========

def parse_story_txt(txt_path):
    """解析 .txt 剧本文件，提取对话文本"""
    with open(txt_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = []
    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        # [name="角色名"]  对话内容
        m = re.match(r'\[name="([^"]+)"\]\s*(.*)', line)
        if m:
            name = m.group(1)
            text = m.group(2).strip()
            if text:
                lines.append(f"{name}：{text}")
            continue
        # [nameText text="文本"]
        m2 = re.match(r'\[nameText\s+text="([^"]+)"', line)
        if m2:
            lines.append(m2.group(1))
            continue
        # [Option] 选项文本
        m3 = re.match(r'\[Option\s+text="([^"]+)"', line)
        if m3:
            lines.append(f"（选项）{m3.group(1)}")

    return "\n".join(lines)


# ======== 分块 ========

def split_into_chunks(text, max_chars=MAX_CHUNK_CHARS):
    """将长文本按对话边界分块"""
    if len(text) <= max_chars:
        return [text] if text.strip() else []

    paragraphs = [p for p in text.split("\n") if p.strip()]
    if not paragraphs:
        return []

    chunks = []
    current = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)
        if current_len + para_len + 1 > max_chars and current:
            chunks.append("\n".join(current))
            current = [para]
            current_len = para_len
        else:
            current.append(para)
            current_len += para_len + 1

    if current:
        chunks.append("\n".join(current))

    return chunks


# ======== 章节名解析 ========

def _load_activity_names():
    """从 activity_table.json 加载活动 ID → 活动名映射（递归遍历嵌套结构）"""
    names = {}
    if not ACTIVITY_TABLE.exists():
        return names
    at = _safe_load_json(ACTIVITY_TABLE)

    def _walk(obj):
        if isinstance(obj, dict):
            # 当前层可能就是活动条目
            if obj.get("id") and obj.get("name"):
                names[obj["id"]] = obj["name"]
            for v in obj.values():
                _walk(v)

    _walk(at)
    return names


# 时区：明日方舟 CN 服使用 UTC+8
_CN_TZ = timezone(timedelta(hours=8))


def _load_activity_dates():
    """从 activity_table.json 的 basicInfo 加载活动 ID → 现实开放时间（YYYY年M月）"""
    dates = {}
    if not ACTIVITY_TABLE.exists():
        return dates
    at = _safe_load_json(ACTIVITY_TABLE)

    basic_info = at.get("basicInfo", {})
    for act_id, info in basic_info.items():
        if not isinstance(info, dict):
            continue
        ts = info.get("startTime")
        if ts and isinstance(ts, (int, float)) and ts > 0:
            dt = datetime.fromtimestamp(ts, tz=_CN_TZ)
            dates[act_id] = f"{dt.year}年{dt.month}月"

    return dates


def _extract_activity_id(story_txt):
    """从 source 路径提取活动 ID（如 activities/act18d0/... → act18d0）"""
    m = re.search(r'activities/([^/]+)/', story_txt)
    return m.group(1) if m else ""


def _resolve_story_name(story_txt, activity_names):
    """根据 source 路径推断章节/活动名"""
    # 主线章节
    for key, name in MAIN_CHAPTER_NAMES.items():
        if key in story_txt:
            return name

    # 活动章节：从路径提取活动 ID（如 activities/act18d0/...）
    m = re.search(r'activities/([^/]+)/', story_txt)
    if m:
        act_id = m.group(1)
        # 先查 activity_table
        if act_id in activity_names:
            return activity_names[act_id]
        # mini/side 活动可能不在 activity_table 中，保留 ID
        return f"活动 {act_id}"

    # 集成战略
    for sk in ["ro1", "ro2", "ro3", "ro4", "ro5"]:
        if sk in story_txt:
            rogue_names = {
                "ro1": "傀影与猩红孤钻", "ro2": "尘影余音",
                "ro3": "水月与深蓝之树", "ro4": "萨卡兹的无终奇语",
                "ro5": "萨米肉鸽",
            }
            return f"[集成战略] {rogue_names.get(sk, '未知')}"

    # 干员密录
    if "memory/" in story_txt:
        return "干员密录"

    return ""


# ======== 剧情 txt ========

def process_all_stories(activity_names, activity_dates):
    """遍历 story/ 下所有 .txt 文件"""
    chunks = []
    stats = {"txt_files": 0, "empty": 0, "total_chunks": 0}

    if not STORY_DIR.exists():
        print(f"  [WARN] story 目录不存在: {STORY_DIR}")
        return chunks, stats

    for root, dirs, fnames in os.walk(STORY_DIR):
        # 跳过 [uc]info 目录（元信息，非剧情）
        dirs[:] = [d for d in dirs if d != "[uc]info" and d not in ("roguelike", "rogue")]

        for fname in sorted(fnames):
            if not fname.endswith(".txt"):
                continue

            txt_path = Path(root) / fname
            rel_path = txt_path.relative_to(STORY_DIR).with_suffix("")
            story_txt = str(rel_path).replace("\\", "/")

            stats["txt_files"] += 1

            text = parse_story_txt(txt_path)
            if not text.strip():
                stats["empty"] += 1
                continue

            story_name = _resolve_story_name(story_txt, activity_names)
            act_id = _extract_activity_id(story_txt)
            real_date = activity_dates.get(act_id, "")

            base_id = story_txt.replace("/", "_")
            sub_chunks = split_into_chunks(text)
            for i, chunk in enumerate(sub_chunks):
                chunk_data = {
                    "id": f"{base_id}_{i}",
                    "type": "story",
                    "source": story_txt,
                    "story_name": story_name,
                }
                if act_id:
                    chunk_data["activity_id"] = act_id
                if real_date:
                    chunk_data["real_date"] = real_date
                chunk_data["text"] = chunk
                chunks.append(chunk_data)

    stats["total_chunks"] = len(chunks)
    return chunks, stats


# ======== 模组 ========

def process_modules():
    if not UNIEQUIP_TABLE.exists():
        return []

    ut = _safe_load_json(UNIEQUIP_TABLE)

    equip_dict = ut.get("equipDict", {})
    if not equip_dict:
        return []

    char_names = _load_char_names()

    chunks = []
    for k, v in equip_dict.items():
        if not isinstance(v, dict):
            continue
        desc = v.get("uniEquipDesc", "")
        if not desc or len(desc) < 50:
            continue

        char_id = v.get("charId", "")
        char_name = char_names.get(char_id, char_id)

        chunks.append({
            "id": f"module_{k}",
            "type": "module",
            "source": "uniequip_table",
            "char_id": char_id,
            "char_name": char_name,
            "module_name": v.get("uniEquipName", ""),
            "module_type": v.get("typeName2", ""),
            "text": desc,
        })

    return chunks


# ======== 干员档案（从 handbook_info_table.json）========

def process_handbook():
    """从 handbook_info_table.json 提取干员档案和密录"""
    if not HANDBOOK_TABLE.exists():
        return []

    hb = _safe_load_json(HANDBOOK_TABLE)

    handbook_dict = hb.get("handbookDict", {})
    char_names = _load_char_names()

    chunks = []
    counter = 0

    for char_id, char_data in handbook_dict.items():
        if not isinstance(char_data, dict):
            continue

        char_name = char_names.get(char_id, char_id)

        # 1. 干员档案（storyTextAudio）
        story_audio = char_data.get("storyTextAudio", [])
        for section in story_audio:
            if not isinstance(section, dict):
                continue
            stories = section.get("stories", [])
            title = section.get("storyTitle", "")
            for story in stories:
                if not isinstance(story, dict):
                    continue
                text = story.get("storyText", "")
                if not text or len(text) < 30:
                    continue

                full_text = f"【{char_name} - {title}】\n{text}"
                sub_chunks = split_into_chunks(full_text, max_chars=1000)
                for i, chunk in enumerate(sub_chunks):
                    counter += 1
                    chunks.append({
                        "id": f"handbook_{counter}",
                        "type": "character",
                        "source": "handbook_info_table",
                        "char_id": char_id,
                        "char_name": char_name,
                        "story_name": title,
                        "text": chunk,
                    })

        # 2. 干员密录简介（handbookAvgList）
        avg_list = char_data.get("handbookAvgList", [])
        for story_set in avg_list:
            if not isinstance(story_set, dict):
                continue
            set_name = story_set.get("storySetName", "")
            if not set_name:
                continue

            avg_entries = story_set.get("avgList", [])
            for entry in avg_entries:
                if not isinstance(entry, dict):
                    continue
                intro = entry.get("storyIntro", "")
                if not intro or len(intro) < 20:
                    continue

                counter += 1
                chunks.append({
                    "id": f"avg_{counter}",
                    "type": "character",
                    "source": "handbook_info_table",
                    "char_id": char_id,
                    "char_name": char_name,
                    "story_name": f"干员密录：{set_name}",
                    "text": f"【{char_name} - {set_name}】{intro}",
                })

    return chunks


# ======== 皮肤描述 ========

def process_skins():
    if not SKIN_TABLE.exists():
        return []

    sk = _safe_load_json(SKIN_TABLE)

    skins_dict = sk.get("charSkins", {})
    char_names = _load_char_names()

    chunks = []
    for k, v in skins_dict.items():
        if not isinstance(v, dict):
            continue

        # 描述在 displaySkin 子对象中
        display = v.get("displaySkin", {})
        if not isinstance(display, dict):
            continue

        char_id = v.get("charId", "")
        char_name = char_names.get(char_id, char_id)

        parts = []
        skin_name = display.get("skinName", "")
        content = display.get("content", "")
        description = display.get("description", "")
        dialog = display.get("dialog", "")

        if content:
            parts.append(content)
        if description:
            parts.append(description)
        if dialog:
            parts.append(f"对话：{dialog}")

        text = "\n".join(parts)
        if len(text) < 30:
            continue

        chunks.append({
            "id": f"skin_{k}",
            "type": "skin",
            "source": "skin_table",
            "char_id": char_id,
            "char_name": char_name,
            "skin_name": skin_name,
            "text": text,
        })

    return chunks


# ======== 干员语音 ========

def process_charword():
    """从 charword_table.json 提取干员语音文本"""
    if not CHARWORD_TABLE.exists():
        return []

    cw = _safe_load_json(CHARWORD_TABLE)

    words_dict = cw.get("charWords", {})
    char_names = _load_char_names()

    chunks = []
    for k, v in words_dict.items():
        if not isinstance(v, dict):
            continue

        voice_text = v.get("voiceText", "")
        voice_title = v.get("voiceTitle", "")
        char_id = v.get("charId", "")
        char_name = char_names.get(char_id, char_id)

        if not voice_text or len(voice_text) < 15:
            continue

        # 跳过纯系统文本（如"___"、"......"）
        if re.match(r'^[\s.、，。！？,_\-]+$', voice_text):
            continue

        chunks.append({
            "id": f"voice_{k}",
            "type": "character",
            "source": "charword_table",
            "char_id": char_id,
            "char_name": char_name,
            "story_name": f"语音：{voice_title}",
            "text": f"【{char_name} - {voice_title}】{voice_text}",
        })

    return chunks


# ======== 集成战略剧情 ========

def process_roguelike(activity_names, activity_dates):
    """解析集成战略剧情（作为补充数据）"""
    chunks = []
    rogue_dir = STORY_DIR / "obt" / "roguelike"
    rogue_sub_dir = STORY_DIR / "obt" / "rogue"

    season_dirs = []
    if rogue_dir.exists():
        season_dirs.append(rogue_dir)
    if rogue_sub_dir.exists():
        season_dirs.append(rogue_sub_dir)

    if not season_dirs:
        return chunks

    for base_dir in season_dirs:
        for root, dirs, fnames in os.walk(base_dir):
            for fname in sorted(fnames):
                if not fname.endswith(".txt"):
                    continue

                txt_path = Path(root) / fname
                rel_path = txt_path.relative_to(STORY_DIR).with_suffix("")
                story_txt = str(rel_path).replace("\\", "/")

                text = parse_story_txt(txt_path)
                if not text.strip():
                    continue

                story_name = _resolve_story_name(story_txt, activity_names)
                act_id = _extract_activity_id(story_txt)
                real_date = activity_dates.get(act_id, "")

                base_id = story_txt.replace("/", "_")
                sub_chunks = split_into_chunks(text)
                for i, chunk in enumerate(sub_chunks):
                    chunk_data = {
                        "id": f"rogue_{base_id}_{i}",
                        "type": "roguelike",
                        "source": story_txt,
                        "story_name": story_name,
                    }
                    if act_id:
                        chunk_data["activity_id"] = act_id
                    if real_date:
                        chunk_data["real_date"] = real_date
                    chunk_data["text"] = chunk
                    chunks.append(chunk_data)

    return chunks


# ======== 工具函数 ========

def _load_char_names():
    char_names = {}
    if CHARACTER_TABLE.exists():
        ct = _safe_load_json(CHARACTER_TABLE)
        for k, v in ct.items():
            if isinstance(v, dict) and v.get("name"):
                char_names[k] = v["name"]
    return char_names


def _save_repo_sha():
    """记录当前仓库 commit SHA 用于更新检测"""
    import subprocess
    sha_file = DATA_DIR / ".last_repo_sha"
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_GIT_DIR),
            capture_output=True, text=True, timeout=10,
        )
        sha = result.stdout.strip()
        if sha:
            sha_file.parent.mkdir(parents=True, exist_ok=True)
            sha_file.write_text(sha)
            print(f"  已记录仓库 SHA: {sha[:12]}")
    except Exception:
        pass


# ======== 现实时间覆盖范围摘要 ========

def _build_realtime_summary(activity_dates, activity_names, all_chunks):
    """生成知识库现实时间覆盖范围的摘要 chunk，帮助 Agent 回答"最新活动"等问题"""
    if not activity_dates:
        return None

    # 解析日期为可排序的 (year, month) 元组
    def _parse_ym(s):
        m = re.match(r'(\d+)年(\d+)月', s)
        return (int(m.group(1)), int(m.group(2))) if m else (0, 0)

    # 找出最晚开放的活动
    sorted_dates = sorted(activity_dates.items(), key=lambda x: _parse_ym(x[1]), reverse=True)
    latest_act_id, latest_date = sorted_dates[0]
    latest_name = activity_names.get(latest_act_id, latest_act_id)

    # 找出最早的
    earliest_date = sorted_dates[-1][1]

    # 按年份分组统计
    year_counts = {}
    for _, d in activity_dates.items():
        ym = _parse_ym(d)
        if ym[0]:
            year_counts.setdefault(ym[0], 0)
            year_counts[ym[0]] += 1

    # 收集最近 5 个活动（按开放时间倒序）
    recent_lines = []
    for act_id, d in sorted_dates[:5]:
        name = activity_names.get(act_id, act_id)
        recent_lines.append(f"  - {name}（{act_id}）：{d}")

    text = (
        "【知识库现实时间覆盖范围】\n"
        "以下是本知识库中游戏活动对应的现实世界（中国服）开放时间信息。\n"
        f"- 数据覆盖现实时间范围：{earliest_date} 至 {latest_date}\n"
        f"- 最新活动：{latest_name}（{latest_act_id}），开放时间 {latest_date}\n"
        f"- 活动总数：{len(activity_dates)}\n"
        f"- 各年份活动数量：{', '.join(f'{y}年{c}个' for y, c in sorted(year_counts.items()))}\n"
        "\n最近开放的活动（按时间倒序）：\n"
        + "\n".join(recent_lines) + "\n"
        "\n注意：上述现实开放时间来源于 activity_table.json 的 basicInfo.startTime 字段。"
        '当用户询问「最新活动」「某年某月的活动」「现实时间」时，请参考以上信息。'
        "当用户询问泰拉历年份或游戏内时间线时，请使用各剧情块中的 year 字段。"
    )

    return {
        "id": "realtime_summary_0",
        "type": "story",
        "source": "system_generated/realtime_summary",
        "story_name": "知识库现实时间覆盖范围",
        "real_date": latest_date,
        "text": text,
    }


# ======== 主流程 ========

def main():
    parser = argparse.ArgumentParser(description="从 ArknightsGameData 解析剧情数据")
    parser.add_argument("--check", action="store_true", help="只检查状态")
    args = parser.parse_args()

    print("=" * 60)
    print("明日方舟剧情数据解析器 (ArknightsGameData)")
    print("=" * 60)

    if not REPO_DIR.exists():
        print(f"\n[ERROR] 仓库不存在: {REPO_DIR}")
        print("请先执行:")
        print("  git clone --depth 1 --filter=blob:none --sparse \\")
        print("    https://github.com/Kengxxiao/ArknightsGameData.git ../ArknightsGameData")
        print("  cd ../ArknightsGameData")
        print("  git sparse-checkout set zh_CN/gamedata/story zh_CN/gamedata/excel")
        return

    print(f"  仓库: {REPO_DIR}")

    if args.check:
        print("\n--- 状态检查 ---")
        txt_count = sum(1 for _, _, fn in os.walk(STORY_DIR) for f in fn if f.endswith(".txt"))
        print(f"  剧情 txt 文件: {txt_count}")
        print(f"  story_table.json: {'✓' if STORY_TABLE.exists() else '✗'}")
        print(f"  activity_table.json: {'✓' if ACTIVITY_TABLE.exists() else '✗'}")
        print(f"  uniequip_table.json: {'✓' if UNIEQUIP_TABLE.exists() else '✗'}")
        print(f"  character_table.json: {'✓' if CHARACTER_TABLE.exists() else '✗'}")
        print(f"  handbook_info_table.json: {'✓' if HANDBOOK_TABLE.exists() else '✗'}")
        print(f"  skin_table.json: {'✓' if SKIN_TABLE.exists() else '✗'}")
        print(f"  charword_table.json: {'✓' if CHARWORD_TABLE.exists() else '✗'}")
        if CHUNKS_DIR.exists():
            meta_path = CHUNKS_DIR / "meta.json"
            if meta_path.exists():
                meta = _safe_load_json(meta_path)
                print(f"  已有 chunks: {meta.get('total_chunks', '?')}")
        return

    # 加载活动名映射
    print("\n[0/8] 加载活动名映射...")
    activity_names = _load_activity_names()
    print(f"  活动名: {len(activity_names)}")

    activity_dates = _load_activity_dates()
    print(f"  活动日期: {len(activity_dates)}")

    # 解析剧情
    print("\n[1/8] 解析剧情文本...")
    story_chunks, story_stats = process_all_stories(activity_names, activity_dates)
    print(f"  txt 文件: {story_stats['txt_files']}")
    print(f"  空文件: {story_stats['empty']}")
    print(f"  剧情块: {story_stats['total_chunks']}")

    # 模组
    print("\n[2/8] 解析模组数据...")
    module_chunks = process_modules()
    print(f"  模组块: {len(module_chunks)}")

    # 干员档案 + 密录
    print("\n[3/8] 解析干员档案和密录...")
    handbook_chunks = process_handbook()
    print(f"  档案/密录块: {len(handbook_chunks)}")

    # 皮肤描述
    print("\n[4/8] 解析皮肤描述...")
    skin_chunks = process_skins()
    print(f"  皮肤描述块: {len(skin_chunks)}")

    # 干员语音
    print("\n[5/8] 解析干员语音...")
    voice_chunks = process_charword()
    print(f"  语音块: {len(voice_chunks)}")

    # 集成战略
    print("\n[6/8] 解析集成战略剧情...")
    rogue_chunks = process_roguelike(activity_names, activity_dates)
    print(f"  集成战略块: {len(rogue_chunks)}")

    # 合并所有块
    all_chunks = story_chunks + module_chunks + handbook_chunks + skin_chunks + voice_chunks + rogue_chunks

    # 生成现实时间覆盖范围摘要 chunk
    summary_chunk = _build_realtime_summary(activity_dates, activity_names, all_chunks)
    if summary_chunk:
        all_chunks.append(summary_chunk)
        print(f"  现实时间摘要块: 1")

    # 保存
    print(f"\n[7/8] 保存数据块...")
    print(f"  总块数: {len(all_chunks)}")

    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

    # 按类型分文件
    type_groups = {}
    for chunk in all_chunks:
        t = chunk["type"]
        type_groups.setdefault(t, []).append(chunk)

    for t, group in type_groups.items():
        out_path = CHUNKS_DIR / f"{t}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(group, f, ensure_ascii=False, indent=2)
        print(f"  {t}.json: {len(group)} 块")

    # 统计唯一干员数
    all_char_names = set()
    for chunk in all_chunks:
        cn = chunk.get("char_name", "")
        if cn:
            all_char_names.add(cn)

    meta = {
        "total_chunks": len(all_chunks),
        "by_type": {t: len(g) for t, g in type_groups.items()},
        "story_files": story_stats["txt_files"],
        "modules": len(module_chunks),
        "characters": len(handbook_chunks) + len(voice_chunks),
        "skins": len(skin_chunks),
        "roguelike": len(rogue_chunks),
        "unique_operators": len(all_char_names),
    }
    with open(CHUNKS_DIR / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # 记录当前仓库 commit SHA
    _save_repo_sha()

    print(f"\n[8/8] 完成!")
    print(f"\n{'=' * 60}")
    print(f"数据解析完成!")
    print(f"  输出: {CHUNKS_DIR}")
    print(f"  总块数: {len(all_chunks)}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()

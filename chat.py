"""明日方舟剧情史学家 - 交互终端 v0.9"""
import sys
import json
import urllib.request
from pathlib import Path

sys.stdin.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")

from agent import Conversation

BASE_DIR = Path(__file__).parent
REPO_DIR = BASE_DIR.parent / "ArknightsGameData"
SHA_FILE = BASE_DIR / "data" / ".last_repo_sha"


def check_repo_update():
    """检查 ArknightsGameData 仓库是否有更新"""
    if not REPO_DIR.exists():
        print("  [WARN] 本地 ArknightsGameData 仓库不存在")
        print("  首次使用请执行:")
        print("    git clone --depth 1 --filter=blob:none --sparse \\")
        print("      https://github.com/Kengxxiao/ArknightsGameData.git")
        print("    cd ArknightsGameData")
        print("    git sparse-checkout set zh_CN/gamedata/story zh_CN/gamedata/excel")
        return False

    print("  正在检查数据源更新...")

    try:
        # 获取远程最新 commit SHA
        url = "https://api.github.com/repos/Kengxxiao/ArknightsGameData/commits/master"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        remote_sha = data.get("sha", "")

        # 读取本地存储的 SHA
        local_sha = ""
        if SHA_FILE.exists():
            local_sha = SHA_FILE.read_text().strip()

        if remote_sha == local_sha:
            print("  数据源已是最新版本")
            return False
        else:
            commit_msg = data.get("commit", {}).get("message", "")[:60]
            print(f"  发现新版本: {commit_msg}")
            print("  请执行以下命令更新数据源:")
            print("    cd ../ArknightsGameData && git pull")
            print("    cd ../mrfz_history_project")
            print("    python github_crawler.py")
            print("    python vector_store.py")
            return True
    except Exception as e:
        print(f"  [WARN] 更新检查失败: {type(e).__name__}")
        return False


def print_banner():
    print()
    print("╔══════════════════════════════════════════════╗")
    print("║     明日方舟剧情史学家 Agent v0.9               ║")
    print("║     知识库 + 向量检索                           ║")
    print("╠══════════════════════════════════════════════╣")
    print("║  命令:                                       ║")
    print("║    /reset  - 重置对话                         ║")
    print("║    /quit   - 退出                             ║")
    print("╚══════════════════════════════════════════════╝")
    print()


def main():
    print_banner()

    # 1. 检查数据源更新
    check_repo_update()
    print()

    # 2. 加载向量库
    print("  正在加载向量库...")
    conv = Conversation()
    conv._init_searcher()
    print("  向量库就绪。\n")

    while True:
        try:
            user_input = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见!")
            break

        if not user_input:
            continue

        if user_input == "/quit":
            print("再见!")
            break
        elif user_input == "/reset":
            conv.reset()
            print("对话已重置。")
            continue

        try:
            print("  正在检索...", end="", flush=True)
            result = conv.ask(user_input)
            if isinstance(result, tuple):
                answer, usage = result
            else:
                answer, usage = result, None
            print("\r  检索完成")
            print(f"\n史学家: 检索完成，以下是我基于知识库整理的回答：\n{answer}")
            if usage:
                total = (usage.prompt_tokens or 0) + (usage.completion_tokens or 0)
                print(f"\n[Token: {total}]")
        except Exception as e:
            print(f"\n[错误] {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()

"""
明日方舟剧情史学家 - 依赖检查与自动安装脚本
自动检测缺少的依赖，使用国内镜像源安装
"""
import importlib
import subprocess
import sys
import os
import shutil
from pathlib import Path

# ─── 配置 ───────────────────────────────────────────────
PROJECT_DIR = Path(__file__).parent
WEB_DIR = PROJECT_DIR / "web"

# pip 镜像源（国内）
PIP_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"
# npm 镜像源（国内）
NPM_MIRROR = "https://registry.npmmirror.com"
# HuggingFace 镜像源
HF_MIRROR = "https://hf-mirror.com"

# Python 依赖列表：(pip包名, import名, 说明, 预估大小MB)
PYTHON_DEPS = [
    ("python-dotenv", "dotenv", "环境变量管理", 5),
    ("openai", "openai", "LLM API 客户端", 30),
    ("sentence-transformers", "sentence_transformers", "文本向量化（含 PyTorch）", 2500),
    ("chromadb", "chromadb", "向量数据库", 200),
    ("fastapi", "fastapi", "Web 框架", 10),
    ("uvicorn", "uvicorn", "ASGI 服务器", 5),
    ("pydantic", "pydantic", "数据校验", 15),
    ("markdown", "markdown", "Markdown 渲染", 5),
    ("requests", "requests", "HTTP 请求", 5),
]

# Node.js 最低版本
NODE_MAJOR_MIN = 18
# Python 最低版本
PYTHON_MAJOR_MIN = 3
PYTHON_MINOR_MIN = 10


# ─── 工具函数 ─────────────────────────────────────────────
def run_cmd(cmd, **kwargs):
    """运行命令，返回 (success, output)"""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300, **kwargs
        )
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)


def find_git():
    """返回可用的 git 命令路径（优先 PATH，其次 Windows 默认安装位置）"""
    candidates = ["git"]
    if os.name == "nt":
        candidates += [
            r"C:\Program Files\Git\cmd\git.exe",
            r"C:\Program Files (x86)\Git\cmd\git.exe",
        ]
    for c in candidates:
        ok, _ = run_cmd([c, "--version"])
        if ok:
            return c
    return None


def try_install_git():
    """尝试通过 winget 安装 Git（仅 Windows），返回 (成功, 消息)"""
    if os.name != "nt":
        return False, "仅支持 Windows 自动安装 Git"
    try:
        result = subprocess.run(
            ["winget", "install", "--id", "Git.Git", "-e",
             "--accept-source-agreements", "--accept-package-agreements"],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode == 0 and find_git():
            return True, "Git 安装成功"
        return False, (result.stderr or result.stdout)[-300:]
    except FileNotFoundError:
        return False, "winget 不可用"
    except Exception as e:
        return False, str(e)


def check_python_version():
    """检查 Python 版本"""
    major, minor = sys.version_info[:2]
    if major > PYTHON_MAJOR_MIN or (major == PYTHON_MAJOR_MIN and minor >= PYTHON_MINOR_MIN):
        return True, f"Python {major}.{minor}"
    return False, f"Python {major}.{minor} (需要 >= {PYTHON_MAJOR_MIN}.{PYTHON_MINOR_MIN})"


def check_node():
    """检查 Node.js 是否安装及版本"""
    ok, out = run_cmd(["node", "--version"])
    if not ok:
        return False, "未安装 Node.js", ""
    version_str = out.strip().lstrip("v")
    parts = version_str.split(".")
    major = int(parts[0]) if parts else 0
    if major >= NODE_MAJOR_MIN:
        return True, f"Node.js {version_str}", out.strip()
    return False, f"Node.js {version_str} (需要 >= {NODE_MAJOR_MIN})", out.strip()


def check_npm():
    """检查 npm 是否安装"""
    ok, out = run_cmd(["npm", "--version"])
    if not ok:
        return False, "未安装 npm"
    return True, f"npm {out.strip()}"


def check_pip_package(import_name):
    """检查单个 Python 包是否可导入"""
    try:
        importlib.import_module(import_name)
        return True
    except ImportError:
        return False


def pip_install(packages):
    """使用国内镜像安装 pip 包"""
    cmd = [
        sys.executable, "-m", "pip", "install",
        "-i", PIP_MIRROR,
        "--trusted-host", "pypi.tuna.tsinghua.edu.cn",
    ] + packages
    ok, out = run_cmd(cmd)
    return ok, out


def npm_install():
    """使用国内镜像安装前端依赖"""
    cmd = ["npm", "install", "--registry", NPM_MIRROR]
    ok, out = run_cmd(cmd, cwd=str(WEB_DIR))
    return ok, out


def set_hf_mirror():
    """设置 HuggingFace 镜像环境变量"""
    os.environ["HF_ENDPOINT"] = HF_MIRROR
    # 也写入 .env 以持久化
    env_file = PROJECT_DIR / ".env"
    if env_file.exists():
        content = env_file.read_text(encoding="utf-8")
        if "HF_ENDPOINT" not in content:
            with open(env_file, "a", encoding="utf-8") as f:
                f.write(f"\nHF_ENDPOINT={HF_MIRROR}\n")
    print(f"  [✓] HuggingFace 镜像已设置为: {HF_MIRROR}")


# ─── 主检查流程 ──────────────────────────────────────────
def check_all():
    """检查所有依赖，返回缺少的列表"""
    missing_python = []
    print("\n--- Python 环境 ---")

    # Python 版本
    ok, ver = check_python_version()
    status = "✓" if ok else "✗"
    print(f"  [{status}] {ver}")
    if not ok:
        print("  [!] 请升级 Python 后重试")
        sys.exit(1)

    # Python 包
    print("\n--- Python 依赖包 ---")
    for pip_name, import_name, desc, size_mb in PYTHON_DEPS:
        installed = check_pip_package(import_name)
        status = "✓" if installed else "✗"
        size_str = f"({size_mb} MB)" if not installed else ""
        print(f"  [{status}] {pip_name} - {desc} {size_str}")
        if not installed:
            missing_python.append((pip_name, import_name, desc, size_mb))

    # Node.js
    print("\n--- Node.js 环境 ---")
    node_ok, node_ver, _ = check_node()
    npm_ok, npm_ver = check_npm()

    node_status = "✓" if node_ok else "✗"
    npm_status = "✓" if npm_ok else "✗"
    print(f"  [{node_status}] {node_ver}")
    print(f"  [{npm_status}] {npm_ver}")

    # 前端依赖
    node_modules = WEB_DIR / "node_modules"
    frontend_missing = not node_modules.exists()
    fe_status = "✓" if not frontend_missing else "✗"
    print(f"  [{fe_status}] 前端依赖 (node_modules) (约 300 MB)")

    # Git（一键更新知识库需要）
    git_missing = not find_git()
    git_status = "✓" if not git_missing else "✗"
    print(f"  [{git_status}] Git (一键更新知识库需要)")

    # .env
    env_file = PROJECT_DIR / ".env"
    env_status = "✓" if env_file.exists() else "✗"
    print(f"\n--- 配置文件 ---")
    print(f"  [{env_status}] .env 文件")

    # HuggingFace 镜像
    hf_set = os.environ.get("HF_ENDPOINT") == HF_MIRROR
    hf_status = "✓" if hf_set else "○"
    print(f"  [{hf_status}] HuggingFace 镜像 ({HF_MIRROR})")

    return missing_python, frontend_missing, not env_file, node_ok, npm_ok, git_missing


def show_summary(missing_python, frontend_missing, env_missing, node_ok, npm_ok, git_missing):
    """显示缺少的依赖汇总及预估大小"""
    total_mb = 0
    items = []

    if not node_ok:
        print("\n[!] Node.js 未安装或版本过低")
        print("    请前往 https://nodejs.org 下载安装 (需要 >= 18)")
        print("    安装后重新运行本脚本")
        sys.exit(1)

    if not npm_ok:
        print("\n[!] npm 未安装")
        print("    安装 Node.js 时会自带 npm，请先安装 Node.js")
        sys.exit(1)

    if missing_python:
        print("\n--- 缺少的 Python 依赖 ---")
        for pip_name, import_name, desc, size_mb in missing_python:
            print(f"  • {pip_name} ({desc}) - 约 {size_mb} MB")
            total_mb += size_mb
        items.append(f"{len(missing_python)} 个 Python 包")

    if frontend_missing:
        print(f"\n--- 缺少前端依赖 ---")
        print(f"  • node_modules - 约 300 MB")
        total_mb += 300
        items.append("前端依赖")

    if git_missing:
        print(f"\n--- 缺少 Git ---")
        print(f"  • Git (一键更新知识库需要)")
        items.append("Git")

    if not items:
        print("\n[✓] 所有依赖已就绪！")
        return False

    # 格式化大小
    if total_mb >= 1024:
        size_str = f"约 {total_mb / 1024:.1f} GB"
    else:
        size_str = f"约 {total_mb} MB"

    print(f"\n{'='*45}")
    print(f"  需要安装: {', '.join(items)}")
    print(f"  预估空间: {size_str}")
    print(f"  安装源:   pip (清华镜像) / npm (淘宝镜像) / winget (Git)")
    print(f"{'='*45}")
    return True


def install_all(missing_python, frontend_missing, env_missing, git_missing):
    """安装缺少的依赖"""
    print()

    # 设置 HuggingFace 镜像
    set_hf_mirror()

    # 安装 Python 包
    if missing_python:
        print("--- 安装 Python 依赖 ---")
        # 先装小的包，最后装大的
        small_pkgs = [p[0] for p in missing_python if p[3] < 100]
        large_pkgs = [p[0] for p in missing_python if p[3] >= 100]

        if small_pkgs:
            print(f"  安装: {', '.join(small_pkgs)}")
            ok, out = pip_install(small_pkgs)
            if ok:
                print("  [✓] 安装成功")
            else:
                print(f"  [✗] 安装失败: {out[-200:]}")

        if large_pkgs:
            for pkg in large_pkgs:
                print(f"  安装: {pkg} (较大包，可能需要几分钟)...")
                ok, out = pip_install([pkg])
                if ok:
                    print("  [✓] 安装成功")
                else:
                    print(f"  [✗] 安装失败: {out[-200:]}")

    # 安装前端依赖
    if frontend_missing:
        print("\n--- 安装前端依赖 ---")
        print("  npm install (可能需要几分钟)...")
        ok, out = npm_install()
        if ok:
            print("  [✓] 安装成功")
        else:
            print(f"  [✗] 安装失败: {out[-200:]}")

    # 安装 Git（通过 winget）
    if git_missing:
        print("\n--- 安装 Git ---")
        print("  正在通过 winget 安装 Git (可能需要几分钟)...")
        ok, msg = try_install_git()
        if ok:
            print("  [✓] Git 安装成功")
        else:
            print(f"  [✗] Git 自动安装失败: {msg}")
            print("      请手动安装: https://git-scm.com/downloads")

    # 创建 .env
    if env_missing:
        print("\n--- 创建配置文件 ---")
        env_file = PROJECT_DIR / ".env"
        api_key = input("  请输入你的 API Key: ").strip()
        base_url = input("  请输入 API Base URL (默认 https://api.deepseek.com): ").strip()
        if not base_url:
            base_url = "https://api.deepseek.com"
        model = input("  请输入模型名称 (默认 deepseek-chat): ").strip()
        if not model:
            model = "deepseek-chat"
        env_file.write_text(
            f"DEEPSEEK_API_KEY={api_key}\n"
            f"DEEPSEEK_BASE_URL={base_url}\n"
            f"DEEPSEEK_MODEL={model}\n"
            f"HF_ENDPOINT={HF_MIRROR}\n",
            encoding="utf-8",
        )
        print("  [✓] .env 文件已创建")

    print("\n" + "=" * 45)
    print("  所有依赖安装完成！")
    print("  请关闭此窗口，然后重新运行 start.py")
    print("=" * 45)


def main():
    print("=" * 45)
    print("  明日方舟剧情史学家 - 依赖检查")
    print("=" * 45)

    os.chdir(str(PROJECT_DIR))

    # 第一步：全面检查
    missing_python, frontend_missing, env_missing, node_ok, npm_ok, git_missing = check_all()

    # 第二步：显示汇总
    needs_install = show_summary(missing_python, frontend_missing, env_missing, node_ok, npm_ok, git_missing)

    if not needs_install:
        # 检查 HF 镜像是否设置
        if os.environ.get("HF_ENDPOINT") != HF_MIRROR:
            set_hf_mirror()
        print("\n直接运行 start.py 即可启动项目。")
        return

    # 第三步：询问用户确认
    print()
    answer = input("是否安装缺少的依赖？(y/n): ").strip().lower()
    if answer != "y":
        print("已取消。请手动安装缺少的依赖后运行 start.py。")
        return

    # 第四步：安装
    install_all(missing_python, frontend_missing, env_missing, git_missing)


if __name__ == "__main__":
    main()

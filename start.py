"""
明日方舟剧情史学家 - 一键启动
双击运行或: python start.py
"""
import subprocess
import sys
import os
import time
import urllib.request
import webbrowser
from pathlib import Path

BACKEND_PORT = 8000
FRONTEND_PORT = 36888

# 应用版本号（与 server.py 保持一致）
APP_VERSION = "1.0.0"

# PyInstaller 冻结时 __file__ 指向临时目录，需要用 exe 所在目录
if getattr(sys, "frozen", False):
    PROJECT_DIR = Path(sys.executable).parent
else:
    PROJECT_DIR = Path(__file__).parent

# 镜像源
PIP_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"
NPM_MIRROR = "https://registry.npmmirror.com"
HF_MIRROR = "https://hf-mirror.com"

# Python 依赖：(pip包名, import名, 说明, 预估大小MB)
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


def get_python():
    """获取真正的 Python 解释器路径（PyInstaller 冻结时回退到系统 Python）"""
    if getattr(sys, "frozen", False):
        import shutil
        python = shutil.which("python") or shutil.which("python3")
        if not python:
            print("[!] 未找到系统 Python")
            print()
            print("  安装方法:")
            print("  1. 访问 https://www.python.org/downloads/")
            print("  2. 下载 Python 3.10+ (推荐 3.12)")
            print("  3. 安装时勾选 [Add Python to PATH]")
            print("  4. 安装完成后重新运行 START.exe")
            input("按 Enter 键退出...")
            sys.exit(1)
        return python
    return sys.executable


def _run_cmd(cmd, **kwargs):
    """运行命令，返回 (success, output)"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, **kwargs)
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)


def _find_git():
    """返回可用的 git 命令路径（优先 PATH，其次 Windows 默认安装位置）"""
    candidates = ["git"]
    if os.name == "nt":
        candidates += [
            r"C:\Program Files\Git\cmd\git.exe",
            r"C:\Program Files (x86)\Git\cmd\git.exe",
        ]
    for c in candidates:
        ok, _ = _run_cmd([c, "--version"])
        if ok:
            return c
    return None


def _try_install_git():
    """尝试通过 winget 安装 Git（仅 Windows），返回 (成功, 消息)"""
    if os.name != "nt":
        return False, "仅支持 Windows 自动安装 Git"
    try:
        result = subprocess.run(
            ["winget", "install", "--id", "Git.Git", "-e",
             "--accept-source-agreements", "--accept-package-agreements"],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode == 0 and _find_git():
            return True, "Git 安装成功"
        return False, (result.stderr or result.stdout)[-300:]
    except FileNotFoundError:
        return False, "winget 不可用"
    except Exception as e:
        return False, str(e)


def quick_check():
    """快速检查环境（静默，只返回 True/False）"""
    # Python 版本
    try:
        result = subprocess.run(
            [get_python(), "--version"],
            capture_output=True, text=True, timeout=10,
        )
        ver_str = result.stderr.strip() or result.stdout.strip()
        parts = ver_str.replace("Python ", "").split(".")
        major, minor = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
        if major < 3 or (major == 3 and minor < 10):
            return False
    except Exception:
        return False

    # Node.js 版本
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        node_ver = result.stdout.strip().lstrip("v")
        node_major = int(node_ver.split(".")[0]) if node_ver else 0
        if node_major < 18:
            return False
    except Exception:
        return False

    # Git（一键更新知识库需要）
    if not _find_git():
        return False

    # .env
    if not (PROJECT_DIR / ".env").exists():
        return False

    # 知识库数据
    chroma_db = PROJECT_DIR / "data" / "vectorstore"
    chunks_meta = PROJECT_DIR / "data" / "chunks" / "meta.json"
    if not chroma_db.exists() or not chunks_meta.exists():
        return False

    # 前端依赖
    if not (PROJECT_DIR / "web" / "node_modules").exists():
        return False

    # Python 包
    try:
        result = subprocess.run(
            [get_python(), "-c",
             "import dotenv,openai,sentence_transformers,chromadb,fastapi,uvicorn"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return False
    except Exception:
        return False

    return True


def full_check_and_install():
    """完整依赖检查 + 自动安装（集成 check_deps 逻辑）"""
    python = get_python()

    # 1. Python 版本
    print("\n--- Python 环境 ---")
    ok, out = _run_cmd([python, "--version"])
    if not ok:
        print(f"  [✗] 无法运行 Python")
        print("  [!] 请安装 Python 3.10+ 并确保在 PATH 中")
        input("按 Enter 键退出...")
        return False
    try:
        # python --version 输出类似 "Python 3.14.3"，可能在 stdout 或 stderr
        ver_str = out.strip().replace("Python ", "").split("\n")[0].strip()
        parts = ver_str.split(".")
        major, minor = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        print(f"  [✗] 无法解析 Python 版本: {out.strip()[:50]}")
        print("  [!] 请确认 Python 已正确安装")
        print("      安装方法: https://www.python.org/downloads/")
        print("      安装时勾选 [Add Python to PATH]")
        input("按 Enter 键退出...")
        return False
    if major < 3 or (major == 3 and minor < 10):
        print(f"  [✗] Python {major}.{minor} (需要 >= 3.10)")
        print("  [!] 请升级 Python: https://www.python.org/downloads/")
        print("      安装时勾选 [Add Python to PATH]")
        input("按 Enter 键退出...")
        return False
    print(f"  [✓] Python {major}.{minor}")

    # 2. Python 包
    missing_python = []
    print("\n--- Python 依赖包 ---")
    for pip_name, import_name, desc, size_mb in PYTHON_DEPS:
        ok, _ = _run_cmd([python, "-c", f"import {import_name}"])
        status = "✓" if ok else "✗"
        size_str = f"(约 {size_mb} MB)" if not ok else ""
        print(f"  [{status}] {pip_name} - {desc} {size_str}")
        if not ok:
            missing_python.append((pip_name, desc, size_mb))

    # 3. Node.js
    print("\n--- Node.js 环境 ---")
    node_ok, node_out = _run_cmd(["node", "--version"])
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    npm_ok, npm_out = _run_cmd([npm_cmd, "--version"])
    if not node_ok:
        print(f"  [✗] 未安装 Node.js (需要 >= 18)")
        print()
        print("  安装方法:")
        print("  1. 访问 https://nodejs.org")
        print("  2. 下载 LTS 版本 (推荐 20.x)")
        print("  3. 安装时保持默认选项即可")
        print("  4. 安装完成后重新运行 START.exe")
        print()
        input("按 Enter 键退出...")
        return False
    print(f"  [✓] Node.js {node_out.strip().lstrip('v')}")
    print(f"  [✓] npm {npm_out.strip()}")

    # 4. Git（一键更新知识库需要）
    git_missing = not _find_git()
    print(f"\n--- Git ---")
    print(f"  [{'✓' if not git_missing else '✗'}] Git (一键更新知识库需要)")

    # 5. 前端依赖
    node_modules = PROJECT_DIR / "web" / "node_modules"
    frontend_missing = not node_modules.exists()
    print(f"\n--- 前端依赖 ---")
    print(f"  [{'✓' if not frontend_missing else '✗'}] 前端依赖 (node_modules) (约 300 MB)")

    # 6. .env
    env_missing = not (PROJECT_DIR / ".env").exists()
    print(f"\n--- 配置文件 ---")
    print(f"  [{'✓' if not env_missing else '✗'}] .env 文件")

    # 汇总
    total_mb = sum(p[2] for p in missing_python)
    if frontend_missing:
        total_mb += 300
    items = []
    if missing_python:
        items.append(f"{len(missing_python)} 个 Python 包")
    if git_missing:
        items.append("Git")
    if frontend_missing:
        items.append("前端依赖")

    if not items and not env_missing:
        print("\n[✓] 所有依赖已就绪！")
        return True

    # 显示预估大小
    if total_mb >= 1024:
        size_str = f"约 {total_mb / 1024:.1f} GB"
    else:
        size_str = f"约 {total_mb} MB"

    print(f"\n{'=' * 45}")
    print(f"  需要安装: {', '.join(items)}")
    print(f"  预估空间: {size_str}")
    print(f"  安装源:   pip (清华镜像) / npm (淘宝镜像)")
    print(f"{'=' * 45}")

    answer = input("\n是否安装缺少的依赖？(y/n): ").strip().lower()
    if answer != "y":
        print("已取消。请手动安装缺少的依赖后重新运行。")
        return False

    # 设置 HF 镜像
    os.environ.setdefault("HF_ENDPOINT", HF_MIRROR)

    # 安装 Python 包
    if missing_python:
        print("\n--- 安装 Python 依赖 ---")
        small = [p[0] for p in missing_python if p[2] < 100]
        large = [p[0] for p in missing_python if p[2] >= 100]

        if small:
            print(f"  安装: {', '.join(small)}")
            ok, out = _run_cmd([python, "-m", "pip", "install", "-i", PIP_MIRROR,
                                "--trusted-host", "pypi.tuna.tsinghua.edu.cn"] + small)
            print(f"  [{'✓' if ok else '✗'}] {'成功' if ok else '失败: ' + out[-200:]}")

        if large:
            for pkg in large:
                print(f"  安装: {pkg} (较大包，可能需要几分钟)...")
                ok, out = _run_cmd([python, "-m", "pip", "install", "-i", PIP_MIRROR,
                                    "--trusted-host", "pypi.tuna.tsinghua.edu.cn", pkg])
                print(f"  [{'✓' if ok else '✗'}] {'成功' if ok else '失败: ' + out[-200:]}")

    # 安装前端依赖
    if frontend_missing:
        print("\n--- 安装前端依赖 ---")
        print("  npm install (可能需要几分钟)...")
        ok, out = _run_cmd([npm_cmd, "install", "--registry", NPM_MIRROR],
                           cwd=str(PROJECT_DIR / "web"))
        print(f"  [{'✓' if ok else '✗'}] {'成功' if ok else '失败: ' + out[-200:]}")

    # 安装 Git（通过 winget）
    if git_missing:
        print("\n--- 安装 Git ---")
        print("  正在通过 winget 安装 Git (可能需要几分钟)...")
        ok, msg = _try_install_git()
        if ok:
            print("  [✓] Git 安装成功")
        else:
            print(f"  [✗] Git 自动安装失败: {msg}")
            print("      请手动安装: https://git-scm.com/downloads")
            print("      安装后重新运行 START.exe")

    # 创建 .env
    if env_missing:
        print("\n--- 创建配置文件 ---")
        api_key = input("  请输入你的 API Key (可留空，稍后在前端配置): ").strip()
        base_url = input(f"  API Base URL (默认 https://api.deepseek.com): ").strip() or "https://api.deepseek.com"
        model = input("  模型名称 (默认 deepseek-chat): ").strip() or "deepseek-chat"
        (PROJECT_DIR / ".env").write_text(
            f"DEEPSEEK_API_KEY={api_key}\n"
            f"DEEPSEEK_BASE_URL={base_url}\n"
            f"DEEPSEEK_MODEL={model}\n"
            f"HF_ENDPOINT={HF_MIRROR}\n",
            encoding="utf-8",
        )
        print("  [✓] .env 文件已创建")

    print(f"\n{'=' * 45}")
    print("  所有依赖安装完成！")
    print("  请关闭此窗口，然后重新双击 START.exe")
    print(f"{'=' * 45}")
    return False


def start_backend():
    """启动后端"""
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.Popen(
        [get_python(), "server.py"],
        cwd=str(PROJECT_DIR),
        env=env,
        creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0,
    )


def wait_for_backend(port, timeout=60):
    """等待后端启动完成（轮询 /api/stats）"""
    url = f"http://127.0.0.1:{port}/api/stats"
    print(f"      等待后端就绪", end="", flush=True)
    for i in range(timeout * 2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "start.py"})
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    print(" ✓")
                    return True
        except Exception:
            pass
        if i % 4 == 0:
            print(".", end="", flush=True)
        time.sleep(0.5)
    print(" ✗")
    return False


def start_frontend():
    """启动前端"""
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    return subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd=str(PROJECT_DIR / "web"),
        creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0,
    )


def main():
    print("=" * 45)
    print("  明日方舟剧情史学家 - 一键启动")
    print("=" * 45)
    print()

    os.chdir(str(PROJECT_DIR))

    # 第一步：快速环境检查
    print("[1/4] 检查环境...")
    all_ok = quick_check()
    if not all_ok:
        print("正在启动完整依赖检查与安装...")
        if not full_check_and_install():
            input("按 Enter 键退出...")
            return
        # 安装成功，继续启动（不再退出）
        print()

    # 设置 HF 镜像（仅在用户未自行配置时使用默认镜像）
    os.environ.setdefault("HF_ENDPOINT", HF_MIRROR)

    # 第二步：启动后端
    print(f"[2/4] 启动后端 (端口 {BACKEND_PORT})...")
    backend = start_backend()

    if not wait_for_backend(BACKEND_PORT):
        print("  [!] 后端启动超时，请检查后端窗口的错误信息")
        try:
            backend.terminate()
            backend.wait(timeout=5)
        except Exception:
            pass
        input("按 Enter 键退出...")
        return

    # 第三步：启动前端
    print(f"[3/4] 启动前端 (端口 {FRONTEND_PORT})...")
    frontend = start_frontend()

    # 第四步：等待用户打开浏览器
    print(f"[4/4] 就绪")
    print()
    print("=" * 45)
    print(f"  后端: http://localhost:{BACKEND_PORT}")
    print(f"  前端: http://localhost:{FRONTEND_PORT}")
    print("=" * 45)
    print()
    print("按 Enter 键打开浏览器，按 Ctrl+C 停止所有服务...")
    print()

    try:
        input()
        webbrowser.open(f"http://localhost:{FRONTEND_PORT}")
        print("服务运行中... 按 Ctrl+C 停止")
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, EOFError):
        print("\n正在停止...")
        for proc in [frontend, backend]:
            try:
                # Windows: /T 杀掉进程树（子进程），/PID 只杀指定进程
                if os.name == "nt" and proc.poll() is None:
                    subprocess.run(
                        ["taskkill", "/f", "/t", "/pid", str(proc.pid)],
                        capture_output=True, timeout=5,
                    )
                else:
                    proc.terminate()
                    proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        print("已停止。")


if __name__ == "__main__":
    main()

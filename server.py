"""
明日方舟剧情史学家 - Web 后端
独立文件，不影响原有项目
"""
# 强制 UTF-8 编码，避免 Windows 下中文导致 ascii codec 错误
import sys
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import json
import re
import uuid
import os
import threading
import subprocess
import time
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI
import agent as agent_module

load_dotenv()

BASE_DIR = Path(__file__).parent
APP_VERSION = "1.0.0"
# 用于检查应用最新版本（格式: "用户名/仓库名"），留空则跳过远程版本检查
GITHUB_REPO = os.getenv("GITHUB_REPO", "")

app = FastAPI(title="明日方舟剧情史学家 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:36888", "http://127.0.0.1:36888"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 当前 LLM 配置
current_config = {
    "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
    "base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    "model": os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
}

# 会话管理：session_id -> Conversation（最多 50 个）
MAX_SESSIONS = 50
sessions: dict[str, object] = {}
sessions_lock = threading.Lock()

# 会话级忙标志：防止同一会话的并发请求
session_busy: dict[str, bool] = {}

# 知识库更新状态与全局锁（更新进行中时拒绝新的 chat 请求）
update_lock = threading.Lock()
update_state = {
    "in_progress": False,
    "progress": 0,
    "step": "",
    "message": "",
    "error": None,
    "started_at": None,
}


class ChatRequest(BaseModel):
    session_id: str = ""
    message: str


class ResetRequest(BaseModel):
    session_id: str


class ConfigRequest(BaseModel):
    api_key: str = ""
    base_url: str = ""
    model: str = ""


def _apply_config():
    """将 current_config 应用到 agent 模块的全局变量"""
    agent_module.client = OpenAI(
        api_key=current_config["api_key"] or "placeholder",
        base_url=current_config["base_url"],
    )
    agent_module.MODEL = current_config["model"]


def _safe_clean(text):
    """兜底清理：如果 _clean_text 返回空，尝试只保留非标签内容"""
    cleaned = agent_module._clean_text(text)
    if cleaned:
        return cleaned
    parts = re.split(r'<｜｜[^>]*>', text)
    return "\n".join(p.strip() for p in parts if p.strip()) or text


def _call_llm(conv, message):
    """调用 LLM，捕获认证/余额等错误。成功返回 (answer, usage)，失败抛出 RuntimeError"""
    # 先设置较短的超时，避免无效 Key 时卡太久
    agent_module.client.timeout = 120
    try:
        return conv.ask(message)
    except Exception as e:
        err_msg = str(e)
        if "api_key" in err_msg.lower() or "auth" in err_msg.lower() or "incorrect" in err_msg.lower():
            raise RuntimeError("API Key 无效，请在模型设置中检查你的 API Key")
        elif "insufficient" in err_msg.lower() or "quota" in err_msg.lower() or "balance" in err_msg.lower() or "rate" in err_msg.lower():
            raise RuntimeError("API 额度不足或触发限流，请检查账户余额")
        elif "connect" in err_msg.lower() or "timeout" in err_msg.lower() or "network" in err_msg.lower():
            raise RuntimeError("无法连接到大模型服务，请检查 Base URL 或网络")
        raise RuntimeError(f"LLM 调用失败: {err_msg}")


def _get_conv(sid):
    """获取或创建 Conversation 实例"""
    with sessions_lock:
        if sid not in sessions:
            if len(sessions) >= MAX_SESSIONS:
                # 清除最早的会话
                oldest = next(iter(sessions))
                del sessions[oldest]
            sessions[sid] = agent_module.Conversation()
        return sessions[sid]


def _check_updating():
    """更新进行中时返回错误提示，否则返回 None"""
    if update_state["in_progress"]:
        # 超时保护：超过 30 分钟认为更新卡住了
        started = update_state.get("started_at")
        if started and (time.time() - started) > 1800:
            # 只重置状态使 chat 恢复正常，不释放锁（锁由 update_data 统一管理）
            update_state["in_progress"] = False
            update_state["error"] = None
            update_state["started_at"] = None
            return None
        return "知识库正在更新中，请等待更新完成后再提问"
    return None


# ======== API ========

@app.get("/api/stats")
def get_stats():
    """获取知识库统计"""
    meta_path = BASE_DIR / "data" / "chunks" / "meta.json"
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"error": "统计信息不可用"}


@app.get("/api/config")
def get_config():
    """获取当前 LLM 配置（API Key 脱敏）"""
    key = current_config["api_key"]
    masked = key[:6] + "****" + key[-4:] if len(key) > 10 else "****"
    return {
        "base_url": current_config["base_url"],
        "model": current_config["model"],
        "api_key_masked": masked,
        "has_key": bool(key),
    }


@app.post("/api/config")
def set_config(req: ConfigRequest):
    """更新 LLM 配置"""
    global current_config
    if req.api_key:
        current_config["api_key"] = req.api_key
    if req.base_url:
        current_config["base_url"] = req.base_url
    if req.model:
        current_config["model"] = req.model

    _apply_config()

    # 清除所有会话（切换模型后旧会话的 messages 不兼容）
    with sessions_lock:
        sessions.clear()
        session_busy.clear()

    return {"success": True}


@app.post("/api/chat")
def chat(req: ChatRequest):
    """发送消息并获取 AI 回答"""
    updating = _check_updating()
    if updating:
        raise HTTPException(status_code=503, detail=updating)
    sid = req.session_id or str(uuid.uuid4())
    conv = _get_conv(sid)
    with sessions_lock:
        if session_busy.get(sid):
            raise HTTPException(status_code=429, detail="该会话正在处理上一个请求，请等待")
        session_busy[sid] = True
    try:
        answer, usage = _call_llm(conv, req.message)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session_busy[sid] = False
    answer = _safe_clean(answer)

    return {
        "session_id": sid,
        "answer": answer,
        "usage": {
            "prompt_tokens": (usage.prompt_tokens or 0) if usage else 0,
            "completion_tokens": (usage.completion_tokens or 0) if usage else 0,
            "total_tokens": ((usage.prompt_tokens or 0) + (usage.completion_tokens or 0)) if usage else 0,
        },
    }


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest):
    """SSE 流式输出 AI 回答（真流式）"""
    sid = req.session_id or str(uuid.uuid4())

    # 更新检查在获取会话之前做
    updating = _check_updating()
    if updating:
        raise HTTPException(status_code=503, detail=updating)

    conv = _get_conv(sid)
    with sessions_lock:
        if session_busy.get(sid):
            raise HTTPException(status_code=429, detail="该会话正在处理上一个请求，请等待")
        session_busy[sid] = True

    def event_generator():
        try:
            for piece in conv.ask_stream(req.message):
                if isinstance(piece, dict):
                    if piece.get("clear"):
                        # 工具调用轮的中间文本需要清空
                        clear_data = json.dumps({"clear": True, "session_id": sid}, ensure_ascii=False)
                        yield f"data: {clear_data}\n\n"
                        continue
                    # 最后一块：usage 信息
                    usage = piece.get("usage")
                    end_data = json.dumps({
                        "done": True,
                        "session_id": sid,
                        "usage": {
                            "prompt_tokens": (usage.prompt_tokens or 0) if usage else 0,
                            "completion_tokens": (usage.completion_tokens or 0) if usage else 0,
                            "total_tokens": ((usage.prompt_tokens or 0) + (usage.completion_tokens or 0)) if usage else 0,
                        },
                    }, ensure_ascii=False)
                    yield f"data: {end_data}\n\n"
                elif isinstance(piece, str):
                    data = json.dumps({"chunk": piece, "session_id": sid}, ensure_ascii=False)
                    yield f"data: {data}\n\n"
        except Exception as e:
            err_msg = str(e)
            err_lower = err_msg.lower()
            if "ascii" in err_lower or "codec" in err_lower or "encode" in err_lower:
                err_msg = "编码错误，请尝试设置环境变量 PYTHONUTF8=1 后重启"
            elif "api_key" in err_lower or "auth" in err_lower or "incorrect" in err_lower:
                err_msg = "API Key 无效，请在模型设置中检查你的 API Key"
            elif "insufficient" in err_lower or "quota" in err_lower or "balance" in err_lower:
                err_msg = "API 额度不足或触发限流"
            elif "connect" in err_lower or "timeout" in err_lower:
                err_msg = "无法连接到大模型服务，请检查 Base URL 或网络"
            err_data = json.dumps({"error": err_msg}, ensure_ascii=False)
            yield f"data: {err_data}\n\n"
        finally:
            session_busy[sid] = False

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/chat/reset")
def reset(req: ResetRequest):
    """重置会话"""
    with sessions_lock:
        if req.session_id in sessions:
            sessions[req.session_id].reset()
            return {"success": True}
    return {"success": False, "reason": "session not found"}


@app.get("/api/check-update")
def check_update():
    """检查 ArknightsGameData 仓库是否有更新"""
    repo_dir = BASE_DIR.parent / "ArknightsGameData"
    sha_file = BASE_DIR / "data" / ".last_repo_sha"

    if not repo_dir.exists():
        return {"status": "warning", "message": "本地数据源仓库不存在"}

    try:
        import urllib.request
        url = "https://api.github.com/repos/Kengxxiao/ArknightsGameData/commits/master"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        remote_sha = data.get("sha", "")
        local_sha = sha_file.read_text().strip() if sha_file.exists() else ""

        if remote_sha == local_sha:
            return {"status": "up_to_date", "message": "数据源已是最新版本"}
        else:
            commit_msg = data.get("commit", {}).get("message", "")[:60]
            return {
                "status": "update_available",
                "message": f"发现新版本: {commit_msg}",
                "hint": "cd ../ArknightsGameData && git pull && cd ../mrfz_history_project && python github_crawler.py && python vector_store.py",
            }
    except Exception as e:
        err_name = type(e).__name__
        if "timeout" in str(e).lower() or "timed out" in str(e).lower():
            return {"status": "error", "message": "GitHub API 请求超时，请检查网络连接"}
        if err_name == "HTTPError" and e.code == 403:
            return {"status": "error", "message": "GitHub API 请求过于频繁，请稍后再试"}
        if err_name == "HTTPError":
            return {"status": "error", "message": f"GitHub 返回错误 (HTTP {e.code})"}
        if "urlerror" in err_name.lower() or "connectionerror" in err_name.lower():
            return {"status": "error", "message": "无法连接 GitHub，请检查网络"}
        return {"status": "error", "message": f"检查失败: {err_name}"}


# ======== 一键更新知识库 ========

REPO_GIT_URL = "https://github.com/Kengxxiao/ArknightsGameData.git"


def _git_cmd():
    """返回可用的 git 命令路径（优先 PATH，其次 Windows 默认安装位置）"""
    candidates = ["git"]
    if os.name == "nt":
        candidates += [
            r"C:\Program Files\Git\cmd\git.exe",
            r"C:\Program Files (x86)\Git\cmd\git.exe",
        ]
    for c in candidates:
        try:
            subprocess.run([c, "--version"], capture_output=True, timeout=10)
            return c
        except Exception:
            continue
    return None


def _try_install_git():
    """尝试通过 winget 安装 Git（仅 Windows），返回 (成功, 消息)"""
    if os.name != "nt":
        return False, "仅支持 Windows 自动安装 Git，其他系统请手动安装"
    try:
        result = subprocess.run(
            ["winget", "install", "--id", "Git.Git", "-e",
             "--accept-source-agreements", "--accept-package-agreements"],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode == 0 and _git_cmd():
            return True, "Git 安装成功"
        return False, (result.stderr or result.stdout)[-300:]
    except FileNotFoundError:
        return False, "winget 不可用，请手动安装 Git (https://git-scm.com)"
    except Exception as e:
        return False, str(e)


def _run_step(cmd, cwd=None, timeout=900):
    """运行命令，返回 (成功, 输出尾部)"""
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        output = (result.stdout or "") + (result.stderr or "")
        return result.returncode == 0, output[-500:]
    except subprocess.TimeoutExpired:
        return False, "命令执行超时"
    except Exception as e:
        return False, str(e)


def _check_app_version():
    """检查应用版本，返回版本信息"""
    info = {"current": APP_VERSION, "latest": None, "update_available": False}
    if not GITHUB_REPO:
        return info
    try:
        import urllib.request
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0", "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        latest = (data.get("tag_name") or "").lstrip("v")
        info["latest"] = latest
        info["update_available"] = bool(latest) and latest != APP_VERSION
        if data.get("html_url"):
            info["release_url"] = data["html_url"]
    except Exception:
        pass
    return info


@app.get("/api/update-status")
def get_update_status():
    """查询当前更新状态"""
    return update_state


@app.post("/api/update-data")
def update_data():
    """一键更新知识库（SSE 流式推送进度）

    流程：检查 git → 拉取/克隆数据 → 解析文本 → 构建向量库 → 导入年表 → 检查版本
    更新进行中时全局拒绝 chat 请求。
    """
    if not update_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="更新正在进行中，请等待完成")

    update_state.update({
        "in_progress": True, "progress": 0, "step": "init",
        "message": "正在启动更新...", "error": None,
        "started_at": time.time(),
    })

    def _emit(progress, message, step):
        update_state.update({"progress": progress, "message": message, "step": step})
        data = json.dumps(
            {"progress": progress, "message": message, "step": step},
            ensure_ascii=False,
        )
        return f"data: {data}\n\n"

    def event_generator():
        try:
            python = sys.executable or "python"
            repo_dir = BASE_DIR.parent / "ArknightsGameData"

            # Step 1: 检查 / 安装 git
            yield _emit(5, "正在检查 Git 环境...", "git_check")
            git = _git_cmd()
            if not git:
                yield _emit(8, "Git 未安装，正在尝试自动安装...", "git_install")
                ok, msg = _try_install_git()
                if not ok:
                    yield _emit(8, "", "error")
                    update_state["error"] = f"Git 安装失败: {msg}"
                    err = json.dumps(
                        {"error": f"Git 安装失败: {msg}。请手动安装 Git 后重试。"},
                        ensure_ascii=False,
                    )
                    yield f"data: {err}\n\n"
                    return
                git = _git_cmd()
                if not git:
                    yield _emit(8, "", "error")
                    update_state["error"] = "Git 安装后仍无法找到，请重启程序"
                    err = json.dumps(
                        {"error": "Git 安装后仍无法找到，请关闭程序后重新启动 START.exe 重试。"},
                        ensure_ascii=False,
                    )
                    yield f"data: {err}\n\n"
                    return
                yield _emit(12, "Git 安装成功", "git_install")
            else:
                yield _emit(12, "Git 环境正常", "git_check")

            # Step 2: 拉取 / 克隆游戏数据
            if repo_dir.exists() and (repo_dir / ".git").exists():
                yield _emit(15, "正在拉取游戏数据更新...", "git_pull")
                ok, msg = _run_step([git, "pull"], cwd=str(repo_dir))
                if not ok:
                    update_state["error"] = f"数据拉取失败: {msg}"
                    err = json.dumps(
                        {"error": f"数据拉取失败: {msg}"}, ensure_ascii=False,
                    )
                    yield f"data: {err}\n\n"
                    return
                yield _emit(30, "游戏数据拉取完成", "git_pull")
            else:
                yield _emit(15, "首次使用，正在克隆游戏数据仓库（需几分钟）...", "git_clone")
                ok, msg = _run_step(
                    [git, "clone", "--depth", "1", "--filter=blob:none",
                     "--sparse", REPO_GIT_URL, str(repo_dir)],
                )
                if not ok:
                    update_state["error"] = f"仓库克隆失败: {msg}"
                    err = json.dumps(
                        {"error": f"仓库克隆失败: {msg}"}, ensure_ascii=False,
                    )
                    yield f"data: {err}\n\n"
                    return
                ok, msg = _run_step(
                    [git, "sparse-checkout", "set",
                     "zh_CN/gamedata/story", "zh_CN/gamedata/excel"],
                    cwd=str(repo_dir),
                )
                if not ok:
                    update_state["error"] = f"sparse-checkout 失败: {msg}"
                    err = json.dumps(
                        {"error": f"sparse-checkout 失败: {msg}"}, ensure_ascii=False,
                    )
                    yield f"data: {err}\n\n"
                    return
                yield _emit(30, "游戏数据克隆完成", "git_clone")

            # Step 3: 解析剧情数据
            yield _emit(35, "正在解析剧情文本...", "crawl")
            ok, msg = _run_step([python, "github_crawler.py"], cwd=str(BASE_DIR))
            if not ok:
                update_state["error"] = f"数据解析失败: {msg}"
                err = json.dumps(
                    {"error": f"数据解析失败: {msg}"}, ensure_ascii=False,
                )
                yield f"data: {err}\n\n"
                return
            yield _emit(60, "剧情文本解析完成", "crawl")

            # Step 4: 构建向量库
            yield _emit(65, "正在构建向量库（需要几分钟）...", "vector")
            ok, msg = _run_step([python, "vector_store.py"], cwd=str(BASE_DIR))
            if not ok:
                update_state["error"] = f"向量库构建失败: {msg}"
                err = json.dumps(
                    {"error": f"向量库构建失败: {msg}"}, ensure_ascii=False,
                )
                yield f"data: {err}\n\n"
                return
            yield _emit(90, "向量库构建完成", "vector")

            # Step 5: 导入泰拉年表（如存在原始文件）
            timeline_file = BASE_DIR / "data" / "timeline_raw.txt"
            if timeline_file.exists():
                yield _emit(92, "正在导入泰拉年表...", "timeline")
                _run_step([python, "import_timeline.py"], cwd=str(BASE_DIR))
                yield _emit(96, "泰拉年表导入完成", "timeline")

            # Step 6: 检查应用版本
            yield _emit(98, "正在检查应用版本...", "version")
            version_info = _check_app_version()

            # 清除旧会话，使后续对话加载新的向量库
            with sessions_lock:
                sessions.clear()
                session_busy.clear()

            yield _emit(100, "知识库更新完成！", "done")
            done_data = json.dumps({
                "done": True,
                "progress": 100,
                "message": "知识库更新完成！请刷新页面以加载新数据。",
                "version_info": version_info,
            }, ensure_ascii=False)
            yield f"data: {done_data}\n\n"

        except Exception as e:
            update_state["error"] = str(e)
            err = json.dumps(
                {"error": f"更新过程出错: {e}"}, ensure_ascii=False,
            )
            yield f"data: {err}\n\n"
        finally:
            update_state["in_progress"] = False
            update_state["started_at"] = None
            try:
                update_lock.release()
            except RuntimeError:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn
    print("启动服务器: http://localhost:8000")
    print("前端: http://localhost:36888")
    uvicorn.run(app, host="127.0.0.1", port=8000)

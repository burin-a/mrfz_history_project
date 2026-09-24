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


# 短缓存：仅做去抖，避免极端高频点击重复建立网络连接
# （git ls-remote 走 git 协议不受 api.github.com 限流，无需长 TTL）
_check_cache = {"ts": 0, "result": None}
_CHECK_CACHE_TTL = 60


@app.get("/api/check-update")
def check_update():
    """检查 ArknightsGameData 仓库是否有更新

    通过 git ls-remote 获取远程 master 的 commit SHA（走 git 协议端点
    github.com/.../xxx.git，不依赖 api.github.com，不受未认证 REST API
    60次/小时限制）。
    """
    repo_dir = BASE_DIR.parent / "ArknightsGameData"
    sha_file = BASE_DIR / "data" / ".last_repo_sha"

    if not repo_dir.exists():
        return {"status": "warning", "message": "本地数据源仓库不存在"}

    # 短缓存去抖：60 秒内重复请求直接返回上次结果
    now = time.time()
    cached = _check_cache["result"]
    if cached and (now - _check_cache["ts"]) < _CHECK_CACHE_TTL:
        return {**cached, "cached": True}

    git = _git_cmd()
    if not git:
        return {"status": "error", "message": "未检测到 Git，请先安装 Git"}

    try:
        result = subprocess.run(
            [git, "ls-remote", REPO_GIT_URL, "refs/heads/master"],
            capture_output=True, text=True, timeout=30, encoding="utf-8",
        )
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "请求超时，请检查网络连接"}
    except FileNotFoundError:
        return {"status": "error", "message": "未检测到 Git，请先安装 Git"}
    except Exception as e:
        return {"status": "error", "message": f"检查失败: {type(e).__name__}"}

    if result.returncode != 0:
        err = (result.stderr or "").strip()
        el = err.lower()
        if "could not resolve host" in el or "timed out" in el:
            return {"status": "error", "message": "无法连接 GitHub，请检查网络"}
        return {"status": "error", "message": f"检查失败: {err[:80]}"}

    # 输出格式：<sha>\trefs/heads/master
    remote_sha = result.stdout.strip().split()[0] if result.stdout.strip() else ""
    if not remote_sha:
        return {"status": "error", "message": "未能获取远程版本信息"}

    local_sha = sha_file.read_text().strip() if sha_file.exists() else ""
    if remote_sha == local_sha:
        out = {"status": "up_to_date", "message": "数据源已是最新版本"}
    else:
        out = {"status": "update_available", "message": "发现新版本，可点击「一键更新知识库」"}

    _check_cache["ts"] = now
    _check_cache["result"] = out
    return out


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


def _stream_step(cmd, cwd, timeout, label, step_name, p_start, p_end, result):
    """流式执行子进程，周期性推送心跳 SSE。

    子进程的 stdout/stderr 逐行读取，每隔约 1.5 秒推送一次心跳事件，
    进度在 [p_start, p_end] 区间内按已用时间渐近推进（半饱和约 25 秒），
    保证长时间运行的步骤也能持续给前端反馈，避免“假死”观感。

    结果写入 result dict: {"ok": bool, "msg": str}。
    失败时已推送 error 事件，调用方在 yield from 后只需检查 result["ok"]。
    """
    def _sse(progress, message, step):
        update_state.update({"progress": progress, "message": message, "step": step})
        return f"data: {json.dumps({'progress': progress, 'message': message, 'step': step}, ensure_ascii=False)}\n\n"

    def _err(message):
        update_state["error"] = message
        return f"data: {json.dumps({'error': message}, ensure_ascii=False)}\n\n"

    yield _sse(p_start, f"{label}...", step_name)

    try:
        proc = subprocess.Popen(
            cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
    except Exception as e:
        result["ok"], result["msg"] = False, str(e)
        yield _err(f"{label}启动失败: {e}")
        return

    collected = []
    start = time.time()
    last_beat = start
    timed_out = False
    try:
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            collected.append(line)
            now = time.time()
            if now - start > timeout:
                timed_out = True
                break
            if now - last_beat >= 1.5:
                tail = line.strip()[:70]
                elapsed = now - start
                frac = elapsed / (elapsed + 25)
                cur = int(p_start + (p_end - 3 - p_start) * frac)
                msg = f"{label}：{tail}" if tail else f"{label}中..."
                yield _sse(cur, msg, step_name)
                last_beat = now
        proc.wait()
    except Exception as e:
        try:
            proc.kill()
        except Exception:
            pass
        result["ok"], result["msg"] = False, str(e)
        yield _err(f"{label}出错: {e}")
        return

    if timed_out:
        try:
            proc.kill()
        except Exception:
            pass
        result["ok"], result["msg"] = False, "命令执行超时"
        yield _err(f"{label}超时")
        return

    output = "".join(collected)
    ok = proc.returncode == 0
    result["ok"], result["msg"] = ok, output[-400:]
    if not ok:
        # 识别 .git 权限拒绝（常见于 IDE 沙箱环境），给出可操作提示
        if "Permission denied" in output and ".git" in output:
            hint = (
                f"{label}失败：Git 无写入权限。"
                "请从 Windows 终端（非 IDE 内置终端）启动后端后重试。"
            )
            yield _err(hint)
        else:
            yield _err(f"{label}失败: {output[-400:]}")
        return
    yield _sse(p_end, f"{label}完成", step_name)


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
                _r = {}
                yield from _stream_step(
                    [git, "pull"], str(repo_dir), 600,
                    "拉取游戏数据更新", "git_pull", 15, 30, _r,
                )
                if not _r.get("ok"):
                    return
            else:
                _r = {}
                yield from _stream_step(
                    [git, "clone", "--depth", "1", "--filter=blob:none",
                     "--sparse", REPO_GIT_URL, str(repo_dir)],
                    None, 1200,
                    "克隆游戏数据仓库", "git_clone", 15, 28, _r,
                )
                if not _r.get("ok"):
                    return
                # sparse-checkout 较快，保持同步
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
            _r = {}
            yield from _stream_step(
                [python, "-u", "github_crawler.py"], str(BASE_DIR), 900,
                "解析剧情文本", "crawl", 35, 60, _r,
            )
            if not _r.get("ok"):
                return

            # Step 4: 构建向量库
            _r = {}
            yield from _stream_step(
                [python, "-u", "vector_store.py"], str(BASE_DIR), 1800,
                "构建向量库", "vector", 65, 90, _r,
            )
            if not _r.get("ok"):
                return

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

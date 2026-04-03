#!/usr/bin/env python3
"""Claude Code / Codex CLI 通知脚本

从 stdin 读取 Claude Code Stop hook 或 Codex CLI notify JSON，发送钉钉 Markdown 消息。
依赖：纯 Python 标准库，无需第三方包。

环境变量：
  DINGTALK_WEBHOOK  钉钉机器人 Webhook URL（必须）
  DINGTALK_SECRET   加签密钥（可选，SEC 开头）
"""

import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime


def get_value(data: dict, key: str):
    """兼容下划线和连字符字段名。"""
    if not isinstance(data, dict):
        return None
    if key in data:
        return data[key]
    alt_key = key.replace("_", "-")
    if alt_key in data:
        return data[alt_key]
    alt_key = key.replace("-", "_")
    if alt_key in data:
        return data[alt_key]
    return None


def get_session_identifier(data: dict) -> str:
    """提取唯一会话/线程标识符。"""
    return (
        get_value(data, "session_id")
        or get_value(data, "thread_id")
        or get_value(data, "thread-id")
        or "unknown"
    )


def get_state_file_path(session_id: str, source: str) -> str:
    """获取会话状态文件路径。"""
    if source == "claude":
        base = os.path.expanduser("~/.claude/state/dingtalk")
    else:
        base = os.path.expanduser("~/.codex/state/dingtalk")

    os.makedirs(base, exist_ok=True)
    return os.path.join(base, f"{session_id}.json")


def save_session_start(session_id: str, source: str) -> None:
    """记录会话开始时间。"""
    state_file = get_state_file_path(session_id, source)
    state = {
        "session_id": session_id,
        "start_time": time.time(),
        "last_activity": time.time(),
    }
    try:
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception as e:
        sys.stderr.write(f"[dingtalk_notify] 保存开始时间失败: {e}\n")


def get_session_duration(session_id: str, source: str) -> float | None:
    """计算会话时长（秒）。如果没有开始时间则返回 None。"""
    state_file = get_state_file_path(session_id, source)

    if not os.path.exists(state_file):
        return None

    try:
        with open(state_file, "r", encoding="utf-8") as f:
            state = json.load(f)

        start_time = state.get("start_time")
        if not start_time:
            return None

        duration = time.time() - start_time
        return duration
    except Exception as e:
        sys.stderr.write(f"[dingtalk_notify] 读取开始时间失败: {e}\n")
        return None


def cleanup_session_state(session_id: str, source: str) -> None:
    """通知发送后清理会话状态文件。"""
    state_file = get_state_file_path(session_id, source)
    try:
        if os.path.exists(state_file):
            os.remove(state_file)
    except Exception:
        pass


def cleanup_old_state_files(source: str, max_age_hours: int = 24) -> None:
    """清理超过 max_age_hours 的旧状态文件。"""
    if source == "claude":
        base = os.path.expanduser("~/.claude/state/dingtalk")
    else:
        base = os.path.expanduser("~/.codex/state/dingtalk")

    if not os.path.exists(base):
        return

    cutoff = time.time() - (max_age_hours * 3600)
    try:
        for filename in os.listdir(base):
            filepath = os.path.join(base, filename)
            if os.path.isfile(filepath) and os.path.getmtime(filepath) < cutoff:
                os.remove(filepath)
    except Exception:
        pass


def should_send_notification(data: dict, event: dict) -> tuple[bool, str]:
    """
    根据时长阈值判断是否应该发送通知。
    返回 (should_send, reason)。
    """
    # 检查是否启用时长过滤
    duration_enabled = os.environ.get("DINGTALK_DURATION_ENABLED", "false").lower() == "true"

    if not duration_enabled:
        return (True, "duration_filter_disabled")

    # 获取最小时长阈值
    try:
        min_duration = int(os.environ.get("DINGTALK_MIN_DURATION", "30"))
    except ValueError:
        min_duration = 30

    # 获取会话标识符
    session_id = get_session_identifier(data)
    if session_id == "unknown":
        return (True, "no_session_id")

    # 计算时长
    duration = get_session_duration(session_id, event["source"])

    if duration is None:
        # 没有开始时间记录 - 发送通知（首次运行或状态丢失）
        return (True, "no_start_time")

    # 检查阈值
    if duration >= min_duration:
        return (True, f"duration_{int(duration)}s_exceeds_threshold_{min_duration}s")
    else:
        return (False, f"duration_{int(duration)}s_below_threshold_{min_duration}s")


def read_stdin_json() -> dict:
    """读取并解析 stdin 传入的 hook JSON。"""
    try:
        import io
        raw = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8").read()
        return json.loads(raw) if raw.strip() else {}
    except Exception as e:
        sys.stderr.write(f"[dingtalk_notify] 解析 stdin 失败: {e}\n")
        return {}


def read_notify_payload(argv: list[str] | None = None) -> dict:
    """优先读取 Codex 通过 argv[1] 传入的 JSON，回退到 stdin。"""
    argv = argv if argv is not None else sys.argv
    if len(argv) >= 2:
        try:
            return json.loads(argv[1])
        except Exception:
            pass
    return read_stdin_json()


def check_loop_guard(data: dict) -> None:
    """若 stop_hook_active=true，直接退出，防止无限循环。"""
    if data.get("stop_hook_active", False):
        print("[dingtalk_notify] stop_hook_active=true，跳过通知")
        sys.exit(0)


def truncate_text(value: str, limit: int = 150) -> str:
    """截断文本，避免摘要过长。"""
    text = (value or "").strip()
    if not text:
        return "（无法获取摘要）"
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def extract_summary(data: dict) -> str:
    """从不同事件格式里提取摘要。"""
    msg = (
        get_value(data, "last_assistant_message")
        or get_value(data, "message")
        or get_value(data, "summary")
        or get_value(data, "text")
    )
    if isinstance(msg, dict):
        msg = (
            get_value(msg, "content")
            or get_value(msg, "text")
            or get_value(msg, "message")
            or get_value(msg, "title")
            or ""
        )
    if not msg:
        return "（无法获取摘要）"
    return truncate_text(str(msg))


def count_turns(transcript_path: str) -> int:
    """读取 transcript JSONL，统计 user 消息数（对话轮数）。"""
    if not transcript_path:
        return 0
    try:
        path = os.path.expanduser(transcript_path)
        if not os.path.exists(path):
            return 0
        count = 0
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    msg = obj.get("message", {})
                    if msg.get("role") == "user":
                        count += 1
                except Exception:
                    continue
        return count
    except Exception:
        return 0


MODE_LABELS = {
    "default": "\U0001F510 默认模式",
    "plan": "\U0001F4D0 计划模式",
    "acceptEdits": "\u270F 自动接受编辑",
    "auto": "\U0001F916 自动模式",
    "dontAsk": "\U0001F680 免确认模式",
    "bypassPermissions": "\u26A1 绕过权限模式",
}


def find_first_string(data, keys: tuple[str, ...]) -> str:
    """在常见字段里查找第一个非空字符串。"""
    if not isinstance(data, dict):
        return ""

    for key in keys:
        value = get_value(data, key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    return item.strip()
        if isinstance(value, dict):
            nested = find_first_string(
                value,
                ("content", "text", "message", "summary", "title", "cwd", "path"),
            )
            if nested:
                return nested

    for nested_key in ("metadata", "context", "data", "payload"):
        nested = get_value(data, nested_key)
        if isinstance(nested, dict):
            result = find_first_string(nested, keys)
            if result:
                return result

    return ""


def find_first_int(data, keys: tuple[str, ...]) -> int:
    """在常见字段里查找第一个整数。"""
    if not isinstance(data, dict):
        return 0

    for key in keys:
        value = get_value(data, key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        if isinstance(value, dict):
            nested = find_first_int(
                value,
                ("turn_count", "turns", "user_turns", "conversation_turns"),
            )
            if nested:
                return nested

    for nested_key in ("metadata", "context", "data", "payload"):
        nested = get_value(data, nested_key)
        if isinstance(nested, dict):
            result = find_first_int(nested, keys)
            if result:
                return result

    return 0


def detect_source(data: dict) -> str:
    """根据字段特征判断事件来源。"""
    if (
        get_value(data, "stop_hook_active") is not None
        or get_value(data, "transcript_path") is not None
        or get_value(data, "session_id") is not None
    ):
        return "claude"
    return "codex"


def normalize_event(data: dict) -> dict:
    """把 Claude/Codex 输入统一成内部事件格式。"""
    source = detect_source(data)
    cwd = find_first_string(data, ("cwd", "project_path", "workspace", "worktree_root", "path"))
    transcript_path = find_first_string(data, ("transcript_path", "transcript", "transcript_file"))
    permission_mode = find_first_string(
        data,
        ("permission_mode", "mode", "session_mode"),
    ) or "default"
    summary = extract_summary(data)
    turns = count_turns(transcript_path)
    if turns == 0:
        turns = find_first_int(data, ("turn_count", "turns", "user_turns", "conversation_turns"))

    project = os.path.basename(cwd) if cwd else "unknown"
    assistant_label = "Claude Code" if source == "claude" else "Codex"

    return {
        "source": source,
        "assistant_label": assistant_label,
        "cwd": cwd,
        "project": project,
        "summary": summary,
        "permission_mode": permission_mode,
        "turns": turns,
    }


def build_payload(
    assistant_label: str,
    project: str,
    turns: int,
    summary: str,
    permission_mode: str,
) -> dict:
    """构造钉钉 Markdown 类型消息 payload。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mode_label = MODE_LABELS.get(permission_mode, "\U0001F527 " + permission_mode)
    ok = "\u2705"
    clock = "\u23F0"
    folder = "\U0001F4C1"
    joystick = "\U0001F3AE"
    speech = "\U0001F4AC"
    memo = "\U0001F4DD"
    arrow = "\U0001F449"
    broom = "\U0001F9F9"

    clear_tip = ""
    if turns >= 8:
        clear_tip = (
            "\n\n---\n\n"
            f"{broom} **建议清空上下文**\uff1a"
            "\u672c\u6b21\u5bf9\u8bdd\u8f6e\u6570\u8f83\u591a"
            "\uff0c\u4efb\u52a1\u82e5\u5df2\u5b8c\u6210\uff0c"
            "\u5efa\u8bae\u6267\u884c `/clear` \u91ca\u653e Token"
        )

    text = (
        f"## {ok} {assistant_label} 任务完成啦！\n\n"
        f"{clock} **完成时间**\uff1a{now}\n\n"
        f"{folder} **当前项目**\uff1a`{project}`\n\n"
        f"{joystick} **工作模式**\uff1a{mode_label}\n\n"
        f"{speech} **对话轮数**\uff1a{turns} 轮\n\n"
        f"{memo} **内容摘要**\uff1a\n\n"
        f"> {summary}\n\n"
        "---\n\n"
        f"{arrow} 请前往终端查看完整结果"
        + clear_tip
    )

    return {
        "msgtype": "markdown",
        "markdown": {
            "title": f"{ok} {assistant_label} 任务完成",
            "text": text,
        },
    }


def sign_webhook(webhook: str, secret: str) -> str:
    """对 Webhook URL 追加钉钉加签参数（timestamp + sign）。"""
    import base64
    ts = str(round(time.time() * 1000))
    string_to_sign = f"{ts}\n{secret}"
    hmac_code = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code).decode("utf-8"))
    return f"{webhook}&timestamp={ts}&sign={sign}"


def send_notification(webhook: str, payload: dict) -> bool:
    """使用 urllib.request 发送 POST 请求到钉钉 Webhook。"""
    import ssl

    def _do_request(ctx=None):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            webhook,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        kwargs = {"timeout": 10}
        if ctx is not None:
            kwargs["context"] = ctx
        with urllib.request.urlopen(req, **kwargs) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)

    try:
        try:
            result = _do_request()
        except Exception as ssl_err:
            if "CERTIFICATE_VERIFY_FAILED" not in str(ssl_err) and not isinstance(ssl_err, ssl.SSLError):
                raise
            # Mac 系统 Python 未安装根证书时降级跳过验证
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            result = _do_request(ctx)
        if result.get("errcode") == 0:
            print("[dingtalk_notify] 发送成功")
            return True
        else:
            print(f"[dingtalk_notify] 发送失败: {result}")
            return False
    except Exception as e:
        print(f"[dingtalk_notify] 请求异常: {e}")
        return False


def main() -> None:
    # 检查 --track-start 标志
    if len(sys.argv) >= 2 and sys.argv[1] == "--track-start":
        # Start hook 模式：记录会话开始时间
        data = read_notify_payload(sys.argv[2:] if len(sys.argv) > 2 else None)
        session_id = get_session_identifier(data)
        source = detect_source(data)

        if session_id != "unknown":
            save_session_start(session_id, source)
            print(f"[dingtalk_notify] 会话开始追踪: {session_id}")

        sys.exit(0)

    # 正常通知模式
    data = read_notify_payload()
    check_loop_guard(data)

    webhook = os.environ.get("DINGTALK_WEBHOOK", "")
    if not webhook:
        print("[dingtalk_notify] 未设置 DINGTALK_WEBHOOK 环境变量，跳过通知")
        sys.exit(0)

    secret = os.environ.get("DINGTALK_SECRET", "")
    if secret:
        webhook = sign_webhook(webhook, secret)

    event = normalize_event(data)
    if event["project"] == "unknown":
        event["project"] = os.path.basename(os.getcwd())

    # 检查时长阈值
    should_send, reason = should_send_notification(data, event)

    if not should_send:
        print(f"[dingtalk_notify] 跳过通知: {reason}")
        # 清理状态文件
        session_id = get_session_identifier(data)
        if session_id != "unknown":
            cleanup_session_state(session_id, event["source"])
        sys.exit(0)

    print(f"[dingtalk_notify] 发送通知: {reason}")

    payload = build_payload(
        assistant_label=event["assistant_label"],
        project=event["project"],
        turns=event["turns"],
        summary=event["summary"],
        permission_mode=event["permission_mode"],
    )

    success = send_notification(webhook, payload)

    # 通知成功后清理状态文件
    if success:
        session_id = get_session_identifier(data)
        if session_id != "unknown":
            cleanup_session_state(session_id, event["source"])

    # 定期清理旧状态文件
    cleanup_old_state_files(event["source"])

    sys.exit(0)


if __name__ == "__main__":
    main()

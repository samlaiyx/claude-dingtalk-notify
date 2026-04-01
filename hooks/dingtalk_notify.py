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

    payload = build_payload(
        assistant_label=event["assistant_label"],
        project=event["project"],
        turns=event["turns"],
        summary=event["summary"],
        permission_mode=event["permission_mode"],
    )
    send_notification(webhook, payload)

    sys.exit(0)


if __name__ == "__main__":
    main()

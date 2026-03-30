#!/usr/bin/env python3
"""Claude Code Stop hook — 钉钉通知脚本

从 stdin 读取 Stop hook JSON，发送钉钉 Markdown 消息。
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


def read_stdin_json() -> dict:
    """读取并解析 stdin 传入的 hook JSON。"""
    try:
        import io
        raw = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8").read()
        return json.loads(raw) if raw.strip() else {}
    except Exception as e:
        sys.stderr.write(f"[dingtalk_notify] 解析 stdin 失败: {e}\n")
        return {}


def check_loop_guard(data: dict) -> None:
    """若 stop_hook_active=true，直接退出，防止无限循环。"""
    if data.get("stop_hook_active", False):
        print("[dingtalk_notify] stop_hook_active=true，跳过通知")
        sys.exit(0)


def extract_summary(data: dict) -> str:
    """从 last_assistant_message 截取前 150 字作为摘要。"""
    msg = data.get("last_assistant_message", "")
    if not msg:
        return "（无法获取摘要）"
    summary = msg.strip()[:150]
    if len(msg.strip()) > 150:
        summary += "…"
    return summary


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


def build_payload(project: str, turns: int, summary: str, permission_mode: str) -> dict:
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
        f"## {ok} Claude 任务完成啦！\n\n"
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
            "title": f"{ok} Claude 任务完成",
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
    data = read_stdin_json()
    check_loop_guard(data)

    webhook = os.environ.get("DINGTALK_WEBHOOK", "")
    if not webhook:
        print("[dingtalk_notify] 未设置 DINGTALK_WEBHOOK 环境变量，跳过通知")
        sys.exit(0)

    secret = os.environ.get("DINGTALK_SECRET", "")
    if secret:
        webhook = sign_webhook(webhook, secret)

    cwd = data.get("cwd", os.getcwd())
    project = os.path.basename(cwd) if cwd else "unknown"
    transcript_path = data.get("transcript_path", "")
    permission_mode = data.get("permission_mode", "default")

    summary = extract_summary(data)
    turns = count_turns(transcript_path)
    payload = build_payload(project, turns, summary, permission_mode)
    send_notification(webhook, payload)

    sys.exit(0)


if __name__ == "__main__":
    main()
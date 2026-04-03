import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "hooks" / "dingtalk_notify.py"


def load_module():
    spec = importlib.util.spec_from_file_location("dingtalk_notify", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DingtalkNotifyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.notify = load_module()

    def test_normalize_event_keeps_claude_stop_payload_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            transcript = Path(tmpdir) / "transcript.jsonl"
            transcript.write_text(
                "\n".join(
                    [
                        json.dumps({"message": {"role": "user", "content": "hi"}}),
                        json.dumps({"message": {"role": "assistant", "content": "hello"}}),
                        json.dumps({"message": {"role": "user", "content": "done?"}}),
                    ]
                ),
                encoding="utf-8",
            )

            event = self.notify.normalize_event(
                {
                    "session_id": "test",
                    "stop_hook_active": False,
                    "transcript_path": str(transcript),
                    "last_assistant_message": "Claude 已经完成任务",
                    "cwd": str(Path(tmpdir) / "demo-project"),
                    "permission_mode": "plan",
                }
            )

        self.assertEqual(event["source"], "claude")
        self.assertEqual(event["assistant_label"], "Claude Code")
        self.assertEqual(event["project"], "demo-project")
        self.assertEqual(event["summary"], "Claude 已经完成任务")
        self.assertEqual(event["permission_mode"], "plan")
        self.assertEqual(event["turns"], 2)

    def test_normalize_event_accepts_codex_notify_payload(self):
        event = self.notify.normalize_event(
            {
                "event": "turn.completed",
                "cwd": r"D:\work\codex-demo",
                "title": "Codex 任务完成",
                "message": "实现已完成，测试通过",
                "metadata": {
                    "mode": "default",
                    "turn_count": 4,
                },
            }
        )

        self.assertEqual(event["source"], "codex")
        self.assertEqual(event["assistant_label"], "Codex")
        self.assertEqual(event["project"], "codex-demo")
        self.assertEqual(event["summary"], "实现已完成，测试通过")
        self.assertEqual(event["permission_mode"], "default")
        self.assertEqual(event["turns"], 4)

    def test_normalize_event_accepts_real_codex_notify_payload_shape(self):
        event = self.notify.normalize_event(
            {
                "type": "agent-turn-complete",
                "thread-id": "019d483b-5a49-70f1-979e-03e42291f0db",
                "turn-id": "019d483b-5cb3-7a40-86a1-8b9b0eeeeafa",
                "cwd": r"D:\claude-workspace",
                "client": "codex-exec",
                "input-messages": ["请只回复这六个字：通知测试中文"],
                "last-assistant-message": "通知测试中文",
            }
        )

        self.assertEqual(event["source"], "codex")
        self.assertEqual(event["assistant_label"], "Codex")
        self.assertEqual(event["project"], "claude-workspace")
        self.assertEqual(event["summary"], "通知测试中文")

    def test_build_payload_uses_assistant_label(self):
        payload = self.notify.build_payload(
            assistant_label="Codex",
            project="codex-demo",
            turns=1,
            summary="任务完成",
            permission_mode="default",
        )

        self.assertEqual(payload["markdown"]["title"], "✅ Codex 任务完成")
        self.assertIn("## ✅ Codex 任务完成啦！", payload["markdown"]["text"])

    def test_get_session_identifier(self):
        """测试会话标识符提取"""
        # Claude Code session_id
        data1 = {"session_id": "claude-session-123"}
        self.assertEqual(self.notify.get_session_identifier(data1), "claude-session-123")

        # Codex thread_id (underscore)
        data2 = {"thread_id": "codex-thread-456"}
        self.assertEqual(self.notify.get_session_identifier(data2), "codex-thread-456")

        # Codex thread-id (hyphen)
        data3 = {"thread-id": "codex-thread-789"}
        self.assertEqual(self.notify.get_session_identifier(data3), "codex-thread-789")

        # No identifier
        data4 = {"other": "value"}
        self.assertEqual(self.notify.get_session_identifier(data4), "unknown")

    def test_session_duration_tracking(self):
        """测试会话时长追踪"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 临时修改状态目录
            session_id = "test-session-duration"
            source = "claude"

            # 保存开始时间
            self.notify.save_session_start(session_id, source)

            # 等待 2 秒
            time.sleep(2)

            # 获取时长
            duration = self.notify.get_session_duration(session_id, source)
            self.assertIsNotNone(duration)
            self.assertGreaterEqual(duration, 2.0)
            self.assertLess(duration, 3.0)

            # 清理
            self.notify.cleanup_session_state(session_id, source)

            # 验证清理后无法获取时长
            duration_after = self.notify.get_session_duration(session_id, source)
            self.assertIsNone(duration_after)

    def test_should_send_notification_disabled(self):
        """测试时长过滤未启用时总是发送"""
        os.environ["DINGTALK_DURATION_ENABLED"] = "false"

        data = {"session_id": "test"}
        event = {"source": "claude"}

        should_send, reason = self.notify.should_send_notification(data, event)
        self.assertTrue(should_send)
        self.assertEqual(reason, "duration_filter_disabled")

    def test_should_send_notification_below_threshold(self):
        """测试时长低于阈值时跳过通知"""
        os.environ["DINGTALK_DURATION_ENABLED"] = "true"
        os.environ["DINGTALK_MIN_DURATION"] = "30"

        session_id = "test-short-session"
        data = {"session_id": session_id}
        event = {"source": "claude"}

        # 保存开始时间
        self.notify.save_session_start(session_id, "claude")

        # 立即检查（时长 ~0s）
        should_send, reason = self.notify.should_send_notification(data, event)
        self.assertFalse(should_send)
        self.assertIn("below_threshold", reason)

        # 清理
        self.notify.cleanup_session_state(session_id, "claude")

    def test_should_send_notification_above_threshold(self):
        """测试时长超过阈值时发送通知"""
        os.environ["DINGTALK_DURATION_ENABLED"] = "true"
        os.environ["DINGTALK_MIN_DURATION"] = "1"

        session_id = "test-long-session"
        data = {"session_id": session_id}
        event = {"source": "claude"}

        # 保存开始时间
        self.notify.save_session_start(session_id, "claude")

        # 等待 2 秒
        time.sleep(2)

        # 检查
        should_send, reason = self.notify.should_send_notification(data, event)
        self.assertTrue(should_send)
        self.assertIn("exceeds_threshold", reason)

        # 清理
        self.notify.cleanup_session_state(session_id, "claude")

    def test_should_send_notification_no_start_time(self):
        """测试没有开始时间时发送通知（fail-safe）"""
        os.environ["DINGTALK_DURATION_ENABLED"] = "true"

        session_id = "test-no-start"
        data = {"session_id": session_id}
        event = {"source": "claude"}

        # 不保存开始时间
        should_send, reason = self.notify.should_send_notification(data, event)
        self.assertTrue(should_send)
        self.assertEqual(reason, "no_start_time")

    def test_should_send_notification_no_session_id(self):
        """测试没有会话 ID 时发送通知"""
        os.environ["DINGTALK_DURATION_ENABLED"] = "true"

        data = {"other": "value"}
        event = {"source": "claude"}

        should_send, reason = self.notify.should_send_notification(data, event)
        self.assertTrue(should_send)
        self.assertEqual(reason, "no_session_id")


if __name__ == "__main__":
    unittest.main()

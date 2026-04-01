import importlib.util
import json
import tempfile
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


if __name__ == "__main__":
    unittest.main()

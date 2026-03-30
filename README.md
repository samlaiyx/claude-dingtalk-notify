# claude-dingtalk-notify

> Claude Code / Codex 对话结束后，自动发送钉钉通知。纯 Python 标准库，零依赖，傻瓜式安装。

![效果示例](docs/screenshot.png)

---

## 通知内容

| 字段 | 说明 |
|---|---|
| ✅ 完成状态 | 任务完成标题 |
| ⏰ 完成时间 | 精确到秒 |
| 📁 当前项目 | 工作目录名 |
| 🎮 工作模式 | plan / auto / default 等 |
| 💬 对话轮数 | 本次对话 user 消息数 |
| 📝 内容摘要 | 最后一条 AI 回复前 150 字 |
| 🧹 清空建议 | 轮数 ≥ 8 时提示执行 /clear |

---

## 前置要求

- Python 3.8+（系统自带即可，**无需 pip 安装任何包**）
- 钉钉群机器人 Webhook
- Claude Code 或 Codex

---

## 第一步：获取钉钉 Webhook

1. 打开钉钉群 → 右上角「···」→「智能群助手」
2. 点击「添加机器人」→「自定义」→「添加」
3. 安全设置选择「**加签**」，复制 `SEC` 开头的密钥
4. 完成后复制 Webhook URL（`https://oapi.dingtalk.com/robot/send?access_token=...`）

---

## 第二步：安装

### Mac / Linux（推荐）

```bash
git clone https://github.com/你的用户名/claude-dingtalk-notify.git
cd claude-dingtalk-notify
bash install.sh
```

按提示输入 Webhook URL 和加签密钥，自动完成所有配置。

### Windows

```bat
git clone https://github.com/你的用户名/claude-dingtalk-notify.git
cd claude-dingtalk-notify
install.bat
```

然后按脚本提示手动编辑 `settings.json`（见下方）。

### 手动安装（任意系统）

1. 复制脚本：
   ```bash
   cp hooks/dingtalk_notify.py ~/.claude/hooks/
   ```

2. 编辑 `~/.claude/settings.json`，添加以下内容（与已有字段合并）：
   ```json
   {
     "env": {
       "DINGTALK_WEBHOOK": "你的Webhook地址",
       "DINGTALK_SECRET": "你的加签密钥"
     },
     "hooks": {
       "Stop": [
         {
           "hooks": [
             {
               "type": "command",
               "command": "python3 ~/.claude/hooks/dingtalk_notify.py",
               "async": true
             }
           ]
         }
       ]
     }
   }
   ```

> **Windows 用户注意**：将 `command` 中的 `python3` 替换为 Python 的完整路径，例如：
> `C:\Users\你的用户名\AppData\Local\Programs\Python\Python312\python.exe ~/.claude/hooks/dingtalk_notify.py`

---

## 第三步：测试

```bash
# Mac/Linux
echo '{"session_id":"test","stop_hook_active":false,"transcript_path":"","last_assistant_message":"测试消息，验证通知是否正常。","cwd":"/your/project","permission_mode":"default"}' \
  | python3 ~/.claude/hooks/dingtalk_notify.py

# Windows PowerShell
'{"session_id":"test","stop_hook_active":false,"transcript_path":"","last_assistant_message":"测试消息","cwd":"C:\\test","permission_mode":"default"}' | python ~/.claude/hooks/dingtalk_notify.py
```

输出 `[dingtalk_notify] 发送成功` 即表示安装成功。

---

## Codex 使用

Codex 暂无原生 Stop hook，可在任务完成后手动触发：

```bash
echo '{"session_id":"codex-task","stop_hook_active":false,"transcript_path":"","last_assistant_message":"任务完成","cwd":"'$(pwd)'","permission_mode":"default"}' \
  | python3 ~/.claude/hooks/dingtalk_notify.py
```

或将其封装为 alias：

```bash
# 加入 ~/.bashrc 或 ~/.zshrc
alias notify-done='echo "{\"session_id\":\"manual\",\"stop_hook_active\":false,\"transcript_path\":\"\",\"last_assistant_message\":\"任务完成\",\"cwd\":\"$(pwd)\",\"permission_mode\":\"default\"}" | python3 ~/.claude/hooks/dingtalk_notify.py'
```

---

## 环境变量说明

| 变量 | 必填 | 说明 |
|---|---|---|
| `DINGTALK_WEBHOOK` | ✅ | 钉钉机器人 Webhook URL |
| `DINGTALK_SECRET` | 可选 | 加签密钥（`SEC` 开头），安全性更高 |

---

## FAQ

**Q: 通知没有收到？**
- 检查 `DINGTALK_WEBHOOK` 环境变量是否已设置
- 检查钉钉机器人的安全设置（加签密钥是否匹配）
- 手动运行测试命令查看输出

**Q: Windows 显示乱码？**
- 确保使用完整 Python 路径，不要用 `python3`（Windows 的 `python3` 指向 Microsoft Store stub）
- 参考上方「手动安装」的 Windows 注意事项

**Q: 怎么关闭通知？**
- 删除 `settings.json` 中的 `hooks.Stop` 段，或将 `DINGTALK_WEBHOOK` 环境变量清空

**Q: 支持其他通知渠道吗？**
- 欢迎 PR！只需修改 `build_payload` 和 `send_notification` 函数即可适配企业微信、飞书等

---

## License

MIT

# claude-dingtalk-notify

> Claude Code / Codex CLI 对话结束后，自动发送钉钉通知。纯 Python 标准库，零依赖。

## Latest Update

`2026-04-01`

- 新增 `Codex CLI notify` 兼容
- 修复 Codex 中文摘要异常 / 空白 / 看起来像乱码的问题
- README 重写为 `Claude Code` / `Codex CLI` 双通道说明

**本次兼容的关键节点**

- `Claude Code` 的通知数据来自 `stdin`
- `Codex CLI` 的通知数据来自通知命令参数 `argv[1]`
- 脚本现在同时兼容 `stdin` 和 `argv[1]`
- 已兼容 Codex 实际字段名：`last-assistant-message`

![效果示例](docs/screenshot.png)

---

## 现在支持什么

- `Claude Code`：通过 `hooks.Stop` 自动通知
- `Codex CLI`：通过 `notify = [...]` 自动通知
- `Codex App`：有自己的系统完成通知，但**不等于**钉钉 Webhook；本项目主要覆盖 `Claude Code` 和 `Codex CLI`

## 兼容 Codex 更新节点

这次更新专门补了 `Codex CLI` 兼容，核心变化只有 3 个：

1. `Codex CLI notify` 的 payload 不在 `stdin`，而是在通知命令的第一个参数 `argv[1]`
2. 脚本新增了 `argv[1] -> stdin` 的双入口解析，继续兼容 `Claude Code Stop hook`
3. 新增了对 Codex 实际字段名的兼容，例如 `last-assistant-message`

如果你之前能发通知但中文摘要异常、空白、或看起来像乱码，通常就是旧脚本还在按 `stdin` 读取 Codex payload。

---

## 一眼看懂

| 客户端 | 配置入口 | 数据入口 | 当前状态 |
|---|---|---|---|
| Claude Code | `settings.json -> hooks.Stop` | `stdin` | ✅ 已兼容 |
| Codex CLI | `config.toml -> notify` | `argv[1]` | ✅ 已兼容 |
| Codex App | 应用内系统通知 | 非本项目链路 | ℹ️ 不走钉钉脚本 |

---

## 通知内容

| 字段 | 说明 |
|---|---|
| ✅ 完成状态 | 任务完成标题 |
| ⏰ 完成时间 | 精确到秒 |
| 📁 当前项目 | 工作目录名 |
| 🎮 工作模式 | `plan` / `default` / `auto` 等 |
| 💬 对话轮数 | 能识别时显示 user 消息数 |
| 📝 内容摘要 | 最后一条 AI 回复前 150 字 |
| 🧹 清空建议 | 轮数 ≥ 8 时提示执行 `/clear` |

> Claude Code 的 hook 数据来自 `stdin`。Codex CLI 的 `notify` 数据来自通知命令的参数 JSON，不走 `stdin`；脚本已同时兼容两种入口。

---

## 前置要求

- Python 3.8+（无需安装第三方包）
- 钉钉群机器人 Webhook
- Claude Code 或 Codex CLI

---

## 第一步：获取钉钉 Webhook

1. 打开钉钉群，进入「智能群助手」
2. 添加「自定义机器人」
3. 安全设置建议选择「加签」，复制 `SEC` 开头密钥
4. 保存 Webhook URL，例如 `https://oapi.dingtalk.com/robot/send?access_token=...`

---

## 第二步：安装脚本

### Mac / Linux

```bash
git clone https://github.com/samlaiyx/claude-dingtalk-notify.git
cd claude-dingtalk-notify
bash install.sh
```

安装脚本会把同一份通知脚本复制到：

- `~/.claude/hooks/dingtalk_notify.py`
- `~/.codex/notify/dingtalk_notify.py`

### Windows

```bat
git clone https://github.com/samlaiyx/claude-dingtalk-notify.git
cd claude-dingtalk-notify
install.bat
```

安装脚本会把脚本复制到：

- `%USERPROFILE%\.claude\hooks\dingtalk_notify.py`
- `%USERPROFILE%\.codex\notify\dingtalk_notify.py`

---

## 第三步：配置环境变量

脚本需要以下环境变量：

| 变量 | 必填 | 说明 |
|---|---|---|
| `DINGTALK_WEBHOOK` | ✅ | 钉钉机器人 Webhook URL |
| `DINGTALK_SECRET` | 可选 | 加签密钥（`SEC` 开头） |

### Claude Code

可以直接放在 `~/.claude/settings.json` 的 `env` 里，参考 [`examples/claude-code-settings.json`](examples/claude-code-settings.json)。

### Codex CLI

Codex CLI 没有 Claude Code 那种 `settings.json env` 配置。最简单的做法是：

- 在启动 Codex 的 shell 环境里提前设置 `DINGTALK_WEBHOOK`
- 如果用了加签，再设置 `DINGTALK_SECRET`

Windows 用户可以直接设置系统级环境变量；Mac / Linux 用户可以写入 `~/.zshrc`、`~/.bashrc` 等 shell 配置。

---

## 第四步：配置 Claude Code

编辑 `~/.claude/settings.json`，与现有字段合并：

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

Windows 用户请把 `python3` 换成 Python 绝对路径。

---

## 第五步：配置 Codex CLI

编辑 `~/.codex/config.toml`，添加：

```toml
notify = ["python3", "/Users/yourname/.codex/notify/dingtalk_notify.py"]
```

Windows 示例：

```toml
notify = [
  "C:\\Users\\yourname\\AppData\\Local\\Programs\\Python\\Python312\\python.exe",
  "C:\\Users\\yourname\\.codex\\notify\\dingtalk_notify.py",
]
```

可直接参考 [`examples/codex-config.toml`](examples/codex-config.toml)。

> `notify` 是 Codex CLI 的通知命令入口，和 Claude Code 的 `hooks.Stop` 不是一回事。

---

## 测试

### Claude Code payload 手动测试

```bash
# Mac / Linux
echo '{"session_id":"test","stop_hook_active":false,"transcript_path":"","last_assistant_message":"测试消息","cwd":"/your/project","permission_mode":"default"}' \
  | python3 ~/.claude/hooks/dingtalk_notify.py

# Windows PowerShell
'{"session_id":"test","stop_hook_active":false,"transcript_path":"","last_assistant_message":"测试消息","cwd":"C:\\test","permission_mode":"default"}' `
  | python C:\Users\你的用户名\.claude\hooks\dingtalk_notify.py
```

### Codex CLI 风格 payload 手动测试

```bash
python3 ~/.codex/notify/dingtalk_notify.py '{"type":"agent-turn-complete","cwd":"/your/project","last-assistant-message":"任务完成"}'
```

输出 `[dingtalk_notify] 发送成功` 即表示安装成功。

---

## FAQ

**Q: Claude Code 能通知，Codex CLI 不能，为什么？**

- 检查 `~/.codex/config.toml` 里是否真的配置了 `notify = [...]`
- 检查 `notify` 指向的 Python 路径和脚本路径是否为绝对路径
- 检查启动 Codex CLI 的环境里是否有 `DINGTALK_WEBHOOK`

**Q: Codex App 的完成通知和这个项目有什么关系？**

- Codex App 自带系统完成通知
- 这个项目是把完成事件转发到钉钉群机器人，两者不是同一个能力

**Q: Windows 显示乱码？**

- 使用完整 Python 路径，不要依赖 `python3`
- 不要把 Codex `notify` 当成 `stdin` JSON 读取；Codex 会把 payload 作为命令参数传入

**Q: 怎么关闭通知？**

- Claude Code：删除 `settings.json` 里的 `hooks.Stop`
- Codex CLI：删除 `config.toml` 里的 `notify`
- 或清空 `DINGTALK_WEBHOOK`

**Q: 支持其他通知渠道吗？**

- 可以，修改 `build_payload` 和 `send_notification` 即可适配飞书、企业微信等

---

## 开发测试

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

---

## License

MIT

#!/usr/bin/env bash
# claude-dingtalk-notify 一键安装脚本（Mac/Linux）
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== Claude 钉钉通知 Hook 安装器 ===${NC}"
echo ""

# 1. 创建目录
HOOKS_DIR="$HOME/.claude/hooks"
mkdir -p "$HOOKS_DIR"
echo -e "${GREEN}✓${NC} 目录已就绪：$HOOKS_DIR"

# 2. 复制脚本
SCRIPT_SRC="$(dirname "$0")/hooks/dingtalk_notify.py"
cp "$SCRIPT_SRC" "$HOOKS_DIR/dingtalk_notify.py"
chmod +x "$HOOKS_DIR/dingtalk_notify.py"
echo -e "${GREEN}✓${NC} 脚本已安装：$HOOKS_DIR/dingtalk_notify.py"

# 3. 获取 Webhook
echo ""
echo -e "${YELLOW}请输入钉钉 Webhook URL：${NC}"
echo "  （格式：https://oapi.dingtalk.com/robot/send?access_token=xxx）"
read -r WEBHOOK

echo -e "${YELLOW}请输入加签密钥（可选，直接回车跳过）：${NC}"
echo "  （格式：SEC 开头的字符串）"
read -r SECRET

# 4. 更新 settings.json
SETTINGS="$HOME/.claude/settings.json"
if [ ! -f "$SETTINGS" ]; then
  echo '{}' > "$SETTINGS"
fi

# 用 Python 合并 JSON（避免依赖 jq）
python3 - <<PYEOF
import json, os
p = os.path.expanduser('~/.claude/settings.json')
with open(p) as f:
    s = json.load(f)
s.setdefault('env', {})
s['env']['DINGTALK_WEBHOOK'] = '$WEBHOOK'
if '$SECRET':
    s['env']['DINGTALK_SECRET'] = '$SECRET'
s.setdefault('hooks', {}).setdefault('Stop', [{'hooks': []}])['Stop'][0]['hooks'] = [
    {'type': 'command', 'command': 'python3 ~/.claude/hooks/dingtalk_notify.py', 'async': True}
]
with open(p, 'w') as f:
    json.dump(s, f, indent=2, ensure_ascii=False)
print('settings.json 已更新')
PYEOF

echo ""
echo -e "${GREEN}=== 安装完成！===${NC}"
echo ""
echo "测试命令："
echo "  echo '{\"session_id\":\"test\",\"stop_hook_active\":false,\"transcript_path\":\"\",\"last_assistant_message\":\"测试消息\",\"cwd\":\"$PWD\",\"permission_mode\":\"default\"}' | python3 ~/.claude/hooks/dingtalk_notify.py"
echo ""
echo -e "${YELLOW}重启 Claude Code 后 Hook 生效。${NC}"

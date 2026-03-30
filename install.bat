@echo off
chcp 65001 >nul
echo === Claude 钉钉通知 Hook 安装器 (Windows) ===
echo.

set HOOKS_DIR=%USERPROFILE%\.claude\hooks
set SETTINGS=%USERPROFILE%\.claude\settings.json

if not exist "%HOOKS_DIR%" mkdir "%HOOKS_DIR%"
echo [OK] 目录已就绪：%HOOKS_DIR%

copy /Y "%~dp0hooks\dingtalk_notify.py" "%HOOKS_DIR%\dingtalk_notify.py" >nul
echo [OK] 脚本已安装：%HOOKS_DIR%\dingtalk_notify.py

echo.
echo 接下来请手动完成配置：
echo.
echo 1. 打开文件：%SETTINGS%
echo    （如果不存在，创建一个空的 {} 文件）
echo.
echo 2. 在 "env" 段中添加：
echo    "DINGTALK_WEBHOOK": "https://oapi.dingtalk.com/robot/send?access_token=你的token"
echo    "DINGTALK_SECRET": "SEC你的加签密钥（可选）"
echo.
echo 3. 在 "hooks" 段中添加 Stop hook（见 examples\claude-code-settings.json）
echo.
echo 4. 测试命令（在 PowerShell 中运行）：
echo    echo {"session_id":"test","stop_hook_active":false,"transcript_path":"","last_assistant_message":"测试","cwd":"C:\test","permission_mode":"default"} | python %HOOKS_DIR%\dingtalk_notify.py
echo.
echo [完成] 重启 Claude Code 后 Hook 生效。
pause

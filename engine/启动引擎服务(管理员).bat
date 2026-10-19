@echo off
chcp 65001 >nul
title 小蕾米引擎 - 后台服务（供小蕾米桌宠连接）
echo ============================================
echo   小蕾米引擎 后台服务
echo   启动后小蕾米桌宠的[一键日常]即可连接本引擎。
echo   弹出管理员确认窗口时点[是]。
echo   本窗口保持开着（最小化即可），关掉=服务停止。
echo ============================================
echo.
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
powershell -NoProfile -Command "Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList ('-m zzz_od.backend.entry.server --host 127.0.0.1 --port 23001') -Verb RunAs -WorkingDirectory '%~dp0'"
if errorlevel 1 (
    echo 启动失败: 未确认管理员权限或启动异常
    pause
    exit /b 1
)
echo 服务已在后台启动（127.0.0.1:23001）。
echo 请把桌宠目录下 绝区零配置.json 的 engine_dir 改为:
echo   %~dp0
pause

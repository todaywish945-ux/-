@echo off
chcp 65001 >nul
title 小蕾米引擎 - 安装服务（开机自启 + 桌宠配置）
echo ============================================
echo   一次性安装（之后桌宠[一键日常]直接可用）
echo   1. 结束旧引擎占用
echo   2. 引擎服务设为开机自启（日常免弹窗）
echo   3. 小蕾米桌宠自动指向迷你引擎（原配置备份）
echo   弹出管理员确认窗口时点[是]
echo ============================================
echo.
cd /d "%~dp0"
powershell -NoProfile -Command "Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList ('\"' + '%~dp0' + 'scripts\setup_service.py\"') -Verb RunAs -WorkingDirectory '%~dp0'"
if errorlevel 1 (
    echo 启动失败: 未确认管理员权限
    pause
    exit /b 1
)
echo 已在新窗口执行安装，完成后该窗口会提示。
pause

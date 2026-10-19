@echo off
chcp 65001 >nul
title 小蕾米引擎 - 一键日常
echo ============================================
echo   小蕾米引擎 一键日常
echo   流程: 吼吼饼铺签到 → 咖啡 → 录像店营业 → 活跃奖励
echo.
echo   注意:
echo   1. 游戏要开着（或已配置游戏路径可自动开游戏）
echo   2. 弹出管理员确认窗口时点[是]
echo   3. 运行期间双手离开键鼠, 别关游戏窗口
echo ============================================
echo.
cd /d "%~dp0"
powershell -NoProfile -Command "Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList ('\"' + '%~dp0' + 'scripts\run_app_elevated.py\" one_dragon') -Verb RunAs -WorkingDirectory '%~dp0'"
if errorlevel 1 (
    echo 启动失败: 未确认管理员权限或启动异常
    pause
    exit /b 1
)
echo 已在新窗口启动一条龙, 进度请看那个窗口。
echo 本窗口可以关掉。
pause

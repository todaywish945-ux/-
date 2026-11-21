@echo off
chcp 65001 >nul
cd /d %~dp0
rem 由计划任务或手动调用：执行绝区零一条龙（自动启动引擎、打开游戏、跑完全部启用任务）
python zzz_daily.py chain >> "%~dp0绝区零定时.log" 2>&1

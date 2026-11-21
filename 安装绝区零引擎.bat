@echo off
chcp 65001 >nul
cd /d %~dp0
rem 一键安装绝区零引擎（首次使用每日任务功能时运行一次即可）
python setup_engine.py
pause

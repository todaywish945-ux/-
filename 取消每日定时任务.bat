@echo off
chcp 65001 >nul
schtasks /Delete /TN "绝区零每日任务" /F
if %errorlevel%==0 (echo 已取消每日定时任务。) else (echo 未找到该任务或删除失败。)
pause

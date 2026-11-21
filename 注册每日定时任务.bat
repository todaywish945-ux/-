@echo off
chcp 65001 >nul
cd /d %~dp0
rem 注册 Windows 计划任务：每天 08:00 自动执行绝区零日常（改时间改 /ST= 后面）
schtasks /Create /F /SC DAILY /ST 08:00 /TN "绝区零每日任务" /TR "\"%~dp0跑绝区零每日.bat\""
if %errorlevel%==0 (
  echo 已注册：每天 08:00 自动跑绝区零日常。
  echo 修改时间：任务计划程序里找 "绝区零每日任务"，或重新运行本脚本前改 /ST 时间。
) else (
  echo 注册失败：请右键"以管理员身份运行"本脚本后重试。
)
pause

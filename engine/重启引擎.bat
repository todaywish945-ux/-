@echo off
title 小蕾米引擎 - 重启（免管理员权限）
cd /d "%~dp0"
echo ============================================
echo   小蕾米引擎 热重启
echo   用途：代码/配置更新后让引擎加载最新内容
echo   注意：若有正在运行的任务会被中断
echo ============================================
echo.

echo 正在通知引擎热重启（免管理员权限）…
powershell -NoProfile -Command "try { Invoke-RestMethod -Method POST -Uri 'http://127.0.0.1:23001/service/reload' -TimeoutSec 5 | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 (
    echo 引擎不在线，改由计划任务拉起…
    schtasks /run /tn "小蕾米引擎服务" >nul 2>&1
)

echo 等待旧实例退出…
ping -n 7 127.0.0.1 >nul

echo 等待服务就绪，最长 60 秒…
powershell -NoProfile -Command "$up=$false; for($i=0;$i -lt 30;$i++){ Start-Sleep 2; try { $r=Invoke-RestMethod 'http://127.0.0.1:23001/health' -TimeoutSec 2; if($r.ok){ $up=$true; break } } catch {} }; if($up){ Write-Host '引擎已重启并就绪，最新代码已生效' } else { Write-Host '等待超时：请查看 debug\引擎服务.log' }"
echo.
pause
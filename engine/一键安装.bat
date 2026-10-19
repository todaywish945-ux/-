@echo off
title 小蕾米引擎 - 一键安装
cd /d "%~dp0"
echo ============================================
echo   小蕾米引擎 一键安装
echo   弹出管理员确认窗口时点【是】即可
echo ============================================
echo.
set "PYEXE="
if exist "runtime\python.exe" (
    set "PYEXE=%~dp0runtime\python.exe"
    echo 检测到便携运行时（runtime），无需安装依赖。
) else (
    echo 仓库不含 runtime，改用本机 Python 构建环境...
    set "PYCMD="
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul && set "PYCMD=py -3"
    if not defined PYCMD python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul && set "PYCMD=python"
    if not defined PYCMD (
        echo 未找到 Python 3.10+，且缺少 runtime 目录。
        echo 请安装 Python 并勾选 Add to PATH 后重新运行，或向作者索取含 runtime 的完整压缩包。
        pause
        exit /b 1
    )
    if not exist ".venv\Scripts\python.exe" (
        echo 正在创建虚拟环境...
        %PYCMD% -m venv .venv
    )
    if not exist ".venv\Scripts\python.exe" (
        echo 虚拟环境创建失败。
        pause
        exit /b 1
    )
    echo 正在安装依赖（清华镜像，约 1-3 分钟）...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet
    if errorlevel 1 (
        echo 依赖安装失败：请检查网络后重新运行。
        pause
        exit /b 1
    )
    set "PYEXE=%~dp0.venv\Scripts\python.exe"
)
echo 启动安装（注册开机自启 + 对接桌宠 + 探测游戏路径）...
powershell -NoProfile -Command "Start-Process -FilePath '%PYEXE%' -ArgumentList ('\"' + '%~dp0' + 'scripts\setup_service.py\"') -Verb RunAs -WorkingDirectory '%~dp0'"
if errorlevel 1 (
    echo 未确认管理员权限，安装取消。
    pause
    exit /b 1
)
echo 安装已在管理员窗口执行，完成后即可使用小蕾米桌宠。
echo 以后代码更新：双击 重启引擎.bat 热生效。
pause

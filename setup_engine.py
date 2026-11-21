# -*- coding: utf-8 -*-
"""
绝区零引擎一键安装脚本（随小蕾米桌宠分发 · 离线优先）
======================================================
给其他玩家准备：双击 安装绝区零引擎.bat（或 python setup_engine.py），
自动完成「绝区零一条龙」引擎的安装与配置预置，装好后桌宠即可一键执行
每日任务。纯标准库，无需预装任何第三方包。

安装模式（自动选择）：
  - 离线包模式：脚本同目录存在 引擎离线包/ 文件夹（含引擎主包、uv、
    便携 Python、配置模板）时，全部使用本地文件，不需要访问 GitHub；
    仅安装依赖时从国内 PyPI 镜像（清华源）下载约 2GB。
  - 在线模式：没有离线包时，自动从 GitHub 下载后走同样流程。

可重复运行：已完成的步骤自动跳过；下载失败时按提示手动把文件放进
_cache 目录后重跑即可。
"""
import os
import sys
import json
import shutil
import zipfile
import subprocess
import urllib.request

ENGINE_TAG_FALLBACK = 'v2.5.2'          # API 不可用时的兜底版本
UV_URL = ('https://github.com/astral-sh/uv/releases/latest/download/'
          'uv-x86_64-pc-windows-msvc.zip')
PIP_MIRROR = 'https://pypi.tuna.tsinghua.edu.cn/simple'   # 国内加速，失败可置空
GAME_EXE_NAME = 'ZenlessZoneZero.exe'
GAME_COMMON_DIRS = [
    r'\miHoYo Launcher\games\ZenlessZoneZero Game',
    r'\ZenlessZoneZero Game',
    r'\Game\ZenlessZoneZero Game',
    r'\Games\ZenlessZoneZero Game',
]
GAME_SEARCH_ROOTS = ['C:\\', 'D:\\', 'E:\\', 'F:\\']

OFFLINE_DIR_NAME = '引擎离线包'
STEP_OK = '✔'


def log(msg, **kw):
    print(msg, flush=True, **kw)


def find_game():
    """定位绝区零客户端 exe：常见盘符路径 → 注册表 → 返回 None"""
    for root in GAME_SEARCH_ROOTS:
        if not os.path.isdir(root):
            continue
        for part in GAME_COMMON_DIRS:
            exe = os.path.join(root.rstrip('\\') + part, GAME_EXE_NAME)
            if os.path.isfile(exe):
                return exe
    try:
        import winreg
        for hive, path in [
                (winreg.HKEY_LOCAL_MACHINE,
                 r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'),
                (winreg.HKEY_LOCAL_MACHINE,
                 r'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'),
                (winreg.HKEY_CURRENT_USER,
                 r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall')]:
            try:
                key = winreg.OpenKey(hive, path)
            except OSError:
                continue
            with key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        sub = winreg.OpenKey(key, winreg.EnumKey(i))
                        with sub:
                            name = winreg.QueryValueEx(sub, 'DisplayName')[0]
                            if '绝区零' not in name and 'Zenless' not in name:
                                continue
                            loc = winreg.QueryValueEx(sub, 'InstallLocation')[0]
                            exe = os.path.join(loc, GAME_EXE_NAME)
                            if os.path.isfile(exe):
                                return exe
                            exe = os.path.join(loc, 'games', 'ZenlessZoneZero Game',
                                               GAME_EXE_NAME)
                            if os.path.isfile(exe):
                                return exe
                    except OSError:
                        continue
    except Exception:
        pass
    return None


def choose_install_dir():
    """选引擎安装目录：默认 D 盘（空间足够时），否则用户目录"""
    default = None
    for drive in ('D:', 'E:', 'C:'):
        if os.path.isdir(drive + '\\'):
            try:
                free = shutil.disk_usage(drive + '\\').free
            except Exception:
                continue
            if free > 8 * 1024 ** 3:
                default = os.path.join(drive + '\\', 'ZenlessZoneZero-OneDragon')
                break
    if default is None:
        default = os.path.join(os.path.expanduser('~'), 'ZenlessZoneZero-OneDragon')
    log('引擎安装目录 [回车=%s]：' % default, end='')
    picked = input().strip().strip('"')
    return picked or default


def http_download(url, dest, label):
    """流式下载（已有文件直接跳过），返回 True/False"""
    if os.path.isfile(dest) and os.path.getsize(dest) > 1024 * 1024:
        log('%s 已存在，跳过下载：%s' % (label, dest))
        return True
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        log('下载 %s …' % label)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as resp, \
                open(dest, 'wb') as f:
            total = int(resp.headers.get('Content-Length') or 0)
            done = 0
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total:
                    sys.stdout.write('\r  %s %.1f/%.1f MB'
                                     % (label, done / 1048576, total / 1048576))
                else:
                    sys.stdout.write('\r  %s %.1f MB' % (label, done / 1048576))
                sys.stdout.flush()
        print()
        return True
    except Exception as e:
        print()
        log('  下载失败：%s' % e)
        return False


def api_latest_tag():
    """取引擎最新 release tag，失败返回 None"""
    try:
        req = urllib.request.Request(
            'https://api.github.com/repos/OneDragon-Anything/'
            'ZenlessZoneZero-OneDragon/releases/latest',
            headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode('utf-8')).get('tag_name')
    except Exception:
        return None


def extract_members(zip_path, base_dir, prefix_strip=0, skip_names=(),
                    include_prefixes=None):
    """解压 zip 到 base_dir（绝对路径基准）：prefix_strip 去掉顶层目录层数；
    include_prefixes 只保留这些前缀"""
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = info.filename
            parts = name.split('/')
            if prefix_strip:
                parts = parts[prefix_strip:]
            rel = '/'.join(parts)
            if not rel or rel.endswith('/'):
                continue
            if any(skip in name for skip in skip_names):
                continue
            if include_prefixes and not any(
                    rel.startswith(p) or rel == p.rstrip('/') for p in include_prefixes):
                continue
            target = os.path.join(base_dir, *parts)
            if info.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(info) as src, open(target, 'wb') as dst:
                shutil.copyfileobj(src, dst)


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    offline_dir = os.path.join(script_dir, OFFLINE_DIR_NAME)
    offline = os.path.isdir(offline_dir)

    log('=' * 56)
    log('  绝区零引擎一键安装（小蕾米桌宠 · 每日任务）')
    log('=' * 56)
    log('安装模式：%s' % ('离线包（无需访问 GitHub）' if offline
                          else '在线下载（需要能访问 GitHub）'))

    if sys.version_info < (3, 8):
        log('需要 Python 3.8 以上')
        return 1

    # 1) 引擎目录
    engine_dir = choose_install_dir()
    os.makedirs(engine_dir, exist_ok=True)
    cache_dir = os.path.join(engine_dir, '_cache')
    os.makedirs(cache_dir, exist_ok=True)
    done_flag = os.path.join(engine_dir, '.venv', 'Scripts', 'python.exe')
    src_flag = os.path.join(engine_dir, 'src', 'zzz_od')
    env_ok = False
    if os.path.isfile(done_flag):
        # 真实验证环境可用（防止中断后残留空环境被误判为已安装）
        env_ok = run_checked([done_flag, '-c', 'import uvicorn'],
                             capture_output=True)
    if os.path.isdir(src_flag) and env_ok:
        log('%s 引擎已安装过（%s），无需重装；桌宠直接使用即可' % (STEP_OK, engine_dir))
        return 0

    # 2) 定位游戏
    game_exe = find_game()
    if game_exe:
        log('%s 找到绝区零客户端：%s' % (STEP_OK, game_exe))
    else:
        log('未自动找到绝区零客户端，可稍后在引擎配置里手动填写路径')
        log('现在手动输入 ZenlessZoneZero.exe 完整路径 [回车=跳过]：', end='')
        game_exe = input().strip().strip('"') or None
        if game_exe and not os.path.isfile(game_exe):
            log('  路径不存在，跳过')
            game_exe = None

    # 3) 版本号
    tag = api_latest_tag() or ENGINE_TAG_FALLBACK
    log('%s 引擎版本：%s' % (STEP_OK, tag))

    # 4) uv：离线包自带（如有）→ pip 安装（国内镜像）→ GitHub 下载兜底
    uv_cmd = None
    uv_zip_local = os.path.join(offline_dir, 'uv.zip') if offline else None
    if uv_zip_local and os.path.isfile(uv_zip_local):
        with zipfile.ZipFile(uv_zip_local) as zf:
            zf.extractall(os.path.join(engine_dir, '.tools'))
        for root, _dirs, files in os.walk(os.path.join(engine_dir, '.tools')):
            if 'uv.exe' in files:
                uv_cmd = [os.path.join(root, 'uv.exe')]
                break
        log('%s uv 就绪（离线包）' % STEP_OK)
    if uv_cmd is None:
        # uv 发布在 PyPI 上，走和依赖同一个国内镜像，无需 GitHub
        log('通过 pip 获取 uv（国内镜像）…')
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'uv',
                        '-i', PIP_MIRROR, '--quiet'])
        r = subprocess.run([sys.executable, '-m', 'uv', '--version'],
                           capture_output=True, text=True)
        if r.returncode == 0:
            uv_cmd = [sys.executable, '-m', 'uv']
            log('%s uv 就绪（pip 版）：%s' % (STEP_OK, r.stdout.strip()))
    if uv_cmd is None:
        uv_zip = os.path.join(cache_dir, 'uv.zip')
        if not http_download(UV_URL, uv_zip, 'uv 工具'):
            log('手动下载 %s 放到 %s 后重跑' % (UV_URL, uv_zip))
            return 1
        with zipfile.ZipFile(uv_zip) as zf:
            zf.extractall(os.path.join(engine_dir, '.tools'))
        for root, _dirs, files in os.walk(os.path.join(engine_dir, '.tools')):
            if 'uv.exe' in files:
                uv_cmd = [os.path.join(root, 'uv.exe')]
                break
        log('%s uv 就绪（GitHub 兜底）' % STEP_OK)
    if uv_cmd is None:
        log('uv 获取失败，请检查网络后重试')
        return 1

    # 5) 引擎主包（src + 识别模型；离线包优先）
    release_zip = os.path.join(cache_dir, 'WithRuntime-Full.zip')
    if not os.path.isdir(src_flag):
        if offline and os.path.isfile(os.path.join(offline_dir,
                                                   'WithRuntime-Full.zip')):
            release_zip = os.path.join(offline_dir, 'WithRuntime-Full.zip')
            log('%s 使用离线包中的引擎主包' % STEP_OK)
        else:
            url = ('https://github.com/OneDragon-Anything/'
                   'ZenlessZoneZero-OneDragon/releases/download/%s/'
                   'ZenlessZoneZero-OneDragon-%s-WithRuntime-Full.zip' % (tag, tag))
            if not http_download(url, release_zip, '引擎主包'):
                log('手动下载 %s 保存为 %s 后重跑' % (url, release_zip))
                return 1
        log('解压引擎主包（几分钟）…')
        extract_members(release_zip, engine_dir,
                        skip_names=('OneDragon-RuntimeLauncher',))
    log('%s 引擎源码与模型就绪' % STEP_OK)

    # 6) pyproject / uv.lock / config 模板 / plugins（离线包优先）
    pyproject = os.path.join(engine_dir, 'pyproject.toml')
    uvlock = os.path.join(engine_dir, 'uv.lock')
    if not (os.path.isfile(pyproject) and os.path.isfile(uvlock)):
        extras = os.path.join(offline_dir, 'extras') if offline else None
        if extras and os.path.isfile(os.path.join(extras, 'pyproject.toml')):
            log('%s 使用离线包中的配置模板' % STEP_OK)
            shutil.copy2(os.path.join(extras, 'pyproject.toml'), pyproject)
            shutil.copy2(os.path.join(extras, 'uv.lock'), uvlock)
            shutil.copytree(os.path.join(extras, 'config'),
                            os.path.join(engine_dir, 'config'), dirs_exist_ok=True)
            shutil.copytree(os.path.join(extras, 'plugins'),
                            os.path.join(engine_dir, 'plugins'), dirs_exist_ok=True)
            # git 仓库里的识别资源（screen_info/模板等），Release 包不带、必须补
            if os.path.isdir(os.path.join(extras, 'assets')):
                shutil.copytree(os.path.join(extras, 'assets'),
                                os.path.join(engine_dir, 'assets'),
                                dirs_exist_ok=True)
        else:
            src_zip = os.path.join(cache_dir, 'source-%s.zip' % tag)
            url = ('https://github.com/OneDragon-Anything/'
                   'ZenlessZoneZero-OneDragon/archive/refs/tags/%s.zip' % tag)
            if not http_download(url, src_zip, '配置模板包'):
                log('手动下载 %s 保存为 %s 后重跑' % (url, src_zip))
                return 1
            log('抽取配置模板（pyproject/uv.lock/config/plugins）…')
            extract_members(src_zip, engine_dir, prefix_strip=1,
                            include_prefixes=('pyproject.toml', 'uv.lock',
                                              'config/', 'plugins/', 'assets/'))
    log('%s 配置模板就绪' % STEP_OK)

    # 7) 依赖安装（uv sync；离线包自带 Python 时不再下载解释器）
    py_exe = os.path.join(offline_dir, 'python', 'python.exe') if offline else None
    if py_exe and not os.path.isfile(py_exe):
        py_exe = None
    env = os.environ.copy()
    env['UV_DEFAULT_INDEX'] = PIP_MIRROR
    cmd = list(uv_cmd) + ['sync', '--group', 'dev']
    if py_exe:
        cmd += ['--python', py_exe]
        log('使用离线包自带的 Python 3.11：%s' % py_exe)
    log('安装引擎依赖（首次约 2GB，需 10~20 分钟）…')
    r = subprocess.run(cmd, cwd=engine_dir, env=env)
    if r.returncode != 0:
        log('依赖安装失败：可改用官方源重试（把脚本里 PIP_MIRROR 置空）')
        return 1
    log('%s 引擎依赖安装完成' % STEP_OK)

    # 8) 预置配置（存在则不覆盖）
    cfg_dir = os.path.join(engine_dir, 'config', '01', 'one_dragon')
    os.makedirs(cfg_dir, exist_ok=True)

    def write_once(rel, text):
        path = os.path.join(cfg_dir, rel)
        if os.path.exists(path):
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)

    if game_exe:
        ga = os.path.join(engine_dir, 'config', '01', 'game_account.yml')
        if not os.path.exists(ga):
            with open(ga, 'w', encoding='utf-8') as f:
                f.write('# 桌宠安装脚本预置\n'
                        'platform: PC\ngame_region: cn\ngame_language: cn\n'
                        'game_path: %s\n' % game_exe)
        log('%s 游戏路径已配置' % STEP_OK)

    write_once('_group.yml', (
        '# 一条龙任务清单（顺序即执行顺序）：喝茶->吼吼饼铺->录像店->领活跃\n'
        'app_list:\n'
        '  - {app_id: coffee, enabled: true}\n'
        '  - {app_id: daily_signin, enabled: true}\n'
        '  - {app_id: random_play, enabled: true}\n'
        '  - {app_id: engagement_reward, enabled: true}\n'))
    write_once('daily_signin.yml', 'selected_sign: hou_hou_bakery\n')
    write_once('charge_plan.yml', (
        'plan_list:\n'
        '- tab_name: 训练\n'
        '  category_name: 实战模拟室\n'
        '  mission_type_name: 基础材料\n'
        '  mission_name: 调查专项\n'
        '  level: 默认等级\n'
        '  auto_battle_config: 全配队通用\n'
        '  run_times: 0\n'
        '  plan_times: 1\n'
        '  card_num: 默认数量\n'
        '  predefined_team_idx: -1\n'
        '  notorious_hunt_buff_num: 1\n'))
    log('%s 任务清单/签到方式/体力计划已预置' % STEP_OK)

    log('')
    log('=' * 56)
    log('安装完成！接下来：')
    log('  1. 游戏内设置：1920x1080 窗口化（16:9）、简体中文、关闭 HDR')
    log('  2. 保持游戏客户端为登录状态')
    log('  3. 打开小蕾米 → 右键 → 🎮 绝区零每日任务 → 一键日常')
    log('引擎目录：%s' % engine_dir)
    log('=' * 56)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        sys.exit(130)

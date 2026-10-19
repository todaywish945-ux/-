"""配置读写：兼容桌宠直接读写的 YAML 字段名，全部按需从磁盘加载（改设置即时生效）。"""

import time
from pathlib import Path

import yaml

from remi_od.core.log import log


def load_yaml(path: Path, default: dict | list | None = None):
    if not path.exists():
        return default
    try:
        return yaml.safe_load(path.read_text(encoding='utf-8'))
    except Exception as e:
        log('配置', f'读取失败 {path.name}: {e}')
        return default


def save_yaml(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding='utf-8'
    )


class EnginePaths:

    """目录约定：config/<实例NN>/<分组>/ 与原引擎一致，桌宠按此路径读写。"""

    def __init__(self, engine_root: Path, instance_idx: int = 1):
        self.root: Path = engine_root
        self.instance_idx: int = instance_idx
        self.instance_dir: Path = engine_root / 'config' / f'{instance_idx:02d}'

    @property
    def assets_dir(self) -> Path:
        return self.root / 'assets'

    @property
    def screen_info_dir(self) -> Path:
        return self.assets_dir / 'screen_info'

    @property
    def template_dir(self) -> Path:
        return self.assets_dir / 'template'

    @property
    def group_yml(self) -> Path:
        return self.instance_dir / 'one_dragon' / '_group.yml'

    @property
    def daily_signin_yml(self) -> Path:
        return self.instance_dir / 'one_dragon' / 'daily_signin.yml'

    @property
    def game_account_yml(self) -> Path:
        return self.instance_dir / 'game_account.yml'

    @property
    def run_record_dir(self) -> Path:
        return self.instance_dir / 'app_run_record'

    @property
    def debug_dir(self) -> Path:
        return self.root / 'debug'


# 一条龙默认顺序：活跃奖励放最后（前面任务攒活跃度，最后领才能领满）
DEFAULT_GROUP_APPS: list[dict] = [
    {'app_id': 'daily_signin', 'enabled': True},
    {'app_id': 'coffee', 'enabled': True},
    {'app_id': 'random_play', 'enabled': True},
    {'app_id': 'engagement_reward', 'enabled': True},
]

DEFAULT_CHARGE_PLAN: dict = {
    'plan_list': [{
        'tab_name': '训练', 'category_name': '实战模拟室', 'mission_type_name': '基础材料',
        'mission_name': '调查专项', 'level': '默认等级', 'auto_battle_config': '全配队通用',
        'run_times': 0, 'plan_times': 1, 'card_num': '默认数量',
        'predefined_team_idx': -1, 'notorious_hunt_buff_num': 1,
    }]
}


def group_apps(paths: EnginePaths) -> list[tuple[str, bool]]:
    """一条龙应用组：[(app_id, enabled)]，保持文件顺序。"""
    data = load_yaml(paths.group_yml, {'app_list': DEFAULT_GROUP_APPS}) or {}
    app_list = data.get('app_list') or []
    result: list[tuple[str, bool]] = []
    for item in app_list:
        if isinstance(item, dict) and item.get('app_id'):
            result.append((str(item['app_id']), bool(item.get('enabled', False))))
    return result


def save_group_apps(paths: EnginePaths, apps: list[tuple[str, bool]]) -> None:
    save_yaml(paths.group_yml, {
        'app_list': [{'app_id': app_id, 'enabled': enabled} for app_id, enabled in apps]
    })


def selected_sign(paths: EnginePaths) -> str:
    """签到方式：hou_hou_bakery / trigrams_collection / scratch_card。"""
    data = load_yaml(paths.daily_signin_yml, {}) or {}
    value = data.get('selected_sign', 'hou_hou_bakery')
    return str(value) if value else 'hou_hou_bakery'


def save_selected_sign(paths: EnginePaths, sign: str) -> None:
    # 桌宠的保存逻辑就是整文件覆写为这一个键，这里保持一致
    save_yaml(paths.daily_signin_yml, {'selected_sign': sign})



def game_account(paths: EnginePaths) -> dict:
    return load_yaml(paths.game_account_yml, {}) or {}


def game_path(paths: EnginePaths) -> str:
    return str(game_account(paths).get('game_path', '') or '')


def save_game_account(paths: EnginePaths, data: dict) -> None:
    save_yaml(paths.game_account_yml, data)


def write_default_configs_if_missing(paths: EnginePaths) -> None:
    """首次运行时落默认配置（已存在的不覆盖）。"""
    if not paths.group_yml.exists():
        save_group_apps(paths, [(a['app_id'], a['enabled']) for a in DEFAULT_GROUP_APPS])
    if not paths.daily_signin_yml.exists():
        save_selected_sign(paths, 'hou_hou_bakery')
    if not paths.game_account_yml.exists():
        save_game_account(paths, {
            'platform': 'PC', 'game_region': 'cn', 'game_language': 'cn',
            'game_path': '', 'refresh_hour_offset': 4,
        })

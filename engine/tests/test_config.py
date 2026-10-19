"""配置读写单测：与桌宠写盘格式互认。"""

from pathlib import Path

import yaml

from remi_od.core import config as config_mod


def test_group_roundtrip_pet_style(tmp_path: Path):
    """桌宠 save_chain_enablement 的写法：读原文件 → 保序改 enabled → 覆写。"""
    paths = config_mod.EnginePaths(tmp_path)
    config_mod.save_group_apps(paths, [('daily_signin', True), ('coffee', False)])

    # —— 模拟桌宠：直接读 YAML、改 enabled、整表写回 ——
    data = yaml.safe_load(paths.group_yml.read_text(encoding='utf-8'))
    app_list = data['app_list']
    for item in app_list:
        if item['app_id'] == 'coffee':
            item['enabled'] = True
    # 桌宠还会把新 app_id 追加到尾部
    app_list.append({'app_id': 'random_play', 'enabled': True})
    paths.group_yml.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding='utf-8')

    # —— 引擎按需读取 ——
    apps = config_mod.group_apps(paths)
    assert apps == [('daily_signin', True), ('coffee', True),
                    ('random_play', True)]


def test_daily_signin_pet_overwrite(tmp_path: Path):
    """桌宠 save_sign_choice 整文件覆写为一个键，引擎要能容忍并读出。"""
    paths = config_mod.EnginePaths(tmp_path)
    paths.daily_signin_yml.parent.mkdir(parents=True, exist_ok=True)
    paths.daily_signin_yml.write_text(
        yaml.safe_dump({'selected_sign': 'scratch_card'}, allow_unicode=True),
        encoding='utf-8')
    assert config_mod.selected_sign(paths) == 'scratch_card'



def test_write_defaults_not_overwrite(tmp_path: Path):
    paths = config_mod.EnginePaths(tmp_path)
    config_mod.write_default_configs_if_missing(paths)
    first = paths.group_yml.read_text(encoding='utf-8')
    # 手工改配置后再跑默认落盘，不应覆盖
    config_mod.save_group_apps(paths, [('coffee', False)])
    config_mod.write_default_configs_if_missing(paths)
    assert 'enabled: false' in paths.group_yml.read_text(encoding='utf-8')
    assert first  # 首次确实写了

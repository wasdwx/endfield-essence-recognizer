import json

import pytest
from pydantic import ValidationError

from endfield_essence_recognizer.exceptions import ConfigVersionMismatchError
from endfield_essence_recognizer.schemas.user_setting import UserSetting
from endfield_essence_recognizer.services.user_setting_manager import (
    UserSettingManager,
)


@pytest.fixture
def settings_file(tmp_path):
    return tmp_path / 'settings.json'


@pytest.fixture
def manager(settings_file):
    return UserSettingManager(settings_file)


def test_manager_initial_state(manager, settings_file):
    assert manager._user_setting_file == settings_file
    assert isinstance(manager.get_user_setting(), UserSetting)


def test_get_user_setting_returns_copy(manager):
    s1 = manager.get_user_setting()
    s2 = manager.get_user_setting()
    assert s1 == s2
    assert s1 is not s2


def test_load_user_setting_file_not_exists(manager, settings_file):
    assert not settings_file.exists()
    manager.load_user_setting()
    assert settings_file.exists()
    assert manager.get_user_setting().trash_weapon_ids == []


def test_load_user_setting_valid_file(manager, settings_file):
    data = {
        'version': UserSetting._VERSION,
        'trash_weapon_ids': ['weapon_1'],
        'treasure_essence_stats': [
            {'attribute': 'atk', 'secondary': 'crit', 'skill': None}
        ],
    }
    settings_file.write_text(json.dumps(data), encoding='utf-8')

    manager.load_user_setting()
    setting = manager.get_user_setting()
    assert setting.trash_weapon_ids == ['weapon_1']
    assert len(setting.treasure_essence_stats) == 1
    assert setting.treasure_essence_stats[0].attribute == 'atk'


def test_load_user_setting_invalid_version_backups_file(manager, settings_file):
    settings_file.write_text(
        json.dumps({'version': -1, 'trash_weapon_ids': ['old_weapon']}),
        encoding='utf-8',
    )

    manager.load_user_setting()

    backup_files = list(settings_file.parent.glob('settings.backup.*.json'))
    assert len(backup_files) == 1
    assert json.loads(backup_files[0].read_text(encoding='utf-8'))['trash_weapon_ids'] == [
        'old_weapon'
    ]
    assert manager.get_user_setting().trash_weapon_ids == []
    assert json.loads(settings_file.read_text(encoding='utf-8'))['version'] == UserSetting._VERSION


def test_load_user_setting_corrupt_json_backups_file(manager, settings_file):
    settings_file.write_text('not a json', encoding='utf-8')

    manager.load_user_setting()

    backup_files = list(settings_file.parent.glob('settings.backup.*.json'))
    assert len(backup_files) == 1
    assert backup_files[0].read_text(encoding='utf-8') == 'not a json'
    assert manager.get_user_setting().version == UserSetting._VERSION


def test_update_from_dict_version_mismatch(manager):
    with pytest.raises(ConfigVersionMismatchError) as excinfo:
        manager.update_from_dict({'version': -1, 'trash_weapon_ids': ['test']})
    assert excinfo.value.expected == UserSetting._VERSION
    assert excinfo.value.got == -1


def test_update_from_user_setting_version_mismatch(manager):
    other = UserSetting()
    other.version = -1
    with pytest.raises(ConfigVersionMismatchError) as excinfo:
        manager.update_from_user_setting(other)
    assert excinfo.value.expected == UserSetting._VERSION
    assert excinfo.value.got == -1


def test_save_user_setting(manager, settings_file):
    manager._user_setting.trash_weapon_ids = ['test_save']
    manager.save_user_setting()

    assert settings_file.exists()
    data = json.loads(settings_file.read_text(encoding='utf-8'))
    assert data['trash_weapon_ids'] == ['test_save']


def test_update_from_dict(manager, settings_file):
    manager.update_from_dict({'trash_weapon_ids': ['dict_update']})
    assert manager.get_user_setting().trash_weapon_ids == ['dict_update']
    assert json.loads(settings_file.read_text(encoding='utf-8'))['trash_weapon_ids'] == ['dict_update']


def test_update_from_user_setting(manager, settings_file):
    new_setting = UserSetting(trash_weapon_ids=['model_update'])
    manager.update_from_user_setting(new_setting)
    assert manager.get_user_setting().trash_weapon_ids == ['model_update']
    assert json.loads(settings_file.read_text(encoding='utf-8'))['trash_weapon_ids'] == ['model_update']


def test_update_from_dict_invalid_data(manager):
    with pytest.raises(ValidationError):
        manager.update_from_dict({'trash_weapon_ids': 'not a list'})


def test_config_migration_from_v4_to_v5():
    old_config = {
        'version': 4,
        'trash_weapon_ids': ['weapon_1'],
        'treasure_essence_stats': [],
        'treasure_action': 'lock',
        'trash_action': 'unlock',
        'non_five_star_behavior': 'process',
        'high_level_treasure_enabled': False,
        'high_level_treasure_attribute_threshold': 3,
        'high_level_treasure_secondary_threshold': 3,
        'high_level_treasure_skill_threshold': 3,
        'auto_page_flip': True,
        'update_mirror': 'github',
        'update_proxy': '',
    }

    migrated = UserSetting.migrate_from_old_version(old_config)

    assert migrated.trash_weapon_ids == ['weapon_1']
    assert migrated.auto_page_flip is True
    assert migrated.page_flip_mode == 'wheel'
    assert migrated.enable_sound is True
    assert migrated.version == UserSetting._VERSION


def test_config_migration_chain_v2_to_v5():
    early_v2_config = {
        'version': 2,
        'trash_weapon_ids': ['weapon_v2'],
        'treasure_essence_stats': [],
        'treasure_action': 'lock',
        'trash_action': 'unlock',
        'high_level_treasure_enabled': False,
        'high_level_treasure_attribute_threshold': 3,
        'high_level_treasure_secondary_threshold': 3,
        'high_level_treasure_skill_threshold': 3,
    }

    migrated = UserSetting.migrate_from_old_version(early_v2_config)

    assert migrated.version == UserSetting._VERSION
    assert migrated.trash_weapon_ids == ['weapon_v2']
    assert migrated.non_five_star_behavior == 'process'
    assert migrated.auto_page_flip is True
    assert migrated.update_mirror == 'github'
    assert migrated.update_proxy == ''
    assert migrated.page_flip_mode == 'wheel'
    assert migrated.enable_sound is True


def test_config_migration_invalid_version():
    with pytest.raises(ValueError, match='配置版本非法'):
        UserSetting.migrate_from_old_version({'version': -1})

    with pytest.raises(ValueError, match='高于当前程序支持的版本'):
        UserSetting.migrate_from_old_version({'version': 999})


def test_load_user_setting_with_migration(manager, settings_file):
    old_config = {
        'version': 4,
        'trash_weapon_ids': ['old_weapon'],
        'treasure_essence_stats': [],
        'treasure_action': 'lock',
        'trash_action': 'unlock',
        'non_five_star_behavior': 'process',
        'high_level_treasure_enabled': False,
        'high_level_treasure_attribute_threshold': 3,
        'high_level_treasure_secondary_threshold': 3,
        'high_level_treasure_skill_threshold': 3,
        'auto_page_flip': True,
        'update_mirror': 'github',
        'update_proxy': '',
    }
    settings_file.write_text(json.dumps(old_config), encoding='utf-8')

    manager.load_user_setting()

    setting = manager.get_user_setting()
    assert setting.version == UserSetting._VERSION
    assert setting.trash_weapon_ids == ['old_weapon']
    assert setting.page_flip_mode == 'wheel'
    assert setting.enable_sound is True

    saved_data = json.loads(settings_file.read_text(encoding='utf-8'))
    assert saved_data['version'] == UserSetting._VERSION
    assert saved_data['page_flip_mode'] == 'wheel'
    assert saved_data['enable_sound'] is True


def test_user_setting_schema_stability():
    expected_fields = {
        'version',
        'trash_weapon_ids',
        'treasure_essence_stats',
        'treasure_action',
        'trash_action',
        'non_five_star_behavior',
        'high_level_treasure_enabled',
        'high_level_treasure_attribute_threshold',
        'high_level_treasure_secondary_threshold',
        'high_level_treasure_skill_threshold',
        'auto_page_flip',
        'page_flip_mode',
        'enable_sound',
        'update_mirror',
        'update_proxy',
    }

    actual_fields = set(UserSetting.model_fields.keys())
    assert actual_fields == expected_fields


def test_migrations_completeness():
    current_version = UserSetting._VERSION
    migrations = UserSetting._MIGRATIONS

    for v in range(2, current_version):
        assert v in migrations, f'缺少迁移链：v{v} -> v{v + 1}'


def test_frontend_config_version_matches_backend():
    import re
    from pathlib import Path

    settings_vue = (
        Path(__file__).resolve().parent.parent
        / 'frontend'
        / 'src'
        / 'pages'
        / 'settings.vue'
    )
    assert settings_vue.exists(), f'未找到前端配置页：{settings_vue}'

    content = settings_vue.read_text(encoding='utf-8')
    match = re.search(r'return\s*\{[^}]*version:\s*(\d+)', content)
    assert match, '无法在 settings.vue 的 config computed 中找到 version 字段'

    frontend_version = int(match.group(1))
    backend_version = UserSetting._VERSION
    assert frontend_version == backend_version

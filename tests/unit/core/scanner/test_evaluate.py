from unittest.mock import MagicMock

import pytest

from endfield_essence_recognizer.core.recognition import (
    AbandonStatusLabel,
    LockStatusLabel,
    RarityLabel,
)
from endfield_essence_recognizer.core.scanner.evaluate import evaluate_essence
from endfield_essence_recognizer.core.scanner.models import (
    CustomTreasureMatch,
    EssenceData,
    EssenceQuality,
)
from endfield_essence_recognizer.schemas.user_setting import (
    EssenceStats,
    NonFiveStarBehavior,
    UserSetting,
)


@pytest.fixture
def mock_static_game_data():
    mock_data = MagicMock()
    mock_data.get_stat.return_value = None
    mock_data.find_weapons_by_stats.return_value = []
    mock_data.get_weapon.return_value = None
    mock_data.get_weapon_type.return_value = None
    mock_data.get_rarity_color.return_value = '#FFD700'
    return mock_data


@pytest.fixture
def default_settings():
    settings = UserSetting()
    settings.non_five_star_behavior = NonFiveStarBehavior.PROCESS
    return settings


@pytest.fixture
def default_essence_data():
    return EssenceData(
        stats=['A', 'B', 'C'],
        levels=[0, 0, 0],
        rarity=RarityLabel.OTHER,
        abandon_label=AbandonStatusLabel.NOT_ABANDONED,
        lock_label=LockStatusLabel.NOT_LOCKED,
    )


def test_evaluate_trash(mock_static_game_data, default_settings, default_essence_data):
    result = evaluate_essence(
        default_essence_data, default_settings, mock_static_game_data
    )
    assert result.quality == EssenceQuality.TRASH


def test_evaluate_treasure_custom(
    mock_static_game_data, default_settings, default_essence_data
):
    default_settings.treasure_essence_stats = [
        EssenceStats(attribute='A', secondary='B', skill='C')
    ]

    result = evaluate_essence(
        default_essence_data, default_settings, mock_static_game_data
    )

    assert result.quality == EssenceQuality.TREASURE
    assert result.matched_custom_treasures == (
        CustomTreasureMatch(
            key='A|B|C',
            attribute='A',
            secondary='B',
            skill='C',
        ),
    )


def test_evaluate_treasure_custom_keeps_weapon_matches(
    mock_static_game_data, default_settings, default_essence_data
):
    default_settings.treasure_essence_stats = [
        EssenceStats(attribute='A', secondary='B', skill='C')
    ]
    mock_static_game_data.find_weapons_by_stats.return_value = ['wpn_test']

    result = evaluate_essence(
        default_essence_data, default_settings, mock_static_game_data
    )

    assert result.quality == EssenceQuality.TREASURE
    assert result.matched_weapons == {'wpn_test'}
    assert result.matched_non_trash_weapons == {'wpn_test'}


def test_evaluate_treasure_weapon_match(
    mock_static_game_data, default_settings, default_essence_data
):
    mock_static_game_data.find_weapons_by_stats.return_value = ['wpn_test']
    weapon_mock = MagicMock()
    weapon_mock.weapon_id = 'wpn_test'
    weapon_mock.name = 'TestWeapon'
    weapon_mock.rarity = 6
    weapon_mock.weapon_type = 1
    mock_static_game_data.get_weapon.return_value = weapon_mock
    weapon_type_mock = MagicMock()
    weapon_type_mock.name = 'TestType'
    mock_static_game_data.get_weapon_type.return_value = weapon_type_mock

    result = evaluate_essence(
        default_essence_data, default_settings, mock_static_game_data
    )

    assert result.quality == EssenceQuality.TREASURE
    assert 'TestWeapon' in result.log_message
    assert 'TestType' in result.log_message
    assert result.matched_weapons == {'wpn_test'}
    assert result.matched_non_trash_weapons == {'wpn_test'}


def test_evaluate_weapon_match_trash_filter(
    mock_static_game_data, default_settings, default_essence_data
):
    mock_static_game_data.find_weapons_by_stats.return_value = ['wpn_test']
    weapon_mock = MagicMock()
    weapon_mock.weapon_id = 'wpn_test'
    weapon_mock.name = 'TestWeapon'
    weapon_mock.rarity = 6
    weapon_mock.weapon_type = 'TestType'
    mock_static_game_data.get_weapon.return_value = weapon_mock
    weapon_type_mock = MagicMock()
    weapon_type_mock.name = 'TestType'
    mock_static_game_data.get_weapon_type.return_value = weapon_type_mock
    default_settings.trash_weapon_ids = ['wpn_test']

    result = evaluate_essence(
        default_essence_data, default_settings, mock_static_game_data
    )

    assert result.quality == EssenceQuality.TRASH
    assert result.matched_weapons == {'wpn_test'}
    assert not result.matched_non_trash_weapons


def test_evaluate_high_level(
    mock_static_game_data, default_settings, default_essence_data
):
    default_settings.high_level_treasure_enabled = True
    default_settings.high_level_treasure_attribute_threshold = 10

    stat = MagicMock()
    stat.stat_id = 'A'
    stat.name = 'AttrA'
    stat.type = 'ATTRIBUTE'
    mock_static_game_data.get_stat.return_value = stat
    default_essence_data.levels = [11, 0, 0]

    result = evaluate_essence(
        default_essence_data, default_settings, mock_static_game_data
    )

    assert result.is_high_level is True
    assert 'AttrA+11' in result.log_message


def test_evaluate_non_five_star_skip(
    mock_static_game_data, default_settings, default_essence_data
):
    default_essence_data.rarity = RarityLabel.FOUR
    default_settings.non_five_star_behavior = NonFiveStarBehavior.SKIP

    result = evaluate_essence(
        default_essence_data, default_settings, mock_static_game_data
    )

    assert result.quality == EssenceQuality.SKIP
    assert result.should_stop_scan is False
    assert '跳过当前项' in result.log_message


def test_evaluate_non_five_star_stop_scan(
    mock_static_game_data, default_settings, default_essence_data
):
    default_essence_data.rarity = RarityLabel.FOUR
    default_settings.non_five_star_behavior = NonFiveStarBehavior.STOP_SCAN

    result = evaluate_essence(
        default_essence_data, default_settings, mock_static_game_data
    )

    assert result.quality == EssenceQuality.SKIP
    assert result.should_stop_scan is True
    assert '结束本次扫描' in result.log_message


def test_evaluate_non_five_star_process(
    mock_static_game_data, default_settings, default_essence_data
):
    default_essence_data.rarity = RarityLabel.FOUR
    default_settings.non_five_star_behavior = NonFiveStarBehavior.PROCESS

    result = evaluate_essence(
        default_essence_data, default_settings, mock_static_game_data
    )

    assert result.quality == EssenceQuality.TRASH
    assert result.should_stop_scan is False

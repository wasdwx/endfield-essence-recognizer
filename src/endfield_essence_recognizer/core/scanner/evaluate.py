from __future__ import annotations

from endfield_essence_recognizer.core.recognition import RarityLabel
from endfield_essence_recognizer.core.scanner.models import (
    CustomTreasureMatch,
    EssenceData,
    EssenceQuality,
    EvaluationResult,
)
from endfield_essence_recognizer.game_data.static_game_data import StaticGameData
from endfield_essence_recognizer.schemas.user_setting import (
    NonFiveStarBehavior,
    UserSetting,
)


def _build_custom_match_key(
    attribute: str | None,
    secondary: str | None,
    skill: str | None,
) -> str:
    return "|".join([attribute or "", secondary or "", skill or ""])


def evaluate_essence(
    data: EssenceData,
    setting: UserSetting,
    static_game_data: StaticGameData,
) -> EvaluationResult:
    """根据用户设置和静态数据判断当前基质的处理结果。"""
    if data.rarity != RarityLabel.FIVE:
        if setting.non_five_star_behavior == NonFiveStarBehavior.STOP_SCAN:
            return EvaluationResult(
                quality=EssenceQuality.SKIP,
                log_message=(
                    "检测到<dim>非无瑕</>基质，按设置"
                    "<yellow><bold>结束本次扫描</></>。"
                ),
                should_stop_scan=True,
            )
        if setting.non_five_star_behavior == NonFiveStarBehavior.SKIP:
            return EvaluationResult(
                quality=EssenceQuality.SKIP,
                log_message="检测到<dim>非无瑕</>基质，按设置跳过当前项。",
                should_stop_scan=False,
            )

    stats = data.stats
    levels = data.levels

    is_high_level_treasure = False
    high_level_info = ""
    if setting.high_level_treasure_enabled:
        thresholds = [
            setting.high_level_treasure_attribute_threshold,
            setting.high_level_treasure_secondary_threshold,
            setting.high_level_treasure_skill_threshold,
        ]
        type_to_index = {
            "ATTRIBUTE": 0,
            "SECONDARY": 1,
            "SKILL": 2,
        }
        for stat_id, level in zip(stats, levels, strict=True):
            if stat_id is None or level is None:
                continue
            stat = static_game_data.get_stat(stat_id)
            if stat is None:
                continue
            idx = type_to_index.get(stat.type)
            if idx is None:
                continue
            threshold = thresholds[idx]
            if level >= threshold:
                is_high_level_treasure = True
                high_level_info = f"（高等级词条：{stat.name}+{level}）"
                break

    matched_custom_treasures: list[CustomTreasureMatch] = []
    seen_custom_keys: set[str] = set()
    for treasure_stat in setting.treasure_essence_stats:
        if (
            treasure_stat.attribute in stats
            and treasure_stat.secondary in stats
            and treasure_stat.skill in stats
        ):
            key = _build_custom_match_key(
                treasure_stat.attribute,
                treasure_stat.secondary,
                treasure_stat.skill,
            )
            if key not in seen_custom_keys:
                seen_custom_keys.add(key)
                matched_custom_treasures.append(
                    CustomTreasureMatch(
                        key=key,
                        attribute=treasure_stat.attribute,
                        secondary=treasure_stat.secondary,
                        skill=treasure_stat.skill,
                    )
                )

    matched_weapon_ids = set(
        static_game_data.find_weapons_by_stats(stats[0], stats[1], stats[2])
    )
    non_trash_weapon_ids = matched_weapon_ids - set(setting.trash_weapon_ids)

    if matched_custom_treasures:
        return EvaluationResult(
            quality=EssenceQuality.TREASURE,
            log_message=(
                "发现<green><bold><underline>宝藏</></></>！"
                f"命中自定义宝藏配置{high_level_info}"
            ),
            matched_weapons=matched_weapon_ids,
            matched_non_trash_weapons=non_trash_weapon_ids,
            matched_custom_treasures=tuple(matched_custom_treasures),
            is_high_level=is_high_level_treasure,
        )

    if not matched_weapon_ids:
        if is_high_level_treasure:
            return EvaluationResult(
                quality=EssenceQuality.TREASURE,
                log_message=(
                    "发现<green><bold><underline>宝藏</></></>！"
                    f"命中高等级宝藏条件{high_level_info}"
                    "<dim>，但未匹配到武器适配。</>"
                ),
                is_high_level=True,
            )
        return EvaluationResult(
            quality=EssenceQuality.TRASH,
            log_message=(
                "未命中任何武器适配，判定为"
                "<red><bold><underline>垃圾</></></>。"
            ),
            is_high_level=False,
        )

    def format_weapon_description(weapon_id: str) -> str:
        weapon = static_game_data.get_weapon(weapon_id)
        if not weapon:
            return f"<bold>{weapon_id}</>"

        weapon_type = static_game_data.get_weapon_type(weapon.weapon_type)
        type_name = weapon_type.name if weapon_type else "未知类型"
        rarity_color = static_game_data.get_rarity_color(weapon.rarity)
        return (
            f"<fg {rarity_color}><bold>"
            f"{weapon.name}（{weapon.rarity}★ {type_name}）"
            f"</></>"
        )

    if non_trash_weapon_ids:
        weapon_descriptions = [
            format_weapon_description(wid) for wid in sorted(non_trash_weapon_ids)
        ]
        weapons_description_str = "、".join(weapon_descriptions)

        return EvaluationResult(
            quality=EssenceQuality.TREASURE,
            log_message=(
                "发现<green><bold><underline>宝藏</></></>！"
                f"适配武器：{weapons_description_str}{high_level_info}"
            ),
            matched_weapons=matched_weapon_ids,
            matched_non_trash_weapons=non_trash_weapon_ids,
            is_high_level=is_high_level_treasure,
        )

    weapon_descriptions = [
        format_weapon_description(wid) for wid in sorted(matched_weapon_ids)
    ]
    weapons_description_str = "、".join(weapon_descriptions)

    if is_high_level_treasure:
        return EvaluationResult(
            quality=EssenceQuality.TREASURE,
            log_message=(
                "发现<green><bold><underline>宝藏</></></>！"
                f"命中高等级宝藏条件{high_level_info}"
                f"<yellow>，但适配武器都在垃圾预设中：{weapons_description_str}</>"
            ),
            matched_weapons=matched_weapon_ids,
            is_high_level=True,
        )

    return EvaluationResult(
        quality=EssenceQuality.TRASH,
        log_message=(
            f"适配武器 {weapons_description_str}，"
            "但它们都在垃圾预设中，判定为"
            "<red><bold><underline>垃圾</></></>。"
        ),
        matched_weapons=matched_weapon_ids,
        is_high_level=False,
    )

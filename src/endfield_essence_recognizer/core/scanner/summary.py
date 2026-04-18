from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from endfield_essence_recognizer.game_data.static_game_data import StaticGameData
    from endfield_essence_recognizer.schemas.scan_summary import (
        CustomTreasureSummaryState,
        LevelCombo,
        ScanSummaryState,
    )

SUMMARY_LOG_PREFIX = "<green><bold>【扫描汇总】</></>"


def get_complete_level_combo(levels: Sequence[int | None]) -> LevelCombo | None:
    if len(levels) < 3:
        return None
    first, second, third = levels[0], levels[1], levels[2]
    if first is None or second is None or third is None:
        return None
    return (first, second, third)


def get_ordered_custom_level_combo(
    stats: Sequence[str | None],
    levels: Sequence[int | None],
    attribute: str | None,
    secondary: str | None,
    skill: str | None,
) -> LevelCombo | None:
    stat_to_level = {
        stat: level
        for stat, level in zip(stats, levels, strict=True)
        if stat is not None and level is not None
    }
    ordered_levels = (
        stat_to_level.get(attribute),
        stat_to_level.get(secondary),
        stat_to_level.get(skill),
    )
    if any(level is None for level in ordered_levels):
        return None
    return ordered_levels  # type: ignore[return-value]


def update_best_level_combos(
    combos: list[LevelCombo],
    combo: LevelCombo | None,
) -> None:
    if combo is None:
        return

    combo_sum = sum(combo)
    if not combos:
        combos.append(combo)
        return

    best_sum = sum(combos[0])
    if combo_sum > best_sum:
        combos.clear()
        combos.append(combo)
        return

    if combo_sum == best_sum:
        combos.append(combo)


def format_level_combo(combo: LevelCombo) -> str:
    return f"+{combo[0]}/+{combo[1]}/+{combo[2]}"


def format_best_level_combos(combos: Sequence[LevelCombo]) -> str | None:
    if not combos:
        return None

    counted: OrderedDict[LevelCombo, int] = OrderedDict()
    for combo in combos:
        counted[combo] = counted.get(combo, 0) + 1

    parts: list[str] = []
    for combo, count in counted.items():
        text = format_level_combo(combo)
        if count > 1:
            text = f"{text}（{count}次）"
        parts.append(text)

    return "，".join(parts)


def format_best_level_suffix(combos: Sequence[LevelCombo]) -> str:
    best = format_best_level_combos(combos)
    if not best:
        return ""
    return f"，最优 <green><bold>{best}</></>"


def _resolve_stat_name(static_game_data: StaticGameData, stat_id: str | None) -> str:
    if stat_id is None:
        return "未设置"
    stat = static_game_data.get_stat(stat_id)
    return stat.name if stat is not None else stat_id


def format_summary_weapon(
    static_game_data: StaticGameData,
    weapon_id: str,
    count: int,
    best_level_combos: Sequence[LevelCombo] = (),
) -> str:
    weapon = static_game_data.get_weapon(weapon_id)
    best_suffix = format_best_level_suffix(best_level_combos)
    if not weapon:
        return (
            f"  - <green><bold>{weapon_id}</></>："
            f"<green><bold>{count}</></> 个{best_suffix}"
        )

    weapon_type = static_game_data.get_weapon_type(weapon.weapon_type)
    type_name = weapon_type.name if weapon_type else "未知类型"
    rarity_color = static_game_data.get_rarity_color(weapon.rarity)
    return (
        f"  - <fg {rarity_color}><bold>"
        f"{weapon.name}（{weapon.rarity}★ {type_name}）"
        f"</></>：<green><bold>{count}</></> 个{best_suffix}"
    )


def format_custom_summary(
    static_game_data: StaticGameData,
    custom_summary: CustomTreasureSummaryState,
) -> str:
    label = " / ".join(
        [
            _resolve_stat_name(static_game_data, custom_summary.attribute),
            _resolve_stat_name(static_game_data, custom_summary.secondary),
            _resolve_stat_name(static_game_data, custom_summary.skill),
        ]
    )
    best_suffix = format_best_level_suffix(custom_summary.best_level_combos)
    return (
        f"  - <green><bold>{label}</></>："
        f"<green><bold>{custom_summary.count}</></> 次命中{best_suffix}"
    )


def sort_weapon_counts(
    static_game_data: StaticGameData,
    weapon_counts: dict[str, int],
) -> list[tuple[str, int]]:
    def sort_key(item: tuple[str, int]) -> tuple[int, str]:
        weapon_id, _ = item
        weapon = static_game_data.get_weapon(weapon_id)
        rarity = -weapon.rarity if weapon else 0
        return (rarity, weapon_id)

    return sorted(weapon_counts.items(), key=sort_key)


def iter_scan_summary_log_messages(
    static_game_data: StaticGameData,
    summary: ScanSummaryState,
    *,
    include_scanned_at: bool = False,
) -> Iterable[str]:
    if include_scanned_at:
        dt = summary.scanned_at
        yield (
            f"{SUMMARY_LOG_PREFIX} 上次扫描时间："
            f"<green><bold>{dt.year}/{dt.month}/{dt.day} "
            f"{dt.hour:02}:{dt.minute:02}:{dt.second:02}</></>"
        )

    yield (
        f"{SUMMARY_LOG_PREFIX} 本次共扫描 "
        f"<green><bold>{summary.total_essence_count}</></> 个基质"
    )

    if summary.weapon_counts:
        yield f"{SUMMARY_LOG_PREFIX} 命中武器基质统计："
        for weapon_id, count in sort_weapon_counts(
            static_game_data, summary.weapon_counts
        ):
            yield format_summary_weapon(
                static_game_data,
                weapon_id,
                count,
                summary.weapon_best_level_combos.get(weapon_id, ()),
            )
    elif summary.total_essence_count > 0:
        yield f"{SUMMARY_LOG_PREFIX} <green><bold>本次扫描未命中任何武器适配。</></>"

    if summary.custom_treasures:
        yield f"{SUMMARY_LOG_PREFIX} 自定义宝藏命中统计："
        for custom_summary in summary.custom_treasures:
            yield format_custom_summary(static_game_data, custom_summary)

from __future__ import annotations

import math
from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np

from endfield_essence_recognizer.core.layout.base import (
    Point,
    Region,
    ResolutionProfile,
)
from endfield_essence_recognizer.core.recognition import (
    AbandonStatusLabel,
    LockStatusLabel,
    RarityLabel,
)
from endfield_essence_recognizer.core.recognition.tasks.ui import UISceneLabel
from endfield_essence_recognizer.core.scanner.action_logic import (
    ActionType,
    decide_actions,
)
from endfield_essence_recognizer.core.scanner.evaluate import evaluate_essence
from endfield_essence_recognizer.core.scanner.models import (
    CustomTreasureMatch,
    EssenceData,
    EssenceQuality,
    EvaluationResult,
)
from endfield_essence_recognizer.core.scanner.summary import (
    get_complete_level_combo,
    get_ordered_custom_level_combo,
    iter_scan_summary_log_messages,
    update_best_level_combos,
)
from endfield_essence_recognizer.core.window.adapter import InMemoryImageSource
from endfield_essence_recognizer.schemas.scan_summary import (
    CustomTreasureSummaryState,
    ScanSummaryState,
)
from endfield_essence_recognizer.schemas.user_setting import PageFlipMode, UserSetting
from endfield_essence_recognizer.utils.log import logger

if TYPE_CHECKING:
    import threading

    from endfield_essence_recognizer.core.interfaces import ImageSource, WindowActions
    from endfield_essence_recognizer.core.scanner.context import ScannerContext
    from endfield_essence_recognizer.services.user_setting_manager import (
        UserSettingManager,
    )

MATCH_LOG_PREFIX = "<green><bold><underline>【命中适配】</></></>"
TREASURE_LOG_PREFIX = "<green><bold><underline>【宝藏】</></></>"


def _format_evaluation_log_message(evaluation: EvaluationResult) -> str:
    if evaluation.quality != EssenceQuality.TREASURE:
        return evaluation.log_message

    prefix = (
        MATCH_LOG_PREFIX
        if evaluation.matched_non_trash_weapons
        else TREASURE_LOG_PREFIX
    )
    return f"{prefix} {evaluation.log_message}"


def _log_evaluation_result(evaluation: EvaluationResult) -> None:
    message = _format_evaluation_log_message(evaluation)

    if evaluation.quality == EssenceQuality.TREASURE:
        logger.opt(colors=True).success(message)
    elif evaluation.quality == EssenceQuality.TRASH:
        logger.opt(colors=True).warning(message)
    else:
        logger.opt(colors=True).info(message)


def check_scene(
    image_source: ImageSource,
    ctx: ScannerContext,
    profile: ResolutionProfile,
) -> bool:
    width, height = image_source.get_client_size()
    if (width, height) != profile.RESOLUTION:
        logger.debug(
            "Current window size: {}, profile expects: {}",
            (width, height),
            profile.RESOLUTION,
        )
        logger.warning(
            "当前终末地窗口分辨率为 {}x{}，与预期的 {}x{} 不一致；请避免在运行时调整窗口大小。",
            width,
            height,
            profile.RESOLUTION[0],
            profile.RESOLUTION[1],
        )
        return False

    screenshot = image_source.screenshot(profile.ESSENCE_UI_ROI)
    scene_label, _max_val = ctx.ui_scene_recognizer.recognize_roi_fallback(
        screenshot,
        fallback_label=UISceneLabel.UNKNOWN,
    )
    if scene_label != UISceneLabel.ESSENCE_UI:
        logger.warning(
            '当前界面不是基质界面。请按 "N" 键打开贵重品库后切换到武器基质页面。'
        )
        return False

    return True


def recognize_essence(
    image_source: ImageSource,
    ctx: ScannerContext,
    profile: ResolutionProfile,
) -> EssenceData:
    stats: list[str | None] = []
    levels: list[int | None] = []

    mem_source = InMemoryImageSource.cache_from(image_source)
    full_screenshot = mem_source.screenshot()

    rois = [profile.STATS_0_ROI, profile.STATS_1_ROI, profile.STATS_2_ROI]
    for index, roi in enumerate(rois):
        screenshot_image = mem_source.screenshot(roi)
        attr, score = ctx.attr_recognizer.recognize_roi(screenshot_image)
        stats.append(attr)
        logger.debug("属性{} 识别结果: {} (分数: {:.3f})", index, attr, score)

        level = ctx.attr_level_recognizer.recognize_level(
            full_screenshot, index, profile
        )
        levels.append(level)
        if level is not None:
            logger.debug("属性{} 等级识别结果: +{}", index, level)
        else:
            logger.debug("属性{} 等级识别结果: 无法识别", index)

    rarity_screenshot = mem_source.screenshot(profile.RARITY_ROI)
    rarity_label, score = ctx.rarity_recognizer.recognize_roi_fallback(
        rarity_screenshot,
        fallback_label=RarityLabel.OTHER,
    )
    logger.debug("稀有度识别结果: {} (分数: {:.3f})", rarity_label.value, score)

    abandon_screenshot = mem_source.screenshot(profile.DEPRECATE_BUTTON_ROI)
    abandon_label, abandon_score = ctx.abandon_status_recognizer.recognize_roi_fallback(
        abandon_screenshot,
        fallback_label=AbandonStatusLabel.MAYBE_ABANDONED,
    )
    logger.debug(
        "弃置按钮识别结果: {} (分数: {:.3f})",
        abandon_label.value,
        abandon_score,
    )

    lock_screenshot = mem_source.screenshot(profile.LOCK_BUTTON_ROI)
    lock_label, lock_score = ctx.lock_status_recognizer.recognize_roi_fallback(
        lock_screenshot,
        fallback_label=LockStatusLabel.MAYBE_LOCKED,
    )
    logger.debug("锁定按钮识别结果: {} (分数: {:.3f})", lock_label.value, lock_score)

    stat_name_parts: list[str] = []
    for stat, level in zip(stats, levels, strict=True):
        if stat is None:
            stat_name_parts.append("无")
            continue

        gem = ctx.static_game_data.get_stat(stat)
        stat_name = gem.name if gem is not None else stat
        if gem is None:
            logger.warning("无法在静态数据中找到基质 ID {} 对应的名称。", stat)

        stat_name_parts.append(
            f"{stat_name}+{level}" if level is not None else stat_name
        )

    stats_name = "、".join(stat_name_parts)
    rarity_text = {
        RarityLabel.FIVE: "<yellow>无瑕</>",
        RarityLabel.FOUR: "<magenta>高纯</>",
        RarityLabel.OTHER: "其他",
    }.get(rarity_label, "未知")

    logger.opt(colors=True).info(
        "已识别当前基质，属性: <magenta>{}</>, 稀有度: {}, <magenta>{}</>, <magenta>{}</>",
        stats_name,
        rarity_text,
        abandon_label.value,
        lock_label.value,
    )

    return EssenceData(stats, levels, rarity_label, abandon_label, lock_label)


def recognize_once(
    image_source: ImageSource,
    ctx: ScannerContext,
    user_setting: UserSetting,
    profile: ResolutionProfile,
) -> None:
    mem_source = InMemoryImageSource.cache_from(image_source)
    if not check_scene(mem_source, ctx, profile):
        return

    data = recognize_essence(mem_source, ctx, profile)
    if (
        data.abandon_label == AbandonStatusLabel.MAYBE_ABANDONED
        or data.lock_label == LockStatusLabel.MAYBE_LOCKED
    ):
        return

    evaluation = evaluate_essence(data, user_setting, ctx.static_game_data)
    _log_evaluation_result(evaluation)


class OneTimeRecognitionEngine:
    def __init__(
        self,
        ctx: ScannerContext,
        image_source: ImageSource,
        window_actions: WindowActions,
        user_setting_manager: UserSettingManager,
        profile: ResolutionProfile,
    ) -> None:
        self.ctx = ctx
        self._image_source = image_source
        self._window_actions = window_actions
        self._user_setting_manager = user_setting_manager
        self._profile = profile

    def execute(self, stop_event: threading.Event) -> None:
        if not self._window_actions.target_exists:
            logger.info("未找到终末地窗口，停止单次识别。")
            return

        if not self._window_actions.target_is_active:
            logger.debug("终末地窗口不在前台，尝试切换到前台进行单次识别。")
            if self._window_actions.activate():
                self._window_actions.wait(0.3)
            if self._window_actions.show():
                self._window_actions.wait(0.3)

        if stop_event.is_set():
            return

        recognize_once(
            self._image_source,
            self.ctx,
            self._user_setting_manager.get_user_setting(),
            self._profile,
        )


class ScannerEngine:
    def __init__(
        self,
        ctx: ScannerContext,
        image_source: ImageSource,
        window_actions: WindowActions,
        user_setting_manager: UserSettingManager,
        profile: ResolutionProfile,
    ) -> None:
        self.ctx = ctx
        self._image_source = image_source
        self._window_actions = window_actions
        self._user_setting_manager = user_setting_manager
        self._profile = profile
        self._weapon_essence_counts: dict[str, int] = {}
        self._weapon_best_level_combos: dict[str, list[tuple[int, int, int]]] = {}
        self._custom_treasure_summaries: dict[str, CustomTreasureSummaryState] = {}
        self._total_essence_count = 0
        self._scan_started = False
        self._scanned_at: datetime | None = None

        from endfield_essence_recognizer.utils.log import str_properties_and_attrs

        logger.opt(lazy=True).debug(
            "Scanner profile configuration: {}",
            lambda: str_properties_and_attrs(profile),
        )

    def execute(self, stop_event: threading.Event) -> None:
        logger.debug("ScannerEngine started execution.")
        user_setting = self._prepare_scan()
        if user_setting is None:
            logger.debug("ScannerEngine finished execution.")
            return

        try:
            self._execute_grid_scan(stop_event, user_setting)
        finally:
            if self._scan_started:
                self._scanned_at = datetime.now()
                self._log_scan_summary()

        logger.debug("ScannerEngine finished execution.")

    def get_weapon_essence_counts(self) -> dict[str, int]:
        return self._weapon_essence_counts.copy()

    def get_scan_summary(self) -> ScanSummaryState | None:
        if not self._scan_started or self._scanned_at is None:
            return None

        return ScanSummaryState(
            scanned_at=self._scanned_at,
            total_essence_count=self._total_essence_count,
            weapon_counts=self._weapon_essence_counts.copy(),
            weapon_best_level_combos={
                weapon_id: combos.copy()
                for weapon_id, combos in self._weapon_best_level_combos.items()
            },
            custom_treasures=[
                summary.model_copy(deep=True)
                for summary in self._custom_treasure_summaries.values()
            ],
        )

    def _prepare_scan(self) -> UserSetting | None:
        if not self._window_actions.target_exists:
            logger.info("未找到终末地窗口，停止基质扫描。")
            return None

        if self._window_actions.restore():
            self._window_actions.wait(0.5)
        if self._window_actions.activate():
            self._window_actions.wait(0.5)
        if self._window_actions.show():
            self._window_actions.wait(0.5)

        logger.debug("Made the window visible and active.")

        if not check_scene(self._image_source, self.ctx, self._profile):
            return None

        self._weapon_essence_counts = {}
        self._weapon_best_level_combos = {}
        self._custom_treasure_summaries = {}
        self._total_essence_count = 0
        self._scan_started = False
        self._scanned_at = None
        return self._user_setting_manager.get_user_setting()

    def _execute_grid_scan(
        self,
        stop_event: threading.Event,
        user_setting: UserSetting,
    ) -> None:
        completed = self._scan_current_page(
            stop_event,
            user_setting,
            list(self._profile.essence_icon_x_list),
            list(self._profile.essence_icon_y_list),
        )
        if completed:
            logger.info("基质扫描完成。")

    def _scan_current_page(
        self,
        stop_event: threading.Event,
        user_setting: UserSetting,
        icon_x_list: list[int],
        icon_y_list: list[int],
        start_row_index: int = 0,
    ) -> bool:
        rows_to_scan = list(enumerate(icon_y_list))[start_row_index:]

        for row_index, relative_y in rows_to_scan:
            for col_index, relative_x in enumerate(icon_x_list):
                if not self._window_actions.target_is_active:
                    logger.info("终末地窗口不在前台，停止基质扫描。")
                    return False

                if stop_event.is_set():
                    logger.info("基质扫描被中断。")
                    return False

                should_continue = self._scan_single_slot(
                    row_index,
                    col_index,
                    relative_x,
                    relative_y,
                    user_setting,
                )
                if not should_continue:
                    return False

        return True

    def _scan_single_slot(
        self,
        row_index: int,
        col_index: int,
        relative_x: int,
        relative_y: int,
        user_setting: UserSetting,
    ) -> bool:
        self._scan_started = True
        logger.info("正在扫描第 {} 行第 {} 列的基质...", row_index + 1, col_index + 1)

        self._window_actions.click(relative_x, relative_y)
        self._window_actions.wait(0.3)

        data = recognize_essence(self._image_source, self.ctx, self._profile)
        if (
            data.abandon_label == AbandonStatusLabel.MAYBE_ABANDONED
            or data.lock_label == LockStatusLabel.MAYBE_LOCKED
        ):
            return True

        evaluation = evaluate_essence(data, user_setting, self.ctx.static_game_data)
        self._record_evaluation(data, evaluation)
        self._log_evaluation(evaluation)
        self._execute_actions(data, evaluation, user_setting)

        if evaluation.should_stop_scan:
            logger.info("已根据设置结束本次扫描。")
            return False

        return True

    def _record_evaluation(
        self,
        data: EssenceData,
        evaluation: EvaluationResult,
    ) -> None:
        if evaluation.quality != EssenceQuality.SKIP:
            self._total_essence_count += 1

        complete_combo = get_complete_level_combo(data.levels)
        for weapon_id in evaluation.matched_non_trash_weapons:
            self._weapon_essence_counts[weapon_id] = (
                self._weapon_essence_counts.get(weapon_id, 0) + 1
            )
            update_best_level_combos(
                self._weapon_best_level_combos.setdefault(weapon_id, []),
                complete_combo,
            )

        for custom_match in evaluation.matched_custom_treasures:
            summary = self._custom_treasure_summaries.setdefault(
                custom_match.key,
                CustomTreasureSummaryState(
                    key=custom_match.key,
                    attribute=custom_match.attribute,
                    secondary=custom_match.secondary,
                    skill=custom_match.skill,
                ),
            )
            summary.count += 1
            update_best_level_combos(
                summary.best_level_combos,
                self._get_custom_match_level_combo(data, custom_match),
            )

    def _log_evaluation(self, evaluation: EvaluationResult) -> None:
        _log_evaluation_result(evaluation)

    def _execute_actions(
        self,
        data: EssenceData,
        evaluation: EvaluationResult,
        user_setting: UserSetting,
    ) -> None:
        actions = decide_actions(data, evaluation, user_setting)
        for action in actions:
            if action.type == ActionType.CLICK_LOCK:
                pos = self._profile.LOCK_BUTTON_POS
                self._window_actions.click(pos.x, pos.y)
            elif action.type == ActionType.CLICK_ABANDON:
                pos = self._profile.DEPRECATE_BUTTON_POS
                self._window_actions.click(pos.x, pos.y)

            self._window_actions.wait(0.3)
            logger.opt(colors=True).success(
                f"<LIGHT-YELLOW><bold>{action.log_message}</></>"
            )

    def _get_custom_match_level_combo(
        self,
        data: EssenceData,
        custom_match: CustomTreasureMatch,
    ) -> tuple[int, int, int] | None:
        return get_ordered_custom_level_combo(
            data.stats,
            data.levels,
            custom_match.attribute,
            custom_match.secondary,
            custom_match.skill,
        )

    def _log_scan_summary(self) -> None:
        summary = self.get_scan_summary()
        if summary is None:
            return

        for message in iter_scan_summary_log_messages(
            self.ctx.static_game_data, summary
        ):
            logger.opt(colors=True).success(message)


class DraggableScannerEngine(ScannerEngine):
    DRAG_STEP_LOGICAL_DISTANCE = 50
    WHEEL_SCROLL_STEPS = 7
    WHEEL_STEP_INTERVAL = 0.08
    FALLBACK_REFERENCE_DISTANCE = 820
    WHEEL_ALIGNMENT_TOLERANCE = 3
    WHEEL_ALIGNMENT_MAX_CORRECTIONS = 8
    WHEEL_ALIGNMENT_CORRECTION_DELTA = 12
    WHEEL_ALIGNMENT_SETTLE_TIME = 0.12
    DEFAULT_WHEEL_DELTAS = (-63, -64, -63, -64, -63, -64, -63)
    WHEEL_DELTA_PRESETS: dict[tuple[int, int], tuple[int, ...]] = {
        (1920, 1080): DEFAULT_WHEEL_DELTAS,
        (2560, 1440): (-62, -62, -62, -62, -62, -62, -62),
        (1920, 1200): (-84, -85, -84, -85, -84, -85, -84),
        (2560, 1600): (-76, -76, -76, -76, -76, -76, -76),
    }

    def _execute_grid_scan(
        self,
        stop_event: threading.Event,
        user_setting: UserSetting,
    ) -> None:
        if not user_setting.auto_page_flip:
            logger.info("自动翻页已关闭，将只扫描当前页。")
            super()._execute_grid_scan(stop_event, user_setting)
            return

        drag_start = getattr(self._profile, "DRAG_START_POS", None)
        drag_end = getattr(self._profile, "DRAG_END_POS", None)
        scrollbar_pos = getattr(self._profile, "SCROLLBAR_CHECK_POS", None)

        if drag_start is None or drag_end is None:
            logger.warning("当前分辨率配置缺少自动翻页坐标，将只扫描当前页。")
            super()._execute_grid_scan(stop_event, user_setting)
            return

        icon_x_list = list(self._profile.essence_icon_x_list)
        icon_y_list = list(self._profile.essence_icon_y_list)
        total_rows = len(icon_y_list)
        max_pages = 100
        page_count = 0
        is_last_page = False
        actual_flip_distance = 0
        max_flip_distance = (
            self._get_page_flip_reference_distance(drag_start, drag_end)
            if user_setting.page_flip_mode == PageFlipMode.DRAG
            else self._get_wheel_page_flip_reference_distance(icon_y_list)
        )

        while not stop_event.is_set() and page_count < max_pages:
            page_count += 1
            logger.info("开始扫描第 {} 页基质...", page_count)

            start_row = 0
            if is_last_page and page_count > 1:
                start_row = min(
                    self._calculate_skip_rows(
                        actual_drag=actual_flip_distance,
                        max_drag=max_flip_distance,
                        total_rows=total_rows,
                    ),
                    total_rows - 1,
                )
                logger.info(
                    "最后一页：本次翻页推进了 {}px / {}px，跳过前 {} 行已扫描基质。",
                    actual_flip_distance,
                    max_flip_distance,
                    start_row,
                )

            completed = self._scan_current_page(
                stop_event,
                user_setting,
                icon_x_list,
                icon_y_list,
                start_row_index=start_row,
            )
            if not completed:
                break

            if is_last_page:
                logger.info("已扫描完最后一页，基质扫描完成。")
                break

            if stop_event.is_set():
                logger.info("基质扫描被中断，停止翻页操作。")
                break

            actual_flip_distance, is_last_page = self._perform_page_flip(
                page_flip_mode=user_setting.page_flip_mode,
                drag_start=drag_start,
                drag_end=drag_end,
                scrollbar_pos=scrollbar_pos,
                stop_event=stop_event,
                step=self.DRAG_STEP_LOGICAL_DISTANCE,
                max_flip_distance=max_flip_distance,
                icon_x_list=icon_x_list,
                icon_y_list=icon_y_list,
            )

            if is_last_page:
                logger.info(
                    "检测到滚动条到底，本次翻页推进 {}px，下一页将是最后一页。",
                    actual_flip_distance,
                )

        if page_count >= max_pages:
            logger.info("已达到最大页数限制({})，扫描停止。", max_pages)

    def _perform_page_flip(
        self,
        page_flip_mode: PageFlipMode,
        drag_start: Point,
        drag_end: Point,
        scrollbar_pos: Point | None,
        stop_event: threading.Event,
        step: int,
        max_flip_distance: int,
        icon_x_list: list[int],
        icon_y_list: list[int],
    ) -> tuple[int, bool]:
        if page_flip_mode == PageFlipMode.DRAG:
            logger.info("开始精准（拖动）翻页...")
            return self._progressive_drag(
                drag_start=drag_start,
                drag_end=drag_end,
                scrollbar_pos=scrollbar_pos,
                stop_event=stop_event,
                step=step,
                max_drag=max_flip_distance,
            )

        logger.info("开始丝滑（滚轮）翻页...")
        return self._progressive_wheel_scroll(
            scrollbar_pos=scrollbar_pos,
            stop_event=stop_event,
            reference_distance=max_flip_distance,
            icon_x_list=icon_x_list,
            icon_y_list=icon_y_list,
        )

    def _get_page_flip_reference_distance(
        self,
        drag_start: Point | None,
        drag_end: Point | None,
    ) -> int:
        if drag_start is None or drag_end is None:
            return self.FALLBACK_REFERENCE_DISTANCE
        return round(math.hypot(drag_end.x - drag_start.x, drag_end.y - drag_start.y))

    def _check_scrollbar_at_bottom(self, check_pos: Point) -> bool:
        try:
            scale_factor = self._get_scale_factor()
            radius = max(1, round(2 / scale_factor))
            roi = Region(
                Point(check_pos.x - radius, check_pos.y - radius),
                Point(check_pos.x + radius + 1, check_pos.y + radius + 1),
            )
            screenshot = self._image_source.screenshot(roi)

            height, width = screenshot.shape[:2]
            for y in range(height):
                for x in range(width):
                    pixel = screenshot[y, x]
                    b, g, r = int(pixel[0]), int(pixel[1]), int(pixel[2])
                    if r > 100 and g > 100 and b > 100:
                        logger.info(
                            "检测到滚动条亮点 at ({}, {}): RGB({}, {}, {})",
                            check_pos.x - radius + x,
                            check_pos.y - radius + y,
                            r,
                            g,
                            b,
                        )
                        return True

            logger.debug("未检测到滚动条亮点 at ({}, {})", check_pos.x, check_pos.y)
            return False
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("滚动条检测失败: {}", exc)
            return False

    def _progressive_drag(
        self,
        drag_start: Point,
        drag_end: Point,
        scrollbar_pos: Point | None,
        stop_event: threading.Event,
        step: int,
        max_drag: int,
    ) -> tuple[int, bool]:
        bottom_hit = False
        stopped_by_user = False

        def on_step(_index: int, _x: int, _y: int) -> bool:
            nonlocal bottom_hit, stopped_by_user

            if stop_event.is_set():
                stopped_by_user = True
                logger.info("精准拖动翻页被中断。")
                return True

            if scrollbar_pos and self._check_scrollbar_at_bottom(scrollbar_pos):
                bottom_hit = True
                return True

            return False

        actual_drag, _stopped_early = self._window_actions.progressive_drag(
            drag_start.x,
            drag_start.y,
            drag_end.x,
            drag_end.y,
            step=step,
            max_drag=max_drag,
            on_step=on_step,
        )

        if not bottom_hit and not stopped_by_user and scrollbar_pos:
            bottom_hit = self._check_scrollbar_at_bottom(scrollbar_pos)

        return actual_drag, bottom_hit

    def _get_scale_factor(self) -> float:
        factor = getattr(self._window_actions, "scale_factor", None)
        return factor if factor is not None and factor > 0 else 1.0

    def _get_physical_client_size(self) -> tuple[int, int]:
        physical_size = getattr(self._image_source, "physical_size", None)
        if (
            isinstance(physical_size, tuple)
            and len(physical_size) == 2
            and all(isinstance(value, int) for value in physical_size)
        ):
            return physical_size
        return self._image_source.get_client_size()

    def _get_wheel_deltas(self) -> list[int]:
        physical_size = self._get_physical_client_size()
        preset = self.WHEEL_DELTA_PRESETS.get(physical_size)
        if preset is not None:
            return list(preset)
        return list(self.DEFAULT_WHEEL_DELTAS)

    def _get_row_step(self, icon_y_list: list[int]) -> int:
        if len(icon_y_list) >= 2:
            diffs = [b - a for a, b in zip(icon_y_list, icon_y_list[1:], strict=False)]
            if diffs:
                return round(sum(diffs) / len(diffs))
        fallback_rows = len(icon_y_list) or 5
        return round(self.FALLBACK_REFERENCE_DISTANCE / fallback_rows)

    def _get_wheel_page_flip_reference_distance(self, icon_y_list: list[int]) -> int:
        if not icon_y_list:
            return self.FALLBACK_REFERENCE_DISTANCE
        return self._get_row_step(icon_y_list) * len(icon_y_list)

    def _estimate_wheel_alignment_offset(
        self,
        icon_x_list: list[int],
        icon_y_list: list[int],
    ) -> float | None:
        if len(icon_x_list) < 2 or len(icon_y_list) < 2:
            return None

        row_step = self._get_row_step(icon_y_list)
        half_card = max(1, round(row_step * 0.46))
        roi = Region(
            Point(
                max(0, icon_x_list[0] - half_card), max(0, icon_y_list[0] - row_step)
            ),
            Point(icon_x_list[-1] + half_card + 1, icon_y_list[-1] + row_step + 1),
        )
        screenshot = self._image_source.screenshot(roi)
        if screenshot.size == 0:
            return None

        brightness = screenshot.mean(axis=2).mean(axis=1).astype(np.float32)
        smoothed = np.convolve(
            brightness, np.ones(5, dtype=np.float32) / 5, mode="same"
        )
        local_centers = np.asarray(icon_y_list, dtype=np.float32) - roi.y0
        local_gaps = local_centers[:-1] + row_step / 2
        center_window = max(1, round(row_step * 0.18))
        gap_window = max(1, round(row_step * 0.04))
        search_radius = max(2, round(row_step / 3))

        def sample_mean(
            series: np.ndarray, pos: float, half_window: int
        ) -> float | None:
            center = round(pos)
            start = max(0, center - half_window)
            end = min(len(series), center + half_window + 1)
            if end <= start:
                return None
            return float(series[start:end].mean())

        best_offset = 0
        best_score = float("-inf")
        for offset in range(-search_radius, search_radius + 1):
            score = 0.0
            sample_count = 0
            for center in local_centers:
                value = sample_mean(smoothed, center + offset, center_window)
                if value is None:
                    continue
                score += value
                sample_count += 1
            for gap in local_gaps:
                value = sample_mean(smoothed, gap + offset, gap_window)
                if value is None:
                    continue
                score += (255.0 - value) * 1.25
                sample_count += 1
            if sample_count == 0:
                continue
            if score > best_score:
                best_score = score
                best_offset = offset

        return float(best_offset)

    def _apply_wheel_boundary_correction(
        self,
        initial_offset: float,
        scrollbar_pos: Point | None,
        stop_event: threading.Event,
        icon_x_list: list[int],
        icon_y_list: list[int],
    ) -> tuple[float, bool]:
        import time

        import win32api  # ty: ignore[import-not-found]
        import win32con  # ty: ignore[import-not-found]

        current_offset = initial_offset
        for _ in range(self.WHEEL_ALIGNMENT_MAX_CORRECTIONS):
            if stop_event.is_set():
                return current_offset, False
            if abs(current_offset) <= self.WHEEL_ALIGNMENT_TOLERANCE:
                return current_offset, False

            delta = (
                -self.WHEEL_ALIGNMENT_CORRECTION_DELTA
                if current_offset > 0
                else self.WHEEL_ALIGNMENT_CORRECTION_DELTA
            )
            win32api.mouse_event(
                win32con.MOUSEEVENTF_WHEEL,
                0,
                0,
                delta,
                0,
            )
            time.sleep(self.WHEEL_ALIGNMENT_SETTLE_TIME)

            if scrollbar_pos and self._check_scrollbar_at_bottom(scrollbar_pos):
                return current_offset, True

            next_offset = self._estimate_wheel_alignment_offset(
                icon_x_list, icon_y_list
            )
            if next_offset is None or abs(next_offset) >= abs(current_offset):
                return current_offset, False
            current_offset = next_offset

        return current_offset, False

    def _progressive_wheel_scroll(
        self,
        scrollbar_pos: Point | None,
        stop_event: threading.Event,
        reference_distance: int,
        icon_x_list: list[int] | None = None,
        icon_y_list: list[int] | None = None,
    ) -> tuple[int, bool]:
        import time

        import win32api  # ty: ignore[import-not-found]
        import win32con  # ty: ignore[import-not-found]

        _physical_width, _physical_height = self._get_physical_client_size()
        deltas = self._get_wheel_deltas()
        total_delta = sum(deltas)
        total_abs_delta = sum(abs(delta) for delta in deltas) or 1
        actual_scroll_distance = 0.0

        logger.info(
            "开始丝滑滚轮翻页：总 delta={}, 分 {} 步，逻辑参考距离 {}px，缩放因子 {:.4f}",
            total_delta,
            len(deltas),
            reference_distance,
            self._get_scale_factor(),
        )

        for index, delta in enumerate(deltas, start=1):
            if stop_event.is_set():
                logger.info("滚轮翻页被中断。")
                return int(round(actual_scroll_distance)), False

            win32api.mouse_event(
                win32con.MOUSEEVENTF_WHEEL,
                0,
                0,
                delta,
                0,
            )
            actual_scroll_distance += reference_distance * (
                abs(delta) / total_abs_delta
            )
            logger.debug(
                "滚轮步 {}/{}: delta={}, 累计逻辑推进 {:.0f}px",
                index,
                len(deltas),
                delta,
                actual_scroll_distance,
            )

            time.sleep(self.WHEEL_STEP_INTERVAL)
            if scrollbar_pos and self._check_scrollbar_at_bottom(scrollbar_pos):
                logger.info(
                    "滚轮翻页中检测到滚动条到底，累计逻辑推进 {:.0f}px。",
                    actual_scroll_distance,
                )
                return int(round(actual_scroll_distance)), True

        if scrollbar_pos and self._check_scrollbar_at_bottom(scrollbar_pos):
            logger.info(
                "滚轮翻页完成后检测到滚动条到底，累计逻辑推进 {:.0f}px。",
                actual_scroll_distance,
            )
            return int(round(actual_scroll_distance)), True

        if not icon_x_list or not icon_y_list:
            return int(round(actual_scroll_distance)), False

        initial_offset = self._estimate_wheel_alignment_offset(icon_x_list, icon_y_list)
        if initial_offset is None:
            return int(round(actual_scroll_distance)), False

        logger.info("Wheel page alignment offset detected: {:.0f}px", initial_offset)
        final_offset, bottom_hit = self._apply_wheel_boundary_correction(
            initial_offset=initial_offset,
            scrollbar_pos=scrollbar_pos,
            stop_event=stop_event,
            icon_x_list=icon_x_list,
            icon_y_list=icon_y_list,
        )
        corrected_distance = max(
            0.0,
            float(reference_distance) + float(initial_offset) - float(final_offset),
        )
        logger.info(
            "Wheel page alignment settled: initial={:.0f}px final={:.0f}px corrected_distance={:.0f}px",
            initial_offset,
            final_offset,
            corrected_distance,
        )
        return int(round(corrected_distance)), bottom_hit

    def _calculate_skip_rows(
        self,
        actual_drag: int,
        max_drag: float,
        total_rows: int,
    ) -> int:
        if total_rows <= 0 or max_drag <= 0 or actual_drag <= 0:
            return 0

        ratio = max(0.0, min(1.0, actual_drag / max_drag))
        skip_rows = total_rows - round(ratio * total_rows)
        skip_rows = max(0, min(total_rows - 1, skip_rows))

        logger.info(
            "计算跳过行数: 比例={:.2f}, 实际推进={}px, 完整页={}px, 跳过={}行",
            ratio,
            actual_drag,
            max_drag,
            skip_rows,
        )
        return skip_rows

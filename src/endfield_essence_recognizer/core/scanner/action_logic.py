from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from endfield_essence_recognizer.core.recognition import (
    AbandonStatusLabel,
    LockStatusLabel,
)
from endfield_essence_recognizer.core.scanner.models import (
    EssenceData,
    EssenceQuality,
    EvaluationResult,
)
from endfield_essence_recognizer.schemas.user_setting import Action, UserSetting


class ActionType(Enum):
    CLICK_LOCK = auto()
    CLICK_ABANDON = auto()


@dataclass
class ScannerAction:
    """表示要执行的实际操作及其反馈文案。"""

    type: ActionType
    log_message: str


def decide_actions(
    data: EssenceData,
    evaluation: EvaluationResult,
    setting: UserSetting,
) -> list[ScannerAction]:
    """根据识别结果和用户设置决定要执行的按钮操作。"""
    if evaluation.quality == EssenceQuality.SKIP:
        return []

    actions: list[ScannerAction] = []

    should_lock = False
    should_unlock = False

    if evaluation.quality == EssenceQuality.TREASURE:
        target_action = setting.treasure_action
    else:
        target_action = setting.trash_action

    if target_action == Action.LOCK:
        should_lock = True
    elif target_action in [Action.UNLOCK, Action.UNLOCK_AND_UNDEPRECATE]:
        should_unlock = True
    elif (
        target_action == Action.LOCK_IF_NOT_DEPRECATED
        and data.abandon_label == AbandonStatusLabel.NOT_ABANDONED
    ):
        should_lock = True

    if data.lock_label == LockStatusLabel.NOT_LOCKED and should_lock:
        actions.append(
            ScannerAction(
                type=ActionType.CLICK_LOCK,
                log_message="给你自动锁上了，记得保管好哦！",
            )
        )
    elif data.lock_label == LockStatusLabel.LOCKED and should_unlock:
        actions.append(
            ScannerAction(
                type=ActionType.CLICK_LOCK,
                log_message="给你自动解锁了！",
            )
        )

    should_abandon = False
    should_unabandon = False

    if target_action == Action.DEPRECATE:
        should_abandon = True
    elif target_action in [Action.UNDEPRECATE, Action.UNLOCK_AND_UNDEPRECATE]:
        should_unabandon = True
    elif (
        target_action == Action.DEPRECATE_IF_NOT_LOCKED
        and data.lock_label == LockStatusLabel.NOT_LOCKED
    ):
        should_abandon = True

    if data.abandon_label == AbandonStatusLabel.NOT_ABANDONED and should_abandon:
        actions.append(
            ScannerAction(
                type=ActionType.CLICK_ABANDON,
                log_message="给你自动标记为弃用了。",
            )
        )
    elif data.abandon_label == AbandonStatusLabel.ABANDONED and should_unabandon:
        actions.append(
            ScannerAction(
                type=ActionType.CLICK_ABANDON,
                log_message="给你自动取消弃用了！",
            )
        )

    return actions

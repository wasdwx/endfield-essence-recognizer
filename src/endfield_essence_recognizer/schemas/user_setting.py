from __future__ import annotations

from enum import StrEnum
from typing import Any, ClassVar

from pydantic import BaseModel, Field


class Action(StrEnum):
    KEEP = "keep"
    LOCK = "lock"
    DEPRECATE = "deprecate"
    UNLOCK = "unlock"
    UNDEPRECATE = "undeprecate"
    UNLOCK_AND_UNDEPRECATE = "unlock_and_undeprecate"
    DEPRECATE_IF_NOT_LOCKED = "deprecate_if_not_locked"
    LOCK_IF_NOT_DEPRECATED = "lock_if_not_deprecated"


class NonFiveStarBehavior(StrEnum):
    PROCESS = "process"
    SKIP = "skip"
    STOP_SCAN = "stop_scan"


class PageFlipMode(StrEnum):
    WHEEL = "wheel"
    DRAG = "drag"


class EssenceStats(BaseModel):
    attribute: str | None
    secondary: str | None
    skill: str | None


class UserSetting(BaseModel):
    _VERSION: ClassVar[int] = 5

    version: int = _VERSION

    trash_weapon_ids: list[str] = Field(default_factory=list)
    treasure_essence_stats: list[EssenceStats] = Field(default_factory=list)

    treasure_action: Action = Action.LOCK
    trash_action: Action = Action.UNLOCK

    non_five_star_behavior: NonFiveStarBehavior = NonFiveStarBehavior.PROCESS

    high_level_treasure_enabled: bool = False
    high_level_treasure_attribute_threshold: int = Field(default=3, ge=1, le=6)
    high_level_treasure_secondary_threshold: int = Field(default=3, ge=1, le=6)
    high_level_treasure_skill_threshold: int = Field(default=3, ge=1, le=3)

    auto_page_flip: bool = True
    page_flip_mode: PageFlipMode = PageFlipMode.WHEEL
    enable_sound: bool = True

    update_mirror: str = "github"
    update_proxy: str = ""

    @staticmethod
    def _migrate_v2_to_v3(data: dict) -> None:
        data.setdefault("non_five_star_behavior", "process")
        data.setdefault("auto_page_flip", True)

    @staticmethod
    def _migrate_v3_to_v4(data: dict) -> None:
        data.setdefault("update_mirror", "github")
        data.setdefault("update_proxy", "")

    @staticmethod
    def _migrate_v4_to_v5(data: dict) -> None:
        data.setdefault("page_flip_mode", "wheel")
        data.setdefault("enable_sound", True)

    _MIGRATIONS: ClassVar[dict[int, Any]] = {
        2: _migrate_v2_to_v3.__func__,
        3: _migrate_v3_to_v4.__func__,
        4: _migrate_v4_to_v5.__func__,
    }

    @classmethod
    def migrate_from_old_version(cls, old_data: dict) -> UserSetting:
        old_version = old_data.get("version", 1)

        if old_version < 1:
            raise ValueError(f"配置版本非法: {old_version}")
        if old_version > cls._VERSION:
            raise ValueError("配置版本高于当前程序支持的版本")

        while old_version < cls._VERSION:
            if old_version not in cls._MIGRATIONS:
                raise ValueError(f"缺少迁移链: v{old_version} -> v{old_version + 1}")
            cls._MIGRATIONS[old_version](old_data)
            old_version += 1

        old_data["version"] = cls._VERSION
        return cls.model_validate(old_data)

    def update_from_model(self, other: UserSetting) -> None:
        for field in self.__class__.model_fields:
            setattr(self, field, getattr(other, field))

    def update_from_dict(self, data: dict[str, Any]) -> None:
        model = UserSetting.model_validate(data)
        self.update_from_model(model)

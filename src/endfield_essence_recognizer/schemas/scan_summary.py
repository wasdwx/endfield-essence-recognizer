from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from datetime import datetime

type LevelCombo = tuple[int, int, int]


class CustomTreasureSummaryState(BaseModel):
    key: str
    attribute: str | None
    secondary: str | None
    skill: str | None
    count: int = 0
    best_level_combos: list[LevelCombo] = Field(default_factory=list)


class ScanSummaryState(BaseModel):
    scanned_at: datetime
    total_essence_count: int
    weapon_counts: dict[str, int] = Field(default_factory=dict)
    weapon_best_level_combos: dict[str, list[LevelCombo]] = Field(default_factory=dict)
    custom_treasures: list[CustomTreasureSummaryState] = Field(default_factory=list)


class LastScanWeaponSummary(BaseModel):
    weapon_id: str
    count: int
    best_levels_text: str | None = None


class LastScanCustomSummary(BaseModel):
    key: str
    label: str
    count: int
    best_levels_text: str | None = None


class LastScanSummaryResponse(BaseModel):
    scanned_at: datetime
    total_essence_count: int
    weapons: list[LastScanWeaponSummary] = Field(default_factory=list)
    custom_treasures: list[LastScanCustomSummary] = Field(default_factory=list)


_DATETIME = __import__("datetime").datetime


CustomTreasureSummaryState.model_rebuild(_types_namespace={"datetime": _DATETIME})
ScanSummaryState.model_rebuild(_types_namespace={"datetime": _DATETIME})
LastScanWeaponSummary.model_rebuild(_types_namespace={"datetime": _DATETIME})
LastScanCustomSummary.model_rebuild(_types_namespace={"datetime": _DATETIME})
LastScanSummaryResponse.model_rebuild(_types_namespace={"datetime": _DATETIME})

from dataclasses import dataclass, field
from enum import StrEnum

from endfield_essence_recognizer.core.recognition import (
    AbandonStatusLabel,
    LockStatusLabel,
    RarityLabel,
)
from endfield_essence_recognizer.game_data.models.v2 import (
    StatId,
    WeaponId,
)


class EssenceQuality(StrEnum):
    """Enumeration of identified essence qualities."""

    TREASURE = "treasure"
    """Identified as a valuable item based on user settings."""

    TRASH = "trash"
    """Identified as junk or unwanted item."""

    SKIP = "skip"
    """Item should be ignored by automatic actions."""


@dataclass
class EssenceData:
    """Raw recognition data for a single essence."""

    stats: list[StatId | None]
    """List of identified attribute IDs on the essence."""

    levels: list[int | None]
    """List of identified attribute levels/enhancement values."""

    rarity: RarityLabel
    """The identified rarity of the essence."""

    abandon_label: AbandonStatusLabel
    """The identified 'abandon' (deprecate) button state."""

    lock_label: LockStatusLabel
    """The identified 'lock' button state."""


@dataclass(frozen=True)
class CustomTreasureMatch:
    key: str
    attribute: str | None
    secondary: str | None
    skill: str | None


@dataclass
class EvaluationResult:
    """The judgement result of an essence after evaluation against user settings."""

    quality: EssenceQuality
    """The overall judged quality (Treasure or Trash)."""

    log_message: str
    """The formatted log message to show to the user (contains color tags)."""

    should_stop_scan: bool = False
    """Whether the current scan should stop immediately after this result."""

    matched_weapons: set[WeaponId] = field(default_factory=set)
    """Set of weapon IDs that this essence is suitable for."""

    matched_non_trash_weapons: set[WeaponId] = field(default_factory=set)
    """
    Set of non-trash weapon IDs that this essence matches (excluding user-blocked weapons).
    Used for incrementing weapon essence counts.
    """

    is_high_level: bool = False
    """Whether any attribute on the essence exceeded a high-level threshold."""

    matched_custom_treasures: tuple[CustomTreasureMatch, ...] = ()
    """Matched custom treasure configurations for later summary aggregation."""

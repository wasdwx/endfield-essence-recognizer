import sys
import threading
from datetime import datetime
from unittest.mock import MagicMock

import numpy as np
import pytest

from endfield_essence_recognizer.core.layout.base import (
    Point,
    Region,
    ResolutionProfile,
)
from endfield_essence_recognizer.core.recognition import (
    AbandonStatusLabel,
    AttributeLevelRecognizer,
    LockStatusLabel,
    RarityLabel,
)
from endfield_essence_recognizer.core.recognition.tasks.ui import UISceneLabel
from endfield_essence_recognizer.core.recognition.template_recognizer import (
    TemplateRecognizer,
)
from endfield_essence_recognizer.core.scanner.action_logic import (
    ActionType,
    ScannerAction,
)
from endfield_essence_recognizer.core.scanner.context import ScannerContext
from endfield_essence_recognizer.core.scanner.engine import (
    DraggableScannerEngine,
    ScannerEngine,
    _format_evaluation_log_message,
)
from endfield_essence_recognizer.core.scanner.models import (
    CustomTreasureMatch,
    EssenceData,
    EssenceQuality,
    EvaluationResult,
)
from endfield_essence_recognizer.core.scanner.summary import format_best_level_combos
from endfield_essence_recognizer.schemas.user_setting import (
    NonFiveStarBehavior,
    PageFlipMode,
    UserSetting,
)
from endfield_essence_recognizer.services.user_setting_manager import UserSettingManager


class MockImageSource:
    def __init__(self, width: int = 1920, height: int = 1080):
        self.width = width
        self.height = height

    def get_client_size(self) -> tuple[int, int]:
        return self.width, self.height

    def screenshot(self, relative_region: Region | None = None) -> np.ndarray:
        if relative_region is not None:
            width = relative_region.x1 - relative_region.x0
            height = relative_region.y1 - relative_region.y0
        else:
            width, height = self.width, self.height
        return np.zeros((height, width, 3), dtype=np.uint8)


class MockScaledImageSource(MockImageSource):
    def __init__(
        self,
        logical_width: int = 1920,
        logical_height: int = 1080,
        physical_size: tuple[int, int] = (2560, 1440),
    ):
        super().__init__(logical_width, logical_height)
        self.physical_size = physical_size


class MockWindowActions:
    def __init__(self, scale_factor: float = 1.0):
        self._target_exists = True
        self._target_is_active = True
        self.scale_factor = scale_factor
        self.click_calls: list[tuple[int, int]] = []
        self.progressive_drag_calls: list[dict[str, object]] = []
        self.progressive_drag_result = (0, False)

    @property
    def target_exists(self) -> bool:
        return self._target_exists

    @property
    def target_is_active(self) -> bool:
        return self._target_is_active

    def restore(self) -> bool:
        return True

    def activate(self) -> bool:
        return True

    def show(self) -> bool:
        return True

    def click(self, relative_x: int, relative_y: int) -> None:
        self.click_calls.append((relative_x, relative_y))

    def wait(self, seconds: float) -> None:
        return None

    def progressive_drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        step: int = 50,
        max_drag: int = 0,
        on_step=None,
    ) -> tuple[int, bool]:
        self.progressive_drag_calls.append(
            {
                "start_x": start_x,
                "start_y": start_y,
                "end_x": end_x,
                "end_y": end_y,
                "step": step,
                "max_drag": max_drag,
                "on_step": on_step,
            }
        )
        return self.progressive_drag_result


@pytest.fixture
def mock_scanner_context():
    ui_scene_recognizer = MagicMock(spec=TemplateRecognizer)
    ui_scene_recognizer.recognize_roi_fallback.return_value = (
        UISceneLabel.ESSENCE_UI,
        1.0,
    )

    attr_recognizer = MagicMock(spec=TemplateRecognizer)
    attr_recognizer.recognize_roi.return_value = ("atk", 0.9)

    attr_level_recognizer = MagicMock(spec=AttributeLevelRecognizer)
    attr_level_recognizer.recognize_level.return_value = 10

    abandon_status_recognizer = MagicMock(spec=TemplateRecognizer)
    abandon_status_recognizer.recognize_roi_fallback.return_value = (
        AbandonStatusLabel.NOT_ABANDONED,
        0.9,
    )

    lock_status_recognizer = MagicMock(spec=TemplateRecognizer)
    lock_status_recognizer.recognize_roi_fallback.return_value = (
        LockStatusLabel.NOT_LOCKED,
        0.9,
    )

    rarity_recognizer = MagicMock(spec=TemplateRecognizer)
    rarity_recognizer.recognize_roi_fallback.return_value = (
        RarityLabel.OTHER,
        0.9,
    )

    static_game_data = MagicMock()
    stat = MagicMock()
    stat.name = "TestStat"
    static_game_data.get_stat.return_value = stat
    static_game_data.find_weapons_by_stats.return_value = []
    static_game_data.get_weapon.return_value = None
    static_game_data.get_weapon_type.return_value = None
    static_game_data.get_rarity_color.return_value = "#FFD700"

    return ScannerContext(
        attr_recognizer=attr_recognizer,
        attr_level_recognizer=attr_level_recognizer,
        abandon_status_recognizer=abandon_status_recognizer,
        lock_status_recognizer=lock_status_recognizer,
        rarity_recognizer=rarity_recognizer,
        ui_scene_recognizer=ui_scene_recognizer,
        static_game_data=static_game_data,
    )


@pytest.fixture
def mock_user_setting_manager():
    manager = MagicMock(spec=UserSettingManager)
    settings = UserSetting()
    settings.non_five_star_behavior = NonFiveStarBehavior.PROCESS
    settings.page_flip_mode = PageFlipMode.WHEEL
    manager.get_user_setting.return_value = settings
    return manager


@pytest.fixture
def mock_profile():
    profile = MagicMock(spec=ResolutionProfile)
    profile.RESOLUTION = (1920, 1080)
    profile.ESSENCE_UI_ROI = Region(Point(38, 66), Point(143, 106))
    profile.STATS_0_ROI = Region(Point(1508, 358), Point(1700, 390))
    profile.STATS_1_ROI = Region(Point(1508, 416), Point(1700, 448))
    profile.STATS_2_ROI = Region(Point(1508, 468), Point(1700, 500))
    profile.DEPRECATE_BUTTON_ROI = Region(Point(1790, 270), Point(1823, 302))
    profile.LOCK_BUTTON_ROI = Region(Point(1825, 270), Point(1857, 302))
    profile.RARITY_ROI = Region(Point(1496, 264), Point(1567, 291))
    profile.LOCK_BUTTON_POS = Point(1839, 286)
    profile.DEPRECATE_BUTTON_POS = Point(1807, 284)
    profile.DRAG_START_POS = Point(750, 870)
    profile.DRAG_END_POS = Point(750, 50)
    profile.SCROLLBAR_CHECK_POS = Point(1453, 950)
    profile.essence_icon_x_list = [100]
    profile.essence_icon_y_list = [200]
    return profile


@pytest.mark.skip_in_ci(reason="Skip scanner engine tests in CI environment")
def test_scanner_engine_execution(
    mock_scanner_context, mock_user_setting_manager, mock_profile
):
    image_source = MockImageSource()
    window_actions = MockWindowActions()

    engine = ScannerEngine(
        ctx=mock_scanner_context,
        image_source=image_source,
        window_actions=window_actions,
        user_setting_manager=mock_user_setting_manager,
        profile=mock_profile,
    )

    engine.execute(threading.Event())

    assert window_actions.click_calls[0] == (100, 200)
    mock_scanner_context.attr_recognizer.recognize_roi.assert_called()


def test_scanner_engine_stop_event(
    mock_scanner_context, mock_user_setting_manager, mock_profile
):
    image_source = MockImageSource()
    window_actions = MockWindowActions()
    mock_profile.essence_icon_x_list = [100, 200]
    mock_profile.essence_icon_y_list = [200]

    engine = ScannerEngine(
        ctx=mock_scanner_context,
        image_source=image_source,
        window_actions=window_actions,
        user_setting_manager=mock_user_setting_manager,
        profile=mock_profile,
    )

    stop_event = threading.Event()
    stop_event.set()
    engine.execute(stop_event)

    assert window_actions.click_calls == []


def test_recognize_essence_screenshot_calls(mock_scanner_context, mock_profile):
    from endfield_essence_recognizer.core.scanner.engine import recognize_essence

    image_source = MagicMock()
    image_source.screenshot.return_value = np.zeros(
        (mock_profile.RESOLUTION[1], mock_profile.RESOLUTION[0], 3), dtype=np.uint8
    )
    image_source.get_client_size.return_value = mock_profile.RESOLUTION

    recognize_essence(image_source, mock_scanner_context, mock_profile)

    assert image_source.screenshot.call_count == 1


def test_recognize_once_screenshot_calls(mock_scanner_context, mock_profile):
    from endfield_essence_recognizer.core.scanner.engine import recognize_once

    image_source = MagicMock()
    image_source.screenshot.return_value = np.zeros(
        (mock_profile.RESOLUTION[1], mock_profile.RESOLUTION[0], 3), dtype=np.uint8
    )
    image_source.get_client_size.return_value = mock_profile.RESOLUTION

    recognize_once(image_source, mock_scanner_context, UserSetting(), mock_profile)

    assert image_source.screenshot.call_count == 1


def test_scanner_engine_screenshot_count(
    mock_scanner_context, mock_user_setting_manager, mock_profile
):
    image_source = MagicMock()
    image_source.screenshot.return_value = np.zeros(
        (mock_profile.RESOLUTION[1], mock_profile.RESOLUTION[0], 3), dtype=np.uint8
    )
    image_source.get_client_size.return_value = mock_profile.RESOLUTION
    window_actions = MockWindowActions()

    engine = ScannerEngine(
        ctx=mock_scanner_context,
        image_source=image_source,
        window_actions=window_actions,
        user_setting_manager=mock_user_setting_manager,
        profile=mock_profile,
    )

    engine.execute(threading.Event())

    assert image_source.screenshot.call_count == 2


def test_scanner_engine_tracks_weapon_counts(
    mock_scanner_context, mock_user_setting_manager, mock_profile
):
    image_source = MockImageSource()
    window_actions = MockWindowActions()

    weapon = MagicMock()
    weapon.name = "TestWeapon"
    weapon.rarity = 6
    weapon.weapon_type = "sword"
    weapon_type = MagicMock()
    weapon_type.name = "Sword"

    mock_scanner_context.static_game_data.find_weapons_by_stats.return_value = [
        "weapon_a"
    ]
    mock_scanner_context.static_game_data.get_weapon.return_value = weapon
    mock_scanner_context.static_game_data.get_weapon_type.return_value = weapon_type

    mock_profile.essence_icon_x_list = [100, 200]
    mock_profile.essence_icon_y_list = [300]

    engine = ScannerEngine(
        ctx=mock_scanner_context,
        image_source=image_source,
        window_actions=window_actions,
        user_setting_manager=mock_user_setting_manager,
        profile=mock_profile,
    )

    engine.execute(threading.Event())

    assert engine.get_weapon_essence_counts() == {"weapon_a": 2}


def test_scanner_engine_stops_on_non_five_star_setting(
    mock_scanner_context, mock_user_setting_manager, mock_profile
):
    image_source = MockImageSource()
    window_actions = MockWindowActions()

    mock_profile.essence_icon_x_list = [100, 200]
    mock_profile.essence_icon_y_list = [300]

    setting = UserSetting()
    setting.non_five_star_behavior = NonFiveStarBehavior.STOP_SCAN
    mock_user_setting_manager.get_user_setting.return_value = setting

    engine = ScannerEngine(
        ctx=mock_scanner_context,
        image_source=image_source,
        window_actions=window_actions,
        user_setting_manager=mock_user_setting_manager,
        profile=mock_profile,
    )

    engine.execute(threading.Event())

    assert window_actions.click_calls == [(100, 300)]


def test_draggable_scanner_engine_reuses_counting_path(
    mock_scanner_context, mock_user_setting_manager, mock_profile, monkeypatch
):
    image_source = MockImageSource()
    window_actions = MockWindowActions()

    weapon = MagicMock()
    weapon.name = "TestWeapon"
    weapon.rarity = 6
    weapon.weapon_type = "sword"
    weapon_type = MagicMock()
    weapon_type.name = "Sword"

    mock_scanner_context.static_game_data.find_weapons_by_stats.return_value = [
        "weapon_a"
    ]
    mock_scanner_context.static_game_data.get_weapon.return_value = weapon
    mock_scanner_context.static_game_data.get_weapon_type.return_value = weapon_type

    mock_profile.essence_icon_x_list = [100]
    mock_profile.essence_icon_y_list = [300, 400]

    engine = DraggableScannerEngine(
        ctx=mock_scanner_context,
        image_source=image_source,
        window_actions=window_actions,
        user_setting_manager=mock_user_setting_manager,
        profile=mock_profile,
    )

    monkeypatch.setattr(
        engine,
        "_perform_page_flip",
        lambda *_args, **_kwargs: (100, True),
    )
    monkeypatch.setattr(engine, "_calculate_skip_rows", lambda *_args, **_kwargs: 1)

    engine.execute(threading.Event())

    assert engine.get_weapon_essence_counts() == {"weapon_a": 3}


def test_format_evaluation_log_message_highlights_treasure_matches():
    evaluation = EvaluationResult(
        quality=EssenceQuality.TREASURE,
        log_message="base message",
        matched_non_trash_weapons={"weapon_a"},
    )

    formatted = _format_evaluation_log_message(evaluation)

    assert "命中适配" in formatted
    assert formatted.endswith("base message")


def test_calculate_skip_rows_matches_original_ratio_logic(
    mock_scanner_context, mock_user_setting_manager, mock_profile
):
    engine = DraggableScannerEngine(
        ctx=mock_scanner_context,
        image_source=MockImageSource(),
        window_actions=MockWindowActions(),
        user_setting_manager=mock_user_setting_manager,
        profile=mock_profile,
    )

    assert engine._calculate_skip_rows(actual_drag=820, max_drag=820, total_rows=5) == 0
    assert engine._calculate_skip_rows(actual_drag=410, max_drag=820, total_rows=5) == 3


def test_wheel_mode_uses_1080p_baseline(
    mock_scanner_context, mock_user_setting_manager, mock_profile, monkeypatch
):
    wheel_deltas: list[int] = []

    class FakeWin32Api:
        @staticmethod
        def mouse_event(_flag, _x, _y, delta, _extra):
            wheel_deltas.append(delta)

    class FakeWin32Con:
        MOUSEEVENTF_WHEEL = 0x0800

    monkeypatch.setitem(sys.modules, "win32api", FakeWin32Api)
    monkeypatch.setitem(sys.modules, "win32con", FakeWin32Con)

    engine = DraggableScannerEngine(
        ctx=mock_scanner_context,
        image_source=MockImageSource(),
        window_actions=MockWindowActions(scale_factor=1.0),
        user_setting_manager=mock_user_setting_manager,
        profile=mock_profile,
    )

    actual_distance, is_last_page = engine._progressive_wheel_scroll(
        scrollbar_pos=None,
        stop_event=threading.Event(),
        reference_distance=820,
    )

    assert wheel_deltas == [-63, -64, -63, -64, -63, -64, -63]
    assert actual_distance == 820
    assert is_last_page is False


def test_wheel_mode_uses_1440p_preset_from_physical_window_size(
    mock_scanner_context, mock_user_setting_manager, mock_profile, monkeypatch
):
    wheel_deltas: list[int] = []

    class FakeWin32Api:
        @staticmethod
        def mouse_event(_flag, _x, _y, delta, _extra):
            wheel_deltas.append(delta)

    class FakeWin32Con:
        MOUSEEVENTF_WHEEL = 0x0800

    monkeypatch.setitem(sys.modules, "win32api", FakeWin32Api)
    monkeypatch.setitem(sys.modules, "win32con", FakeWin32Con)

    engine = DraggableScannerEngine(
        ctx=mock_scanner_context,
        image_source=MockScaledImageSource(physical_size=(2560, 1440)),
        window_actions=MockWindowActions(scale_factor=0.75),
        user_setting_manager=mock_user_setting_manager,
        profile=mock_profile,
    )

    engine._progressive_wheel_scroll(
        scrollbar_pos=None,
        stop_event=threading.Event(),
        reference_distance=820,
    )

    assert wheel_deltas == [-62] * 7


def test_wheel_mode_uses_1200p_preset_from_physical_window_size(
    mock_scanner_context, mock_user_setting_manager, mock_profile, monkeypatch
):
    wheel_deltas: list[int] = []

    class FakeWin32Api:
        @staticmethod
        def mouse_event(_flag, _x, _y, delta, _extra):
            wheel_deltas.append(delta)

    class FakeWin32Con:
        MOUSEEVENTF_WHEEL = 0x0800

    monkeypatch.setitem(sys.modules, "win32api", FakeWin32Api)
    monkeypatch.setitem(sys.modules, "win32con", FakeWin32Con)

    engine = DraggableScannerEngine(
        ctx=mock_scanner_context,
        image_source=MockScaledImageSource(physical_size=(1920, 1200)),
        window_actions=MockWindowActions(scale_factor=0.9),
        user_setting_manager=mock_user_setting_manager,
        profile=mock_profile,
    )

    engine._progressive_wheel_scroll(
        scrollbar_pos=None,
        stop_event=threading.Event(),
        reference_distance=930,
    )

    assert wheel_deltas == [-84, -85, -84, -85, -84, -85, -84]


def test_wheel_mode_uses_1600p_preset_from_physical_window_size(
    mock_scanner_context, mock_user_setting_manager, mock_profile, monkeypatch
):
    wheel_deltas: list[int] = []

    class FakeWin32Api:
        @staticmethod
        def mouse_event(_flag, _x, _y, delta, _extra):
            wheel_deltas.append(delta)

    class FakeWin32Con:
        MOUSEEVENTF_WHEEL = 0x0800

    monkeypatch.setitem(sys.modules, "win32api", FakeWin32Api)
    monkeypatch.setitem(sys.modules, "win32con", FakeWin32Con)

    engine = DraggableScannerEngine(
        ctx=mock_scanner_context,
        image_source=MockScaledImageSource(physical_size=(2560, 1600)),
        window_actions=MockWindowActions(scale_factor=0.675),
        user_setting_manager=mock_user_setting_manager,
        profile=mock_profile,
    )

    engine._progressive_wheel_scroll(
        scrollbar_pos=None,
        stop_event=threading.Event(),
        reference_distance=930,
    )

    assert wheel_deltas == [-76] * 7


def test_wheel_mode_falls_back_to_default_preset_for_unknown_sizes(
    mock_scanner_context, mock_user_setting_manager, mock_profile, monkeypatch
):
    wheel_deltas: list[int] = []

    class FakeWin32Api:
        @staticmethod
        def mouse_event(_flag, _x, _y, delta, _extra):
            wheel_deltas.append(delta)

    class FakeWin32Con:
        MOUSEEVENTF_WHEEL = 0x0800

    monkeypatch.setitem(sys.modules, "win32api", FakeWin32Api)
    monkeypatch.setitem(sys.modules, "win32con", FakeWin32Con)

    engine = DraggableScannerEngine(
        ctx=mock_scanner_context,
        image_source=MockScaledImageSource(physical_size=(2304, 1296)),
        window_actions=MockWindowActions(scale_factor=1.0),
        user_setting_manager=mock_user_setting_manager,
        profile=mock_profile,
    )

    engine._progressive_wheel_scroll(
        scrollbar_pos=None,
        stop_event=threading.Event(),
        reference_distance=910,
    )

    assert wheel_deltas == [-63, -64, -63, -64, -63, -64, -63]


def test_wheel_reference_distance_uses_visible_full_rows(
    mock_scanner_context, mock_user_setting_manager, mock_profile
):
    engine = DraggableScannerEngine(
        ctx=mock_scanner_context,
        image_source=MockImageSource(),
        window_actions=MockWindowActions(),
        user_setting_manager=mock_user_setting_manager,
        profile=mock_profile,
    )

    assert (
        engine._get_wheel_page_flip_reference_distance([202, 357, 512, 667, 822]) == 775
    )
    assert (
        engine._get_wheel_page_flip_reference_distance([202, 357, 512, 667, 822, 977])
        == 930
    )


def test_drag_mode_uses_progressive_drag(
    mock_scanner_context, mock_user_setting_manager, mock_profile
):
    window_actions = MockWindowActions()
    window_actions.progressive_drag_result = (615, False)

    engine = DraggableScannerEngine(
        ctx=mock_scanner_context,
        image_source=MockImageSource(),
        window_actions=window_actions,
        user_setting_manager=mock_user_setting_manager,
        profile=mock_profile,
    )

    actual_distance, is_last_page = engine._perform_page_flip(
        page_flip_mode=PageFlipMode.DRAG,
        drag_start=mock_profile.DRAG_START_POS,
        drag_end=mock_profile.DRAG_END_POS,
        scrollbar_pos=None,
        stop_event=threading.Event(),
        step=50,
        max_flip_distance=820,
        icon_x_list=[100],
        icon_y_list=[200],
    )

    assert actual_distance == 615
    assert is_last_page is False
    assert len(window_actions.progressive_drag_calls) == 1


def test_wheel_mode_alignment_adjusts_corrected_distance(
    mock_scanner_context, mock_user_setting_manager, mock_profile, monkeypatch
):
    wheel_deltas: list[int] = []

    class FakeWin32Api:
        @staticmethod
        def mouse_event(_flag, _x, _y, delta, _extra):
            wheel_deltas.append(delta)

    class FakeWin32Con:
        MOUSEEVENTF_WHEEL = 0x0800

    monkeypatch.setitem(sys.modules, "win32api", FakeWin32Api)
    monkeypatch.setitem(sys.modules, "win32con", FakeWin32Con)

    engine = DraggableScannerEngine(
        ctx=mock_scanner_context,
        image_source=MockImageSource(),
        window_actions=MockWindowActions(scale_factor=1.0),
        user_setting_manager=mock_user_setting_manager,
        profile=mock_profile,
    )

    monkeypatch.setattr(engine, "_estimate_wheel_alignment_offset", lambda *_args: 6.0)
    monkeypatch.setattr(
        engine,
        "_apply_wheel_boundary_correction",
        lambda **_kwargs: (1.0, False),
    )

    actual_distance, is_last_page = engine._progressive_wheel_scroll(
        scrollbar_pos=None,
        stop_event=threading.Event(),
        reference_distance=775,
        icon_x_list=[100, 255],
        icon_y_list=[202, 357, 512, 667, 822],
    )

    assert wheel_deltas == [-63, -64, -63, -64, -63, -64, -63]
    assert actual_distance == 780
    assert is_last_page is False


def test_execute_actions_highlights_action_logs(
    mock_scanner_context, mock_user_setting_manager, mock_profile, monkeypatch
):
    image_source = MockImageSource()
    window_actions = MockWindowActions()
    engine = ScannerEngine(
        ctx=mock_scanner_context,
        image_source=image_source,
        window_actions=window_actions,
        user_setting_manager=mock_user_setting_manager,
        profile=mock_profile,
    )

    messages: list[str] = []

    class FakeLogger:
        def opt(self, **_kwargs):
            return self

        def success(self, message, *args):
            messages.append(message.format(*args) if args else message)

    monkeypatch.setattr(
        "endfield_essence_recognizer.core.scanner.engine.decide_actions",
        lambda *_args, **_kwargs: [
            ScannerAction(ActionType.CLICK_LOCK, "给你自动锁上了"),
        ],
    )
    monkeypatch.setattr(
        "endfield_essence_recognizer.core.scanner.engine.logger", FakeLogger()
    )

    data = MagicMock()
    evaluation = EvaluationResult(quality=EssenceQuality.TREASURE, log_message="ok")
    engine._execute_actions(data, evaluation, UserSetting())

    assert any("<LIGHT-YELLOW><bold>给你自动锁上了</></>" in msg for msg in messages)


def test_log_scan_summary_colors_weapon_names_by_rarity(
    mock_scanner_context, mock_user_setting_manager, mock_profile, monkeypatch
):
    image_source = MockImageSource()
    window_actions = MockWindowActions()
    engine = ScannerEngine(
        ctx=mock_scanner_context,
        image_source=image_source,
        window_actions=window_actions,
        user_setting_manager=mock_user_setting_manager,
        profile=mock_profile,
    )
    engine._total_essence_count = 3
    engine._weapon_essence_counts = {"weapon_a": 2}
    engine._scan_started = True
    engine._scanned_at = datetime.now()

    weapon = MagicMock()
    weapon.name = "TestWeapon"
    weapon.rarity = 6
    weapon.weapon_type = "sword"
    weapon_type = MagicMock()
    weapon_type.name = "Sword"
    mock_scanner_context.static_game_data.get_weapon.return_value = weapon
    mock_scanner_context.static_game_data.get_weapon_type.return_value = weapon_type
    mock_scanner_context.static_game_data.get_rarity_color.return_value = "#FFD700"

    messages: list[str] = []

    class FakeLogger:
        def opt(self, **_kwargs):
            return self

        def success(self, message, *args):
            messages.append(message.format(*args) if args else message)

    monkeypatch.setattr(
        "endfield_essence_recognizer.core.scanner.engine.logger", FakeLogger()
    )

    engine._log_scan_summary()

    assert any(
        "<fg #FFD700><bold>TestWeapon（6★ Sword）</></>" in msg for msg in messages
    )


def test_record_evaluation_tracks_best_combos_and_duplicate_counts(
    mock_scanner_context, mock_user_setting_manager, mock_profile
):
    image_source = MockImageSource()
    window_actions = MockWindowActions()
    engine = ScannerEngine(
        ctx=mock_scanner_context,
        image_source=image_source,
        window_actions=window_actions,
        user_setting_manager=mock_user_setting_manager,
        profile=mock_profile,
    )

    custom_match = CustomTreasureMatch(
        key="A|B|C",
        attribute="A",
        secondary="B",
        skill="C",
    )
    evaluation = EvaluationResult(
        quality=EssenceQuality.TREASURE,
        log_message="ok",
        matched_non_trash_weapons={"weapon_a"},
        matched_custom_treasures=(custom_match,),
    )

    for levels in ([1, 1, 1], [2, 1, 1], [2, 1, 1]):
        engine._record_evaluation(
            EssenceData(
                stats=["A", "B", "C"],
                levels=levels,
                rarity=RarityLabel.FIVE,
                abandon_label=AbandonStatusLabel.NOT_ABANDONED,
                lock_label=LockStatusLabel.NOT_LOCKED,
            ),
            evaluation,
        )

    engine._scan_started = True
    engine._scanned_at = datetime.now()

    summary = engine.get_scan_summary()

    assert summary is not None
    assert summary.weapon_counts == {"weapon_a": 3}
    assert (
        format_best_level_combos(summary.weapon_best_level_combos["weapon_a"])
        == "+2/+1/+1（2次）"
    )
    assert summary.custom_treasures[0].count == 3
    assert (
        format_best_level_combos(summary.custom_treasures[0].best_level_combos)
        == "+2/+1/+1（2次）"
    )


def test_log_scan_summary_includes_custom_treasure_statistics(
    mock_scanner_context, mock_user_setting_manager, mock_profile, monkeypatch
):
    image_source = MockImageSource()
    window_actions = MockWindowActions()
    engine = ScannerEngine(
        ctx=mock_scanner_context,
        image_source=image_source,
        window_actions=window_actions,
        user_setting_manager=mock_user_setting_manager,
        profile=mock_profile,
    )

    custom_match = CustomTreasureMatch(
        key="A|B|C",
        attribute="A",
        secondary="B",
        skill="C",
    )
    evaluation = EvaluationResult(
        quality=EssenceQuality.TREASURE,
        log_message="ok",
        matched_custom_treasures=(custom_match,),
    )
    engine._record_evaluation(
        EssenceData(
            stats=["A", "B", "C"],
            levels=[2, 1, 1],
            rarity=RarityLabel.FIVE,
            abandon_label=AbandonStatusLabel.NOT_ABANDONED,
            lock_label=LockStatusLabel.NOT_LOCKED,
        ),
        evaluation,
    )
    engine._scan_started = True
    engine._scanned_at = datetime.now()

    stat_a = MagicMock()
    stat_a.name = "攻击提升"
    stat_b = MagicMock()
    stat_b.name = "物伤提升"
    stat_c = MagicMock()
    stat_c.name = "技巧"
    mock_scanner_context.static_game_data.get_stat.side_effect = lambda stat_id: {
        "A": stat_a,
        "B": stat_b,
        "C": stat_c,
    }.get(stat_id)

    messages: list[str] = []

    class FakeLogger:
        def opt(self, **_kwargs):
            return self

        def success(self, message, *args):
            messages.append(message.format(*args) if args else message)

    monkeypatch.setattr(
        "endfield_essence_recognizer.core.scanner.engine.logger", FakeLogger()
    )

    engine._log_scan_summary()

    assert any("自定义宝藏命中统计" in msg for msg in messages)
    assert any("攻击提升 / 物伤提升 / 技巧" in msg for msg in messages)
    assert any("最优 <green><bold>+2/+1/+1" in msg for msg in messages)

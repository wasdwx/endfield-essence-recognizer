from fastapi import APIRouter, Depends
from pydantic import BaseModel

from endfield_essence_recognizer.core.interfaces import AutomationEngine
from endfield_essence_recognizer.core.scanner.engine import (
    OneTimeRecognitionEngine,
    ScannerEngine,
)
from endfield_essence_recognizer.core.scanner.summary import (
    format_best_level_combos,
    sort_weapon_counts,
)
from endfield_essence_recognizer.dependencies import (
    get_delivery_claimer_engine_dep,
    get_one_time_recognition_engine_dep,
    get_scanner_engine_dep,
    get_scanner_service,
    get_static_game_data,
    require_game_or_webview_is_active,
    require_game_window_exists,
)
from endfield_essence_recognizer.game_data.static_game_data import StaticGameData
from endfield_essence_recognizer.schemas.scan_summary import (
    LastScanCustomSummary,
    LastScanSummaryResponse,
    LastScanWeaponSummary,
)
from endfield_essence_recognizer.schemas.scanner import TaskType
from endfield_essence_recognizer.services.scanner_service import ScannerService

router = APIRouter(prefix='', tags=['scanner'])


class ToggleScanningRequest(BaseModel):
    task_type: TaskType


@router.post(
    '/recognize_once',
    dependencies=[
        Depends(require_game_or_webview_is_active),
        Depends(require_game_window_exists),
    ],
)
async def recognize_once(
    engine: OneTimeRecognitionEngine = Depends(get_one_time_recognition_engine_dep),
    scanner_service: ScannerService = Depends(get_scanner_service),
) -> None:
    scanner_service.start_scan(scanner_factory=lambda: engine)


@router.post(
    '/start_scanning',
    dependencies=[
        Depends(require_game_or_webview_is_active),
        Depends(require_game_window_exists),
    ],
)
async def start_scanning(
    scanner: ScannerEngine = Depends(get_scanner_engine_dep),
    scanner_service: ScannerService = Depends(get_scanner_service),
) -> None:
    scanner_service.toggle_scan(scanner_factory=lambda: scanner)


@router.post(
    '/toggle_scanning',
    dependencies=[
        Depends(require_game_or_webview_is_active),
        Depends(require_game_window_exists),
    ],
)
async def toggle_scanning(
    request: ToggleScanningRequest,
    scanner_service: ScannerService = Depends(get_scanner_service),
    essence_engine: ScannerEngine = Depends(get_scanner_engine_dep),
    delivery_engine: AutomationEngine = Depends(get_delivery_claimer_engine_dep),
) -> None:
    def get_engine() -> AutomationEngine:
        match request.task_type:
            case TaskType.ESSENCE:
                return essence_engine
            case TaskType.DELIVERY_CLAIM:
                return delivery_engine
            case _:
                raise ValueError(f'Unsupported task type: {request.task_type}')

    scanner_service.toggle_scan(scanner_factory=get_engine)


@router.get('/weapon_essence_counts')
async def get_weapon_essence_counts(
    scanner_service: ScannerService = Depends(get_scanner_service),
) -> dict[str, int]:
    return scanner_service.get_weapon_essence_counts()


@router.get('/scanning_status')
async def get_scanning_status(
    scanner_service: ScannerService = Depends(get_scanner_service),
) -> dict[str, bool]:
    return {'is_running': scanner_service.is_running()}


@router.get('/last_scan_summary', response_model=LastScanSummaryResponse | None)
async def get_last_scan_summary(
    scanner_service: ScannerService = Depends(get_scanner_service),
    static_game_data: StaticGameData = Depends(get_static_game_data),
) -> LastScanSummaryResponse | None:
    summary = scanner_service.get_last_scan_summary()
    if summary is None:
        return None

    weapon_summaries = [
        LastScanWeaponSummary(
            weapon_id=weapon_id,
            count=count,
            best_levels_text=format_best_level_combos(
                summary.weapon_best_level_combos.get(weapon_id, [])
            ),
        )
        for weapon_id, count in sort_weapon_counts(
            static_game_data, summary.weapon_counts
        )
    ]

    def resolve_stat_name(stat_id: str | None) -> str:
        if stat_id is None:
            return '??'
        stat = static_game_data.get_stat(stat_id)
        return stat.name if stat is not None else stat_id

    custom_summaries = [
        LastScanCustomSummary(
            key=custom.key,
            label=' / '.join(
                [
                    resolve_stat_name(custom.attribute),
                    resolve_stat_name(custom.secondary),
                    resolve_stat_name(custom.skill),
                ]
            ),
            count=custom.count,
            best_levels_text=format_best_level_combos(custom.best_level_combos),
        )
        for custom in sorted(summary.custom_treasures, key=lambda item: item.key)
    ]

    return LastScanSummaryResponse(
        scanned_at=summary.scanned_at,
        total_essence_count=summary.total_essence_count,
        weapons=weapon_summaries,
        custom_treasures=custom_summaries,
    )

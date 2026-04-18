import asyncio

from fastapi import APIRouter, Depends

from endfield_essence_recognizer.dependencies import get_data_update_service
from endfield_essence_recognizer.schemas.data_update import (
    DataUpdateActionResponse,
    DataUpdateStatusResponse,
)
from endfield_essence_recognizer.services.data_update_service import DataUpdateService

router = APIRouter(prefix="/data_update", tags=["data_update"])


@router.get("/status")
async def get_data_update_status(
    service: DataUpdateService = Depends(get_data_update_service),
) -> DataUpdateStatusResponse:
    return service.get_status()


@router.post("/check")
async def check_data_update(
    service: DataUpdateService = Depends(get_data_update_service),
) -> DataUpdateActionResponse:
    return await asyncio.to_thread(service.check_for_updates)


@router.post("/download")
async def download_data_update(
    service: DataUpdateService = Depends(get_data_update_service),
) -> DataUpdateActionResponse:
    return await asyncio.to_thread(service.download_updates)

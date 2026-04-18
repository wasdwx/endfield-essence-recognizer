from datetime import datetime
from enum import StrEnum

from pydantic import AliasGenerator, BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class DataSource(StrEnum):
    BUNDLED = "bundled"
    OVERRIDE = "override"


class DataUpdateStatusResponse(BaseModel):
    current_data_source: DataSource = Field(description="当前实际生效的武器数据来源。")
    applied_version: str | None = Field(
        default=None,
        description="当前已应用并生效的数据版本标识。",
    )
    pending_version: str | None = Field(
        default=None,
        description="已下载但尚未应用的数据版本标识。",
    )
    last_checked_version: str | None = Field(
        default=None,
        description="最近一次检查到的远端版本标识。",
    )
    update_available: bool = Field(description="是否检测到可下载的新武器数据。")
    pending_apply: bool = Field(description="是否存在已下载但尚未应用的新数据。")
    last_checked_at: datetime | None = Field(
        default=None,
        description="最近一次向上游检查数据的时间。",
    )
    last_downloaded_at: datetime | None = Field(
        default=None,
        description="最近一次成功下载武器数据的时间。",
    )
    last_applied_at: datetime | None = Field(
        default=None,
        description="最近一次成功应用武器数据的时间。",
    )
    last_error: str | None = Field(
        default=None,
        description="最近一次检查、下载或应用失败信息。",
    )

    model_config = ConfigDict(
        alias_generator=AliasGenerator(
            validation_alias=to_camel,
            serialization_alias=to_camel,
        ),
        populate_by_name=True,
    )


class DataUpdateActionResponse(BaseModel):
    status: DataUpdateStatusResponse
    message: str = Field(description="本次检查、下载或应用的结果说明。")
    downloaded: bool = Field(description="本次请求是否实际下载了新数据。")
    applied: bool = Field(description="本次请求是否已经将新数据应用到运行时。")

    model_config = ConfigDict(
        alias_generator=AliasGenerator(
            validation_alias=to_camel,
            serialization_alias=to_camel,
        ),
        populate_by_name=True,
    )

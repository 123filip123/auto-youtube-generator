"""The HTTP wire contract.

`frontend/src/lib/types.ts` mirrors this file field for field. Change both
together.
"""

from typing import Any

from pydantic import BaseModel, Field, field_validator

import config
from api.config_view import OVERRIDABLE, effective_config
from api.runs import Run
from models import Item


class ItemPayload(BaseModel):
    title: str
    description: str
    image_prompts: list[str]

    @classmethod
    def from_item(cls, item: Item) -> "ItemPayload":
        return cls(
            title=item.title,
            description=item.description,
            image_prompts=list(item.image_prompts),
        )


class AssetStatusPayload(BaseModel):
    label: str
    ok: bool
    error: str | None = None


class RunSummaryPayload(BaseModel):
    id: str
    topic: str
    num_items: int
    status: str
    created_at: str
    finished_at: str | None = None


class RunDetailPayload(RunSummaryPayload):
    review_items: bool
    overrides: dict[str, Any]
    production_models: bool
    items: list[ItemPayload]
    assets: list[AssetStatusPayload]
    asset_total: int
    logs: list[str]
    error: str | None = None
    video_url: str | None = None
    archive_slug: str | None = None


class CreateRunRequest(BaseModel):
    topic: str
    num_items: int = Field(ge=1, le=50)
    review_items: bool = False
    overrides: dict[str, Any] = Field(default_factory=dict)
    production_models: bool = False

    @field_validator("topic")
    @classmethod
    def topic_is_not_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("topic must not be blank")
        return text


class ApproveItemsRequest(BaseModel):
    items: list[ItemPayload] = Field(min_length=1)


class ConfigFieldPayload(BaseModel):
    name: str
    type: str
    choices: list[str] | None = None
    description: str = ""


class ConfigPayload(BaseModel):
    values: dict[str, Any]
    overridable: list[ConfigFieldPayload]
    production_image_settings: dict[str, str]


class ArchiveSummaryPayload(BaseModel):
    slug: str
    item_count: int
    image_count: int
    audio_count: int
    has_video: bool
    modified_at: str


class ArchiveItemPayload(BaseModel):
    title: str
    description: str
    image_prompts: list[str]
    image_urls: list[str]
    titled_image_urls: list[str]
    audio_url: str | None = None


class ArchiveDetailPayload(BaseModel):
    slug: str
    video_url: str | None = None
    items: list[ArchiveItemPayload]


def config_payload() -> ConfigPayload:
    return ConfigPayload(
        values=effective_config(),
        overridable=[
            ConfigFieldPayload(
                name=field.name,
                type=field.type,
                choices=list(field.choices) if field.choices else None,
                description=field.description,
            )
            for field in OVERRIDABLE
        ],
        production_image_settings=dict(config.PRODUCTION_IMAGE_SETTINGS),
    )


def run_summary(run: Run) -> RunSummaryPayload:
    return RunSummaryPayload(
        id=run.id,
        topic=run.topic,
        num_items=run.num_items,
        status=run.status,
        created_at=run.created_at,
        finished_at=run.finished_at,
    )


def run_detail(run: Run) -> RunDetailPayload:
    """Build the full payload, including a cache-busted video URL.

    The rendered video always lands at the same path, so without the run id
    query the browser would replay the previous run's video.
    """
    video_url = None
    if run.video_path is not None and run.video_path.is_file():
        video_url = f"/media/{run.video_path.as_posix()}?run={run.id}"

    return RunDetailPayload(
        **run_summary(run).model_dump(),
        review_items=run.review_items,
        overrides=run.overrides,
        production_models=run.production_models,
        items=[ItemPayload.from_item(item) for item in run.items],
        assets=[
            AssetStatusPayload(label=asset.label, ok=asset.ok, error=asset.error)
            for asset in run.assets
        ],
        asset_total=run.asset_total,
        logs=list(run.logs),
        error=run.error,
        video_url=video_url,
        archive_slug=run.archive_slug,
    )

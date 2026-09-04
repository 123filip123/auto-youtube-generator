"""The HTTP wire contract.

`frontend/src/lib/types.ts` mirrors this file field for field. Change both
together.
"""

from typing import Any

from pydantic import BaseModel, Field, field_validator

from api.config_view import OVERRIDABLE, effective_config
from api.runs import Run
from models import Script


class SectionPayload(BaseModel):
    """One section on the wire.

    `start` and `end` are output-only: they are derived from narration length
    and later from measured audio, so a client that edits them is ignored.
    """

    label: str
    narration: str
    prompts: list[str] = Field(default_factory=list)
    start: float = 0.0
    end: float = 0.0


class ScriptPayload(BaseModel):
    topic: str = ""
    title: str = ""
    style: str = ""
    sections: list[SectionPayload] = Field(default_factory=list)

    @classmethod
    def from_script(cls, script: Script) -> "ScriptPayload":
        return cls(
            topic=script.topic,
            title=script.title,
            style=script.style,
            sections=[
                SectionPayload(
                    label=section.label,
                    narration=section.narration,
                    prompts=list(section.prompts),
                    start=section.start,
                    end=section.end,
                )
                for section in script.sections
            ],
        )


class AssetStatusPayload(BaseModel):
    label: str
    ok: bool
    error: str | None = None


class RunSummaryPayload(BaseModel):
    id: str
    topic: str
    target_seconds: int
    status: str
    created_at: str
    finished_at: str | None = None


class RunDetailPayload(RunSummaryPayload):
    review_script: bool
    overrides: dict[str, Any]
    script: ScriptPayload
    assets: list[AssetStatusPayload]
    asset_total: int
    logs: list[str]
    error: str | None = None
    video_url: str | None = None
    archive_slug: str | None = None


class CreateRunRequest(BaseModel):
    topic: str
    target_seconds: int = Field(default=85, ge=15, le=180)
    review_script: bool = False
    overrides: dict[str, Any] = Field(default_factory=dict)

    @field_validator("topic")
    @classmethod
    def topic_is_not_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("topic must not be blank")
        return text


class ApproveScriptRequest(BaseModel):
    script: ScriptPayload


class ConfigFieldPayload(BaseModel):
    name: str
    type: str
    choices: list[str] | None = None
    description: str = ""


class ConfigPayload(BaseModel):
    values: dict[str, Any]
    overridable: list[ConfigFieldPayload]


class ArchiveSummaryPayload(BaseModel):
    slug: str
    section_count: int
    image_count: int
    audio_count: int
    has_video: bool
    legacy: bool = False
    modified_at: str


class ArchiveSectionPayload(BaseModel):
    label: str
    narration: str
    prompts: list[str]
    start: float = 0.0
    end: float = 0.0
    image_urls: list[str]
    composed_image_urls: list[str]
    audio_url: str | None = None


class ArchiveDetailPayload(BaseModel):
    slug: str
    topic: str
    title: str
    style: str = ""
    video_url: str | None = None
    legacy: bool = False
    sections: list[ArchiveSectionPayload]


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
    )


def run_summary(run: Run) -> RunSummaryPayload:
    return RunSummaryPayload(
        id=run.id,
        topic=run.topic,
        target_seconds=run.target_seconds,
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
        review_script=run.review_script,
        overrides=run.overrides,
        script=ScriptPayload.from_script(run.script),
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

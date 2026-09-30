"""Every HTTP endpoint. Translates domain errors into status codes only."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from api import archives, schemas
from api.config_view import ConfigOverrideError, validate_overrides
from api.runs import RunConflictError, RunNotFoundError, RunStore
from models import InvalidItemsError, parse_items

router = APIRouter()


def get_store(request: Request) -> RunStore:
    return request.app.state.run_store


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/config", response_model=schemas.ConfigPayload)
def read_config() -> schemas.ConfigPayload:
    return schemas.config_payload()


@router.get("/runs", response_model=list[schemas.RunSummaryPayload])
def list_runs(store: RunStore = Depends(get_store)):
    return [schemas.run_summary(run) for run in store.list()]


@router.post(
    "/runs",
    response_model=schemas.RunDetailPayload,
    status_code=status.HTTP_201_CREATED,
)
def create_run(payload: schemas.CreateRunRequest, store: RunStore = Depends(get_store)):
    try:
        overrides: dict[str, Any] = validate_overrides(payload.overrides)
    except ConfigOverrideError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    try:
        run = store.start(
            payload.topic,
            payload.num_items,
            review_items=payload.review_items,
            overrides=overrides,
            production_models=payload.production_models,
        )
    except RunConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    return schemas.run_detail(run)


@router.get("/runs/{run_id}", response_model=schemas.RunDetailPayload)
def read_run(run_id: str, store: RunStore = Depends(get_store)):
    try:
        return schemas.run_detail(store.get(run_id))
    except RunNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no run {run_id}") from exc


@router.post("/runs/{run_id}/items", response_model=schemas.RunDetailPayload)
def approve_items(
    run_id: str,
    payload: schemas.ApproveItemsRequest,
    store: RunStore = Depends(get_store),
):
    # Reuse the pipeline's own validation so the UI cannot submit an item the
    # renderer would choke on. The prompt count is free-form here: the user may
    # legitimately add or remove prompts while reviewing.
    try:
        items = parse_items(
            [item.model_dump() for item in payload.items], expected_prompts=None
        )
    except InvalidItemsError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    try:
        return schemas.run_detail(store.approve_items(run_id, items))
    except RunNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no run {run_id}") from exc
    except RunConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/runs/{run_id}/cancel", response_model=schemas.RunDetailPayload)
def cancel_run(run_id: str, store: RunStore = Depends(get_store)):
    try:
        return schemas.run_detail(store.cancel(run_id))
    except RunNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no run {run_id}") from exc
    except RunConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/archives", response_model=list[schemas.ArchiveSummaryPayload])
def list_archives():
    return archives.list_archives()


@router.get("/archives/{slug}", response_model=schemas.ArchiveDetailPayload)
def read_archive(slug: str):
    try:
        return archives.archive_detail(slug)
    except archives.ArchiveNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no archive {slug}") from exc

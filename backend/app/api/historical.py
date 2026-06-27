from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.database import (
    Container,
    ProcessingStatus,
    SafetyEvaluation,
    UploadBatch,
    get_db_session,
)


router = APIRouter(prefix="/historical", tags=["historical"])


class BatchListItem(BaseModel):
    batch_id: uuid.UUID
    source_filename: str
    uploaded_by: str | None
    processing_status: str
    total_containers: int
    created_at: datetime
    processed_at: datetime | None


class BatchListResponse(BaseModel):
    page: int
    page_size: int
    total_records: int
    total_pages: int
    records: list[BatchListItem] = Field(default_factory=list)


class EvaluationView(BaseModel):
    evaluation_id: uuid.UUID
    container_id: uuid.UUID
    status: str
    overall_score: float
    racking_ratio: float
    wind_exposure_ratio: float
    tier_load_ratio: float
    corner_post_stress_ratio: float
    remediation_actions: list[str] = Field(default_factory=list)
    evaluated_at: datetime


class ContainerView(BaseModel):
    container_id: uuid.UUID
    container_number: str
    iso_type_code: str | None
    gross_weight_kg: float
    tare_weight_kg: float
    payload_weight_kg: float
    cargo_description: str | None


class BatchDetailResponse(BaseModel):
    batch_id: uuid.UUID
    source_filename: str
    uploaded_by: str | None
    processing_status: str
    parse_error: str | None
    total_containers: int
    created_at: datetime
    processed_at: datetime | None
    containers: list[ContainerView] = Field(default_factory=list)
    evaluations: list[EvaluationView] = Field(default_factory=list)


@router.get("/batches", response_model=BatchListResponse)
async def list_batches(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: ProcessingStatus | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_db_session),
) -> BatchListResponse:
    filters = []
    if status_filter is not None:
        filters.append(UploadBatch.processing_status == status_filter)

    count_stmt = select(func.count()).select_from(UploadBatch)
    if filters:
        count_stmt = count_stmt.where(*filters)

    total_records = (await session.execute(count_stmt)).scalar_one()
    total_pages = (total_records + page_size - 1) // page_size if total_records else 0

    query = (
        select(UploadBatch)
        .where(*filters) if filters else select(UploadBatch)
    )
    query = query.order_by(UploadBatch.created_at.desc()).offset((page - 1) * page_size).limit(page_size)

    batches = (await session.execute(query)).scalars().all()

    return BatchListResponse(
        page=page,
        page_size=page_size,
        total_records=total_records,
        total_pages=total_pages,
        records=[
            BatchListItem(
                batch_id=batch.id,
                source_filename=batch.source_filename,
                uploaded_by=batch.uploaded_by,
                processing_status=batch.processing_status.value,
                total_containers=batch.total_containers,
                created_at=batch.created_at,
                processed_at=batch.processed_at,
            )
            for batch in batches
        ],
    )


@router.get("/batches/{batch_id}", response_model=BatchDetailResponse)
async def get_batch_details(
    batch_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> BatchDetailResponse:
    batch_stmt = (
        select(UploadBatch)
        .options(
            selectinload(UploadBatch.containers),
            selectinload(UploadBatch.evaluations),
        )
        .where(UploadBatch.id == batch_id)
    )
    batch = (await session.execute(batch_stmt)).scalar_one_or_none()
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found.")

    containers = [
        ContainerView(
            container_id=item.id,
            container_number=item.container_number,
            iso_type_code=item.iso_type_code,
            gross_weight_kg=item.gross_weight_kg,
            tare_weight_kg=item.tare_weight_kg,
            payload_weight_kg=item.payload_weight_kg,
            cargo_description=item.cargo_description,
        )
        for item in sorted(batch.containers, key=lambda c: c.container_number)
    ]

    evaluations = [
        EvaluationView(
            evaluation_id=ev.id,
            container_id=ev.container_id,
            status=ev.status.value,
            overall_score=ev.overall_score,
            racking_ratio=ev.racking_ratio,
            wind_exposure_ratio=ev.wind_exposure_ratio,
            tier_load_ratio=ev.tier_load_ratio,
            corner_post_stress_ratio=ev.corner_post_stress_ratio,
            remediation_actions=ev.remediation_actions,
            evaluated_at=ev.evaluated_at,
        )
        for ev in sorted(batch.evaluations, key=lambda e: e.evaluated_at, reverse=True)
    ]

    return BatchDetailResponse(
        batch_id=batch.id,
        source_filename=batch.source_filename,
        uploaded_by=batch.uploaded_by,
        processing_status=batch.processing_status.value,
        parse_error=batch.parse_error,
        total_containers=batch.total_containers,
        created_at=batch.created_at,
        processed_at=batch.processed_at,
        containers=containers,
        evaluations=evaluations,
    )


@router.get("/containers/{container_id}/evaluations", response_model=list[EvaluationView])
async def get_container_evaluations(
    container_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> list[EvaluationView]:
    container_exists = (
        await session.execute(select(Container.id).where(Container.id == container_id))
    ).scalar_one_or_none()
    if container_exists is None:
        raise HTTPException(status_code=404, detail="Container not found.")

    stmt = (
        select(SafetyEvaluation)
        .where(SafetyEvaluation.container_id == container_id)
        .order_by(SafetyEvaluation.evaluated_at.desc())
    )
    evaluations = (await session.execute(stmt)).scalars().all()

    return [
        EvaluationView(
            evaluation_id=ev.id,
            container_id=ev.container_id,
            status=ev.status.value,
            overall_score=ev.overall_score,
            racking_ratio=ev.racking_ratio,
            wind_exposure_ratio=ev.wind_exposure_ratio,
            tier_load_ratio=ev.tier_load_ratio,
            corner_post_stress_ratio=ev.corner_post_stress_ratio,
            remediation_actions=ev.remediation_actions,
            evaluated_at=ev.evaluated_at,
        )
        for ev in evaluations
    ]

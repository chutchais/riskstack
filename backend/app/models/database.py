from __future__ import annotations

import os
import uuid
from datetime import datetime
from enum import Enum
from typing import AsyncGenerator

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum as SAEnum, Float, ForeignKey
from sqlalchemy import Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://riskstack:riskstack@localhost:5432/riskstack",
)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ProcessingStatus(str, Enum):
    PENDING = "PENDING"
    PARSED = "PARSED"
    EVALUATED = "EVALUATED"
    FAILED = "FAILED"


class SafetyStatus(str, Enum):
    SAFE = "SAFE"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class UploadBatch(TimestampMixin, Base):
    __tablename__ = "upload_batches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    uploaded_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    total_containers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        SAEnum(ProcessingStatus, name="processing_status_enum"),
        nullable=False,
        default=ProcessingStatus.PENDING,
    )
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    containers: Mapped[list[Container]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
    )
    evaluations: Mapped[list[SafetyEvaluation]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
    )


class Container(TimestampMixin, Base):
    __tablename__ = "containers"
    __table_args__ = (
        CheckConstraint("gross_weight_kg >= 0", name="ck_containers_gross_weight_non_negative"),
        CheckConstraint("tare_weight_kg >= 0", name="ck_containers_tare_weight_non_negative"),
        CheckConstraint("payload_weight_kg >= 0", name="ck_containers_payload_weight_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("upload_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    container_number: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    iso_type_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    gross_weight_kg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tare_weight_kg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    payload_weight_kg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cargo_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    edi_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    batch: Mapped[UploadBatch] = relationship(back_populates="containers")
    placements: Mapped[list[ContainerPlacement]] = relationship(
        back_populates="container",
        cascade="all, delete-orphan",
    )
    evaluations: Mapped[list[SafetyEvaluation]] = relationship(
        back_populates="container",
        cascade="all, delete-orphan",
    )


class YardBlock(TimestampMixin, Base):
    __tablename__ = "yard_blocks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    slots: Mapped[list[YardSlot]] = relationship(
        back_populates="block",
        cascade="all, delete-orphan",
    )


class YardSlot(TimestampMixin, Base):
    __tablename__ = "yard_slots"
    __table_args__ = (
        UniqueConstraint("block_id", "bay", "row", "tier", name="uq_yard_slots_position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    block_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("yard_blocks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    bay: Mapped[int] = mapped_column(Integer, nullable=False)
    row: Mapped[int] = mapped_column(Integer, nullable=False)
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    max_stack_weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)

    block: Mapped[YardBlock] = relationship(back_populates="slots")
    placements: Mapped[list[ContainerPlacement]] = relationship(
        back_populates="slot",
        cascade="all, delete-orphan",
    )


class ContainerPlacement(TimestampMixin, Base):
    __tablename__ = "container_placements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    container_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("containers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    slot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("yard_slots.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    placed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    container: Mapped[Container] = relationship(back_populates="placements")
    slot: Mapped[YardSlot] = relationship(back_populates="placements")


class SafetyEvaluation(TimestampMixin, Base):
    __tablename__ = "safety_evaluations"
    __table_args__ = (
        UniqueConstraint("batch_id", "container_id", name="uq_safety_eval_batch_container"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("upload_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    container_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("containers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[SafetyStatus] = mapped_column(
        SAEnum(SafetyStatus, name="safety_status_enum"),
        nullable=False,
    )
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)

    racking_ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    racking_ratio: Mapped[float] = mapped_column(Float, nullable=False)

    wind_ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    wind_exposure_ratio: Mapped[float] = mapped_column(Float, nullable=False)

    weight_distribution_ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    center_of_gravity_offset_m: Mapped[float] = mapped_column(Float, nullable=False)

    tier_metrics_ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    tier_load_ratio: Mapped[float] = mapped_column(Float, nullable=False)

    corner_post_stress_ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    corner_post_stress_ratio: Mapped[float] = mapped_column(Float, nullable=False)

    rule_details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    remediation_actions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    batch: Mapped[UploadBatch] = relationship(back_populates="evaluations")
    container: Mapped[Container] = relationship(back_populates="evaluations")


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session

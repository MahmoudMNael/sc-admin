from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres.base import Base
from app.modules.assets.models import Asset


class FixtureApplication(StrEnum):
    INTERIOR = "interior"
    INDUSTRIAL = "industrial"


class ElectricalProtection(StrEnum):
    OV = "OV"
    OC = "OC"
    OT = "OT"


_APP_VALUES = [v.value for v in FixtureApplication]
_APP_SQL = ", ".join(f"'{v}'" for v in _APP_VALUES)
_ELECTRICAL_SQL = ", ".join(f"'{v.value}'" for v in ElectricalProtection)
_BOTH_APPLICATIONS = " AND ".join(f"applications @> ARRAY['{v}']::text[]" for v in _APP_VALUES)


class Fixture(Base):
    __tablename__ = "fixtures"
    __table_args__ = (
        CheckConstraint("cardinality(applications) >= 1", name="ck_fixtures_applications_nonempty"),
        CheckConstraint("cardinality(applications) <= 2", name="ck_fixtures_applications_max"),
        CheckConstraint(
            f"applications <@ ARRAY[{_APP_SQL}]::text[]",
            name="ck_fixtures_applications_allowed",
        ),
        # ponytail: uniqueness CHECK assumes a 2-value closed set; use a trigger if applications grow.
        CheckConstraint(
            f"cardinality(applications) = 1 OR ({_BOTH_APPLICATIONS})",
            name="ck_fixtures_applications_unique",
        ),
        Index("ix_fixtures_applications", "applications", postgresql_using="gin"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    manufacturer_name: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    is_main_solution: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false"), index=True
    )
    applications: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    variants: Mapped[list["FixtureVariant"]] = relationship(
        back_populates="fixture",
        lazy="raise",
        cascade="all, delete-orphan",
    )


class FixtureVariant(Base):
    __tablename__ = "fixture_variants"
    __table_args__ = (
        UniqueConstraint("fixture_id", "name", name="uq_fixture_variants_fixture_id_name"),
        CheckConstraint(
            f"electrical_protections <@ ARRAY[{_ELECTRICAL_SQL}]::text[]",
            name="ck_fixture_variants_electrical_allowed",
        ),
        # ponytail: PG CHECK cannot DISTINCT-unnest; duplicate array tags are a DTO concern.
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    fixture_id: Mapped[UUID] = mapped_column(ForeignKey("fixtures.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    power: Mapped[int] = mapped_column(Integer, nullable=False)
    chip: Mapped[str] = mapped_column(String, nullable=False)
    driver: Mapped[str] = mapped_column(String, nullable=False)
    power_factor: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    cri: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    efficacy: Mapped[int] = mapped_column(Integer, nullable=False)
    mechanical_protections: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    electrical_protections: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    dimension_length: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    dimension_width: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    dimension_depth: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    dimension_radius: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    model_3d_file_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), index=True, nullable=True
    )
    ies_file_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    fixture: Mapped[Fixture] = relationship(back_populates="variants", lazy="raise")
    model_3d_file: Mapped[Asset | None] = relationship(lazy="raise", foreign_keys=[model_3d_file_id])
    ies_file: Mapped[Asset] = relationship(lazy="raise", foreign_keys=[ies_file_id])
    images: Mapped[list["FixtureVariantImage"]] = relationship(
        back_populates="variant",
        lazy="raise",
        cascade="all, delete-orphan",
    )


class FixtureVariantImage(Base):
    __tablename__ = "fixture_variant_images"
    __table_args__ = (
        UniqueConstraint("variant_id", "image_file_id", name="uq_fixture_variant_images_variant_file"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    variant_id: Mapped[UUID] = mapped_column(
        ForeignKey("fixture_variants.id", ondelete="CASCADE"), index=True
    )
    image_file_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"), index=True)

    variant: Mapped[FixtureVariant] = relationship(back_populates="images", lazy="raise")
    image_file: Mapped[Asset] = relationship(lazy="raise")

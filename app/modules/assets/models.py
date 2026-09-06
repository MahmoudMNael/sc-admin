from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres.base import Base


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    relative_path: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    mime_type: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

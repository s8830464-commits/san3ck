from datetime import datetime
from typing import List, Optional
from sqlalchemy import Integer, String, Text, DateTime, JSON, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Tags stored as JSON array of strings e.g. ["tag1", "tag2"]
    tags: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    # Section categorized by AI: 'games', 'movies', 'work', 'tasks', 'tech'
    section: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default=None)
    # Status can be 'published', 'draft', 'hidden'
    status: Mapped[str] = mapped_column(String(20), default="published", index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    def to_dict(self) -> dict:
        """Helper to serialize note data for future REST API or export."""
        return {
            "id": self.id,
            "text": self.text,
            "tags": self.tags or [],
            "section": self.section,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<Note id={self.id} status={self.status} tags={self.tags}>"

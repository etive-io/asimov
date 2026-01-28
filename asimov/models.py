"""
Database models for Asimov ledger.

This module defines the Pydantic models and SQLAlchemy ORM models
for the asimov database backend.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    JSON,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, Session
from sqlalchemy.pool import StaticPool

Base = declarative_base()


class EventModel(Base):
    """SQLAlchemy model for Event."""

    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False, index=True)
    repository = Column(String, nullable=True)
    working_directory = Column(String, nullable=True)
    meta = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime, 
        default=lambda: datetime.now(timezone.utc), 
        onupdate=lambda: datetime.now(timezone.utc), 
        nullable=False
    )

    # Relationships
    productions = relationship(
        "ProductionModel", back_populates="event", cascade="all, delete-orphan"
    )

    def to_dict(self):
        """Convert to dictionary compatible with existing Event.to_dict()."""
        data = {
            "name": self.name,
            "repository": self.repository,
            "working directory": self.working_directory,
        }
        # Merge meta fields
        if self.meta:
            data.update(self.meta)
        # Note: productions relationship is not included by default to avoid
        # lazy loading issues. Use query_productions to get productions separately.
        return data


class ProductionModel(Base):
    """SQLAlchemy model for Production."""

    __tablename__ = "productions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, index=True)
    event_name = Column(
        String, ForeignKey("events.name", ondelete="CASCADE"), nullable=False, index=True
    )
    pipeline = Column(String, nullable=False, index=True)
    status = Column(String, nullable=True, index=True, default="ready")
    comment = Column(String, nullable=True)
    meta = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime, 
        default=lambda: datetime.now(timezone.utc), 
        onupdate=lambda: datetime.now(timezone.utc), 
        nullable=False
    )

    # Relationships
    event = relationship("EventModel", back_populates="productions")

    def to_dict(self):
        """Convert to dictionary compatible with existing Production.to_dict()."""
        data = {
            "name": self.name,
            "pipeline": self.pipeline,
            "status": self.status,
            "event": self.event_name,
        }
        if self.comment:
            data["comment"] = self.comment
        # Merge meta fields
        if self.meta:
            data.update(self.meta)
        return data


class ProjectAnalysisModel(Base):
    """SQLAlchemy model for ProjectAnalysis."""

    __tablename__ = "project_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False, index=True)
    pipeline = Column(String, nullable=False)
    status = Column(String, nullable=True, index=True, default="ready")
    comment = Column(String, nullable=True)
    meta = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime, 
        default=lambda: datetime.now(timezone.utc), 
        onupdate=lambda: datetime.now(timezone.utc), 
        nullable=False
    )

    def to_dict(self):
        """Convert to dictionary compatible with existing ProjectAnalysis.to_dict()."""
        data = {
            "name": self.name,
            "pipeline": self.pipeline,
            "status": self.status,
        }
        if self.comment:
            data["comment"] = self.comment
        # Merge meta fields
        if self.meta:
            data.update(self.meta)
        return data


# Pydantic validation models

class EventSchema(BaseModel):
    """Pydantic schema for Event validation."""

    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=1, description="Event identifier")
    repository: Optional[str] = None
    working_directory: Optional[str] = Field(None, alias="working directory")
    meta: Dict[str, Any] = Field(default_factory=dict)


class ProductionSchema(BaseModel):
    """Pydantic schema for Production validation."""

    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=1, description="Production name")
    event_name: str = Field(..., description="Parent event name")
    pipeline: str = Field(..., description="Pipeline type")
    status: Optional[str] = "ready"
    comment: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class ProjectAnalysisSchema(BaseModel):
    """Pydantic schema for ProjectAnalysis validation."""

    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=1, description="Analysis name")
    pipeline: str = Field(..., description="Pipeline type")
    status: Optional[str] = "ready"
    comment: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)

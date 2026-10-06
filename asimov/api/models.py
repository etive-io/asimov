"""
Pydantic validation models for API request/response data.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class EventCreate(BaseModel):
    """Model for creating a new event."""
    name: str = Field(..., min_length=1, description="Event identifier")
    repository: Optional[str] = None
    working_directory: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class EventUpdate(BaseModel):
    """Model for updating an existing event."""
    repository: Optional[str] = None
    working_directory: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


class AnalysisCreate(BaseModel):
    """Model for creating a new analysis."""
    name: str = Field(..., min_length=1, description="Analysis name")
    pipeline: str = Field(..., description="Pipeline type: bilby, rift, bayeswave, etc.")
    comment: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)


class AnalysisUpdate(BaseModel):
    """Model for updating an existing analysis."""
    status: Optional[str] = None
    comment: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None

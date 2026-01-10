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


class ProductionCreate(BaseModel):
    """Model for creating a new production."""
    name: str = Field(..., min_length=1, description="Production name")
    pipeline: str = Field(..., description="Pipeline type: bilby, rift, bayeswave, etc.")
    comment: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)


class ProductionUpdate(BaseModel):
    """Model for updating an existing production."""
    status: Optional[str] = None
    comment: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None

"""Strict transport contracts; adapters normalize into these events."""
from typing import Literal
from datetime import datetime, timezone
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    schema_version: Literal["1.0"] = "1.0"
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.:-]+$")
    event_type: Literal["arrival", "aoi", "measurement", "release"]
    run_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    board_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    line_id: str = Field(min_length=1, max_length=40)
    buffer_id: str = Field(min_length=1, max_length=40)
    slot_id: str = Field(min_length=1, max_length=40)
    occupancy_id: str = Field(min_length=1, max_length=80)
    payload: dict = Field(default_factory=dict)


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    site_id: str
    decision: Literal["false_call", "real_defect"]


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    reviewer: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=1000)
    decisions: list[Decision] = Field(min_length=1, max_length=100)

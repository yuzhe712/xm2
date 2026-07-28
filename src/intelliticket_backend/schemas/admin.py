from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TeamResponse(BaseModel):
    id: str
    code: str
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class TeamCreateRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=60, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(..., min_length=1, max_length=120)


class TeamUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    is_active: bool | None = None


class SlaPolicyResponse(BaseModel):
    id: str
    name: str
    priority: Literal["P1", "P2", "P3", "P4"]
    response_minutes: int
    resolution_minutes: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class SlaPolicyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    priority: Literal["P1", "P2", "P3", "P4"]
    response_minutes: int = Field(..., ge=1, le=525600)
    resolution_minutes: int = Field(..., ge=1, le=525600)
    is_active: bool = True


class SlaPolicyUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    response_minutes: int | None = Field(default=None, ge=1, le=525600)
    resolution_minutes: int | None = Field(default=None, ge=1, le=525600)
    is_active: bool | None = None


class ServiceCatalogResponse(BaseModel):
    id: str
    service_key: str
    name: str
    description: str
    desk_id: Literal["ops", "support"]
    team_id: str | None = None
    keywords: list[str]
    default_category: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid")


class ServiceCatalogCreateRequest(BaseModel):
    service_key: str = Field(
        ..., min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$"
    )
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    desk_id: Literal["ops", "support"] = "ops"
    team_id: str | None = Field(default=None, max_length=36)
    keywords: list[str] = Field(default_factory=list, max_length=30)
    default_category: str | None = Field(default=None, max_length=80)
    is_active: bool = True

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if any(len(value) > 80 for value in normalized):
            raise ValueError("服务关键词长度不能超过 80")
        return list(dict.fromkeys(normalized))


class ServiceCatalogUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    desk_id: Literal["ops", "support"] | None = None
    team_id: str | None = Field(default=None, max_length=36)
    keywords: list[str] | None = Field(default=None, max_length=30)
    default_category: str | None = Field(default=None, max_length=80)
    is_active: bool | None = None

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        normalized = [value.strip() for value in values if value.strip()]
        if any(len(value) > 80 for value in normalized):
            raise ValueError("服务关键词长度不能超过 80")
        return list(dict.fromkeys(normalized))

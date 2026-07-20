from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from intelliticket_backend.schemas.tickets import DataMode, DeskId


class CatalogItem(BaseModel):
    evidence_id: str
    source_type: str
    source_id: str
    source_name: str
    retrieved_at: str | None = None
    observed_at: str | None = None
    desk_scope: DeskId
    id: str
    title: str
    category: str
    priority_hint: str
    affected_service: str
    description: str
    template_text: str
    quality: str
    data_mode: DataMode
    summary: str

    model_config = ConfigDict(extra="forbid")


class CatalogResponse(BaseModel):
    desk_id: DeskId
    data_mode: DataMode = DataMode.MOCK
    items: list[CatalogItem] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class KnowledgeArticle(BaseModel):
    evidence_id: str
    source_type: str
    source_id: str
    source_name: str
    retrieved_at: str | None = None
    observed_at: str | None = None
    desk_scope: DeskId
    service: str
    article_id: str
    title: str
    actions: list[str]
    quality: str
    data_mode: DataMode
    summary: str
    trace_uri: str | None = None
    quality_reason: str | None = None

    model_config = ConfigDict(extra="forbid")


class KnowledgeResponse(BaseModel):
    desk_id: DeskId
    data_mode: DataMode = DataMode.MOCK
    items: list[KnowledgeArticle] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

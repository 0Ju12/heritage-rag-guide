"""화면 ↔ 서버 요청·응답 형식 (F2013)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    item_id: str
    question: str = Field(default="", max_length=500)
    mode: Literal["qa", "guide", "factcheck"] = "qa"
    history: list[HistoryMessage] = Field(default_factory=list, max_length=20)
    top_k: int | None = Field(default=None, ge=1, le=15)
    search_type: Literal["similarity", "mmr"] | None = None


class SourceOut(BaseModel):
    number: int
    source_type: str
    title: str
    url: str
    excerpt: str


class CollectionOut(BaseModel):
    queries: list[str]
    from_cache: bool
    offline: bool
    indexed_titles: list[str]
    kept: list[dict]
    dropped: list[dict]
    elapsed: float
    message: str


class ChatResponse(BaseModel):
    answer: str
    judgment: str = ""
    sources: list[SourceOut]            # 답변이 실제로 인용한 근거만 (F2008)
    evidence_count: int
    no_citation_notice: str | None = None
    notice: str = ""
    disclaimer: str = ""
    collection: CollectionOut | None = None
    elapsed: float


class ExploreRequest(BaseModel):
    condition: str = Field(max_length=300)


class ExploreResult(BaseModel):
    item_id: str
    name: str
    label: str
    era: str
    region: str
    reason: str
    order_label: str = ""
    category: str = ""
    era_group: str = ""
    image_url: str = ""


class ExploreResponse(BaseModel):
    condition: str
    searched: int
    results: list[ExploreResult]


class LinkOut(BaseModel):
    kind: str                   # official | wiki | youtube | search | map | route
    label: str
    url: str


class ItemOut(BaseModel):
    item_id: str
    name: str
    name_hanja: str = ""
    label: str                  # '001 · 서울 숭례문  (조선 · 서울 중구)'
    order_label: str = ""       # '제1호' / '관리번호 350'
    order_note: str = ""        # '옛 지정번호 제1호 (2021년 11월 지정번호 표기 폐지)'
    category: str = ""          # 대분류
    category_path: list[str] = Field(default_factory=list)
    era: str
    era_group: str = ""
    region: str
    address: str = ""
    designated_date: str = ""
    image_url: str = ""
    khs_url: str
    wiki_url: str = ""
    links: list[LinkOut] = Field(default_factory=list)   # 관련 링크 (근거 아님)


class Facet(BaseModel):
    name: str
    count: int


class FacetsOut(BaseModel):
    total: int
    categories: list[Facet]
    eras: list[Facet]


class HealthOut(BaseModel):
    ready: bool
    has_key: bool
    items_total: int
    items_indexed: int
    docs_indexed: int
    message: str = ""
    title: str
    tagline: str
    examples: dict

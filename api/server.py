"""FastAPI 서버 — HTML/CSS/JS 화면(frontend/)과 분리된 API (F2013).

실행:
    uvicorn api.server:app --port 8000
    → 브라우저에서 http://localhost:8000

    GET  /api/health          준비 상태 (키·색인)
    GET  /api/items?q=        국보 목록
    POST /api/chat            질의응답 · 관람 해설 · 통설 판정
    POST /api/explore         조건 기반 탐색

오류 응답에는 안내 문구만 담는다. 상세는 data/logs/app.log (NF2004).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core.errors import AppError, IndexEmptyError, ItemNotFoundError, MissingKeyError, friendly_message, get_logger
from core.llm import has_api_key
from data_prep.domain import (
    DISCLAIMER, EXAMPLE_CLAIMS, EXAMPLE_CONDITIONS, EXAMPLE_QUESTIONS, RISKY_DOMAIN, SERVICE_TAGLINE,
    SERVICE_TITLE, era_group, item_label, main_category, order_label, order_note, related_links, safe_url,
)
from data_prep.items import ALL, get_catalog
from services.assistant import ask
from services.explore import explore
from vectorstore.store import raw_counts

from .schemas import (
    ChatRequest, ChatResponse, CollectionOut, ExploreRequest, ExploreResponse, ExploreResult, Facet, FacetsOut,
    HealthOut, ItemOut, LinkOut, SourceOut,
)

log = get_logger("heritage_rag.api")
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title=SERVICE_TITLE, version="1.0", docs_url="/api/docs", redoc_url=None)


# ── 오류 → 안내 문구 ─────────────────────────────────────────
@app.exception_handler(AppError)
async def app_error_handler(_req: Request, exc: AppError):
    status = 503 if isinstance(exc, (MissingKeyError, IndexEmptyError)) else 404 if isinstance(exc, ItemNotFoundError) else 400
    return JSONResponse(status_code=status, content={"detail": exc.message, "kind": exc.kind})


@app.exception_handler(RequestValidationError)
async def validation_handler(_req: Request, _exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": "요청 형식이 올바르지 않습니다. 입력을 확인해 주세요.", "kind": "input"})


@app.exception_handler(Exception)
async def unexpected_handler(_req: Request, exc: Exception):
    log.exception("API 처리 실패")
    return JSONResponse(status_code=500, content={"detail": friendly_message(exc), "kind": "error"})


# ── API ──────────────────────────────────────────────────────
def _region(it: dict) -> str:
    return " ".join(x for x in (it.get("sido", ""), it.get("sigungu", "")) if x)


@app.get("/api/health", response_model=HealthOut)
def health() -> HealthOut:
    counts = raw_counts()
    try:
        total = len(get_catalog())
    except IndexEmptyError:
        total = 0
    key = has_api_key()
    msg = ""
    if not key:
        msg = MissingKeyError().message
    elif counts["items"] == 0 or total == 0:
        msg = IndexEmptyError().message
    return HealthOut(ready=key and counts["items"] > 0 and total > 0, has_key=key, items_total=total,
                     items_indexed=counts["items"], docs_indexed=counts["docs"], message=msg,
                     title=SERVICE_TITLE, tagline=SERVICE_TAGLINE,
                     examples={"questions": EXAMPLE_QUESTIONS, "claims": EXAMPLE_CLAIMS, "conditions": EXAMPLE_CONDITIONS})


def item_out(it: dict) -> ItemOut:
    wiki = it.get("ko_wiki_title")
    return ItemOut(
        item_id=it["heritage_id"], name=it["name"], name_hanja=it.get("name_hanja", "") or "", label=item_label(it),
        order_label=order_label(it), order_note=order_note(it), category=main_category(it),
        category_path=list(it.get("category") or []), era=it.get("era", ""), era_group=era_group(it.get("era", "")),
        region=_region(it), address=it.get("address", "") or "", designated_date=it.get("designated_date", "") or "",
        image_url=safe_url(it.get("image_url", "")), khs_url=safe_url(it.get("khs_url", "")),
        wiki_url=f"https://ko.wikipedia.org/wiki/{wiki.replace(' ', '_')}" if wiki else "",
        links=[LinkOut(**link) for link in related_links(it)],
    )


@app.get("/api/items", response_model=list[ItemOut])
def items(q: str = Query(default="", max_length=50), category: str = Query(default=ALL, max_length=30),
          era: str = Query(default=ALL, max_length=30), limit: int = Query(default=500, ge=1, le=1000)) -> list[ItemOut]:
    """옛 지정번호 순. q는 이름·지역 또는 번호('1', '78호'), category·era는 /api/facets 의 값."""
    return [item_out(it) for it in get_catalog().filter(q, category, era)[:limit]]


@app.get("/api/facets", response_model=FacetsOut)
def facets() -> FacetsOut:
    c = get_catalog()
    f = c.facets()
    return FacetsOut(total=len(c), categories=[Facet(name=n, count=k) for n, k in f["categories"]],
                     eras=[Facet(name=n, count=k) for n, k in f["eras"]])


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest) -> ChatResponse:
    history = [m.model_dump() for m in req.history]
    res = await run_in_threadpool(ask, req.item_id, req.question, req.mode, history, req.top_k, req.search_type)
    d = res.to_dict()
    sources = [SourceOut(number=e["number"], source_type=e["source_type"], title=e["title"], url=e["url"],
                         excerpt=e["text"].split("\n", 1)[-1].replace("\n", " ")[:200]) for e in d["cited"]]
    col = d["collection"]
    return ChatResponse(
        answer=d["answer"], judgment=d["judgment"], sources=sources, evidence_count=len(d["evidence"]),
        no_citation_notice=None if sources else "답변에 인용된 근거가 없습니다.",
        notice=res.notice, disclaimer=DISCLAIMER if RISKY_DOMAIN else "",
        collection=CollectionOut(**{k: col[k] for k in CollectionOut.model_fields}) if col else None,
        elapsed=d["elapsed"],
    )


@app.post("/api/explore", response_model=ExploreResponse)
async def explore_endpoint(req: ExploreRequest) -> ExploreResponse:
    hits, n = await run_in_threadpool(explore, req.condition)
    return ExploreResponse(condition=req.condition, searched=n, results=[ExploreResult(**h.to_dict()) for h in hits])


# ── 화면 (정적 파일) ─────────────────────────────────────────
@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

"""질의응답 · 특화 기능 묶음 — 화면(Streamlit, FastAPI)이 공통으로 부르는 진입점.

    ask(item_id, question, mode)
        mode="qa"         일반 질의응답 (F2009)
        mode="guide"      관람 해설 카드 (F2010)
        mode="factcheck"  통설 판정      (F2010)
    처음 들어온 검색어만 외부 문서를 수집하고(F2003~F2005), 매 질문마다 retrieve → generate (F2006~F2008).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

from core.errors import AppError, IndexEmptyError, MissingKeyError, get_logger
from core.llm import has_api_key
from data_prep.collector import CollectionResult, DocumentCollector
from data_prep.domain import GUIDE_REQUEST, SOURCE_ITEM
from data_prep.items import get_catalog
from rag.graph import MODES, RagResult, run_rag
from vectorstore.store import get_store

log = get_logger("heritage_rag.assistant")
Progress = Callable[[str], None]


@dataclass
class AskResult:
    mode: str
    question: str
    collection: CollectionResult | None
    rag: RagResult
    elapsed: float

    @property
    def notice(self) -> str:
        """비정상 상황 안내 (F2012): 위키 연결 실패 / 외부 문서 검색 결과 없음."""
        notes = []
        if self.collection and self.collection.offline:
            notes.append(self.collection.message)
        if not any(e.source_type != SOURCE_ITEM for e in self.rag.evidence):
            notes.append("관련 외부 문서(위키백과·국가유산청)를 찾지 못해 국보 기본 정보만으로 답했습니다. "
                         "질문을 조금 바꾸거나 다른 표현으로 물어보세요.")
        return " ".join(notes)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode, "question": self.question, "elapsed": round(self.elapsed, 2),
            "collection": self.collection.to_dict() if self.collection else None, **self.rag.to_dict(),
        }


def ensure_ready() -> None:
    """키 누락 · 색인 없음을 먼저 확인한다 (F2012)."""
    if not has_api_key():
        raise MissingKeyError()
    if get_store().counts()["items"] == 0:
        raise IndexEmptyError()


@lru_cache(maxsize=1)
def get_collector() -> DocumentCollector:
    return DocumentCollector()


def format_history(messages: list[dict] | None, max_turns: int = 3) -> str:
    """같은 국보의 최근 대화 몇 턴 — 후속 질문의 맥락용 (근거로 쓰지 않는다)."""
    if not messages:
        return ""
    tail = messages[-max_turns * 2:]
    lines = []
    for m in tail:
        who = "사용자" if m.get("role") == "user" else "안내"
        text = (m.get("content") or "").replace("\n", " ")
        lines.append(f"{who}: {text[:300]}")
    return "\n".join(lines)


def ask(item_id: str, question: str = "", mode: str = "qa", history: list[dict] | None = None,
        top_k: int | None = None, search_type: str | None = None, progress: Progress | None = None,
        collect: bool = True) -> AskResult:
    t0 = time.time()
    mode = mode if mode in MODES else "qa"
    question = (question or "").strip()
    if mode == "guide" and not question:
        question = GUIDE_REQUEST
    if not question:
        raise AppError("질문을 입력해 주세요." if mode == "qa" else "판정할 이야기를 입력해 주세요.", "input")
    if len(question) > 500:
        raise AppError("질문이 너무 깁니다. 500자 이내로 줄여 주세요.", "input")

    ensure_ready()
    item = get_catalog().get(item_id)
    say = progress or (lambda _m: None)

    collection = get_collector().collect(item, question, say) if collect else None
    say("근거를 찾고 답변을 만드는 중")
    rag = run_rag(item, question, mode, format_history(history), top_k, search_type)
    total = time.time() - t0
    log.info("ask item=%s mode=%s collect=%.1fs rag=%.1fs total=%.1fs cited=%d/%d",
             item_id, mode, collection.elapsed if collection else 0, rag.elapsed, total,
             len(rag.cited), len(rag.evidence))
    return AskResult(mode=mode, question=question, collection=collection, rag=rag, elapsed=total)

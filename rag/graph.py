"""LangGraph RAG 파이프라인 — retrieve → generate 두 노드 (F2007).

    retrieve : 두 컬렉션 검색 · 병합 · 중복 제거 · 근거 번호 부여 (rag/retriever.py)
    generate : 프롬프트 3으로 근거만 써서 답한다. 모드에 따라 일반 답변 / 관람 해설 / 통설 판정.

그래프 구조 확인: python scripts/check_pipeline.py --graph
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from functools import lru_cache

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from core.llm import chat
from data_prep.domain import FACTCHECK_LABELS

from . import prompts
from .citations import cited_evidence, strip_unknown_citations
from .retriever import Evidence, evidence_block, retrieve

MODES = ("qa", "guide", "factcheck")


class RagState(TypedDict, total=False):
    question: str
    item_id: str
    item_name: str
    mode: str
    history: str
    top_k: int
    search_type: str
    evidence: list[dict]
    answer: str
    judgment: str


def retrieve_node(state: RagState) -> dict:
    ev = retrieve(state["item_id"], state["question"], state.get("top_k"), state.get("search_type"))
    return {"evidence": [e.to_dict() for e in ev]}


_JUDGMENT = re.compile(r"판정\s*[:：]\s*\**\s*(" + "|".join(sorted(map(re.escape, FACTCHECK_LABELS), key=len, reverse=True)) + ")")


def parse_judgment(answer: str) -> str:
    m = _JUDGMENT.search(answer or "")
    return m.group(1) if m else ""


def generate_node(state: RagState) -> dict:
    evidence = [Evidence(**d) for d in state.get("evidence", [])]
    if not evidence:
        return {"answer": prompts.NOT_FOUND, "judgment": "문서로 확인 불가" if state.get("mode") == "factcheck" else ""}
    messages = prompts.answer_generation(state.get("mode", "qa"), state["item_name"], state["question"],
                                         evidence_block(evidence), state.get("history", ""))
    answer = strip_unknown_citations(chat(messages), evidence).strip() or prompts.NOT_FOUND
    judgment = parse_judgment(answer) if state.get("mode") == "factcheck" else ""
    if state.get("mode") == "factcheck" and not judgment:
        judgment = "문서로 확인 불가"
    return {"answer": answer, "judgment": judgment}


@lru_cache(maxsize=1)
def build_graph():
    g = StateGraph(RagState)
    g.add_node("retrieve", retrieve_node)
    g.add_node("generate", generate_node)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", END)
    return g.compile()


@dataclass
class RagResult:
    answer: str
    evidence: list[Evidence]
    cited: list[Evidence] = field(default_factory=list)
    judgment: str = ""
    elapsed: float = 0.0

    def to_dict(self) -> dict:
        return {
            "answer": self.answer, "judgment": self.judgment, "elapsed": round(self.elapsed, 2),
            "evidence": [e.to_dict() for e in self.evidence], "cited": [e.to_dict() for e in self.cited],
        }


def run_rag(item: dict, question: str, mode: str = "qa", history: str = "", top_k: int | None = None,
            search_type: str | None = None) -> RagResult:
    if mode not in MODES:
        mode = "qa"
    t0 = time.time()
    state: RagState = {"question": question, "item_id": item["heritage_id"], "item_name": item["name"],
                       "mode": mode, "history": history}
    if top_k is not None:
        state["top_k"] = int(top_k)
    if search_type:
        state["search_type"] = search_type
    out = build_graph().invoke(state)
    evidence = [Evidence(**d) for d in out.get("evidence", [])]
    answer = out.get("answer", prompts.NOT_FOUND)
    return RagResult(answer=answer, evidence=evidence, cited=cited_evidence(answer, evidence),
                     judgment=out.get("judgment", ""), elapsed=time.time() - t0)


def graph_mermaid() -> str:
    return build_graph().get_graph().draw_mermaid()

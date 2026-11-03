"""검증용 비교 — 유사도 vs MMR (F2014), RAG 사용 전후 (F2015)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.llm import chat
from rag import prompts
from rag.retriever import Evidence, retrieve

from .assistant import ask

UNKNOWN_PATTERNS = ("확인되지 않", "알 수 없", "모르", "정보가 없", "확인할 수 없")


def compare_search(item_id: str, question: str, top_k: int | None = None) -> dict[str, list[Evidence]]:
    return {
        "similarity": retrieve(item_id, question, top_k, "similarity"),
        "mmr": retrieve(item_id, question, top_k, "mmr"),
    }


@dataclass
class RagComparison:
    item_name: str
    question: str
    without_rag: str
    with_rag: str
    cited: list[Evidence]

    @property
    def rag_cites(self) -> int:
        return len(self.cited)

    @staticmethod
    def admits_unknown(text: str) -> bool:
        return any(p in text for p in UNKNOWN_PATTERNS)


def compare_rag(item: dict, question: str) -> RagComparison:
    plain = chat(prompts.no_rag_answer(item["name"], question))
    res = ask(item["heritage_id"], question, "qa")
    return RagComparison(item["name"], question, plain, res.rag.answer, res.rag.cited)


def md_cell(text: str) -> str:
    return re.sub(r"\s*\n\s*", "<br>", (text or "").replace("|", "\\|")).strip()

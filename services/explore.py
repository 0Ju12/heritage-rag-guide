"""조건 기반 항목 탐색 (F2011).

    1) 자연어 조건으로 메타데이터 컬렉션에서 후보를 넉넉히(explore_candidates) 검색
    2) LLM이 후보의 메타데이터와 조건을 대조해 조건을 모두 만족하는 국보만 고름
    3) 후보 목록에 없는 ID는 버린다 → 검색되지 않은 국보가 끼어들 수 없다
"""

from __future__ import annotations

from dataclasses import dataclass

from core.config import get_settings
from core.errors import AppError
from core.llm import chat
from data_prep.domain import era_group, item_label, main_category, order_label
from data_prep.items import get_catalog
from rag import prompts
from rag.parsing import parse_object_list
from vectorstore.store import get_store

from .assistant import ensure_ready


@dataclass
class ExploreHit:
    item: dict
    reason: str

    def to_dict(self) -> dict:
        it = self.item
        return {"item_id": it["heritage_id"], "name": it["name"], "label": item_label(it), "era": it.get("era", ""),
                "region": " ".join(x for x in (it.get("sido", ""), it.get("sigungu", "")) if x), "reason": self.reason,
                "order_label": order_label(it), "category": main_category(it), "era_group": era_group(it.get("era", "")),
                "image_url": it.get("image_url", "") or ""}


def explore(condition: str, k: int | None = None, max_results: int = 10) -> tuple[list[ExploreHit], int]:
    """(조건에 맞는 국보, 검색한 후보 수)"""
    condition = (condition or "").strip()
    if not condition:
        raise AppError("찾고 싶은 조건을 입력해 주세요.", "input")
    ensure_ready()
    k = int(k or get_settings().section("retrieval").get("explore_candidates", 20))
    docs = get_store().search_items(condition, k)
    if not docs:
        return [], 0
    block = "\n\n".join(f"ID: {d.metadata.get('item_id')}\n{d.page_content}" for d in docs)
    picks = parse_object_list(chat(prompts.explore_selection(condition, block, max_results)))

    allowed = {d.metadata.get("item_id") for d in docs}
    catalog = get_catalog()
    hits, seen = [], set()
    for p in picks:
        iid = str(p.get("id", "")).strip()
        if iid in allowed and iid not in seen and iid in catalog.by_id:
            seen.add(iid)
            hits.append(ExploreHit(catalog.by_id[iid], str(p.get("reason", "")).strip()))
    return hits[:max_results], len(docs)

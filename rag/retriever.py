"""근거 검색과 병합 (F2006, F2014).

    1) 선택한 국보의 메타데이터 청크 — 검색 없이 ID로 꺼내 항상 [근거 1]로 넣는다.
    2) 외부 문서 청크 — 질문과의 의미 유사도로 검색하되, item_id 필터로 그 국보 범위만.
       search_type=mmr 이면 후보를 넉넉히(fetch_k) 가져와 다양성 기준으로 top_k개를 고른다.
    3) 메타데이터 컬렉션에서 질문과 관련된 다른 국보를 related_items_k개 (비교 질문 대비).
    4) 병합 → 같은 청크 ID, 같은 본문은 하나만 남김 → 1부터 번호를 붙인다.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass

from langchain_core.documents import Document

from core.config import get_settings
from data_prep.domain import SOURCE_ITEM
from vectorstore.store import HeritageStore, get_store


@dataclass
class Evidence:
    number: int
    chunk_id: str
    source_type: str
    title: str
    url: str
    text: str
    item_id: str
    related_item: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def block(self) -> str:
        return f"[근거 {self.number}] ({self.source_type}) {self.title}\n{self.text}"


def _fingerprint(text: str) -> str:
    norm = re.sub(r"\s+", " ", text).strip()
    return hashlib.md5(norm.encode("utf-8")).hexdigest()


def _to_evidence(doc: Document, number: int) -> Evidence:
    m = doc.metadata or {}
    return Evidence(
        number=number,
        chunk_id=m.get("chunk_id") or doc.id or "",
        source_type=m.get("source_type", ""),
        title=m.get("title", ""),
        url=m.get("url", ""),
        text=doc.page_content,
        item_id=m.get("item_id", ""),
        related_item=m.get("related_item", ""),
    )


def retrieve(item_id: str, question: str, top_k: int | None = None, search_type: str | None = None,
             store: HeritageStore | None = None, related_items_k: int | None = None) -> list[Evidence]:
    cfg = get_settings().section("retrieval")
    store = store or get_store()
    k = int(top_k if top_k is not None else cfg.get("top_k", 5))
    stype = (search_type or cfg.get("search_type", "similarity")).lower()
    rk = int(related_items_k if related_items_k is not None else cfg.get("related_items_k", 0))

    merged: list[Document] = []
    own = store.get_item_chunk(item_id)
    if own is not None:
        merged.append(own)
    merged += store.search_docs(question, item_id, k, stype, int(cfg.get("mmr_fetch_k", 30)),
                                float(cfg.get("mmr_lambda", 0.5)))
    if rk > 0:
        merged += [d for d in store.search_items(question, rk + 1) if (d.metadata or {}).get("item_id") != item_id][:rk]

    out: list[Evidence] = []
    seen_ids, seen_text = set(), set()
    for d in merged:
        cid = (d.metadata or {}).get("chunk_id") or d.id
        fp = _fingerprint(d.page_content)
        if cid in seen_ids or fp in seen_text:
            continue
        seen_ids.add(cid)
        seen_text.add(fp)
        out.append(_to_evidence(d, len(out) + 1))
    return out


def evidence_block(evidence: list[Evidence]) -> str:
    return "\n\n".join(e.block() for e in evidence)


def is_item_meta(e: Evidence) -> bool:
    return e.source_type == SOURCE_ITEM

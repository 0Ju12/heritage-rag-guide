"""청킹 (F2005, F2016).

청크 크기와 중복 길이는 config.yaml의 chunking 에서 출처 종류별로 읽는다.
    위키백과   : 길고 문단이 많은 서술형 → 1,000자 / 200자 중복 (문맥이 끊기지 않게)
    국가유산청 : 짧고 정제된 공식 설명 → 800자 / 100자 중복 (대부분 1~2청크로 통째로 들어감)

청크 ID = "{항목 ID}:{문서 ID}:{순번}"
    여러 국보가 같은 위키 문서(예: '불국사')를 수집해도 국보 ID가 달라 서로 덮어쓰지 않는다.
    같은 국보·같은 문서를 다시 색인하면 같은 ID라 덮어쓰기(업서트)만 일어난다.
"""

from __future__ import annotations

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from core.config import get_settings
from data_prep.domain import SOURCE_OFFICIAL

SEPARATORS = ["\n\n", "\n", ". ", "다. ", " ", ""]


def chunk_config(source_type: str) -> tuple[int, int]:
    cfg = get_settings().section("chunking")
    key = "official" if source_type == SOURCE_OFFICIAL else "wiki"
    c = cfg.get(key, {"chunk_size": 1000, "chunk_overlap": 200})
    return int(c["chunk_size"]), int(c["chunk_overlap"])


def splitter_for(source_type: str, chunk_size: int | None = None, chunk_overlap: int | None = None):
    size, overlap = chunk_config(source_type)
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size or size,
        chunk_overlap=chunk_overlap if chunk_overlap is not None else overlap,
        separators=SEPARATORS,
    )


def chunk_id(item_id: str, page_id: str, seq: int) -> str:
    return f"{item_id}:{page_id}:{seq}"


def split_source_doc(doc: dict, chunk_size: int | None = None, chunk_overlap: int | None = None) -> list[tuple[str, Document]]:
    """수집 문서 1건 → [(청크 ID, Document)].

    doc 필드: item_id, related_item, title, url, page_id, text, source_type, search_query, collected_at
    """
    source_type = doc.get("source_type", "")
    pieces = splitter_for(source_type, chunk_size, chunk_overlap).split_text(doc.get("text", "") or "")
    out = []
    for seq, piece in enumerate(pieces):
        cid = chunk_id(doc["item_id"], str(doc["page_id"]), seq)
        meta = {
            "chunk_id": cid,
            "item_id": doc["item_id"],
            "related_item": doc.get("related_item", ""),
            "title": doc.get("title", ""),
            "url": doc.get("url", ""),
            "page_id": str(doc["page_id"]),
            "source_type": source_type,
            "search_query": doc.get("search_query", ""),
            "collected_at": doc.get("collected_at", ""),
            "chunk_index": seq,
        }
        # 문서 제목을 앞에 붙여 두면 짧은 조각도 무엇에 대한 것인지 임베딩과 LLM이 안다
        out.append((cid, Document(page_content=f"[{doc.get('title', '')}]\n{piece}", metadata=meta)))
    return out

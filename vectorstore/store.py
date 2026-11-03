"""Vector DB (ChromaDB) — 컬렉션 두 개.

    heritage_items (RAG 1)  국보 1건 = 청크 1개, 청크 ID = 국보 ID          (F2002)
    heritage_docs  (RAG 2)  위키백과 + 국가유산청 설명문 청크                (F2005, F2016)

두 컬렉션 모두 업서트라 같은 작업을 다시 실행해도 건수가 늘지 않는다.
"""

from __future__ import annotations

import threading

from langchain_chroma import Chroma
from langchain_core.documents import Document

from core.config import get_settings
from core.llm import get_embeddings
from data_prep.domain import SOURCE_ITEM, index_text

from .chunking import split_source_doc

_lock = threading.RLock()


def chroma_client(path: str):
    """같은 폴더는 한 프로세스에서 같은 설정으로 열어야 한다. 익명 사용 통계 전송은 끈다."""
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    return chromadb.PersistentClient(path=path, settings=ChromaSettings(anonymized_telemetry=False))


def _scalar(v) -> str | int | float | bool:
    """Chroma 메타데이터는 스칼라만 받는다."""
    if v is None:
        return ""
    if isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (list, tuple)):
        return " > ".join(str(x) for x in v if x)
    return str(v)


class HeritageStore:
    def __init__(self, embeddings=None, persist_dir: str | None = None):
        s = get_settings()
        cfg = s.section("vectorstore")
        emb = embeddings or get_embeddings()
        path = persist_dir or str(s.chroma_dir)
        client = chroma_client(path)
        self.items = Chroma(collection_name=cfg["items_collection"], embedding_function=emb, client=client)
        self.docs = Chroma(collection_name=cfg["docs_collection"], embedding_function=emb, client=client)

    # ── 현황 ─────────────────────────────────────────────
    def counts(self) -> dict[str, int]:
        return {"items": self.items._collection.count(), "docs": self.docs._collection.count()}

    # ── RAG 1: 국보 메타데이터 ────────────────────────────
    def index_items(self, items: list[dict], batch: int = 64) -> int:
        """국보 1건 = 청크 1개. ID를 국보 ID로 고정해 재실행해도 덮어쓰기만 일어난다."""
        with _lock:
            for s in range(0, len(items), batch):
                part = items[s:s + batch]
                docs = [
                    Document(page_content=index_text(it), metadata={
                        "chunk_id": it["heritage_id"], "item_id": it["heritage_id"], "title": it["name"],
                        "url": it.get("khs_url", ""), "source_type": SOURCE_ITEM,
                        "era": _scalar(it.get("era")), "sido": _scalar(it.get("sido")),
                        "category": _scalar(it.get("category")),
                    })
                    for it in part
                ]
                self.items.add_documents(docs, ids=[it["heritage_id"] for it in part])
        return self.items._collection.count()

    def get_item_chunk(self, item_id: str) -> Document | None:
        got = self.items.get(ids=[item_id])
        if not got["ids"]:
            return None
        return Document(id=got["ids"][0], page_content=got["documents"][0], metadata=got["metadatas"][0])

    def search_items(self, query: str, k: int) -> list[Document]:
        if k <= 0 or self.items._collection.count() == 0:
            return []
        return self.items.similarity_search(query, k=k)

    # ── RAG 2: 외부 문서 ─────────────────────────────────
    def index_documents(self, source_docs: list[dict], chunk_size: int | None = None,
                        chunk_overlap: int | None = None) -> list[str]:
        ids: list[str] = []
        docs: list[Document] = []
        for sd in source_docs:
            for cid, d in split_source_doc(sd, chunk_size, chunk_overlap):
                ids.append(cid)
                docs.append(d)
        with _lock:
            for s in range(0, len(docs), 64):
                self.docs.add_documents(docs[s:s + 64], ids=ids[s:s + 64])
        return ids

    def delete_docs_where(self, where: dict) -> int:
        with _lock:
            got = self.docs.get(where=where)
            if got["ids"]:
                self.docs.delete(ids=got["ids"])
            return len(got["ids"])

    def has_doc(self, item_id: str, page_id: str) -> bool:
        got = self.docs.get(ids=[f"{item_id}:{page_id}:0"])
        return bool(got["ids"])

    def search_docs(self, query: str, item_id: str, k: int, search_type: str = "similarity",
                    fetch_k: int = 30, lambda_mult: float = 0.5) -> list[Document]:
        """선택한 국보로 범위를 좁혀(item_id 필터) 검색한다 — 다른 국보의 문서가 근거에 섞이지 않는다."""
        if k <= 0:
            return []
        flt = {"item_id": item_id}
        if search_type == "mmr":
            return self.docs.max_marginal_relevance_search(query, k=k, fetch_k=max(fetch_k, k), lambda_mult=lambda_mult, filter=flt)
        return self.docs.similarity_search(query, k=k, filter=flt)


def raw_counts() -> dict[str, int]:
    """임베딩(API 키) 없이 컬렉션 건수만 센다 — 키가 없어도 화면에 색인 현황을 보여 주기 위해."""
    s = get_settings()
    cfg = s.section("vectorstore")
    out = {"items": 0, "docs": 0}
    if not s.chroma_dir.exists():
        return out
    client = chroma_client(str(s.chroma_dir))
    for key, name in (("items", cfg["items_collection"]), ("docs", cfg["docs_collection"])):
        try:
            out[key] = client.get_collection(name).count()
        except Exception:  # 컬렉션이 아직 없음
            out[key] = 0
    return out


_store: HeritageStore | None = None


def get_store() -> HeritageStore:
    global _store
    with _lock:
        if _store is None:
            _store = HeritageStore()
        return _store


def reset_store() -> None:
    global _store
    with _lock:
        _store = None

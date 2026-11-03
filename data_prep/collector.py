"""외부 문서 수집 — 검색어 추출(프롬프트 1) → 검색 → 선별(프롬프트 2) → 본문 수집 → 청킹·색인.

    F2003  도메인 전문가 프롬프트로 검색어 추출. 국보 자체 문서 검색어는 항상 첫 번째로 포함.
    F2004  검색 후보 중 선별 프롬프트로 고른 문서만 본문을 받아 색인. 국보 자체 문서는
           선별·길이 등 어떤 제외 규칙보다 우선해 항상 색인. 원문 URL과 제목을 함께 저장.
    NF2002 이미 처리한 검색어는 다시 수집하지 않는다 (data/wiki_manifest.json).
    대비책  위키 호출이 막히면 data/wiki/ 에 저장된 문서 묶음을 읽어 수집 단계를 대신한다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from core.config import get_settings
from core.errors import get_logger
from core.llm import chat
from rag import prompts
from rag.parsing import parse_int_list, parse_string_list
from vectorstore.store import HeritageStore, get_store

from .docs_store import Manifest, load_saved_docs, normalize_query, save_wiki_doc
from .domain import SOURCE_WIKI, index_text, own_doc_query
from .http_client import ExternalAPIError
from .wiki_api import WikiClient, get_wiki

log = get_logger("heritage_rag.collector")
Progress = Callable[[str], None]


@dataclass
class Candidate:
    title: str
    page_id: str
    snippet: str
    query: str
    decision: str = "pending"  # own | selected | rejected | short | missing | already
    note: str = ""


@dataclass
class CollectionResult:
    item_id: str
    queries: list[str] = field(default_factory=list)
    new_queries: list[str] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    indexed_titles: list[str] = field(default_factory=list)
    chunks_added: int = 0
    from_cache: bool = False
    offline: bool = False
    elapsed: float = 0.0
    message: str = ""

    @property
    def kept(self) -> list[Candidate]:
        return [c for c in self.candidates if c.decision in ("own", "selected")]

    @property
    def dropped(self) -> list[Candidate]:
        return [c for c in self.candidates if c.decision in ("rejected", "short", "missing")]

    def to_dict(self) -> dict:
        return {
            "queries": self.queries, "new_queries": self.new_queries, "from_cache": self.from_cache,
            "offline": self.offline, "indexed_titles": self.indexed_titles, "chunks_added": self.chunks_added,
            "kept": [{"title": c.title, "decision": c.decision, "query": c.query} for c in self.kept],
            "dropped": [{"title": c.title, "decision": c.decision, "query": c.query, "note": c.note} for c in self.dropped],
            "elapsed": round(self.elapsed, 2), "message": self.message,
        }


class DocumentCollector:
    def __init__(self, wiki: WikiClient | None = None, store: HeritageStore | None = None,
                 manifest: Manifest | None = None):
        self.wiki = wiki or get_wiki()
        self.store = store or get_store()
        self.manifest = manifest or Manifest()
        self.cfg = get_settings().section("collection")

    # ── 프롬프트 1 ───────────────────────────────────────
    def extract_queries(self, item: dict, question: str) -> list[str]:
        own = own_doc_query(item)
        n = int(self.cfg.get("max_queries", 4))
        raw = chat(prompts.query_extraction(index_text(item), own, question, n))
        queries = parse_string_list(raw)  # 형식이 깨지면 [] → 자체 문서 검색어만 쓴다
        if not queries:
            log.warning("검색어 추출 결과 해석 실패: %r", raw[:200])
        out, seen = [own], {normalize_query(own)}
        for q in queries:
            key = normalize_query(q)
            if key and key not in seen and len(q) <= 40:
                seen.add(key)
                out.append(q.strip())
        return out[:n]

    # ── 프롬프트 2 ───────────────────────────────────────
    def select(self, item: dict, question: str, cands: list[Candidate]) -> set[int]:
        if not cands:
            return set()
        m = int(self.cfg.get("max_selected", 5))
        raw = chat(prompts.candidate_selection(item["name"], question,
                                               [{"title": c.title, "snippet": c.snippet} for c in cands], m))
        nums = parse_int_list(raw)
        if nums is None:  # 형식이 깨졌으면 국보 이름이 제목에 들어간 후보만 남긴다
            log.warning("선별 결과 해석 실패: %r", raw[:200])
            key = item["name"].split()[-1]
            return {i for i, c in enumerate(cands, 1) if key in c.title}
        valid = [n for n in dict.fromkeys(nums) if 1 <= n <= len(cands)]
        return set(valid[:m])

    # ── 수집 ─────────────────────────────────────────────
    def collect(self, item: dict, question: str, progress: Progress | None = None) -> CollectionResult:
        t0 = time.time()
        say = progress or (lambda _m: None)
        item_id = item["heritage_id"]
        res = CollectionResult(item_id=item_id)

        cached = self.manifest.cached_queries(item_id, question)
        if cached:
            res.queries = cached  # 같은 질문 → 그때 고른 검색어 그대로 (NF2002)
        else:
            say("검색어를 고르는 중 (프롬프트 1)")
            res.queries = self.extract_queries(item, question)
        res.new_queries = [q for q in res.queries if not self.manifest.has_query(item_id, q)]
        if not res.new_queries and self.manifest.own_done(item_id):
            res.from_cache = True
            res.message = "이미 수집한 검색어라 다시 수집하지 않았습니다."
            res.elapsed = time.time() - t0
            return res

        try:
            docs_to_index = self._gather(item, question, res, say)
            if docs_to_index:
                say(f"문서 {len(docs_to_index)}건을 청킹·색인하는 중")
                ids = self.store.index_documents(docs_to_index)
                res.chunks_added = len(ids)
                for d in docs_to_index:
                    save_wiki_doc(d)
                    self.manifest.add_indexed(item_id, d["page_id"], d["title"])
                    res.indexed_titles.append(d["title"])
        except BaseException as e:
            # 수집·색인이 끝나지 않았는데 '처리함' 표시가 남으면 다음부터 영영 다시 받지 않는다.
            # 이번 호출에서 메모리에 쌓인 이력은 버리고 디스크 상태로 되돌린다.
            self.manifest.load()
            if isinstance(e, ExternalAPIError):
                log.exception("위키 호출 실패 — 저장된 문서 묶음으로 대체")
                return self._offline(item, res, t0, say)
            raise

        for q in res.new_queries:
            self.manifest.record_query(
                item_id, q,
                [c.title for c in res.candidates if c.query == q and c.decision in ("own", "selected")],
                [c.title for c in res.candidates if c.query == q and c.decision in ("rejected", "short", "missing")],
            )
        self.manifest.record_question(item_id, question, res.queries)
        self.manifest.save()
        res.elapsed = time.time() - t0
        res.message = f"새 문서 {len(res.indexed_titles)}건 색인" if res.indexed_titles else "새로 색인할 문서가 없었습니다."
        return res

    def _gather(self, item: dict, question: str, res: CollectionResult, say: Progress) -> list[dict]:
        item_id = item["heritage_id"]
        own_q = own_doc_query(item)
        indexed = set(self.manifest.indexed(item_id))
        docs: list[dict] = []
        seen_titles = set(self.manifest.indexed(item_id).values())

        # ① 국보 자체 문서 — 선별·길이 규칙보다 우선해 항상 색인
        if not self.manifest.own_done(item_id):
            say(f"'{own_q}' 문서를 가져오는 중")
            page = self._find_own_page(item)
            if page:
                res.candidates.append(Candidate(page["title"], page["page_id"], "", own_q, "own", "국보 자체 문서"))
                seen_titles.add(page["title"])
                if page["page_id"] not in indexed:
                    docs.append(self._doc(item, page, own_q))
                    indexed.add(page["page_id"])
            self.manifest.mark_own(item_id, page["title"] if page else None)

        # ② 관련 문서 후보 (본문은 아직 받지 않는다)
        cands: list[Candidate] = []
        limit = int(self.cfg.get("search_limit", 5))
        for q in res.new_queries:
            if normalize_query(q) == normalize_query(own_q):
                continue
            say(f"위키백과에서 '{q}' 검색")
            for h in self.wiki.search(q, limit=limit):
                if h["title"] in seen_titles:
                    continue
                seen_titles.add(h["title"])
                cands.append(Candidate(h["title"], h["page_id"], h["snippet"], q))

        # ③ 프롬프트 2로 선별 → 고른 문서만 본문 수집
        if cands:
            say(f"후보 {len(cands)}건 중 색인할 문서를 고르는 중 (프롬프트 2)")
            chosen = self.select(item, question, cands)
            min_chars = int(self.cfg.get("min_doc_chars", 300))
            for i, c in enumerate(cands, 1):
                if i not in chosen:
                    c.decision, c.note = "rejected", "선별 프롬프트에서 제외"
                    continue
                if c.page_id in indexed:
                    c.decision, c.note = "already", "이미 색인됨"
                    continue
                say(f"'{c.title}' 본문을 가져오는 중")
                page = self.wiki.fetch(c.title)
                if page is None:
                    c.decision, c.note = "missing", "문서를 가져오지 못함"
                elif len(page["text"]) < min_chars:
                    c.decision, c.note = "short", f"본문 {len(page['text'])}자 — 너무 짧음"
                else:
                    c.decision = "selected"
                    docs.append(self._doc(item, page, c.query))
                    indexed.add(page["page_id"])
        res.candidates.extend(cands)
        return docs

    def _find_own_page(self, item: dict) -> dict | None:
        """국보 자체 문서: 연결된 위키 제목 → 없으면 이름으로 검색해 끝 단어가 제목에 든 첫 문서."""
        from .collect_items import pick_search_hit, region_words

        own_q = own_doc_query(item)
        page = self.wiki.fetch(own_q)
        if page is None:  # 일반명사 문서('석굴', '삼층석탑')를 자체 문서로 잡지 않도록 같은 판정 규칙을 쓴다
            hit = pick_search_hit(item["name"], [h["title"] for h in self.wiki.search(item["name"], limit=5)],
                                  region_words(item))
            page = self.wiki.fetch(hit) if hit else None
        return page if page and page["text"].strip() else None

    def collect_own(self, item: dict) -> str | None:
        """국보 자체 문서만 미리 수집·색인한다 (scripts/prefetch_wiki.py). 프롬프트를 쓰지 않는다."""
        item_id = item["heritage_id"]
        if self.manifest.own_done(item_id):
            return self.manifest.data.get(item_id, {}).get("own_doc")
        page = self._find_own_page(item)
        if page and page["page_id"] not in self.manifest.indexed(item_id):
            doc = self._doc(item, page, own_doc_query(item))
            self.store.index_documents([doc])
            save_wiki_doc(doc)
            self.manifest.add_indexed(item_id, page["page_id"], page["title"])
        self.manifest.mark_own(item_id, page["title"] if page else None)
        self.manifest.save()
        return page["title"] if page else None

    def _doc(self, item: dict, page: dict, query: str) -> dict:
        return {
            "item_id": item["heritage_id"], "related_item": item["name"], "title": page["title"],
            "url": page["url"], "page_id": str(page["page_id"]), "text": page["text"],
            "source_type": SOURCE_WIKI, "search_query": query, "collected_at": date.today().isoformat(),
        }

    def _offline(self, item: dict, res: CollectionResult, t0: float, say: Progress) -> CollectionResult:
        res.offline = True
        res.candidates, res.indexed_titles, res.chunks_added = [], [], 0  # 실패한 시도의 기록은 보여 주지 않는다
        saved =[d for d in load_saved_docs(item["heritage_id"]) if not self.store.has_doc(d["item_id"], d["page_id"])]
        if saved:
            say(f"위키백과에 연결하지 못해 저장된 문서 {len(saved)}건으로 대신합니다")
            res.chunks_added = len(self.store.index_documents(saved))
            res.indexed_titles = [d["title"] for d in saved]
            for d in saved:
                self.manifest.add_indexed(d["item_id"], d["page_id"], d["title"])
            self.manifest.save()
        res.message = "위키백과에 연결하지 못해 이미 색인된 문서와 저장된 문서로 답합니다."
        res.elapsed = time.time() - t0
        return res

"""필수 기능 F2001~F2008, F2010~F2011, F2014, NF2002 — 외부 호출 없이 검증."""

from __future__ import annotations


def test_f2001_index_text_has_all_attributes(env):
    from data_prep.domain import index_text
    from data_prep.items import get_catalog

    items = get_catalog().items
    assert len(items) == 4
    text = index_text(items[0])
    for word in ("서울 숭례문", "崇禮門", "국보", "성곽", "조선 태조 7년", "서울 중구", "1962-12-20", "개요"):
        assert word in text, word
    # 빈 필드는 줄째 빠진다 (반가사유상은 한자명 없음)
    assert "()" not in index_text(items[3])


def test_f2002_index_is_idempotent(env):
    from data_prep.items import get_catalog
    from vectorstore.store import get_store

    store = get_store()
    items = get_catalog().items
    assert store.index_items(items) == len(items)
    assert store.index_items(items) == len(items)  # 두 번 실행해도 늘지 않음
    assert store.get_item_chunk(items[0]["heritage_id"]).metadata["source_type"] == "국보 메타데이터"


def test_f2005_chunk_ids_and_config(env):
    from data_prep.docs_store import load_all_official_docs
    from vectorstore.chunking import split_source_doc

    doc = {"item_id": "A", "page_id": "123", "title": "불국사", "text": "가나다라마바사 " * 400,
           "source_type": "위키백과", "url": "u"}
    default = split_source_doc(doc)
    small = split_source_doc(doc, chunk_size=300, chunk_overlap=50)
    assert len(small) > len(default) > 1
    assert default[0][0] == "A:123:0" and default[1][0] == "A:123:1"
    # 같은 문서를 다른 국보가 수집해도 ID가 겹치지 않는다
    other = split_source_doc({**doc, "item_id": "B"})
    assert {i for i, _ in default}.isdisjoint({i for i, _ in other})
    meta = default[0][1].metadata
    for key in ("title", "url", "item_id", "related_item", "source_type", "page_id", "chunk_id"):
        assert key in meta
    assert load_all_official_docs()[0]["source_type"] == "국가유산청"


def test_f2003_f2004_collect_select_and_cache(indexed):
    from data_prep.items import get_catalog
    from services.assistant import get_collector

    item = get_catalog().get("kh_11_00010000_11")
    col = get_collector()
    res = col.collect(item, "2008년 화재 뒤 복원하면서 달라진 점은?")
    assert res.queries[0] == "숭례문"                         # 자체 문서 검색어가 첫 번째
    assert "숭례문 방화 사건" in res.queries
    own = [c for c in res.candidates if c.decision == "own"]
    assert own and own[0].title == "숭례문"                   # 자체 문서는 항상 색인
    assert res.kept and res.dropped                            # 색인된 문서와 버려진 문서가 구분됨
    assert res.chunks_added > 0 and "숭례문" in res.indexed_titles
    calls_before = len(indexed.wiki.calls)
    again = col.collect(item, "2008년 화재 뒤 복원하면서 달라진 점은?")
    assert again.from_cache and len(indexed.wiki.calls) == calls_before   # NF2002: 다시 수집하지 않음


def test_f2004_own_doc_beats_selection_and_length(indexed):
    """선별 프롬프트가 아무것도 고르지 않고, 자체 문서가 짧아도 자체 문서는 색인된다."""
    from data_prep.items import get_catalog
    from services.assistant import get_collector

    indexed.chat.selection = "[]"
    indexed.wiki.pages["다보탑"] = "짧은 자체 문서."
    item = get_catalog().get("kh_11_00200000_37")
    res = get_collector().collect(item, "돌사자는 몇 마리였어?")
    assert [c.title for c in res.candidates if c.decision == "own"] == ["다보탑"]
    assert "다보탑" in res.indexed_titles
    assert all(c.decision == "rejected" for c in res.candidates if c.decision != "own")


def test_f2004_offline_bundle(indexed):
    """위키가 막히면 data/wiki/에 저장된 문서 묶음으로 대신한다."""
    import json

    from data_prep.items import get_catalog
    from services.assistant import get_collector

    item = get_catalog().get("kh_11_00700000_11")
    wiki_dir = indexed.data / "wiki"
    wiki_dir.mkdir(exist_ok=True)
    (wiki_dir / "kh_11_00700000_11_훈민정음.json").write_text(json.dumps({
        "item_id": item["heritage_id"], "related_item": "훈민정음", "title": "훈민정음", "url": "u", "page_id": "777",
        "text": "훈민정음 해례본은 간송미술관에 있다. " * 50, "source_type": "위키백과", "search_query": "훈민정음",
        "collected_at": "2026-09-01"}, ensure_ascii=False), encoding="utf-8")
    indexed.wiki.fail = True
    res = get_collector().collect(item, "해례본은 어디 있어?")
    assert res.offline and res.indexed_titles == ["훈민정음"] and res.chunks_added > 0


def test_f2006_retrieve_merge_and_topk(indexed):
    from data_prep.items import get_catalog
    from rag.retriever import retrieve
    from services.assistant import get_collector

    item = get_catalog().get("kh_11_00010000_11")
    get_collector().collect(item, "화재 뒤 복원")
    ev3 = retrieve(item["heritage_id"], "화재 뒤 복원", top_k=3, related_items_k=0)
    ev6 = retrieve(item["heritage_id"], "화재 뒤 복원", top_k=6, related_items_k=0)
    assert ev3[0].source_type == "국보 메타데이터" and ev3[0].item_id == item["heritage_id"]  # 항상 포함
    assert len(ev3) == 4 and len(ev6) > len(ev3)                                           # Top-k 반영
    assert [e.number for e in ev6] == list(range(1, len(ev6) + 1))
    assert len({e.chunk_id for e in ev6}) == len(ev6)                                      # 중복 제거
    assert all(e.item_id == item["heritage_id"] for e in ev6)                              # 다른 국보 문서 없음
    assert {"위키백과", "국가유산청"} <= {e.source_type for e in ev6}                       # 출처 종류 구분
    with_related = retrieve(item["heritage_id"], "화재 뒤 복원", top_k=3, related_items_k=2)
    assert sum(e.source_type == "국보 메타데이터" for e in with_related) == 3


def test_f2014_mmr_runs_and_can_differ(indexed):
    from data_prep.items import get_catalog
    from services.assistant import get_collector
    from services.evaluation import compare_search

    item = get_catalog().get("kh_11_00010000_11")
    get_collector().collect(item, "화재 뒤 복원")
    out = compare_search(item["heritage_id"], "화재 뒤 복원", top_k=4)
    assert out["similarity"] and out["mmr"]
    assert out["similarity"][0].source_type == out["mmr"][0].source_type == "국보 메타데이터"


def test_f2007_f2008_graph_and_citations(indexed):
    from rag.graph import build_graph, graph_mermaid
    from services.assistant import ask

    nodes = set(build_graph().get_graph().nodes)
    assert {"retrieve", "generate"} <= nodes and len(nodes - {"__start__", "__end__"}) == 2
    assert "retrieve --> generate" in graph_mermaid()

    res = ask("kh_11_00010000_11", "2008년 화재 뒤 어떻게 됐어?")
    assert "[근거 99]" not in res.rag.answer and "99" not in res.rag.answer    # 없는 번호는 지움
    assert [e.number for e in res.rag.cited] == sorted(e.number for e in res.rag.cited)
    assert {e.number for e in res.rag.cited} <= {e.number for e in res.rag.evidence}
    assert len(res.rag.cited) == 2 and res.rag.cited[0].number == 1
    assert res.collection and res.collection.indexed_titles


def test_f2007_no_citation_case(indexed):
    from rag.prompts import NOT_FOUND
    from services.assistant import ask

    indexed.chat.answer_override = NOT_FOUND
    res = ask("kh_11_00010000_11", "숭례문 관리 직원은 몇 명이야?")
    assert res.rag.answer == NOT_FOUND and res.rag.cited == []


def test_f2010_guide_and_factcheck(indexed):
    from services.assistant import ask

    guide = ask("kh_11_00010000_11", mode="guide")
    assert "### 한눈에 보기" in guide.rag.answer and guide.rag.cited
    fc = ask("kh_11_00010000_11", "숭례문은 전부 새로 지은 것이다", mode="factcheck")
    assert fc.rag.judgment == "사실과 다름" and fc.rag.cited


def test_f2011_explore_only_returns_searched_and_matching(indexed):
    from services.explore import explore

    hits, n = explore("통일신라 경주 석탑")
    assert n == 4
    assert [h.item["heritage_id"] for h in hits] == ["kh_11_00200000_37"]   # 가짜 ID는 버려짐


def test_f2012_errors(env, monkeypatch):
    import pytest

    from core import llm
    from core.errors import AppError, IndexEmptyError, MissingKeyError, friendly_message
    from services.assistant import ask

    with pytest.raises(IndexEmptyError):        # 색인 없음
        ask("kh_11_00010000_11", "질문")
    llm.set_overrides()                          # 키 없음
    with pytest.raises(MissingKeyError):
        ask("kh_11_00010000_11", "질문")
    with pytest.raises(AppError):
        ask("kh_11_00010000_11", "   ")
    msg = friendly_message(RuntimeError("secret sk-123 Traceback"))
    assert "sk-123" not in msg and "Traceback" not in msg


def test_citation_parsing_variants():
    from rag.citations import cited_numbers

    text = "가 [근거 1]. 나 [근거 2, 4]. 다 [근거3][근거 5·6]. 라 [근거 7~8]."
    assert cited_numbers(text) == [1, 2, 4, 3, 5, 6, 7, 8]


def test_json_parsing_robust():
    from rag.parsing import parse_int_list, parse_object_list, parse_string_list

    assert parse_string_list('검색어는 다음과 같습니다:\n```json\n["숭례문", "한양도성"]\n```') == ["숭례문", "한양도성"]
    assert parse_int_list("[]") == [] and parse_int_list("고를 것 없음") is None
    assert parse_int_list('["1", 3]') == [1, 3]
    assert parse_object_list('[{"id": "a", "reason": "x [y]"}]') == [{"id": "a", "reason": "x [y]"}]

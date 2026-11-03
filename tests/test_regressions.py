"""회귀 테스트 — 코드 재점검에서 찾은 버그가 다시 생기지 않게."""

from __future__ import annotations

import pytest
def test_own_doc_not_lost_after_failure(indexed):
    from data_prep.items import get_catalog
    from data_prep.http_client import ExternalAPIError
    from services.assistant import get_collector
    col = get_collector()
    item = get_catalog().get("kh_11_00010000_11")
    real_search = indexed.wiki.search
    def broken(q, limit=5):
        raise ExternalAPIError("down after own doc")
    indexed.wiki.search = broken             # 자체 문서는 받았지만 관련 문서 검색에서 실패
    col.collect(item, "화재 뒤 복원")
    assert not col.manifest.own_done(item["heritage_id"])
    indexed.wiki.search = real_search
    res = col.collect(item, "화재 뒤 복원")
    assert [c.title for c in res.candidates if c.decision == "own"] == ["숭례문"]

def test_llm_failure_does_not_poison(indexed):
    from data_prep.items import get_catalog
    from services.assistant import get_collector
    col = get_collector()
    item = get_catalog().get("kh_11_00010000_11")
    orig = indexed.chat.selection
    indexed.chat.selection = None
    class Boom(Exception): pass
    real = indexed.chat._answer
    def answer(task, s, h):
        if task == "후보 문서 선별": raise Boom()
        return real(task, s, h)
    indexed.chat._answer = answer
    with pytest.raises(Boom):
        col.collect(item, "화재 뒤 복원")
    assert not col.manifest.own_done(item["heritage_id"])
    indexed.chat._answer = real; indexed.chat.selection = orig
    res = col.collect(item, "화재 뒤 복원")
    assert [c.title for c in res.candidates if c.decision == "own"] == ["숭례문"]


def test_wiki_linking_avoids_generic_pages(env):
    from data_prep.collect_items import link_wiki_titles
    from tests.fakes import FakeWiki
    pages = {"석굴": "x", "삼층석탑": "x", "불국사": "x", "다보탑": "x", "석굴암": "x",
             "불국사 삼층석탑": "x", "경주 감은사지 동·서 삼층석탑": "x"}
    w = FakeWiki(pages)
    def search(q, limit=5):
        order = {"경주 석굴암 석굴": ["석굴", "석굴암", "불국사"],
                 "경주 불국사 다보탑": ["불국사", "다보탑"],
                 "경주 황룡사지 구층목탑 터": ["불국사", "삼층석탑"]}
        return [{"page_id": "1", "title": t, "snippet": ""} for t in order.get(q, [])]
    w.search = search
    names = ["경주 석굴암 석굴", "경주 불국사 다보탑", "경주 불국사 삼층석탑", "경주 황룡사지 구층목탑 터"]
    got = link_wiki_titles(w, names, log=lambda m: None, regions={n: {"경주시", "경주", "경북"} for n in names})
    assert got["경주 석굴암 석굴"][0] == "석굴암"
    assert got["경주 불국사 다보탑"][0] == "다보탑"
    assert got["경주 불국사 삼층석탑"][0] == "불국사 삼층석탑"
    assert "경주 황룡사지 구층목탑 터" not in got   # 맞는 문서가 없으면 연결하지 않는다


def test_same_question_no_recollect_even_if_llm_varies(indexed):
    import itertools
    from data_prep.items import get_catalog
    from services.assistant import get_collector
    variants = itertools.cycle([["숭례문 방화 사건"], ["숭례문 화재"], ["한양도성 남문"]])
    real = indexed.chat._answer
    def answer(task, s, h):
        if task == "검색어 추출":
            indexed.chat.query_extra = next(variants)
        return real(task, s, h)
    indexed.chat._answer = answer
    col = get_collector()
    item = get_catalog().get("kh_11_00010000_11")
    col.collect(item, "2008년 화재 뒤 어떻게 됐어?")
    n_calls = len(indexed.wiki.calls)
    again = col.collect(item, "  2008년 화재 뒤 어떻게 됐어? ")
    assert again.from_cache and len(indexed.wiki.calls) == n_calls


def test_notice_when_no_external_docs(indexed):
    from services.assistant import ask
    indexed.wiki.pages = {}                    # 위키에서 아무것도 못 찾음, 국가유산청 설명도 없는 국보
    res = ask("kh_11_00700000_11", "해례본은 어디 있어?")
    assert "찾지 못해" in res.notice
    ok = ask("kh_11_00010000_11", "화재")      # 국가유산청 설명이 있는 국보는 안내 없음
    assert ok.notice == ""


def test_designation_number_rules():
    from data_prep.domain import designation_number, era_group, item_label, order_label, order_note, sort_key

    assert designation_number({"heritage_id": "kh_11_00010000_11"}) == (1, 0)
    assert order_label({"heritage_id": "kh_11_00780002_11"}) == "제78-2호"                       # 부번호
    post = {"heritage_id": "kh_11_03500000_37", "designated_date": "2023-05-01"}
    assert order_label(post) == "관리번호 350" and "폐지 이후" in order_note(post)               # 폐지 뒤 지정
    for bad in ("kh_wiki_숭례문", "kh_11_ABC_11", "kh_11_00000000_11", "", "x"):
        assert designation_number({"heritage_id": bad}) is None and order_label({"heritage_id": bad}) == ""
    assert item_label({"heritage_id": "kh_wiki_숭례문", "name": "숭례문"}) == "숭례문"            # 번호 없으면 번호 없이
    items = [{"heritage_id": "kh_wiki_가", "name": "가"}, {"heritage_id": "kh_11_00100000_11", "name": "나"},
             {"heritage_id": "kh_11_00020000_11", "name": "다"}]
    assert [i["name"] for i in sorted(items, key=sort_key)] == ["다", "나", "가"]                  # 번호 없는 것은 뒤
    assert era_group("통일신라 경덕왕 10년") == "통일신라" and era_group("신라 진흥왕") == "삼국"
    assert era_group("고려 말~조선 초") == "고려" and era_group("") == "기타"

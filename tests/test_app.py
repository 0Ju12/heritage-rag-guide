"""Streamlit 화면 — F2008, F2009, F2010, F2011, F2012, NF2004 (AppTest로 실제 app.py 실행)."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")
SUNGNYEMUN = "kh_11_00010000_11"
DABOTAP = "kh_11_00200000_37"


def _texts(at) -> str:
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    parts += [e.value for e in at.error] + [w.value for w in at.warning] + [i.value for i in at.info]
    parts += [s.value for s in at.success]
    return "\n".join(str(p) for p in parts)


def _start(item_id=None):
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    if item_id:
        at.selectbox(key="item_id").set_value(item_id).run()
        assert not at.exception, at.exception
    return at


def test_f2012_no_index_message(env):
    at = _start()
    assert "색인이 비어 있습니다" in _texts(at)


def test_f2012_no_key_message(indexed):
    from core import llm

    llm.set_overrides()
    at = _start()
    assert "GMS_KEY가 설정되지 않았습니다" in _texts(at)
    assert "4건" in " ".join(str(m.value) for m in at.sidebar.metric)   # 키가 없어도 색인 현황은 보임


def test_f2009_f2008_chat_per_item(indexed):
    at = _start(SUNGNYEMUN)
    at.chat_input[0].set_value("2008년 화재 뒤 어떻게 됐어?").run()
    assert not at.exception, at.exception
    text = _texts(at)
    assert "[근거 1]" in text and "[근거 99]" not in text
    assert any("답변에 사용한 근거" in e.label for e in at.expander)
    assert "🏛️ 국가유산청" in text or "📖 위키백과" in text
    assert "검색어 (프롬프트 1)" in text
    n_msgs = len(at.chat_message)
    assert n_msgs == 2

    at.selectbox(key="item_id").set_value(DABOTAP).run()      # 다른 국보 → 대화가 섞이지 않음
    assert len(at.chat_message) == 0
    at.selectbox(key="item_id").set_value(SUNGNYEMUN).run()   # 돌아오면 그대로
    assert len(at.chat_message) == 2


def test_no_citation_notice(indexed):
    from rag.prompts import NOT_FOUND

    indexed.chat.answer_override = NOT_FOUND
    at = _start(SUNGNYEMUN)
    at.chat_input[0].set_value("직원 수는?").run()
    assert "인용된 근거가 없습니다" in _texts(at)


def test_f2010_guide_and_factcheck(indexed):
    at = _start(SUNGNYEMUN)
    at.button(key=f"guide_{SUNGNYEMUN}").click().run()
    assert not at.exception, at.exception
    assert "한눈에 보기" in _texts(at)
    [t for t in at.text_input if t.label == "들은 이야기"][0].set_value("숭례문은 전부 새로 지었다").run()
    at.button(key=f"FormSubmitter:fc_form_{SUNGNYEMUN}-판정하기").click().run()
    assert not at.exception, at.exception
    assert "사실과 다름" in _texts(at)


def test_f2011_explore_and_pick(indexed):
    at = _start()
    explore_input = [t for t in at.text_input if t.label == "찾고 싶은 조건"][0]
    explore_input.set_value("통일신라 경주 석탑").run()
    at.button(key="FormSubmitter:explore_form-찾기").click().run()
    assert not at.exception, at.exception
    assert "조건에 맞는 1건" in _texts(at)
    at.button(key=f"pick_{DABOTAP}").click().run()
    assert at.session_state["item_id"] == DABOTAP
    assert "골랐습니다" in _texts(at)


def test_nf2004_errors_hide_details(indexed, monkeypatch):
    from services import assistant

    def boom(*a, **k):
        raise RuntimeError("Traceback secret-key-123 [작업] 근거 기반 답변")

    monkeypatch.setattr(assistant, "run_rag", boom)
    at = _start(SUNGNYEMUN)
    at.chat_input[0].set_value("질문").run()
    text = _texts(at)
    assert "처리 중 문제가 생겼습니다" in text
    assert "secret-key-123" not in text and "Traceback" not in text and "[작업]" not in text


def test_numbered_list_filters_and_photo(indexed):
    def names(at):  # AppTest의 options는 화면에 보이는 문구
        return [o.split(" · ", 1)[1].split("  (")[0] for o in at.selectbox(key="item_id").options]

    at = _start()
    labels = at.selectbox(key="item_id").options
    assert labels[0].startswith("001 · 서울 숭례문")                       # 옛 지정번호 순 + 번호 표시
    assert [l[:3] for l in labels] == ["001", "020", "070", "078"]

    at.selectbox(key="item_cat").set_value("유물").run()                   # 분류 필터
    assert names(at) == ["금동 미륵보살 반가사유상"]
    at.selectbox(key="item_cat").set_value("전체").run()
    at.selectbox(key="item_era").set_value("통일신라").run()               # 시대 필터
    assert names(at) == ["경주 불국사 다보탑"]
    at.selectbox(key="item_era").set_value("전체").run()
    at.text_input(key="item_filter").set_value("70호").run()               # 번호로 찾기
    assert names(at) == ["훈민정음"]

    at.text_input(key="item_filter").set_value("").run()
    at.selectbox(key="item_id").set_value(SUNGNYEMUN).run()
    assert not at.exception, at.exception
    assert len(at.get("image")) == 1                                          # 사진
    assert "옛 지정번호 제1호" in _texts(at)
    assert "사진: 국가유산청" in str(at.get("image")[0].proto)


def test_photo_background_and_links(indexed):
    at = _start(SUNGNYEMUN)
    styles = [m.value for m in at.markdown if "<style>" in str(m.value)]
    assert styles and "sungnyemun.jpg" in styles[0] and "stApp" in styles[0]        # 사진 배경
    text = _texts(at)
    for label in ("관련 링크", "유튜브 영상 찾기", "youtube.com/results?search_query=", "네이버 검색", "위키백과"):
        assert label in text, label
    assert "답변의 근거가 아닙니다" in text

    at.toggle(key="photo_bg").set_value(False).run()                                     # 배경 끄기
    assert not [m for m in at.markdown if "<style>" in str(m.value)]

    at.toggle(key="photo_bg").set_value(True).run()
    at.selectbox(key="item_id").set_value(DABOTAP).run()                                # 사진 없는 국보 → 배경 없음
    assert not [m for m in at.markdown if "<style>" in str(m.value)]
    assert "유튜브 영상 찾기" in _texts(at)


def test_background_rejects_unsafe_url(indexed, monkeypatch):
    import json

    items = json.loads((indexed.data / "items.json").read_text(encoding="utf-8"))
    items[0]["image_url"] = 'http://x/a.jpg"); } body { display:none } /*'
    (indexed.data / "items.json").write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    from data_prep.items import reset_catalog
    reset_catalog()
    at = _start(SUNGNYEMUN)
    assert not [m for m in at.markdown if "<style>" in str(m.value)]
    assert len(at.get("image")) == 0

"""FastAPI 서버 — F2013 요청·응답 형식, 오류 안내 (NF2004)."""

from __future__ import annotations

from fastapi.testclient import TestClient

SUNGNYEMUN = "kh_11_00010000_11"


def _client():
    from api.server import app
    return TestClient(app, raise_server_exceptions=False)


def test_static_and_health(indexed):
    c = _client()
    r = c.get("/")
    assert r.status_code == 200 and "국보 입문 가이드" in r.text
    assert c.get("/static/app.js").status_code == 200 and c.get("/static/style.css").status_code == 200
    h = c.get("/api/health").json()
    assert h["ready"] and h["items_indexed"] == 4 and h["items_total"] == 4 and h["examples"]["questions"]


def test_items_filter(indexed):
    c = _client()
    assert len(c.get("/api/items").json()) == 4
    got = c.get("/api/items", params={"q": "경주"}).json()
    assert [g["name"] for g in got] == ["경주 불국사 다보탑"]


def test_chat_modes(indexed):
    c = _client()
    r = c.post("/api/chat", json={"item_id": SUNGNYEMUN, "question": "2008년 화재 뒤 어떻게 됐어?", "top_k": 3})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["sources"] and {s["number"] for s in d["sources"]} == {1, 2}
    assert d["sources"][0]["source_type"] == "국보 메타데이터"
    assert d["collection"]["queries"][0] == "숭례문"
    assert d["evidence_count"] == 1 + 3 + 2   # 선택 국보 메타 1 + 외부 문서 top_k 3 + 관련 국보 2
    again = c.post("/api/chat", json={"item_id": SUNGNYEMUN, "question": "2008년 화재 뒤 어떻게 됐어?"}).json()
    assert again["collection"]["from_cache"] is True

    g = c.post("/api/chat", json={"item_id": SUNGNYEMUN, "mode": "guide"}).json()
    assert "한눈에 보기" in g["answer"]
    f = c.post("/api/chat", json={"item_id": SUNGNYEMUN, "mode": "factcheck", "question": "전부 새로 지었다"}).json()
    assert f["judgment"] == "사실과 다름"


def test_explore(indexed):
    d = _client().post("/api/explore", json={"condition": "통일신라 석탑"}).json()
    assert d["searched"] == 4 and [r["item_id"] for r in d["results"]] == ["kh_11_00200000_37"]


def test_errors_are_friendly(indexed, monkeypatch):
    c = _client()
    r = c.post("/api/chat", json={"item_id": "없는ID", "question": "q"})
    assert r.status_code == 404 and "찾지 못했습니다" in r.json()["detail"]
    r = c.post("/api/chat", json={"item_id": SUNGNYEMUN, "question": "x" * 600})
    assert r.status_code == 422 and "detail" in r.json()
    r = c.post("/api/chat", json={"item_id": SUNGNYEMUN, "question": "  "})
    assert r.status_code == 400

    from services import assistant

    def boom(*a, **k):
        raise RuntimeError("Traceback sk-secret [작업] 근거 기반 답변")

    monkeypatch.setattr(assistant, "run_rag", boom)
    r = c.post("/api/chat", json={"item_id": SUNGNYEMUN, "question": "질문"})
    assert r.status_code == 500
    body = r.text
    assert "sk-secret" not in body and "Traceback" not in body and "[작업]" not in body


def test_missing_key_and_index(env):
    from core import llm

    c = _client()
    r = c.post("/api/chat", json={"item_id": SUNGNYEMUN, "question": "q"})
    assert r.status_code == 503 and "색인이 비어" in r.json()["detail"]
    llm.set_overrides()
    h = c.get("/api/health").json()
    assert not h["ready"] and not h["has_key"] and "GMS_KEY" in h["message"]


def test_items_numbered_and_facets(indexed):
    c = _client()
    items = c.get("/api/items").json()
    assert [i["order_label"] for i in items] == ["제1호", "제20호", "제70호", "제78호"]
    assert items[0]["label"].startswith("001 · 서울 숭례문") and items[0]["image_url"].startswith("http")
    assert "옛 지정번호 제1호" in items[0]["order_note"] and items[0]["wiki_url"].endswith("숭례문")
    f = c.get("/api/facets").json()
    assert f["total"] == 4 and {x["name"] for x in f["categories"]} == {"유적건조물", "기록유산", "유물"}
    assert [x["name"] for x in f["eras"]] == ["삼국", "통일신라", "조선"]          # 시대는 시간 순
    assert [i["name"] for i in c.get("/api/items", params={"era": "통일신라"}).json()] == ["경주 불국사 다보탑"]
    assert [i["name"] for i in c.get("/api/items", params={"category": "유물"}).json()] == ["금동 미륵보살 반가사유상"]
    assert [i["name"] for i in c.get("/api/items", params={"q": "제70호"}).json()] == ["훈민정음"]


def test_items_links(indexed):
    items = _client().get("/api/items").json()
    kinds = [l["kind"] for l in items[0]["links"]]
    assert kinds[:4] == ["official", "wiki", "youtube", "search"]
    yt = next(l for l in items[0]["links"] if l["kind"] == "youtube")["url"]
    assert yt.startswith("https://www.youtube.com/results?search_query=")

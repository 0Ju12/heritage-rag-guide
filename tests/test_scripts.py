"""스크립트 — 수집·색인·점검·비교가 끝까지 도는지 (가짜 API)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"script_{name}", SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeKhs:
    LIST = [{"ccbaKdcd": "11", "ccbaAsno": f"{i:08d}", "ccbaCtcd": "11", "ccbaMnm1": n, "ccbaCncl": c}
            for i, (n, c) in enumerate([("서울 숭례문", "N"), ("경주 불국사 다보탑", "N"), ("해제된 국보", "Y"),
                                        ("훈민정음", "N")], 1)]

    def list_items(self):
        return [r for r in self.LIST if r["ccbaCncl"] != "Y"]

    def detail(self, row):
        return {"ccmaName": "국보", "ccceName": "조선", "ccbaCtcdNm": "서울", "ccsiName": "중구",
                "gcodeName": "유적건조물", "content": f"<p>{row['ccbaMnm1']} 설명입니다.</p><br/>둘째 줄&nbsp;내용 " * 40}


def test_collect_items_script(env, monkeypatch, capsys):
    from data_prep import collect_items as ci

    monkeypatch.setattr(ci, "KhsClient", FakeKhs)
    monkeypatch.setattr(ci, "WikiClient", lambda: env.wiki)
    assert load("collect_items").main([]) == 0
    items = json.loads((env.data / "items.json").read_text(encoding="utf-8"))
    assert [i["name"] for i in items] == ["서울 숭례문", "경주 불국사 다보탑", "훈민정음"]   # 지정 해제 제외
    assert items[0]["ko_wiki_title"] == "숭례문" and items[0]["wiki_match"] == "trimmed"
    assert items[1]["ko_wiki_title"] == "다보탑"
    off = json.loads((env.data / "official" / f"{items[0]['heritage_id']}.json").read_text(encoding="utf-8"))
    assert off["source_type"] == "국가유산청" and "<p>" not in off["text"] and "&nbsp;" not in off["text"]
    assert "색인 텍스트 예시" in capsys.readouterr().out


def test_index_scripts_and_rechunk(env, capsys):
    assert load("index_items").main(["--show", "1"]) == 0
    assert load("index_items").main([]) == 0
    out = capsys.readouterr().out
    assert out.count("색인 후 청크 수      4개") == 2 and "다시 실행해도 늘지 않음" in out

    assert load("index_official").main([]) == 0
    assert load("index_official").main(["--reset"]) == 0
    from vectorstore.store import get_store
    official_chunks = get_store().counts()["docs"]

    rc = load("rechunk")
    assert rc.main(["--dry-run"]) == 0
    a = capsys.readouterr().out
    assert rc.main(["--dry-run", "--chunk-size", "200", "--overlap", "20"]) == 0
    b = capsys.readouterr().out
    count = lambda s: int(s.split("합계")[1].split("청크")[1].split("개")[0])  # noqa: E731
    assert count(b) > count(a)                       # 청크 크기를 줄이면 청크 수가 늘어난다
    assert rc.main([]) == 0
    assert get_store().counts()["docs"] == official_chunks


def test_prefetch_and_check_pipeline(indexed, capsys):
    assert load("prefetch_wiki").main(["--limit", "3"]) == 0
    out = capsys.readouterr().out
    assert "자체 문서 색인 3건" in out
    cp = load("check_pipeline")
    assert cp.main(["--graph"]) == 0
    assert "retrieve → generate" in capsys.readouterr().out
    assert cp.main(["--item", "숭례문", "--question", "화재 뒤 복원", "--top-k", "3"]) == 0
    out = capsys.readouterr().out
    assert "[프롬프트 1] 검색어: 숭례문" in out and "일치: ✓" in out
    assert cp.main(["--item", "숭례문", "--question", "화재 뒤 복원"]) == 0
    assert "다시 수집하지 않았습니다" in capsys.readouterr().out


def test_compare_scripts(indexed, tmp_path, capsys):
    out1, out2 = tmp_path / "s.md", tmp_path / "r.md"
    assert load("compare_search").main(["--item", "숭례문", "--question", "화재", "--top-k", "3", "--out", str(out1)]) == 0
    assert "| # | 유사도 검색 | MMR 검색 |" in out1.read_text(encoding="utf-8")
    assert load("compare_rag").main(["--out", str(out2)]) == 0
    text = out2.read_text(encoding="utf-8")
    assert text.count("\n| ") >= 5 and "RAG 사용 답변의 근거" in text


def test_reset_index(indexed, capsys):
    from vectorstore.store import raw_counts, reset_store

    assert raw_counts()["items"] == 4
    assert load("reset_index").main([]) == 1          # --yes 없으면 지우지 않음
    reset_store()
    assert load("reset_index").main(["--yes"]) == 0
    assert raw_counts()["items"] == 0

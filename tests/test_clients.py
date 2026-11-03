"""외부 API 클라이언트 — 응답 파싱과 호출 예절(NF2006)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

LIST_P1 = """<?xml version="1.0" encoding="UTF-8"?>
<result><totalCnt>3</totalCnt><pageUnit>2</pageUnit><pageIndex>1</pageIndex>
<item><sn>1</sn><no>1</no><ccmaName>국보</ccmaName><ccbaMnm1>서울 숭례문</ccbaMnm1><ccbaMnm2>서울 崇禮門</ccbaMnm2>
<ccbaCtcdNm>서울</ccbaCtcdNm><ccsiName>중구</ccsiName><ccbaKdcd>11</ccbaKdcd><ccbaCtcd>11</ccbaCtcd>
<ccbaAsno>00010000</ccbaAsno><ccbaCncl>N</ccbaCncl><longitude>126.97</longitude><latitude>37.55</latitude></item>
<item><ccbaMnm1>해제된 것</ccbaMnm1><ccbaKdcd>11</ccbaKdcd><ccbaCtcd>11</ccbaCtcd><ccbaAsno>00999000</ccbaAsno><ccbaCncl>Y</ccbaCncl></item>
</result>"""
LIST_P2 = """<?xml version="1.0" encoding="UTF-8"?><result><totalCnt>3</totalCnt>
<item><ccbaMnm1>경주 불국사 다보탑</ccbaMnm1><ccbaKdcd>11</ccbaKdcd><ccbaCtcd>37</ccbaCtcd><ccbaAsno>00200000</ccbaAsno><ccbaCncl>N</ccbaCncl></item>
</result>"""
DETAIL_EUCKR = """<?xml version="1.0" encoding="EUC-KR"?>
<result><ccbaKdcd>11</ccbaKdcd><ccbaAsno>00010000</ccbaAsno><ccbaCtcd>11</ccbaCtcd><ccbaCpno>1111100010000</ccbaCpno>
<ccbaMnm1>서울 숭례문</ccbaMnm1><longitude>126.97</longitude>
<item><ccmaName>국보</ccmaName><gcodeName>유적건조물</gcodeName><bcodeName>정치국방</bcodeName><mcodeName>성</mcodeName>
<scodeName>성곽</scodeName><ccbaQuan>1동</ccbaQuan><ccbaAsdt>19621220</ccbaAsdt><ccbaLcad>서울 중구 세종대로 40</ccbaLcad>
<ccceName>조선 태조 7년(1398)</ccceName><ccbaPoss>국유</ccbaPoss><ccbaAdmin>서울 중구</ccbaAdmin>
<imageUrl>http://example/a.jpg</imageUrl><content><![CDATA[<p>숭례문은 서울 도성의 정문이다.</p><br/>2008년&nbsp;화재.]]></content></item>
</result>""".encode("euc-kr")


class FakePolite:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get_bytes(self, url, params):
        self.calls.append((url, dict(params)))
        r = self.responses(url, params)
        return r if isinstance(r, bytes) else r.encode("utf-8")

    def get_json(self, url, params):
        self.calls.append((url, dict(params)))
        return self.responses(url, params)


def test_khs_list_paging_and_detail(env):
    from data_prep.collect_items import clean_html, fmt_date
    from data_prep.khs_api import KhsClient, portal_url

    def resp(url, p):
        if "List" in url:
            return LIST_P1 if p["pageIndex"] == 1 else LIST_P2
        return DETAIL_EUCKR

    k = KhsClient(client=FakePolite(resp), hosts=["https://www.khs.go.kr"])
    rows = k.list_items(page_unit=2)
    assert [r["ccbaMnm1"] for r in rows] == ["서울 숭례문", "경주 불국사 다보탑"]   # 지정 해제 제외, 2쪽까지
    d = {**rows[0], **k.detail(rows[0])}
    assert d["ccceName"] == "조선 태조 7년(1398)" and d["scodeName"] == "성곽" and d["ccbaCpno"] == "1111100010000"
    assert clean_html(d["content"]) == "숭례문은 서울 도성의 정문이다.\n\n2008년 화재."
    assert fmt_date(d["ccbaAsdt"]) == "1962-12-20"
    assert "ccbaAsno=00010000" in portal_url(d)


def test_khs_host_fallback_and_bad_xml(env):
    from data_prep.http_client import ExternalAPIError
    from data_prep.khs_api import KhsClient

    class Flaky(FakePolite):
        def get_bytes(self, url, params):
            if "khs.go.kr" in url:
                raise ExternalAPIError("down")
            return super().get_bytes(url, params)

    k = KhsClient(client=Flaky(lambda u, p: LIST_P2), hosts=["https://www.khs.go.kr", "https://www.cha.go.kr"])
    assert len(k.list_items()) == 1                          # 예비 주소로 넘어감
    bad = KhsClient(client=FakePolite(lambda u, p: "<html>점검 중</htm>"), hosts=["https://x"])
    with pytest.raises(ExternalAPIError):
        bad.list_items()


def test_wiki_client_parsing(env):
    from data_prep.wiki_api import WikiClient

    def resp(url, p):
        if p.get("list") == "search":
            return {"query": {"search": [{"pageid": 7, "title": "숭례문", "snippet": '<span class="searchmatch">숭례문</span> &amp; 도성'}]}}
        if p.get("prop") == "extracts|info":
            if p["titles"] == "없는문서":
                return {"query": {"pages": [{"title": "없는문서", "missing": True}]}}
            return {"query": {"pages": [{"pageid": 7, "title": "숭례문", "fullurl": "https://ko.wikipedia.org/wiki/숭례문", "extract": "본문"}]}}
        return {"query": {"normalized": [{"from": "남대문_", "to": "남대문 "}],
                          "redirects": [{"from": "남대문", "to": "숭례문"}],
                          "pages": [{"title": "숭례문"}, {"title": "없음", "missing": True}]}}

    w = WikiClient(client=FakePolite(resp))
    assert w.search("숭례문") == [{"page_id": "7", "title": "숭례문", "snippet": "숭례문 & 도성"}]
    assert w.fetch("숭례문")["url"].endswith("숭례문") and w.fetch("없는문서") is None
    assert w.existing(["남대문", "없음"]) == {"남대문": "숭례문"}


def test_polite_client_retry_and_user_agent(env, monkeypatch):
    from data_prep import http_client as hc

    monkeypatch.setenv("WIKI_CONTACT", "me@example.com")
    assert "(me@example.com)" in hc.user_agent()
    monkeypatch.setenv("WIKI_CONTACT", "홍길동")
    assert "홍길동" not in hc.user_agent()                    # 헤더에 한글은 넣지 않음

    sleeps, seen = [], []
    monkeypatch.setattr(hc.time, "sleep", lambda s: sleeps.append(s))
    seq = [SimpleNamespace(status_code=429, headers={"Retry-After": "3"}),
           SimpleNamespace(status_code=503, headers={}),
           SimpleNamespace(status_code=200, headers={}, json=lambda: {"ok": 1})]

    c = hc.PoliteClient(min_interval=0, max_retries=4)
    monkeypatch.setattr(c.session, "get", lambda url, params, headers, timeout: (seen.append(headers), seq.pop(0))[1])
    assert c.get_json("https://x", {}) == {"ok": 1}
    assert 3.0 in sleeps                                      # Retry-After를 따름
    assert all("User-Agent" in h for h in seen)

    c2 = hc.PoliteClient(min_interval=0, max_retries=2)
    monkeypatch.setattr(c2.session, "get", lambda *a, **k: SimpleNamespace(status_code=429, headers={}))
    with pytest.raises(hc.ExternalAPIError):
        c2.get("https://x", {})


def test_polite_client_interval(env, monkeypatch):
    from data_prep import http_client as hc

    sleeps = []
    monkeypatch.setattr(hc.time, "sleep", lambda s: sleeps.append(s))
    c = hc.PoliteClient(min_interval=0.5, max_retries=1)
    monkeypatch.setattr(c.session, "get", lambda *a, **k: SimpleNamespace(status_code=200, headers={}))
    c.get("https://x", {})
    c.get("https://x", {})
    assert any(0 < s <= 0.5 for s in sleeps)                  # 두 번째 호출 전에 간격을 둠

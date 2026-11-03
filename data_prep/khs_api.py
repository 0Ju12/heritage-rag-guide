"""국가유산청 국가유산 검색 오픈API (키 불필요, XML).

    목록  /cha/SearchKindOpenapiList.do  ccbaKdcd=11(국보), pageUnit, pageIndex
    상세  /cha/SearchKindOpenapiDt.do    ccbaKdcd, ccbaAsno, ccbaCtcd

응답 태그 이름이 바뀌어도 깨지지 않도록 <item>의 하위 태그를 전부 dict로 담는다.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from core.config import get_settings

from .http_client import ExternalAPIError, PoliteClient

LIST_PATH = "/cha/SearchKindOpenapiList.do"
DETAIL_PATH = "/cha/SearchKindOpenapiDt.do"
KIND_NATIONAL_TREASURE = "11"
PORTAL_DETAIL = "https://www.heritage.go.kr/heri/cul/culSelectDetail.do?ccbaKdcd={k}&ccbaAsno={a}&ccbaCtcd={c}"


_DECL = re.compile(rb"""^\s*<\?xml[^>]*encoding=["']([A-Za-z0-9_\-]+)["'][^>]*\?>""")


def decode_xml(data: bytes) -> str:
    """XML 선언의 인코딩(UTF-8, EUC-KR 등)으로 직접 디코딩하고 선언은 뗀다.

    ElementTree는 EUC-KR 같은 멀티바이트 인코딩 선언을 직접 읽지 못한다.
    """
    m = _DECL.match(data)
    enc = (m.group(1).decode("ascii") if m else "utf-8").lower()
    if enc in ("euc-kr", "euckr", "ks_c_5601-1987", "ksc5601"):
        enc = "cp949"  # EUC-KR의 상위 집합
    body = data[m.end():] if m else data
    try:
        return body.decode(enc)
    except (LookupError, UnicodeDecodeError):
        return body.decode("utf-8", errors="replace")


def parse_items(xml: bytes | str) -> tuple[list[dict], int]:
    """<item> 하위 태그 → dict. 상세 응답은 종목코드·지정번호·이름이 <item> 밖(루트)에 있어 함께 담는다."""
    text = decode_xml(xml) if isinstance(xml, bytes) else re.sub(r"^\s*<\?xml[^>]*\?>", "", xml)
    try:
        root = ET.fromstring(text)
    except (ET.ParseError, ValueError) as e:
        raise ExternalAPIError(f"국가유산청 응답을 해석하지 못했습니다: {e}") from e
    total_text = (root.findtext("totalCnt") or "0").strip()
    total = int(total_text) if total_text.isdigit() else 0
    root_fields = {c.tag: (c.text or "").strip() for c in root if c.tag != "item" and len(c) == 0}
    items = [{**root_fields, **{c.tag: (c.text or "").strip() for c in it}} for it in root.iter("item")]
    return items, total


class KhsClient:
    def __init__(self, client: PoliteClient | None = None, hosts: list[str] | None = None):
        cfg = get_settings().section("khs")
        self.hosts = hosts or cfg.get("hosts", ["https://www.khs.go.kr"])
        self.client = client or PoliteClient(cfg.get("min_interval", 0.3), cfg.get("max_retries", 4), cfg.get("timeout", 30))

    def _get(self, path: str, params: dict) -> bytes:
        last: Exception | None = None
        for host in self.hosts:  # 기관명 변경 전 주소를 예비로 둔다
            try:
                return self.client.get_bytes(host + path, params)
            except ExternalAPIError as e:
                last = e
        raise ExternalAPIError(f"국가유산청 API 호출 실패: {last}")

    def list_items(self, kind: str = KIND_NATIONAL_TREASURE, page_unit: int = 100, max_pages: int = 50) -> list[dict]:
        rows: dict[tuple, dict] = {}
        total = None
        for page in range(1, max_pages + 1):
            batch, total = parse_items(self._get(LIST_PATH, {"ccbaKdcd": kind, "pageUnit": page_unit, "pageIndex": page}))
            new = 0
            for r in batch:
                key = (r.get("ccbaKdcd"), r.get("ccbaAsno"), r.get("ccbaCtcd"))
                if key not in rows:
                    rows[key] = r
                    new += 1
            # 빈 쪽, 새 항목이 없는 쪽(쪽 번호가 무시됨), 전체 건수 도달 중 하나면 멈춘다
            if not batch or new == 0 or (total and len(rows) >= total):
                break
        return [r for r in rows.values() if r.get("ccbaCncl", "N") != "Y" and r.get("ccbaAsno")]  # 지정 해제 제외

    def detail(self, row: dict) -> dict:
        items, _ = parse_items(self._get(DETAIL_PATH, {
            "ccbaKdcd": row["ccbaKdcd"], "ccbaAsno": row["ccbaAsno"], "ccbaCtcd": row["ccbaCtcd"],
        }))
        return items[0] if items else {}


def portal_url(row: dict) -> str:
    return PORTAL_DETAIL.format(k=row["ccbaKdcd"], a=row["ccbaAsno"], c=row["ccbaCtcd"])

"""국보 항목 메타데이터 + 국가유산청 공식 설명문 수집 (scripts/collect_items.py가 호출).

    국가유산청 목록 → 상세 → items.json (RAG 1 원천) + official/{id}.json (RAG 2, 출처 종류 "국가유산청")
    국보 이름 → 한국어 위키 문서 제목 연결 (정확한 제목 → 지역명 뺀 제목 → 끝 단어 → 위키 검색)
    국가유산청 API가 막히면 위키 '분류:대한민국의 국보'로 목록만이라도 확보한다.
"""

from __future__ import annotations

import html
import json
import re
from datetime import date
from typing import Callable

from core.config import get_settings

from .docs_store import safe_filename
from .domain import SOURCE_OFFICIAL
from .http_client import ExternalAPIError
from .khs_api import KhsClient, portal_url
from .wiki_api import WikiClient

SIDO_PREFIX = ("서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남",
               "충청", "전북", "전남", "전라", "경북", "경남", "경상", "제주")

Log = Callable[[str], None]


def clean_html(s: str) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p\s*>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"[ \t ]+", " ", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def fmt_date(d: str) -> str:
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if re.fullmatch(r"\d{8}", d or "") else (d or "")


# 이름 끝 단어가 이런 일반명사면 그 단어만으로는 국보 자체 문서를 찾지 않는다
# ('경주 석굴암 석굴' → '석굴' 문서, '○○ 삼층석탑' → '삼층석탑' 문서가 잘못 연결되는 것을 막는다)
GENERIC_TAIL = re.compile(
    r"^(?:[이삼사오육칠팔구십다]층)?(?:목탑|석탑|전탑|모전석탑|탑|승탑|탑비|비|석비|석등|범종|동종|종|불상|석불|"
    r"좌상|입상|석조|마애불|당간지주|부도|향로|정병|석굴|고분|산성|사지|터|대웅전|극락전|대웅보전|누각|성곽|"
    r"궁|문|경|책|지도|일기|상|도|병|호|잔|합|함|판)$"
)


def _compact(s: str) -> str:
    return re.sub(r"[\s·・,()]+", "", s)


def region_words(item: dict) -> set[str]:
    """국가유산청 소재지 → 이름 앞에 붙는 지역명 후보. '경주시' → {'경주시', '경주'}"""
    words = set()
    for v in (item.get("sigungu", ""), item.get("sido", "")):
        v = (v or "").strip()
        if v:
            words.add(v)
            if len(v) > 2 and v[-1] in "시군구도":
                words.add(v[:-1])
    return words


def _is_region(token: str, regions: set[str] | None) -> bool:
    if regions and token in regions:
        return True
    return token.startswith(SIDO_PREFIX) or (len(token) >= 2 and token.endswith(("시", "군", "구", "도")))


def title_candidates(name: str, regions: set[str] | None = None) -> list[str]:
    """'서울 숭례문' → ['서울 숭례문', '숭례문'] / '경주 불국사 다보탑' → [..., '불국사 다보탑', '다보탑']

    regions: 이 국보의 소재지에서 나온 지역명 ('경주시' → '경주'). 이름 첫 단어가 지역명이면 떼어 본다.
    """
    cands = [name]
    toks = name.split()
    if len(toks) > 1 and _is_region(toks[0], regions):
        cands.append(" ".join(toks[1:]))
    if len(toks) > 2 and len(toks[-1]) >= 2 and not GENERIC_TAIL.match(toks[-1]):
        cands.append(toks[-1])
    return list(dict.fromkeys(cands))


def pick_search_hit(name: str, hits: list[str], regions: set[str] | None = None) -> str | None:
    """위키 검색 결과 중 국보 자체 문서로 볼 만한 것.

    이름의 단어(2자 이상)가 제목에 2개 이상 들어 있거나(예: '금동 미륵보살 반가사유상' ↔ '금동미륵보살반가사유상'),
    제목이 지역명을 뺀 이름과 같거나, 일반명사가 아닌 끝 단어와 정확히 같을 때만 받아들인다.
    """
    toks = [t for t in name.split() if len(t) >= 2]
    tail = name.split()[-1]
    toks_all = name.split()
    trimmed = " ".join(toks_all[1:]) if len(toks_all) > 1 and _is_region(toks_all[0], regions) else name
    best, best_score = None, 0
    for h in hits:
        if "동음이의" in h or "목록" in h:
            continue
        base = re.sub(r"\s*\(.*\)$", "", h)
        score = sum(1 for t in toks if _compact(t) in _compact(base))
        if _compact(base) in (_compact(name), _compact(trimmed)):
            score = max(score, 99)
        elif base == tail and not GENERIC_TAIL.match(tail):
            score = max(score, 2)
        if score >= 2 and score > best_score:
            best, best_score = h, score
    return best


def link_wiki_titles(wiki: WikiClient, names: list[str], log: Log = print,
                     regions: dict[str, set[str]] | None = None) -> dict[str, tuple[str, str]]:
    """국보 이름 → (위키 문서 제목, 연결 방식 exact|trimmed|search). 맞는 문서가 없으면 연결하지 않는다."""
    regions = regions or {}
    result: dict[str, tuple[str, str]] = {}
    cands = {n: title_candidates(n, regions.get(n)) for n in names}
    for step in range(3):
        trial = {n: c[step] for n, c in cands.items() if n not in result and len(c) > step}
        if not trial:
            continue
        found = wiki.existing(list(dict.fromkeys(trial.values())))
        for n, t in trial.items():
            if t in found:
                result[n] = (found[t], "exact" if step == 0 else "trimmed")
    rest = [n for n in names if n not in result]
    if rest:
        log(f"  위키 검색으로 제목 찾기 {len(rest)}건")
    for n in rest:
        hit = pick_search_hit(n, [h["title"] for h in wiki.search(n, limit=5)], regions.get(n))
        if hit:
            result[n] = (hit, "search")
    return result


def collect_items(limit: int = 0, khs: KhsClient | None = None, wiki: WikiClient | None = None,
                  log: Log = print) -> list[dict]:
    s = get_settings()
    khs = khs or KhsClient()
    wiki = wiki or WikiClient()
    today = date.today().isoformat()

    try:
        rows = khs.list_items()
    except ExternalAPIError as e:
        log(f"! 국가유산청 API를 쓸 수 없습니다({e}). 위키 분류로 대체합니다.")
        return _fallback_from_wiki_category(wiki, log)
    log(f"국가유산청 목록: 국보 {len(rows)}건 (지정 해제 제외)")
    if limit:
        rows = rows[:limit]

    s.official_dir.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []
    for i, row in enumerate(rows, 1):
        try:
            d = {**row, **khs.detail(row)}
        except ExternalAPIError:
            d = dict(row)  # 상세가 실패해도 목록 정보로 항목은 남긴다
            log(f"  ! 상세 조회 실패: {row.get('ccbaMnm1')}")
        hid = f"kh_{d['ccbaKdcd']}_{d['ccbaAsno']}_{d['ccbaCtcd']}"
        name = d.get("ccbaMnm1", "").strip()
        url = portal_url(d)
        content = clean_html(d.get("content", ""))
        items.append({
            "heritage_id": hid,
            "name": name,
            "name_hanja": d.get("ccbaMnm2", ""),
            "designation": d.get("ccmaName", "국보") or "국보",
            "category": [d[k] for k in ("gcodeName", "bcodeName", "mcodeName", "scodeName") if d.get(k)],
            "era": d.get("ccceName", ""),
            "sido": d.get("ccbaCtcdNm", ""),
            "sigungu": d.get("ccsiName", ""),
            "address": d.get("ccbaLcad", ""),
            "quantity": d.get("ccbaQuan", ""),
            "designated_date": fmt_date(d.get("ccbaAsdt", "")),
            "owner": d.get("ccbaPoss", ""),
            "manager": d.get("ccbaAdmin", ""),
            "latitude": d.get("latitude", ""),
            "longitude": d.get("longitude", ""),
            "image_url": d.get("imageUrl", ""),
            "summary": content[:300],
            "khs_url": url,
            "ko_wiki_title": None,
            "wiki_match": None,
            "collected_at": today,
        })
        if content:
            doc = {
                "item_id": hid, "related_item": name, "title": f"{name} (국가유산청 설명)", "url": url,
                "page_id": "khs", "text": content, "source_type": SOURCE_OFFICIAL, "search_query": name,
                "collected_at": today,
            }
            (s.official_dir / f"{safe_filename(hid)}.json").write_text(
                json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        if i % 25 == 0:
            log(f"  상세 {i}/{len(rows)}")

    log("한국어 위키 문서 연결")
    regions: dict[str, set[str]] = {}
    for it in items:
        regions.setdefault(it["name"], set()).update(region_words(it))
    links = link_wiki_titles(wiki, [it["name"] for it in items], log, regions)
    for it in items:
        if it["name"] in links:
            it["ko_wiki_title"], it["wiki_match"] = links[it["name"]]
    return items


def _fallback_from_wiki_category(wiki: WikiClient, log: Log) -> list[dict]:
    data = wiki.client.get_json(wiki.api_url, {
        "action": "query", "format": "json", "formatversion": 2, "list": "categorymembers",
        "cmtitle": "분류:대한민국의 국보", "cmtype": "page", "cmlimit": 500,
    })
    titles = [m["title"] for m in data.get("query", {}).get("categorymembers", [])]
    today = date.today().isoformat()
    items = [{
        "heritage_id": f"kh_wiki_{safe_filename(t)}", "name": t, "name_hanja": "", "designation": "국보",
        "category": [], "era": "", "sido": "", "sigungu": "", "address": "", "summary": "",
        "khs_url": "", "ko_wiki_title": t, "wiki_match": "category", "collected_at": today,
    } for t in titles]
    log(f"(대체) 위키 분류에서 {len(items)}건 — 시대·소재지는 비어 있습니다. 국가유산청 API가 되면 다시 수집하세요.")
    return items


def write_items(items: list[dict]) -> None:
    s = get_settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    s.items_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

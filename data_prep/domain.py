"""도메인에 묶인 부분을 한곳에 모은다 (NF2005).

다른 도메인으로 바꿀 때는 이 파일과 collect_items.py만 고치면 된다.
"""

from __future__ import annotations

import re
from urllib.parse import quote, quote_plus

DOMAIN = "국보"
SERVICE_TITLE = "국보 입문 가이드"
SERVICE_TAGLINE = "국보에 대해 물으면 위키백과와 국가유산청 설명을 찾아 근거와 함께 답합니다"
ICON = "🏛️"

# 프롬프트 1·3의 역할 (F2003: 도메인 전문가 역할)
EXPERT_ROLE = "너는 한국 국가유산, 특히 국보를 깊이 아는 문화유산 해설사다."

# 위험 도메인 여부 (F2012). 국보는 건강·금융처럼 판단이 위험한 도메인이 아니다.
RISKY_DOMAIN = False
DISCLAIMER = ""  # 위험 도메인이면 예: "이 답변은 전문가의 조언을 대신하지 않습니다."

# 근거 출처 종류 표시 (F2007, F2016)
SOURCE_ITEM = "국보 메타데이터"
SOURCE_WIKI = "위키백과"
SOURCE_OFFICIAL = "국가유산청"

# 특화 기능 (F2010)
GUIDE_REQUEST = (
    "관람 전에 알아 두면 좋은 내용을 정리해 줘. 무엇인지, 언제·누가·왜 만들었는지, "
    "현장에서 꼭 볼 부분, 복원·보수 이력, 함께 보면 좋은 유산."
)
FACTCHECK_LABELS = ["사실", "일부 사실", "사실과 다름", "문서로 확인 불가"]

EXAMPLE_QUESTIONS = [
    "2008년 화재 뒤 복원하면서 원형과 달라진 부분은?",
    "언제, 누가 만들었어?",
    "왜 국보로 지정됐어?",
    "지금 어디에 있고, 직접 볼 수 있어?",
]
EXAMPLE_CLAIMS = [
    "숭례문은 2008년 화재로 완전히 없어져서 지금 것은 전부 새로 지은 것이다.",
    "석굴암 본존불은 지금도 공식적으로 국보 제24호라고 부른다.",
]
EXAMPLE_CONDITIONS = [
    "통일신라 시대에 만든 경주의 석탑",
    "서울에 있는 조선 시대 건축물",
    "금동으로 만든 불상",
]


def _join(v) -> str:
    if isinstance(v, list):
        return " > ".join(x for x in v if x)
    return str(v or "")


# ── 번호 · 시대 · 분류 (목록 정렬과 필터) ──────────────────────────
# 국보 지정번호 표기는 2021-11-19 폐지됐다. 국가유산청 데이터의 지정번호 칸(ccbaAsno, 예: 00010000)
# 앞 4자리가 옛 지정번호다. 폐지 이후 지정된 국보는 같은 칸을 '관리번호'로만 표시한다.
NUMBERING_ABOLISHED = "2021-11-19"

ERA_GROUPS = [  # (묶음 이름, 시대 문자열에 들어 있으면 그 묶음) — 위에서부터 먼저 맞는 것
    ("선사", ("선사", "구석기", "신석기", "청동기", "철기", "초기철기")),
    ("통일신라", ("통일신라",)),
    ("삼국", ("삼국", "고구려", "백제", "신라", "가야")),
    ("발해", ("발해",)),
    ("고려", ("고려",)),
    ("조선", ("조선",)),
    ("근현대", ("대한제국", "근대", "일제", "현대")),
]
# 화면 표시는 시간 순 (위 목록은 "통일신라"를 "신라"보다 먼저 검사하려는 매칭 순서라 다르다)
ERA_ORDER = ["선사", "삼국", "통일신라", "발해", "고려", "조선", "근현대", "기타"]


def designation_number(item: dict) -> tuple[int, int] | None:
    """(번호, 부번호). heritage_id 'kh_11_00010000_11' → (1, 0). 알 수 없으면 None."""
    asno = item.get("asno")
    if not asno:
        parts = str(item.get("heritage_id", "")).split("_")
        asno = parts[2] if len(parts) >= 4 and parts[0] == "kh" else ""
    if len(asno) != 8 or not asno.isdigit():
        return None
    num, sub = int(asno[:4]), int(asno[4:])
    return (num, sub) if num > 0 else None


def is_post_abolition(item: dict) -> bool:
    d = item.get("designated_date", "")
    return bool(d) and d >= NUMBERING_ABOLISHED


def order_label(item: dict) -> str:
    """'제1호' / '제78-2호' / 폐지 뒤 지정이면 '관리번호 350'."""
    n = designation_number(item)
    if not n:
        return ""
    num = f"{n[0]}" + (f"-{n[1]}" if n[1] else "")
    return f"관리번호 {num}" if is_post_abolition(item) else f"제{num}호"


def order_note(item: dict) -> str:
    """국보 화면 머리에 붙이는 설명 — 번호를 단정하지 않는다."""
    label = order_label(item)
    if not label:
        return ""
    if is_post_abolition(item):
        return f"{label} (지정번호 표기 폐지 이후 지정)"
    return f"옛 지정번호 {label} (2021년 11월 지정번호 표기 폐지)"


def sort_key(item: dict) -> tuple:
    n = designation_number(item)
    return (0, n[0], n[1], item.get("name", "")) if n else (1, 0, 0, item.get("name", ""))


def era_group(era: str) -> str:
    era = era or ""
    for group, words in ERA_GROUPS:
        if any(w in era for w in words):
            return group
    return "기타"


def main_category(item: dict) -> str:
    cat = item.get("category") or []
    return cat[0] if isinstance(cat, list) and cat else "미분류"


def index_text(item: dict) -> str:
    """항목 1건 → 색인 텍스트 1개 (F2001).

    사용자가 국보를 찾을 때 쓰는 말(이름, 번호, 시대, 지역, 분류, 재질·형태)이 모두 들어가야 검색에 걸린다.
    재질·형태는 별도 필드가 없어서 국가유산청 설명문 앞부분(개요)을 함께 넣는다.
    """
    name = item.get("name", "")
    hanja = item.get("name_hanja", "")
    region = " ".join(x for x in (item.get("sido", ""), item.get("sigungu", "")) if x)
    era = item.get("era", "")
    group = era_group(era)
    lines = [
        f"이름: {name}" + (f" ({hanja})" if hanja else ""),
        f"지정: {item.get('designation') or DOMAIN}",
        f"번호: {order_note(item)}",
        f"분류: {_join(item.get('category'))}",
        f"시대: {era}" + (f" [{group}]" if era and group != "기타" and group not in era else ""),
        f"소재지: {region}" + (f" ({item['address']})" if item.get("address") else ""),
        f"수량: {item.get('quantity', '')}",
        f"지정일: {item.get('designated_date', '')}",
        f"소유·관리: {' / '.join(x for x in (item.get('owner', ''), item.get('manager', '')) if x)}",
        f"개요: {item.get('summary', '')}",
    ]
    return "\n".join(line for line in lines if not line.endswith(": ") and line.split(": ", 1)[-1].strip())


def item_label(item: dict) -> str:
    """목록·카드에 보여 줄 한 줄 — '001 · 서울 숭례문  (조선 · 서울 중구)'."""
    n = designation_number(item)
    head = (f"{n[0]:03d}" + (f"-{n[1]}" if n[1] else "") + " · ") if n else ""
    bits = [item.get("era", ""), " ".join(x for x in (item.get("sido", ""), item.get("sigungu", "")) if x)]
    tail = " · ".join(b for b in bits if b)
    return f"{head}{item.get('name', '')}" + (f"  ({tail})" if tail else "")


def own_doc_query(item: dict) -> str:
    """국보 자체 문서를 찾는 검색어 — 위키 문서 제목을 알면 그것, 모르면 이름."""
    return item.get("ko_wiki_title") or item.get("name", "")


# ── 사진 · 관련 링크 (근거가 아닌 편의 정보) ─────────────────────
_SAFE_URL = re.compile(r"""^https?://[^\s"'()<>\\]+$""")


def safe_url(url: str) -> str:
    """http(s) 주소이고 따옴표·괄호·공백이 없을 때만 그대로 — CSS url()과 HTML 속성에 넣어도 안전하게."""
    return url if isinstance(url, str) and _SAFE_URL.match(url) else ""


def _coord(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f != 0 else None


def related_links(item: dict) -> list[dict]:
    """국보별 관련 링크. 유튜브·네이버는 검색 결과 링크(API 키 불필요), 카카오맵은 좌표가 있을 때만.

    답변의 근거가 아니므로 화면에서는 근거 목록과 따로 '관련 링크'로 보여 준다.
    """
    name = item.get("name", "")
    q = quote_plus(f"{name} {DOMAIN}")
    links = []
    if safe_url(item.get("khs_url", "")):
        links.append({"kind": "official", "label": "국가유산포털", "url": item["khs_url"]})
    if item.get("ko_wiki_title"):
        links.append({"kind": "wiki", "label": "위키백과",
                      "url": "https://ko.wikipedia.org/wiki/" + quote(item["ko_wiki_title"].replace(" ", "_"))})
    links.append({"kind": "youtube", "label": "유튜브 영상 찾기", "url": f"https://www.youtube.com/results?search_query={q}"})
    links.append({"kind": "search", "label": "네이버 검색", "url": f"https://search.naver.com/search.naver?query={q}"})
    lat, lng = _coord(item.get("latitude")), _coord(item.get("longitude"))
    if lat is not None and lng is not None and -90 <= lat <= 90 and -180 <= lng <= 180:
        place = quote(name.replace(",", " "))
        links.append({"kind": "map", "label": "카카오맵 위치", "url": f"https://map.kakao.com/link/map/{place},{lat},{lng}"})
        links.append({"kind": "route", "label": "카카오맵 길찾기", "url": f"https://map.kakao.com/link/to/{place},{lat},{lng}"})
    return links

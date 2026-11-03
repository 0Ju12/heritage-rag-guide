"""항목 메타데이터 로드 (F2001)."""

from __future__ import annotations

import json
import re
from collections import Counter
from functools import lru_cache

from core.config import get_settings
from core.errors import IndexEmptyError, ItemNotFoundError

from .domain import ERA_ORDER, designation_number, era_group, main_category, sort_key


ALL = "전체"


class ItemCatalog:
    def __init__(self, items: list[dict]):
        self.items = sorted(items, key=sort_key)  # 옛 지정번호 순 (번호 없는 것은 뒤에 이름순)
        self.by_id = {it["heritage_id"]: it for it in self.items}

    def __len__(self) -> int:
        return len(self.items)

    def get(self, item_id: str) -> dict:
        try:
            return self.by_id[item_id]
        except KeyError:
            raise ItemNotFoundError(item_id) from None

    def find_by_name(self, name: str) -> dict | None:
        """이름 일치 → 부분 일치 순으로 찾는다 (스크립트용)."""
        for it in self.items:
            if it["name"] == name:
                return it
        for it in self.items:
            if name in it["name"] or (it.get("ko_wiki_title") and name in it["ko_wiki_title"]):
                return it
        return None

    def filter(self, text: str = "", category: str = ALL, era: str = ALL) -> list[dict]:
        """글자(이름·시대·지역) 또는 번호('1', '1호', '제78호')로 거르고, 분류·시대로 좁힌다."""
        out = self.items
        if category and category != ALL:
            out = [it for it in out if main_category(it) == category]
        if era and era != ALL:
            out = [it for it in out if era_group(it.get("era", "")) == era]
        text = (text or "").strip()
        if not text:
            return out
        m = re.fullmatch(r"(?:국보\s*)?제?\s*(\d{1,4})\s*(?:-\s*(\d+))?\s*호?", text)
        if m:
            num, sub = int(m.group(1)), m.group(2)
            hits = [it for it in out if (n := designation_number(it)) and n[0] == num and (sub is None or n[1] == int(sub))]
            if hits:
                return hits
        region = lambda it: f"{it.get('sido', '')} {it.get('sigungu', '')}"  # noqa: E731
        return [it for it in out if text in it["name"] or text in it.get("era", "") or text in region(it)
                or text in (it.get("name_hanja") or "")]

    def facets(self) -> dict[str, list[tuple[str, int]]]:
        """분류·시대별 건수 — 필터 선택지. 시대는 시간 순, 분류는 많은 순."""
        cats = Counter(main_category(it) for it in self.items)
        eras = Counter(era_group(it.get("era", "")) for it in self.items)
        return {
            "categories": sorted(cats.items(), key=lambda kv: (-kv[1], kv[0])),
            "eras": [(e, eras[e]) for e in ERA_ORDER if eras.get(e)],
        }


def load_items_file() -> list[dict]:
    path = get_settings().items_path
    if not path.exists():
        raise IndexEmptyError("국보 메타데이터 파일(data/items.json)이 없어")
    with open(path, encoding="utf-8") as f:
        items = json.load(f)
    seen, unique = set(), []
    for it in items:  # 같은 ID가 두 번 들어와도 한 번만
        if it.get("heritage_id") and it["heritage_id"] not in seen:
            seen.add(it["heritage_id"])
            unique.append(it)
    return unique


@lru_cache(maxsize=1)
def get_catalog() -> ItemCatalog:
    return ItemCatalog(load_items_file())


def reset_catalog() -> None:
    get_catalog.cache_clear()

"""한국어 위키백과 API — 검색(후보)과 본문 수집.

search()  : 검색어 → 후보 문서의 제목과 짧은 요약 (본문은 아직 받지 않는다)
fetch()   : 제목 → 본문 · 원문 URL · page_id
existing(): 제목 여러 개 → 실제 있는 문서 (넘겨주기를 따라감)
"""

from __future__ import annotations

import html
import re
from functools import lru_cache

from core.config import get_settings

from .http_client import PoliteClient


class WikiClient:
    def __init__(self, client: PoliteClient | None = None, api_url: str | None = None):
        cfg = get_settings().section("wiki")
        self.api_url = api_url or cfg["api_url"]
        self.client = client or PoliteClient(cfg.get("min_interval", 0.5), cfg.get("max_retries", 4), cfg.get("timeout", 20))

    def _query(self, params: dict) -> dict:
        return self.client.get_json(self.api_url, {"action": "query", "format": "json", "formatversion": 2, **params})

    def search(self, query: str, limit: int = 5) -> list[dict]:
        data = self._query({"list": "search", "srsearch": query, "srlimit": limit, "srnamespace": 0})
        return [
            {
                "page_id": str(it["pageid"]),
                "title": it["title"],
                "snippet": html.unescape(re.sub(r"<[^>]+>", "", it.get("snippet", ""))),
            }
            for it in data.get("query", {}).get("search", [])
        ]

    def fetch(self, title: str) -> dict | None:
        data = self._query({
            "prop": "extracts|info", "titles": title, "explaintext": 1, "inprop": "url", "redirects": 1,
        })
        pages = data.get("query", {}).get("pages", [])
        if not pages or pages[0].get("missing") or pages[0].get("invalid"):
            return None
        p = pages[0]
        return {"page_id": str(p["pageid"]), "title": p["title"], "url": p["fullurl"], "text": p.get("extract", "")}

    def existing(self, titles: list[str]) -> dict[str, str]:
        """요청한 제목 → 실제 문서 제목 (없으면 빠짐). 50개씩 나눠 묻는다."""
        found: dict[str, str] = {}
        for s in range(0, len(titles), 50):
            batch = titles[s:s + 50]
            data = self._query({"titles": "|".join(batch), "redirects": 1, "prop": "info"})
            q = data.get("query", {})
            alias = {}
            for key in ("normalized", "redirects"):
                for m in q.get(key, []):
                    alias[m["from"]] = m["to"]
            real = {p["title"] for p in q.get("pages", []) if not p.get("missing") and not p.get("invalid")}
            for t in batch:
                cur = t
                for _ in range(3):  # normalized → redirect 연쇄
                    cur = alias.get(cur, cur)
                if cur in real:
                    found[t] = cur
        return found


@lru_cache(maxsize=1)
def get_wiki() -> WikiClient:
    return WikiClient()

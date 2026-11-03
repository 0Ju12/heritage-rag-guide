"""수집 이력(매니페스트)과 수집 문서 파일.

    data/wiki_manifest.json        국보별: 처리한 검색어, 색인한 문서, 자체 문서 처리 여부 (NF2002 캐시)
    data/wiki/{item_id}_{제목}.json 수집한 위키 문서 원문 (영화 팩 movielab_wiki와 같은 형식)

위키 호출이 막혔을 때는 data/wiki/ 에 있는 문서 묶음을 읽어 수집 단계를 대신한다 (F2004).
"""

from __future__ import annotations

import json
import re
import threading
from datetime import date
from pathlib import Path

from core.config import get_settings

_lock = threading.RLock()


def normalize_query(q: str) -> str:
    return re.sub(r"\s+", " ", (q or "").strip()).lower()


def safe_filename(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", s)[:80]


class Manifest:
    def __init__(self, path: Path | None = None):
        self.path = path or get_settings().manifest_path
        self.data: dict = {}
        self.load()

    def load(self) -> None:
        with _lock:
            if self.path.exists():
                with open(self.path, encoding="utf-8") as f:
                    self.data = json.load(f)
            else:
                self.data = {}

    def save(self) -> None:
        with _lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)

    def _entry(self, item_id: str) -> dict:
        return self.data.setdefault(item_id, {"queries": {}, "indexed": {}, "own_doc": None, "own_done": False})

    def has_query(self, item_id: str, query: str) -> bool:
        return normalize_query(query) in self.data.get(item_id, {}).get("queries", {})

    def record_query(self, item_id: str, query: str, selected: list[str], rejected: list[str]) -> None:
        with _lock:
            self._entry(item_id)["queries"][normalize_query(query)] = {
                "query": query, "selected": selected, "rejected": rejected, "at": date.today().isoformat(),
            }

    def cached_queries(self, item_id: str, question: str) -> list[str] | None:
        """같은 국보에 같은 질문이 들어온 적 있으면 그때 프롬프트 1이 고른 검색어.

        LLM은 같은 질문에도 검색어를 조금씩 다르게 뽑을 수 있어, 이것이 없으면 같은 질문에 수집이 다시 일어난다.
        """
        return self.data.get(item_id, {}).get("questions", {}).get(normalize_query(question))

    def record_question(self, item_id: str, question: str, queries: list[str]) -> None:
        with _lock:
            self._entry(item_id).setdefault("questions", {})[normalize_query(question)] = list(queries)

    def own_done(self, item_id: str) -> bool:
        return bool(self.data.get(item_id, {}).get("own_done"))

    def mark_own(self, item_id: str, title: str | None) -> None:
        with _lock:
            e = self._entry(item_id)
            e["own_done"], e["own_doc"] = True, title

    def indexed(self, item_id: str) -> dict:
        """page_id → 제목"""
        return self.data.get(item_id, {}).get("indexed", {})

    def add_indexed(self, item_id: str, page_id: str, title: str) -> None:
        with _lock:
            self._entry(item_id)["indexed"][str(page_id)] = title


def save_wiki_doc(doc: dict) -> Path:
    d = get_settings().wiki_dir
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{safe_filename(doc['item_id'])}_{safe_filename(doc['title'])}.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_saved_docs(item_id: str) -> list[dict]:
    d = get_settings().wiki_dir
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob(f"{safe_filename(item_id)}_*.json")):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if doc.get("item_id") == item_id and doc.get("text"):
            out.append(doc)
    return out


def load_official_doc(item_id: str) -> dict | None:
    p = get_settings().official_dir / f"{safe_filename(item_id)}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def load_all_official_docs() -> list[dict]:
    d = get_settings().official_dir
    if not d.exists():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))]

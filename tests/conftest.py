"""테스트 환경 — 임시 폴더에 설정·데이터·Chroma를 만들고, 가짜 LLM·임베딩·위키를 꽂는다."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.fakes import OFFICIAL, SAMPLE_ITEMS, FakeChat, FakeWiki  # noqa: E402


@pytest.fixture()
def env(tmp_path, monkeypatch):
    from langchain_core.embeddings import DeterministicFakeEmbedding

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    cfg["app"]["data_dir"] = str(tmp_path / "data")
    cfg["vectorstore"]["persist_dir"] = str(tmp_path / "data" / "chroma")
    cfg["wiki"]["min_interval"] = 0
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    monkeypatch.setenv("HERITAGE_RAG_CONFIG", str(cfg_path))
    monkeypatch.setenv("GMS_KEY", "")

    from core import config, llm
    config.reload_settings()
    chat = FakeChat()
    llm.set_overrides(chat=chat, embeddings=DeterministicFakeEmbedding(size=96))

    data = tmp_path / "data"
    (data / "official").mkdir(parents=True)
    (data / "items.json").write_text(json.dumps(SAMPLE_ITEMS, ensure_ascii=False), encoding="utf-8")
    for it in SAMPLE_ITEMS:
        if it["heritage_id"] in OFFICIAL:
            doc = {"item_id": it["heritage_id"], "related_item": it["name"], "title": f"{it['name']} (국가유산청 설명)",
                   "url": it["khs_url"], "page_id": "khs", "text": OFFICIAL[it["heritage_id"]],
                   "source_type": "국가유산청", "search_query": it["name"], "collected_at": "2026-10-21"}
            (data / "official" / f"{it['heritage_id']}.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    from data_prep import collector as collector_mod
    from data_prep.items import reset_catalog
    from services import assistant
    from vectorstore.store import reset_store

    wiki = FakeWiki()
    monkeypatch.setattr(collector_mod, "get_wiki", lambda: wiki)
    reset_store()
    reset_catalog()
    assistant.get_collector.cache_clear()

    yield type("Env", (), {"tmp": tmp_path, "data": data, "chat": chat, "wiki": wiki, "cfg_path": cfg_path})

    llm.set_overrides()
    reset_store()
    reset_catalog()
    assistant.get_collector.cache_clear()
    config.reload_settings()


@pytest.fixture()
def indexed(env):
    """국보 메타데이터와 국가유산청 설명문까지 색인된 상태."""
    from data_prep.docs_store import load_all_official_docs
    from data_prep.items import get_catalog
    from vectorstore.store import get_store

    store = get_store()
    store.index_items(get_catalog().items)
    store.index_documents(load_all_official_docs())
    return env

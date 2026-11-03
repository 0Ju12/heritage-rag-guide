"""API 키·네트워크 없이 화면을 미리 보는 데모 서버 (가짜 LLM·결정적 임베딩·샘플 국보 4건).

    python scripts/demo_offline.py          # → http://127.0.0.1:8765

답변 문장은 화면 확인용 고정 예시입니다. 실제 서비스는 scripts/collect_items.py 로 수집한 데이터와 LLM을 씁니다.
"""

import _bootstrap  # noqa: F401

import json
import os
import sys
import tempfile
from pathlib import Path

import yaml

from tests.fakes import OFFICIAL, SAMPLE_ITEMS, FakeChat, FakeWiki

DEMO_ANSWER = (
    "서울 숭례문은 2008년 2월 10일 방화로 누각 2층이 크게 무너졌고, 5년 3개월에 걸친 복구 공사 끝에 "
    "2013년 5월 4일 다시 공개되었습니다 [근거 2].\n"
    "- 복구 때 좌우 성곽 일부를 함께 복원했습니다 [근거 2].\n"
    "- 위키백과에는 복원 과정과 단청·재료에 관한 논란이 기록되어 있습니다 [근거 3].\n"
    "기본 정보로는 조선 태조 7년(1398)에 완공된 한양도성의 정문입니다 [근거 1, 9]."
)


def main(port: int = 8765) -> int:
    root = Path(__file__).resolve().parent.parent
    tmp = Path(tempfile.mkdtemp(prefix="heritage_demo_"))
    cfg = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    cfg["app"]["data_dir"] = str(tmp / "data")
    cfg["vectorstore"]["persist_dir"] = str(tmp / "data" / "chroma")
    (tmp / "config.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    os.environ["HERITAGE_RAG_CONFIG"] = str(tmp / "config.yaml")

    data = tmp / "data"
    (data / "official").mkdir(parents=True)
    (data / "items.json").write_text(json.dumps(SAMPLE_ITEMS, ensure_ascii=False), encoding="utf-8")
    for it in SAMPLE_ITEMS:
        if it["heritage_id"] in OFFICIAL:
            doc = {"item_id": it["heritage_id"], "related_item": it["name"], "title": f"{it['name']} (국가유산청 설명)",
                   "url": it["khs_url"], "page_id": "khs", "text": OFFICIAL[it["heritage_id"]],
                   "source_type": "국가유산청", "search_query": it["name"], "collected_at": "2026-10-21"}
            (data / "official" / f"{it['heritage_id']}.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    from langchain_core.embeddings import DeterministicFakeEmbedding

    from core import config, llm
    config.reload_settings()
    chat = FakeChat()
    chat.answer_override = DEMO_ANSWER
    llm.set_overrides(chat=chat, embeddings=DeterministicFakeEmbedding(size=96))

    from data_prep import collector
    from data_prep.docs_store import load_all_official_docs
    from data_prep.items import get_catalog
    from vectorstore.store import get_store
    wiki = FakeWiki()
    collector.get_wiki = lambda: wiki
    store = get_store()
    store.index_items(get_catalog().items)
    store.index_documents(load_all_official_docs())

    import uvicorn
    from api.server import app
    print(f"데모 서버: http://127.0.0.1:{port}  (가짜 LLM — 답변 문장은 고정 예시)")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 8765))

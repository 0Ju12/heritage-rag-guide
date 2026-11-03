"""③ 국가유산청 설명문 색인 — RAG 2의 두 번째 출처 종류 (F2005, F2016).

    python scripts/index_official.py
    python scripts/index_official.py --reset    # 청킹 설정을 바꿨을 때: 기존 국가유산청 청크를 지우고 다시 색인

위키백과 문서는 질문할 때 자동으로 수집·색인된다. 미리 모아 두려면 scripts/prefetch_wiki.py.
"""

import _bootstrap  # noqa: F401

import argparse
import sys

from core.errors import AppError
from data_prep.docs_store import load_all_official_docs
from data_prep.domain import SOURCE_OFFICIAL
from vectorstore.chunking import chunk_config
from vectorstore.store import get_store


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true", help="기존 국가유산청 청크를 지우고 다시 색인")
    args = ap.parse_args(argv)

    docs = load_all_official_docs()
    if not docs:
        print("✗ data/official/ 이 비어 있습니다. 먼저 python scripts/collect_items.py 를 실행하세요.")
        return 1
    try:
        store = get_store()
    except AppError as e:
        print("✗", e.message)
        return 1

    removed = store.delete_docs_where({"source_type": SOURCE_OFFICIAL}) if args.reset else 0
    before = store.counts()["docs"]
    ids = store.index_documents(docs)
    size, overlap = chunk_config(SOURCE_OFFICIAL)
    print("=" * 60)
    print(f"국가유산청 설명문     {len(docs)}건")
    print(f"청킹 설정             chunk_size={size}, chunk_overlap={overlap}  (config.yaml → chunking.official)")
    print(f"만든 청크             {len(ids)}개")
    if args.reset:
        print(f"지운 기존 청크        {removed}개")
    print(f"외부 문서 컬렉션      {before} → {store.counts()['docs']}개")
    print("=" * 60)
    print("다음: streamlit run app.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

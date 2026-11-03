"""청킹 설정 바꾼 뒤 다시 색인 / 청크 수 비교 (F2005 확인).

    python scripts/rechunk.py --dry-run                         # 지금 설정으로 청크가 몇 개 나오는지만 (API 호출 없음)
    python scripts/rechunk.py --dry-run --chunk-size 500 --overlap 100   # 설정을 바꾸면 몇 개가 되는지 비교
    python scripts/rechunk.py                                   # 외부 문서 컬렉션을 비우고 지금 config.yaml 값으로 다시 색인

다시 색인 대상: data/official/ (국가유산청) + data/wiki/ (지금까지 수집한 위키 문서)
"""

import _bootstrap  # noqa: F401

import argparse
import json
import sys

from core.config import get_settings
from core.errors import AppError
from data_prep.docs_store import load_all_official_docs
from data_prep.domain import SOURCE_OFFICIAL, SOURCE_WIKI
from vectorstore.chunking import chunk_config, split_source_doc


def load_wiki_docs() -> list[dict]:
    d = get_settings().wiki_dir
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("*.json")):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if doc.get("text") and doc.get("item_id"):
            out.append(doc)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="색인하지 않고 청크 수만 계산")
    ap.add_argument("--chunk-size", type=int, help="(--dry-run 비교용) 두 출처에 같은 값 적용")
    ap.add_argument("--overlap", type=int, help="(--dry-run 비교용)")
    args = ap.parse_args(argv)

    groups = {SOURCE_OFFICIAL: load_all_official_docs(), SOURCE_WIKI: load_wiki_docs()}
    print("=" * 64)
    total = 0
    for src, docs in groups.items():
        size, overlap = chunk_config(src)
        size, overlap = args.chunk_size or size, args.overlap if args.overlap is not None else overlap
        n = sum(len(split_source_doc(d, size, overlap)) for d in docs)
        total += n
        print(f"{src:<8} 문서 {len(docs):>4}건 → 청크 {n:>5}개   (chunk_size={size}, chunk_overlap={overlap})")
    print(f"{'합계':<8} {'':>13}   청크 {total:>5}개")
    print("=" * 64)
    if args.dry_run:
        return 0
    if args.chunk_size or args.overlap is not None:
        print("✗ 실제 색인은 config.yaml의 chunking 값을 바꿔서 하세요. (--chunk-size/--overlap 은 --dry-run 전용)")
        return 1
    try:
        from vectorstore.store import get_store

        store = get_store()
    except AppError as e:
        print("✗", e.message)
        return 1
    before = store.counts()["docs"]
    store.delete_docs_where({"source_type": {"$in": [SOURCE_OFFICIAL, SOURCE_WIKI]}})
    added = sum(len(store.index_documents(docs)) for docs in groups.values() if docs)
    print(f"외부 문서 컬렉션 {before}개 → {store.counts()['docs']}개 (새로 색인 {added}개)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

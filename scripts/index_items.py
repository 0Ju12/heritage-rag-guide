"""② 국보 메타데이터 색인 — RAG 1 (F2002). 두 번 실행해도 건수가 늘지 않는다.

    python scripts/index_items.py
    python scripts/index_items.py --show 3     # 색인 텍스트 3건 출력 (F2001 확인)
"""

import _bootstrap  # noqa: F401

import argparse
import sys

from core.errors import AppError
from data_prep.domain import index_text
from data_prep.items import load_items_file
from vectorstore.store import get_store


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", type=int, default=1, help="색인 텍스트를 몇 건 보여 줄지")
    args = ap.parse_args(argv)
    try:
        items = load_items_file()
        store = get_store()
    except AppError as e:
        print("✗", e.message)
        return 1

    before = store.counts()["items"]
    after = store.index_items(items)
    print("=" * 60)
    print(f"로드한 국보          {len(items)}건")
    print(f"색인 전 청크 수      {before}개")
    print(f"색인 후 청크 수      {after}개   {'✓ 로드 건수와 일치' if after == len(items) else '✗ 로드 건수와 다름'}")
    if before == after == len(items):
        print("                     (다시 실행해도 늘지 않음 — 청크 ID를 국보 ID로 고정해 덮어쓰기만 함)")
    print("=" * 60)
    for it in items[: max(0, args.show)]:
        print(f"[{it['heritage_id']}]")
        print(index_text(it))
        print("-" * 60)
    print("다음: python scripts/index_official.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

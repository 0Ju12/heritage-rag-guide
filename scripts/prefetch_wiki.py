"""(선택) 국보 자체 위키 문서를 미리 수집·색인 — 첫 질문을 빠르게 (NF2001).

    python scripts/prefetch_wiki.py --limit 30    # 앞에서 30건
    python scripts/prefetch_wiki.py               # 전부 (위키 호출 간격 때문에 수 분)

이미 수집한 국보는 건너뛴다. 관련 문서(사건·사찰·시대 등)는 질문할 때 프롬프트 1·2로 수집된다.
"""

import _bootstrap  # noqa: F401

import argparse
import sys

from core.errors import AppError
from data_prep.collector import DocumentCollector
from data_prep.http_client import ExternalAPIError
from data_prep.items import load_items_file


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)
    try:
        items = load_items_file()
        col = DocumentCollector()
    except AppError as e:
        print("✗", e.message)
        return 1
    targets = items[: args.limit] if args.limit else items
    found = missing = 0
    for i, it in enumerate(targets, 1):
        try:
            title = col.collect_own(it)
        except ExternalAPIError:
            print("✗ 위키백과에 연결하지 못했습니다. 잠시 뒤 다시 실행하세요. (이미 받은 문서는 저장됨)")
            return 1
        if title:
            found += 1
        else:
            missing += 1
            print(f"  - 자체 문서 없음: {it['name']}")
        if i % 20 == 0:
            print(f"  {i}/{len(targets)}")
    print(f"자체 문서 색인 {found}건 · 못 찾음 {missing}건 · 외부 문서 청크 {col.store.counts()['docs']}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())

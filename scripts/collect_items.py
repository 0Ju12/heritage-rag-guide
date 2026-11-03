"""① 국보 메타데이터 + 국가유산청 설명문 수집 (F2001, F2016 원천).

    python scripts/collect_items.py              # 국보 전부 (호출 간격 때문에 수 분)
    python scripts/collect_items.py --limit 20   # 빠른 시험

결과
    data/items.json            국보 메타데이터 (항목 ID, 이름, 시대, 분류, 소재지 …, 위키 문서 제목)
    data/official/{ID}.json    국가유산청 공식 설명문 (출처 종류 "국가유산청")
"""

import _bootstrap  # noqa: F401

import argparse
import sys
from collections import Counter

from core.config import get_settings
from data_prep.collect_items import collect_items, write_items
from data_prep.domain import era_group, index_text, main_category, order_label, sort_key


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=0, help="앞에서 N건만 (0 = 전부)")
    args = ap.parse_args(argv)

    s = get_settings()
    if not s.wiki_contact:
        print("! .env에 WIKI_CONTACT(영문 이메일)가 없습니다. 위키백과 호출이 분당 10회로 제한됩니다.\n")
    items = collect_items(limit=args.limit)
    if not items:
        print("✗ 항목을 하나도 모으지 못했습니다. python scripts/check_setup.py 로 연결을 확인하세요.")
        return 1
    write_items(items)

    official = len(list(s.official_dir.glob("*.json"))) if s.official_dir.exists() else 0
    linked = Counter(it.get("wiki_match") for it in items)
    print("\n" + "=" * 60)
    print(f"국보 메타데이터      {len(items)}건  → {s.items_path}")
    print(f"국가유산청 설명문    {official}건  → {s.official_dir}")
    print(f"위키 문서 연결       {len(items) - linked.get(None, 0)}건  (정확 {linked.get('exact', 0)} · "
          f"지역명 제거 {linked.get('trimmed', 0)} · 검색 {linked.get('search', 0)} · 없음 {linked.get(None, 0)})")
    ordered = sorted(items, key=sort_key)
    with_img = sum(1 for it in items if it.get("image_url"))
    print(f"대표 사진 주소        {with_img}건")
    print("번호 순 앞 3건 (숭례문이 제1호로 나오면 번호 계산이 맞습니다):")
    for it in ordered[:3]:
        print(f"   {order_label(it) or '번호 없음':>8}  {it['name']}  [{main_category(it)} · {era_group(it.get('era', ''))}]")
    print("=" * 60)
    print("[항목 1건의 색인 텍스트 예시]")
    print(index_text(items[0]))
    print("\n다음: python scripts/index_items.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

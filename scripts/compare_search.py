"""유사도 검색 vs MMR 검색 근거 비교 (F2014). 결과를 docs/search_comparison.md 에도 남긴다.

    python scripts/compare_search.py --item "숭례문" --question "화재 뒤 복원 과정"
    python scripts/compare_search.py --item "다보탑" --question "돌사자" --top-k 6

먼저 그 국보로 질문을 한 번 해서(앱이나 check_pipeline.py) 외부 문서가 색인돼 있어야 차이가 보인다.
"""

import _bootstrap  # noqa: F401

import argparse
import sys
from pathlib import Path
from datetime import datetime

from core.config import get_settings
from core.errors import AppError
from data_prep.items import get_catalog
from services.evaluation import compare_search


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--item", required=True)
    ap.add_argument("--question", required=True)
    ap.add_argument("--top-k", type=int)
    ap.add_argument("--out", help="결과 파일 (기본 docs/search_comparison.md)")
    args = ap.parse_args(argv)
    try:
        item = get_catalog().find_by_name(args.item)
        if not item:
            print(f"✗ '{args.item}' 국보를 찾지 못했습니다.")
            return 1
        out = compare_search(item["heritage_id"], args.question, args.top_k)
    except AppError as e:
        print("✗", e.message)
        return 1

    cfg = get_settings().section("retrieval")
    sim, mmr = out["similarity"], out["mmr"]
    sim_ids, mmr_ids = {e.chunk_id for e in sim}, {e.chunk_id for e in mmr}
    lines = [
        f"# 유사도 vs MMR 근거 비교 ({datetime.now():%Y-%m-%d %H:%M})",
        "",
        f"- 국보: {item['name']}  /  질문: {args.question}",
        f"- top_k={args.top_k or cfg.get('top_k')}, mmr_fetch_k={cfg.get('mmr_fetch_k')}, mmr_lambda={cfg.get('mmr_lambda')}",
        f"- 겹치는 근거 {len(sim_ids & mmr_ids)}건, 유사도에만 {len(sim_ids - mmr_ids)}건, MMR에만 {len(mmr_ids - sim_ids)}건",
        f"- 서로 다른 문서 수: 유사도 {len({e.title for e in sim})}개, MMR {len({e.title for e in mmr})}개",
        "",
        "| # | 유사도 검색 | MMR 검색 |",
        "|---|---|---|",
    ]
    for i in range(max(len(sim), len(mmr))):
        a = f"{sim[i].source_type} · {sim[i].title} `{sim[i].chunk_id}`" if i < len(sim) else ""
        b = f"{mmr[i].source_type} · {mmr[i].title} `{mmr[i].chunk_id}`" if i < len(mmr) else ""
        lines.append(f"| {i + 1} | {a} | {b} |")
    text = "\n".join(lines)
    print(text)
    path = Path(args.out) if args.out else get_settings().root / "docs" / "search_comparison.md"
    path.parent.mkdir(exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(text + "\n\n")
    print(f"\n→ {path} 에 추가했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

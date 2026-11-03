"""파이프라인 점검 — 체크리스트 3·4·6·7·8·9 증빙용 출력.

    python scripts/check_pipeline.py --graph
        LangGraph 구조(retrieve → generate) 출력 (F2007)

    python scripts/check_pipeline.py --item "숭례문" --question "2008년 화재 뒤 원형과 달라진 부분은?"
        프롬프트 1 검색어, 프롬프트 2로 색인된 문서/버린 문서, 근거 목록, 답변, 인용 대조 (F2003~F2008)
        같은 명령을 한 번 더 실행하면 "이미 수집한 검색어"로 다시 수집하지 않는 것을 확인할 수 있다 (NF2002)

    --top-k 3 / --top-k 8         근거 수를 바꿔 근거 목록 비교 (F2006)
    --search-type mmr             MMR 검색 (F2014)
    --mode guide | factcheck      특화 기능 (F2010)
"""

import _bootstrap  # noqa: F401

import argparse
import sys

from core.errors import AppError, friendly_message
from data_prep.items import get_catalog
from rag.citations import cited_numbers
from rag.graph import build_graph, graph_mermaid

DECISION = {"own": "국보 자체 문서(항상 색인)", "selected": "선별됨", "rejected": "선별 제외", "short": "너무 짧음",
            "missing": "가져오지 못함", "already": "이미 색인됨"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--graph", action="store_true")
    ap.add_argument("--item", help="국보 이름(일부만 써도 됨)")
    ap.add_argument("--question", default="")
    ap.add_argument("--top-k", type=int)
    ap.add_argument("--search-type", choices=["similarity", "mmr"])
    ap.add_argument("--mode", choices=["qa", "guide", "factcheck"], default="qa")
    args = ap.parse_args(argv)

    if args.graph or not args.item:
        g = build_graph().get_graph()
        nodes = [n for n in g.nodes if not n.startswith("__")]
        print("LangGraph 노드:", " → ".join(nodes))
        print(graph_mermaid())
        if not args.item:
            return 0

    try:
        catalog = get_catalog()
    except AppError as e:
        print("✗", e.message)
        return 1
    item = catalog.find_by_name(args.item)
    if not item:
        print(f"✗ '{args.item}' 국보를 찾지 못했습니다.")
        return 1

    from services.assistant import ask

    try:
        res = ask(item["heritage_id"], args.question, args.mode, None, args.top_k, args.search_type,
                  progress=lambda m: print("  …", m))
    except Exception as e:
        print("✗", friendly_message(e))
        return 1

    col = res.collection
    print("\n" + "=" * 70)
    print(f"국보: {item['name']}  |  모드: {res.mode}  |  질문: {res.question}")
    print("=" * 70)
    print("[프롬프트 1] 검색어:", " / ".join(col.queries))
    if col.from_cache:
        print("  → 모든 검색어를 이미 수집했습니다. 다시 수집하지 않았습니다 (NF2002).")
    else:
        print("  → 새로 처리한 검색어:", " / ".join(col.new_queries))
    if col.candidates:
        print("[프롬프트 2] 후보 선별 결과")
        for c in col.candidates:
            mark = "✓" if c.decision in ("own", "selected") else "✗"
            print(f"  {mark} {c.title:<30} ← '{c.query}'  {DECISION.get(c.decision, c.decision)} {c.note if c.decision not in ('own',) else ''}")
    print(f"  색인한 문서 {len(col.indexed_titles)}건, 청크 {col.chunks_added}개, 수집 {col.elapsed:.1f}초")

    r = res.rag
    print(f"\n[retrieve] 근거 {len(r.evidence)}건 (top_k={args.top_k or '설정값'}, 방식={args.search_type or '설정값'})")
    for e in r.evidence:
        print(f"  [근거 {e.number}] {e.source_type:<8} {e.title}  ({e.chunk_id})")
    print("\n[generate] 답변")
    print(r.answer)
    if r.judgment:
        print("판정:", r.judgment)
    nums = cited_numbers(r.answer)
    print("\n[인용 대조]")
    print("  본문의 근거 번호:", nums or "없음")
    print("  화면에 표시할 근거:", [e.number for e in r.cited] or "없음 → '인용된 근거가 없습니다' 안내")
    ok = sorted(nums) == sorted(e.number for e in r.cited)
    print("  일치:", "✓" if ok else "✗")
    print(f"\n⏱ 전체 {res.elapsed:.1f}초 (수집 {col.elapsed:.1f}초, 검색·생성 {r.elapsed:.1f}초)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

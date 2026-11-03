"""실행 전 점검 — .env, 외부 API 연결, GMS(LLM·임베딩) 연결.

    python scripts/check_setup.py
"""

import _bootstrap  # noqa: F401

import argparse
import sys

from core.config import get_settings


def main(argv=None) -> int:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    s = get_settings()
    ok = True
    print("① 환경변수")
    if s.gms_key:
        print("   ✓ GMS_KEY 있음")
    else:
        ok = False
        print("   ✗ GMS_KEY 없음 → .env에 GMS_KEY=발급받은_키 를 넣으세요")
    if s.wiki_contact:
        try:
            s.wiki_contact.encode("latin-1")
            print(f"   ✓ WIKI_CONTACT = {s.wiki_contact}")
        except UnicodeEncodeError:
            ok = False
            print("   ✗ WIKI_CONTACT에 한글이 있습니다 → 영문 이메일로 바꾸세요")
    else:
        print("   ! WIKI_CONTACT 없음 → 위키백과 호출 한도가 분당 10회로 줄어듭니다. .env에 이메일을 넣으세요")

    print("② 위키백과 API")
    try:
        from data_prep.wiki_api import WikiClient

        hits = WikiClient().search("숭례문", limit=1)
        print(f"   ✓ 연결됨 (검색 결과 예: {hits[0]['title'] if hits else '없음'})")
    except Exception as e:
        ok = False
        print(f"   ✗ 연결 실패: {type(e).__name__} — 네트워크를 확인하세요")

    print("③ 국가유산청 오픈API")
    try:
        from data_prep.khs_api import LIST_PATH, KhsClient, parse_items

        k = KhsClient()
        items, total = parse_items(k._get(LIST_PATH, {"ccbaKdcd": "11", "pageUnit": 1, "pageIndex": 1}))
        print(f"   ✓ 연결됨 (국보 전체 {total}건)")
    except Exception as e:
        ok = False
        print(f"   ✗ 연결 실패: {type(e).__name__} — 교육장 네트워크에서 막혔다면 핫스팟으로 시도하세요")

    print("④ GMS (LLM · 임베딩)")
    if not s.gms_key:
        print("   - 키가 없어 건너뜀")
    else:
        try:
            from core.llm import chat, get_embeddings

            reply = chat([("system", "한 단어로만 답한다."), ("human", "안녕?")])
            vec = get_embeddings().embed_query("숭례문")
            print(f"   ✓ LLM 응답: {reply[:20]} / 임베딩 차원: {len(vec)}")
        except Exception as e:
            ok = False
            print(f"   ✗ 호출 실패: {type(e).__name__} — 키와 네트워크를 확인하세요")

    print("\n결과:", "모두 정상입니다." if ok else "✗ 표시된 항목을 먼저 해결하세요.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

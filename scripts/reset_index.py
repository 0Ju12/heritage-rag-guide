"""색인 지우기 — '색인 없음' 안내 확인용 (체크리스트 13), 또는 처음부터 다시 할 때.

    python scripts/reset_index.py --yes            # Vector DB(data/chroma)와 위키 수집 이력만 지움
    python scripts/reset_index.py --yes --all      # + 수집한 위키 문서(data/wiki)까지

items.json, official/ 은 지우지 않는다 (다시 수집하려면 collect_items.py).
"""

import _bootstrap  # noqa: F401

import argparse
import shutil
import sys

from core.config import get_settings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yes", action="store_true", help="정말 지움")
    ap.add_argument("--all", action="store_true", help="수집한 위키 문서까지 지움")
    args = ap.parse_args(argv)
    s = get_settings()
    targets = [s.chroma_dir, s.manifest_path] + ([s.wiki_dir] if args.all else [])
    if not args.yes:
        print("지울 대상:", *[str(t) for t in targets], sep="\n  ")
        print("정말 지우려면 --yes 를 붙여 다시 실행하세요.")
        return 1
    for t in targets:
        if t.is_dir():
            shutil.rmtree(t, ignore_errors=True)
        elif t.exists():
            t.unlink()
        print("지움:", t)
    print("다시 만들려면: python scripts/index_items.py → python scripts/index_official.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

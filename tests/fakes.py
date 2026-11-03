"""외부 호출 없이 전체 흐름을 돌리기 위한 가짜 LLM · 위키 · 국가유산청."""

from __future__ import annotations

import json
import re
from types import SimpleNamespace

SAMPLE_ITEMS = [
    {"heritage_id": "kh_11_00010000_11", "name": "서울 숭례문", "name_hanja": "崇禮門", "designation": "국보",
     "category": ["유적건조물", "정치국방", "성", "성곽"], "era": "조선 태조 7년(1398)", "sido": "서울",
     "sigungu": "중구", "address": "세종대로 40", "quantity": "1동", "designated_date": "1962-12-20",
     "owner": "국유", "manager": "서울 중구", "summary": "숭례문은 조선시대 한양도성의 정문으로 남쪽에 있다고 해서 남대문이라고도 불렀다.",
     "khs_url": "https://www.heritage.go.kr/heri/cul/culSelectDetail.do?ccbaKdcd=11&ccbaAsno=00010000&ccbaCtcd=11",
     "ko_wiki_title": "숭례문", "wiki_match": "trimmed", "image_url": "http://www.heritage.go.kr/x/sungnyemun.jpg"},
    {"heritage_id": "kh_11_00200000_37", "name": "경주 불국사 다보탑", "name_hanja": "多寶塔", "designation": "국보",
     "category": ["유적건조물", "종교신앙", "불교", "탑"], "era": "통일신라", "sido": "경북", "sigungu": "경주시",
     "address": "불국로 385", "quantity": "1기", "designated_date": "1962-12-20", "owner": "불국사",
     "manager": "불국사", "summary": "다보탑은 불국사 대웅전 앞 동쪽에 있는 석탑으로 화강암으로 만들었다.",
     "khs_url": "https://www.heritage.go.kr/x?a=20", "ko_wiki_title": "다보탑", "wiki_match": "trimmed"},
    {"heritage_id": "kh_11_00700000_11", "name": "훈민정음", "name_hanja": "訓民正音", "designation": "국보",
     "category": ["기록유산", "전적류", "목판본"], "era": "조선 세종 28년(1446)", "sido": "서울", "sigungu": "성북구",
     "address": "간송미술관", "quantity": "1책", "designated_date": "1962-12-20", "owner": "간송미술문화재단",
     "manager": "", "summary": "훈민정음 해례본은 새로 만든 문자의 뜻과 사용법을 풀이한 책이다.",
     "khs_url": "https://www.heritage.go.kr/x?a=70", "ko_wiki_title": "훈민정음", "wiki_match": "exact"},
    {"heritage_id": "kh_11_00780000_11", "name": "금동 미륵보살 반가사유상", "name_hanja": "", "designation": "국보",
     "category": ["유물", "불교조각", "금속조", "보살상"], "era": "삼국시대", "sido": "서울", "sigungu": "용산구",
     "address": "국립중앙박물관", "quantity": "1구", "designated_date": "1962-12-20", "owner": "국유",
     "manager": "국립중앙박물관", "summary": "금동으로 만든 반가사유상으로 한쪽 다리를 다른 다리 위에 올리고 생각하는 모습이다.",
     "khs_url": "https://www.heritage.go.kr/x?a=78", "ko_wiki_title": None, "wiki_match": None},
]

OFFICIAL = {
    "kh_11_00010000_11": "숭례문은 서울 도성의 정문이다. 2008년 2월 10일 방화로 누각 2층이 무너졌고, "
                         "5년 3개월에 걸친 복구 공사로 2013년 5월 4일 다시 공개되었다. 복구 때 좌우 성곽 일부를 함께 복원하였다. " * 3,
    "kh_11_00200000_37": "다보탑은 높이 10.4m로 통일신라 경덕왕 10년(751)에 김대성이 불국사를 지을 때 세운 것으로 전한다. "
                         "기단 네 귀퉁이의 돌사자 가운데 하나만 남아 있다. " * 3,
}

WIKI_PAGES = {
    "숭례문": "숭례문은 조선 한양도성의 남쪽 정문이다. 1398년에 완공되었다. " * 30,
    "숭례문 방화 사건": "숭례문 방화 사건은 2008년 2월 10일 일어난 방화로 누각이 크게 무너진 사건이다. "
                      "복원 과정에서 전통 기와와 단청 재료 논란이 있었다. " * 20,
    "한양도성": "한양도성은 조선의 수도 한양을 둘러싼 성곽이다. " * 30,
    "남대문시장": "남대문시장은 서울의 전통시장이다. " * 30,
    "숭례문 (동음이의)": "숭례문은 다음을 가리킬 수 있다.",
    "다보탑": "다보탑은 불국사에 있는 통일신라의 석탑이다. 돌사자는 원래 네 마리였다고 전한다. " * 30,
    "불국사": "불국사는 경주에 있는 절로 751년 김대성이 창건했다고 전한다. " * 30,
    "석가탑": "석가탑은 불국사 삼층석탑이다. " * 30,
    "훈민정음": "훈민정음 해례본은 1446년 간행되었으며 간송미술관에 있다. " * 30,
    "짧은 문서": "짧다.",
}


class FakeChat:
    """시스템 프롬프트의 '[작업] …' 줄로 어떤 프롬프트인지 알아보고 정해진 답을 돌려준다."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.query_extra = ["숭례문 방화 사건", "한양도성"]
        self.selection = "[1, 2, 3]"
        self.answer_override: str | None = None

    def invoke(self, messages):
        system = next(c for r, c in messages if r == "system")
        human = next(c for r, c in messages if r == "human")
        task = re.search(r"\[작업\] (.+)", system).group(1).strip()
        self.calls.append((task, human))
        return SimpleNamespace(content=self._answer(task, system, human))

    def _answer(self, task: str, system: str, human: str) -> str:
        if task == "검색어 추출":
            own = re.search(r'자체 문서인 "(.+?)"', system).group(1)
            return "```json\n" + json.dumps([own] + self.query_extra, ensure_ascii=False) + "\n```"
        if task == "후보 문서 선별":
            return self.selection
        nums = [int(n) for n in re.findall(r"\[근거 (\d+)\]", human)]
        if task == "근거 기반 답변":
            if self.answer_override is not None:
                return self.answer_override
            if len(nums) >= 2:
                return f"숭례문은 2008년 화재 뒤 복구되었습니다 [근거 {nums[1]}]. 기본 정보는 이렇습니다 [근거 1, 99]."
            return "기본 정보만 있습니다 [근거 1]."
        if task == "관람 해설 카드":
            return "### 한눈에 보기\n한양도성의 정문입니다 [근거 1].\n### 복원·보수 이력\n2013년에 다시 공개되었습니다 [근거 2]."
        if task == "통설 판정":
            return "판정: 사실과 다름\n2008년 화재 뒤 일부가 남아 복구에 쓰였습니다 [근거 2]."
        if task == "조건 탐색 선별":
            ids = re.findall(r"ID: (\S+)", human)
            picks = [{"id": i, "reason": "조건과 맞음"} for i in ids if "00200000" in i] + [{"id": "kh_가짜", "reason": "x"}]
            return json.dumps(picks, ensure_ascii=False)
        if task == "일반 답변":
            return "숭례문은 1398년에 지어졌고 2008년에 불탔습니다."
        raise AssertionError(task)


class FakeWiki:
    def __init__(self, pages: dict[str, str] | None = None, fail: bool = False):
        self.pages = dict(pages or WIKI_PAGES)
        self.fail = fail
        self.calls: list[tuple[str, str]] = []
        self.api_url = "https://ko.wikipedia.org/w/api.php"

    def _ensure(self):
        if self.fail:
            from data_prep.http_client import ExternalAPIError
            raise ExternalAPIError("offline")

    def _pid(self, title: str) -> str:
        return str(abs(hash(title)) % 10_000_000)

    def search(self, query: str, limit: int = 5) -> list[dict]:
        self._ensure()
        self.calls.append(("search", query))
        key = query.split()[0][:2]
        hits = [t for t in self.pages if key in t or query in t]
        return [{"page_id": self._pid(t), "title": t, "snippet": self.pages[t][:50]} for t in hits[:limit]]

    def fetch(self, title: str) -> dict | None:
        self._ensure()
        self.calls.append(("fetch", title))
        if title not in self.pages:
            return None
        return {"page_id": self._pid(title), "title": title, "url": f"https://ko.wikipedia.org/wiki/{title}",
                "text": self.pages[title]}

    def existing(self, titles: list[str]) -> dict[str, str]:
        self._ensure()
        return {t: t for t in titles if t in self.pages}

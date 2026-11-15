"""Hiring steps (코딩테스트, 사전과제, 1·2차 면접, 레퍼런스체크) read from a posting's description.

The answer tells "unknown" apart from "none": None when the posting does not describe its
process, a list (possibly empty) when it does. A step mentioned only as a possibility
('과제 전형이 추가될 수 있습니다') counts as present, so a "without 코딩테스트" filter does
not offer postings that might still have one; a step the posting says it skips
('코딩 테스트는 없습니다') counts as absent, even where the posting goes on to explain why.
"""
from __future__ import annotations

import re

# Stored keys, in the order the viewer shows them.
STEPS = ("coding", "assignment", "interview1", "interview2", "reference")

# Section headings the scrapers write (see scrapers/base.py `sections`).
_PROCESS_SECTION = re.compile(
    r"^\[(?:채용 전형|채용절차)\]\n(.*?)(?=\n\n\[(?:기타|서비스 소개)\]\n|\Z)", re.MULTILINE | re.DOTALL
)
# A process described elsewhere, under a heading of its own.
_PROCESS_HEADING = re.compile(
    r"(?:채용|전형|선발|합류|지원)\s*(?:절차|전형|과정|프로세스|여정|단계|안내)|hiring\s*process"
    r"|recruit(?:ment|ing)?\s*process|interview\s*process",
    re.IGNORECASE,
)
_HEADING_WINDOW = 600

# Signs that a text really describes a process, and not, say, which documents to submit.
_LOOKS_LIKE_PROCESS = re.compile(
    r"면접|인터뷰|interview|서류\s*(?:전형|심사|검토|평가|접수|합격)|최종\s*합격|전형\s*[>＞→▶▸-]", re.IGNORECASE
)

_CODING = re.compile(
    r"코딩\s*(?:역량\s*)?(?:테스트|시험|인터뷰|면접|평가)|(?:라이브|실시간|온라인|화이트\s*보드)\s*코딩|live\s*coding"
    r"|coding\s*(?:test|interview)|코테|알고리즘\s*(?:테스트|시험|평가|문제)|프로그래밍\s*(?:테스트|시험|평가)"
    r"|\(\s*코딩\s*\)|codility|hackerrank|프로그래머스",
    re.IGNORECASE,
)
_ASSIGNMENT = re.compile(
    r"(?<!국책)(?<!국책 )(?<!정부)(?<!연구)과제|take[\s-]*home|assignment|미니\s*프로젝트|pre[\s-]*task", re.IGNORECASE
)
_REFERENCE = re.compile(r"레퍼런스|reference|평판", re.IGNORECASE)
_INTERVIEW_WORD = r"(?:면접|인터뷰|interview|(?<!처우)(?<!처우 )(?<!연봉)(?<!연봉 )면담)"
# A step that is an interview ('2차 컬쳐핏 인터뷰', '면접전형', '대표 면담'), not a note about one
# ('면접 결과는 개별 안내').
_INTERVIEW_STEP = re.compile(
    _INTERVIEW_WORD + r"(?:\s*(?:전형|진행|단계|심사))?(?:\s*\d\s*(?:차|회))?(?:\s*등)?$", re.IGNORECASE
)
# '면접전형 2회', '면접전형 (1~2차)', '화상면접 1/2차': how many interviews, said as a number.
_INTERVIEW_COUNT = re.compile(r"(?:면접|인터뷰)\s*(?:전형)?\s*\(?\s*(?:\d\s*[~/,]\s*)?([1-9])\s*(?:회|차)")
_STEP_JOINER = re.compile(r"\s*(?:\s및\s|&|/|,|\+)\s*")  # '직무&문화적합성 인터뷰', '최종 인터뷰 및 연봉협상'
_DOCUMENT_STEP = re.compile(r"(?:\d\s*차\s*)?서류\s*(?:전형|심사|검토|평가|접수)?")
# '채용절차 : 1차 서류전형, 2차 면접' — the label before the colon is not a step.
_LABEL = re.compile(r"^(?:채용|전형|선발|합류|면접)?\s*(?:절차|전형|과정|프로세스|안내)\s*[:：]\s*")
# '코딩테스트 없이', '과제는 진행하지 않습니다'. '생략될 수 있습니다' is not a no.
_NEGATED = re.compile(r"[^.\n,>＞→]{0,12}?(?:없이|없습니다|없음|없는|없으며|없고|미실시|미진행|진행하지\s*않)")

# '2차 면접', '2차(임원) 인터뷰', '2차 컬쳐핏 인터뷰'. Not '2차 : 실무진 면접', where 2차 numbers the steps,
# and not at all once '1차 서류' shows the ordinals count every step.
_ORDINAL_INTERVIEW = re.compile(
    r"([1-9])\s*차\s*(?:\([^)]*\)\s*)?(?:[^\s:：>＞→,/\-]{1,10}\s*){0,2}?" + _INTERVIEW_WORD, re.IGNORECASE
)
_NUMBERED_STEPS = re.compile(r"1\s*차\s*[:：]?\s*(?:\([^)]*\)\s*)?서류")
_ARROWS = re.compile(r"\s*(?:-+\s*[>＞]|=+>|[>＞〉›»→⇒⇢➔➜➝➞➤⟶⇨➡⮕▶▸►▷👉])\ufe0f?\s*")
_GAPS = re.compile(r"\s{2,}")  # '서류전형  팀별면접  임원면접': arrows that were images
_DASHES = re.compile(r"(?<=[가-힣A-Za-z)\]])\s*[-–—]\s*(?=[가-힣A-Za-z(\[0-9])")
_LEADING = re.compile(
    r"^[\s•·∙ㆍ*\-–◦▪■□●○✔✅※▶>]*"
    r"(?:(?:step|단계)\s*-?\s*\d+\s*[.:：)]?|\d+\s*단계\s*[.:：)]?|\d+\s*차\s*[:：]|\d+\s*[.)_]|[①-⑩])?\s*",
    re.IGNORECASE,
)
_NOTE = re.compile(r"(?:니다|세요|어요|아요|해요|돼요|에요|예요|경우|따라)[.!)\s]*$|있으며|합니다|드립니다")


def _process_text(description: str) -> str | None:
    for match in _PROCESS_SECTION.finditer(description):
        if _LOOKS_LIKE_PROCESS.search(match.group(1)):
            return match.group(1)
    for match in _PROCESS_HEADING.finditer(description):
        window = description[match.start():match.end() + _HEADING_WINDOW]
        if _LOOKS_LIKE_PROCESS.search(window):
            return window
    return None


def _mentioned(pattern: re.Pattern, text: str) -> bool:
    """Mentioned, and never said to be skipped: '코딩 테스트는 없습니다. 코딩 테스트는 …' is a no."""
    negated = [bool(_NEGATED.match(text, m.end())) for m in pattern.finditer(text)]
    return bool(negated) and not any(negated)


def _steps(text: str) -> list[str]:
    """The step names in a flow ('서류 ＞ 1차 면접 ＞ 2차 면접') or a list of short lines."""
    steps: list[str] = []
    for line in text.splitlines():
        line = re.sub(r"\([^)]*\)|\u200b", "", line).strip()
        line = _LABEL.sub("", _LEADING.sub("", line))
        parts = _ARROWS.split(line)
        arrows = len(parts) > 1
        if not arrows:
            parts = _DASHES.split(line)
        if len(parts) == 1:
            parts = _GAPS.split(line)
        if len(parts) == 1 and len(line) <= 40:
            parts = line.split(",")
        for part in parts:
            head = re.split(r"\s*[:：]\s*", _LEADING.sub("", part), maxsplit=1)[0]
            if arrows:  # 'Step 2 : 면접 - 기술 면접 및 Culture Fit 인터뷰'
                head = re.split(r"\s+[-–—]\s+", head, maxsplit=1)[0]
            head = re.sub(r"[\[\]【】]", "", head).strip()
            if head and len(head) <= 25 and not _NOTE.search(head):
                steps.append(head)
    return steps


def _interviews(steps: list[str], text: str) -> int:
    named = {
        re.sub(r"\s+", "", step).casefold()
        for step in steps
        if any(_INTERVIEW_STEP.search(part) for part in _STEP_JOINER.split(step))
    }
    numbered = [] if _NUMBERED_STEPS.search(text) else [int(m.group(1)) for m in _ORDINAL_INTERVIEW.finditer(text)]
    counted = [int(m.group(1)) for m in _INTERVIEW_COUNT.finditer(text)]
    return max([len(named), *numbered, *counted])


def hiring_steps(description: str | None) -> list[str] | None:
    """Which of STEPS the posting's process includes; None when the posting doesn't describe one."""
    text = _process_text(description or "")
    if text is None:
        return None
    steps = _steps(text)
    interviews = _interviews(steps, text)
    found = {
        "coding": _mentioned(_CODING, text),
        "assignment": _mentioned(_ASSIGNMENT, text),
        "interview1": interviews >= 1,
        "interview2": interviews >= 2,
        "reference": _mentioned(_REFERENCE, text),
    }
    if not any(found.values()) and not any(_DOCUMENT_STEP.fullmatch(step) for step in steps):
        return None  # e.g. an English equal-opportunity note under 'hiring process'
    return [step for step in STEPS if found[step]]

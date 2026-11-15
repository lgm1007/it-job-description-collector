import pytest

from jdc.hiring import hiring_steps


def section(body: str, heading: str = "채용절차") -> str:
    """A description as the scrapers build it."""
    return f"[주요업무]\n백엔드 개발\n\n[{heading}]\n{body}\n\n[기타]\n수습 3개월"


@pytest.mark.parametrize("body, expected", [
    ("서류전형 ＞ 1차 면접 ＞ 2차 면접 ＞ 최종합격", ["interview1", "interview2"]),
    ("서류전형-＞1차면접-＞2차면접-＞최종합격", ["interview1", "interview2"]),
    ("서류전형 → 면접 → 최종합격", ["interview1"]),
    ("서류 전형 ＞ 직무 인터뷰 ＞ 문화적합성 인터뷰 ＞ 레퍼런스 체크 ＞ 처우 협의 ＞ 최종 합격",
     ["interview1", "interview2", "reference"]),
    ("서류접수 ＞ 사전과제 ＞ 직무 인터뷰 ＞ 처우협의", ["assignment", "interview1"]),
    ("서류 심사 -＞ 코딩테스트 -＞ 1차 면접(Tech) -＞ 2차 면접(Culture-Fit) -＞ 최종 합격",
     ["coding", "interview1", "interview2"]),
    ("서류전형 - 1차면접(구술/Live Coding Test) - 인성검사 - 2차면접 - Reference Check - 합격",
     ["coding", "interview1", "interview2", "reference"]),
    ("서류전형 ▶ 1차면접(실무진) ▶ 2차면접(대표이사) ▶ 처우협상 ▶ 채용", ["interview1", "interview2"]),
    ("• 서류 전형\n• 1차 비대면 면접 : 이력 및 직무 관련 면접 30분\n• 2차 대면 면접 : 컬처핏 면접 30분\n• 최종 합격",
     ["interview1", "interview2"]),
    ("• 1차 : 서류전형\n• 2차 : 실무진 면접\n• 3차 : 임원진 면접(필요시)", ["interview1", "interview2"]),
    ("1차 서류전형 > 2차 면접 > 최종합격", ["interview1"]),  # the ordinals number the steps, not interviews
    ("서류전형 ＞ 면접전형 2회", ["interview1", "interview2"]),
    ("서류전형 - 화상면접 1/2차 - 최종 합격", ["interview1", "interview2"]),
    ("ㆍ서류전형  팀별면접  임원면접  최종합격", ["interview1", "interview2"]),  # arrows were images
    ("서류전형 › 대표 면담 › 처우 협의 › 최종합격", ["interview1"]),
    ("• 채용절차 : 1차 서류전형, 2차 면접", ["interview1"]),
    ("▸ Step 1 : 서류 전형 - 이력서 검토\n▸ Step 2 : 면접 - 기술 면접 및 Culture Fit 인터뷰\n▸ Step 3 : 최종 합격",
     ["interview1"]),  # one step, named 면접, then what it covers
    ("서류전형 → 최종합격", []),
])
def test_steps_from_the_process_section(body, expected):
    assert hiring_steps(section(body)) == expected


def test_possible_steps_count_as_present():
    body = ("• 서류전형 ＞ 1차 온라인 기술 인터뷰 ＞ 2차 컬쳐 인터뷰 ＞ 최종 합격\n"
            "*면접 일정에 대해서는 수시로 연락을 드립니다.\n"
            "*상황에 따라 과제 또는 추가 인터뷰, 평판 조회 전형이 추가될 수 있습니다.")
    assert hiring_steps(section(body, "채용 전형")) == ["assignment", "interview1", "interview2", "reference"]


def test_notes_about_interviews_are_not_more_interviews():
    body = "서류전형 ＞ 면접 ＞ 최종합격\n면접 결과는 개별 안내\n면접 일정은 추후 통보됩니다."
    assert hiring_steps(section(body)) == ["interview1"]


@pytest.mark.parametrize("body", [
    "서류전형 > 1차 면접 > 최종합격\n별도의 코딩 테스트는 없으며, 과제 없이 진행합니다.",
    "서류전형 > 1차 면접 > 최종합격\n전형 — 코딩 테스트와 과제가 없습니다\n코딩 테스트는 서로에게 부담이 되기 때문입니다.",
])
def test_steps_the_posting_says_it_skips_are_absent(body):
    assert hiring_steps(section(body)) == ["interview1"]


def test_government_projects_are_not_assignments():
    assert hiring_steps(section("서류전형 > 면접 > 최종합격\n국책과제 수행 경험자 우대")) == ["interview1"]


@pytest.mark.parametrize("description", [
    None,
    "",
    "[자격요건]\nJava 3년 이상",
    section("허위 사실이 발견될 경우, 채용이 취소될 수 있습니다."),
    section("[제출서류]\n• 이력서\n• 자기소개서"),
    section("[근무형태]\n• 계약직(수습기간 3개월)으로 채용 후 정규직 전환"),
    "[소개]\nWe are committed to making our hiring process accessible to everyone.",
])
def test_unknown_when_the_posting_does_not_describe_its_process(description):
    assert hiring_steps(description) is None


def test_process_under_a_heading_outside_the_section():
    description = "[자격요건]\nJava\n\n[우대사항]\n■ 전형 절차\n서류 전형 ＞ 코딩 테스트 ＞ 1차 인터뷰 ＞ 2차 인터뷰\n\n■ 근무지\n판교"
    assert hiring_steps(description) == ["coding", "interview1", "interview2"]

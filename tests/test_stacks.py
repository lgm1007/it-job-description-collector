import pytest

from jdc.stacks import STACK_NAMES, find_stacks, stack_of_tag, stacks_in_text


@pytest.mark.parametrize("tag, expected", [
    ("Java", "Java"), ("JAVA", "Java"), ("java", "Java"),
    ("Spring Boot", "Spring"), ("SpringBoot", "Spring"), ("spring boot", "Spring"), ("스프링", "Spring"),
    ("Node.js", "Node.js"), ("NODE.JS", "Node.js"), ("nodejs", "Node.js"),
    ("MY SQL", "MySQL"), ("MS-SQL", "MSSQL"), ("Oracle DB", "Oracle"), ("postgres", "PostgreSQL"),
    ("C언어", "C"), ("c++", "C++"), ("C#", "C#"), (".NET", ".NET"), ("ASP.NET", ".NET"),
    ("k8s", "Kubernetes"), ("Golang", "Go"), ("Vue.js", "Vue.js"), ("nextJs", "Next.js"),
    ("AI/인공지능", None), ("유지보수", None), ("SI개발", None), ("Java게임", None), ("", None),
])
def test_tags_are_spelled_one_way(tag, expected):
    assert stack_of_tag(tag) == expected


@pytest.mark.parametrize("text, expected", [
    ("Java, Kotlin 기반 Spring Boot 개발 경험", ["Java", "Kotlin", "Spring"]),
    ("JavaScript/TypeScript, React 경험", ["JavaScript", "TypeScript", "React"]),
    ("React Native로 앱 개발", ["React Native"]),
    ("Node.js(Express.js), NestJS", ["Node.js", "Express", "NestJS"]),
    ("C/C++ 또는 C# 개발", ["C", "C++", "C#"]),
    ("C 언어 기반 펌웨어", ["C"]),
    ("Go 또는 Golang", ["Go"]),
    ("SQL Server, MS-SQL 운영", ["MSSQL"]),
    ("MySQL, PostgreSQL, SQL 튜닝", ["MySQL", "PostgreSQL", "SQL"]),
    ("자바, 파이썬, 코틀린 중 하나", ["Java", "Python", "Kotlin"]),
    ("자바스크립트 경험", ["JavaScript"]),
    ("k8s, Docker, AWS EKS", ["Kubernetes", "Docker", "AWS"]),
])
def test_stacks_are_found_in_text(text, expected):
    assert stacks_in_text(text) == expected


@pytest.mark.parametrize("text", [
    "C-Level 인터뷰와 C레벨 면접", "C/S 프로그램 유지보수", "C 레벨 임원", "Go-to-market 전략",
    "Google, Github 계정", "example.net 도메인", "javascript", "R&D 센터", "Let's go",
])
def test_words_that_only_look_like_stacks_are_ignored(text):
    assert "C" not in stacks_in_text(text)
    assert "Go" not in stacks_in_text(text)
    assert ".NET" not in stacks_in_text(text)
    assert "Java" not in stacks_in_text(text)


def test_tags_come_first_then_title_and_description():
    stacks = find_stacks(
        ["유지보수", "Java", "C/C++", "VisualC·C++", "spring boot"],
        "[백엔드] Kotlin 개발자",
        "[자격요건]\nGo, Python 경험\n\n[혜택 및 복지]\nAWS 자격증 취득 지원",
    )
    assert stacks == ["Java", "C", "C++", "Spring", "Kotlin", "Go", "Python"]  # not AWS from the benefits


def test_every_name_is_its_own_tag():
    assert all(stack_of_tag(name) == name for name in STACK_NAMES)
    assert len(set(STACK_NAMES)) == len(STACK_NAMES)

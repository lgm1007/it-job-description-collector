"""Tech stacks: one spelling per technology, whichever site or wording a posting used.

Sites tag postings differently: 점핏 and 잡플래닛 list real stacks, 사람인 and 잡코리아 mix them with
job keywords (유지보수, SI개발), and 원티드·리멤버 rarely tag at all but name the stack in the
requirements. So a posting's stacks come from its tags, its title and its description, matched
against the vocabulary below; anything outside the vocabulary is left out rather than guessed.
"""
from __future__ import annotations

import re

_L = r"(?<![0-9A-Za-z.])"  # not inside a longer word, and not 'Node.js' matching 'js'
_R = r"(?![0-9A-Za-z+#])"  # 'c' must not take the start of 'c++'


def _words(*names: str) -> str:
    return "|".join(_L + name + _R for name in names)


# canonical name, tag spellings (compared without case, spaces, dots, dashes or underscores),
# and the pattern that finds it in free text (None: tags only, too ambiguous in prose).
_VOCABULARY: list[tuple[str, tuple[str, ...], str | None]] = [
    # languages
    ("Java", ("java", "jdk", "자바"), _words(r"java(?!\s*script)") + r"|자바(?!\s*스크립트)"),
    ("Kotlin", ("kotlin", "코틀린"), _words("kotlin") + "|코틀린"),
    ("Python", ("python", "python3", "파이썬"), _words("python3?") + "|파이썬"),
    ("JavaScript", ("javascript", "js", "ecmascript", "es6", "자바스크립트"),
     _words(r"java\s*script", "ecmascript", "es6") + r"|자바\s*스크립트"),
    ("TypeScript", ("typescript", "ts", "타입스크립트"), _words("typescript") + "|타입스크립트"),
    ("Go", ("go", "golang", "고랭"), _words("golang") + r"|(?-i:(?<![0-9A-Za-z.])Go(?![0-9A-Za-z+#'’-]))"),
    ("Rust", ("rust",), _words("rust")),
    # 'C' in prose: only in lists like 'C/C++', 'C, Java' or 'C언어', never 'C-Level', 'C레벨' or 'C/S'.
    ("C", ("c", "c언어"),
     r"(?-i:(?<![0-9A-Za-z#+./&-])C(?!\s*/\s*S(?![0-9A-Za-z]))(?:\s*언어|(?=\s*[/,·)\]]|\s+(?:및|와|or|and)\s)))"),
    ("C++", ("c++", "cpp", "visualc++", "mfc/c++"), _L + r"(?:visual\s*)?c\s*\+\+|" + _words("cpp")),
    ("C#", ("c#", "csharp"), _L + r"c\s*#" + _R + "|" + _words(r"c\s*sharp")),
    ("Swift", ("swift", "swiftui"), _words("swift", "swiftui")),
    ("Objective-C", ("objectivec", "objc"), _words(r"objective[\s-]?c", r"obj[\s-]?c")),
    ("Dart", ("dart",), _words("dart")),
    ("PHP", ("php",), _words("php")),
    ("Ruby", ("ruby",), _words("ruby")),
    ("Scala", ("scala",), _words("scala")),
    ("R", ("r",), None),
    # backend
    ("Spring", ("spring", "springboot", "springframework", "springmvc", "springcloud", "springbatch",
                "springsecurity", "springwebflux", "webflux", "스프링", "스프링부트", "스프링프레임워크"),
     _words("spring", "webflux") + r"|스프링(?!클러)"),
    ("eGovFrame", ("egovframe", "egovframework", "egov", "전자정부프레임워크", "전자정부표준프레임워크"),
     _words(r"egov(?:frame(?:work)?)?") + r"|전자\s*정부\s*(?:표준\s*)?프레임\s*워크"),
    ("JPA", ("jpa", "hibernate", "springdatajpa"), _words("jpa", "hibernate")),
    ("MyBatis", ("mybatis", "ibatis"), _words("mybatis", "ibatis")),
    ("QueryDSL", ("querydsl",), _words("querydsl")),
    ("Node.js", ("nodejs", "node", "노드"), _words(r"node\s*\.?\s*js")),
    ("NestJS", ("nestjs", "nest"), _words(r"nest\s*\.?\s*js")),
    ("Express", ("express", "expressjs"), _words(r"express\s*\.?\s*js")),
    ("Django", ("django", "장고"), _words("django")),
    ("FastAPI", ("fastapi",), _words("fastapi")),
    ("Flask", ("flask",), _words("flask")),
    ("Rails", ("rails", "rubyonrails", "ror"), _words("rails")),
    ("Laravel", ("laravel",), _words("laravel")),
    (".NET", ("net", "dotnet", "aspnet", "netcore", "aspnetcore", "netframework", "aspnetmvc"),
     r"(?<![0-9A-Za-z])(?:asp\s*)?\.net" + _R + "|" + _words("dotnet")),
    ("GraphQL", ("graphql",), _words("graphql")),
    ("gRPC", ("grpc",), _words("grpc")),
    ("Kafka", ("kafka", "apachekafka", "카프카"), _words("kafka") + "|카프카"),
    ("RabbitMQ", ("rabbitmq",), _words("rabbitmq")),
    ("Redis", ("redis", "레디스"), _words("redis") + "|레디스"),
    ("Elasticsearch", ("elasticsearch", "elastic", "elk", "elkstack", "opensearch", "엘라스틱서치"),
     _words(r"elastic\s*search", "opensearch", "elk") + r"|엘라스틱\s*서치"),
    ("Nginx", ("nginx",), _words("nginx")),
    # databases
    ("MySQL", ("mysql",), _words("mysql")),
    ("MariaDB", ("mariadb",), _words(r"maria\s*db")),
    ("PostgreSQL", ("postgresql", "postgres", "postgre", "psql"), _words(r"postgre(?:s|sql)?")),
    ("Oracle", ("oracle", "oracledb", "오라클"), _words("oracle") + "|오라클"),
    ("MSSQL", ("mssql", "sqlserver", "mssqlserver"), _words(r"ms\s*-?\s*sql", r"sql\s*server")),
    ("MongoDB", ("mongodb", "mongo"), _words(r"mongo(?:\s*db)?")),
    ("DynamoDB", ("dynamodb",), _words(r"dynamo\s*db")),
    # not the SQL of 'MySQL', 'MS-SQL' or 'SQL Server'
    ("SQL", ("sql",), r"(?<![0-9A-Za-z.])(?<!\bms[ \t-])sql(?!\s*server)" + _R),
    # frontend
    ("React", ("react", "reactjs", "리액트"), _words(r"react(?:\s*\.?\s*js)?(?!\s*native)") + r"|리액트(?!\s*네이티브)"),
    ("React Native", ("reactnative", "rn"), _words(r"react\s*native") + r"|리액트\s*네이티브"),
    ("Vue.js", ("vue", "vuejs", "vue2", "vue3", "뷰"), _words(r"vue(?:\s*\.?\s*js)?[23]?")),
    ("Nuxt", ("nuxt", "nuxtjs"), _words(r"nuxt(?:\s*\.?\s*js)?")),
    ("Next.js", ("next", "nextjs"), _words(r"next\s*\.?\s*js")),
    ("Angular", ("angular", "angularjs"), _words(r"angular(?:\s*\.?\s*js)?")),
    ("Svelte", ("svelte", "sveltekit"), _words("svelte(?:kit)?")),
    # mobile
    ("Android", ("android", "aos", "안드로이드"), _words("android") + "|안드로이드"),
    ("iOS", ("ios",), _words("ios")),
    ("Flutter", ("flutter", "플러터"), _words("flutter") + "|플러터"),
    # games, graphics, embedded
    ("Unity", ("unity", "unity3d", "유니티"), _words(r"unity(?:\s*3d)?") + "|유니티"),
    ("Unreal", ("unreal", "unrealengine", "ue4", "ue5", "언리얼"), _words("unreal", "ue[45]") + "|언리얼"),
    ("Qt", ("qt",), r"(?-i:(?<![0-9A-Za-z])Qt(?![0-9A-Za-z]))"),
    ("MFC", ("mfc",), _words("mfc")),
    ("WPF", ("wpf",), _words("wpf")),
    ("ROS", ("ros", "ros2"), r"(?-i:(?<![0-9A-Za-z])ROS2?(?![0-9A-Za-z]))"),
    ("RTOS", ("rtos", "freertos"), _words("(?:free)?rtos")),
    ("Verilog", ("verilog", "systemverilog"), _words(r"(?:system\s*)?verilog")),
    ("VHDL", ("vhdl",), _words("vhdl")),
    ("CUDA", ("cuda",), _words("cuda")),
    # infrastructure
    ("AWS", ("aws", "amazonwebservices"), _words("aws", r"amazon\s*web\s*services")),
    ("GCP", ("gcp", "googlecloud", "googlecloudplatform"), _words("gcp", r"google\s*cloud")),
    ("Azure", ("azure", "msazure", "애저"), _words("azure")),
    ("Kubernetes", ("kubernetes", "k8s", "eks", "gke", "쿠버네티스"), _words("kubernetes", "k8s") + "|쿠버네티스"),
    ("Docker", ("docker", "도커"), _words("docker") + "|도커"),
    ("Terraform", ("terraform",), _words("terraform")),
    ("Linux", ("linux", "ubuntu", "centos", "rhel", "redhat", "리눅스"),
     _words("linux", "ubuntu", "centos", "rhel") + "|리눅스"),
    ("Jenkins", ("jenkins",), _words("jenkins")),
    ("ArgoCD", ("argocd", "argo"), _words(r"argo\s*cd")),
    # data and machine learning
    ("Spark", ("spark", "apachespark", "pyspark", "sparksql"), _words("spark", "pyspark")),
    ("Hadoop", ("hadoop", "hdfs"), _words("hadoop", "hdfs")),
    ("Airflow", ("airflow", "apacheairflow"), _words("airflow")),
    ("Flink", ("flink",), _words("flink")),
    ("BigQuery", ("bigquery",), _words(r"big\s*query")),
    ("Snowflake", ("snowflake",), _words("snowflake")),
    ("PyTorch", ("pytorch", "torch", "파이토치"), _words("pytorch") + "|파이토치"),
    ("TensorFlow", ("tensorflow", "텐서플로", "텐서플로우"), _words("tensorflow") + r"|텐서\s*플로우?"),
    ("scikit-learn", ("scikitlearn", "sklearn"), _words(r"scikit[\s-]?learn", "sklearn")),
    ("OpenCV", ("opencv",), _words("opencv")),
    ("LangChain", ("langchain",), _words("langchain")),
]

STACK_NAMES = tuple(name for name, _, _ in _VOCABULARY)


def _key(text: str) -> str:
    return re.sub(r"[\s._\-]+", "", text.casefold())


_BY_TAG = {_key(alias): name for name, aliases, _ in _VOCABULARY for alias in (name, *aliases)}


def _triggers(name: str, aliases: tuple[str, ...]) -> tuple[str, ...]:
    """The start of each spelling: a match contains one of these (checked against every stored posting)."""
    out = set()
    for alias in (name, *aliases):
        alias = alias.casefold()
        out.add(alias[:3] if alias.isascii() else alias[:2])
    return tuple(out)


# One pattern per stack, tried only when the text contains one of its triggers: a single
# alternation of every pattern would be tried at every character and takes ~15ms per posting.
_IN_TEXT = [
    (name, _triggers(name, aliases), re.compile(pattern, re.IGNORECASE))
    for name, aliases, pattern in _VOCABULARY
    if pattern
]

# Benefits sections mention tools the company pays for, not what the job uses.
_SECTION = re.compile(r"^\[([^\]\n]+)\]\n", re.MULTILINE)
_SKIPPED_SECTIONS = ("복지", "혜택")


def stack_of_tag(tag: str) -> str | None:
    """'spring boot' -> 'Spring'; a tag outside the vocabulary (유지보수, SI개발) -> None."""
    return _BY_TAG.get(_key(tag or ""))


def stacks_in_text(text: str | None) -> list[str]:
    """Stacks named in free text, in the order they first appear."""
    lowered = (text or "").casefold()
    found: list[tuple[int, str]] = []
    for name, triggers, pattern in _IN_TEXT:
        if any(t in lowered for t in triggers) and (match := pattern.search(text)):
            found.append((match.start(), name))
    return [name for _, name in sorted(found)]


def _without_benefits(description: str) -> str:
    parts = _SECTION.split(description)
    # split() gives [before, heading, body, heading, body, ...]
    kept = [parts[0]]
    for heading, body in zip(parts[1::2], parts[2::2]):
        if not any(word in heading for word in _SKIPPED_SECTIONS):
            kept.append(body)
    return "\n".join(kept)


def find_stacks(tags: list[str], title: str = "", description: str | None = None) -> list[str]:
    """A posting's stacks: its tags first, then what its title and description name."""
    found: list[str] = []

    def add(name: str | None) -> None:
        if name and name not in found:
            found.append(name)

    for tag in tags or []:
        name = stack_of_tag(tag)
        if name is None:  # combined tags such as 'C/C++' or 'VisualC·C++'
            for part in re.split(r"[/·,]", tag or ""):
                add(stack_of_tag(part))
        add(name)
    for name in stacks_in_text(title):
        add(name)
    for name in stacks_in_text(_without_benefits(description) if description else None):
        add(name)
    return found

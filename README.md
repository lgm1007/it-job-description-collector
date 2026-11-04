# dev-jobs — 개발자 채용공고 모아보기

원티드 · 리멤버 · 잡플래닛 · 점핏 · 사람인 · 잡코리아의 개발 직군 채용공고를
[browser-harness](https://github.com/browser-use/browser-harness)로 수집해서,
키워드 · 지역 · 경력 같은 조건으로 한 번에 찾는 로컬 웹 서비스입니다.
수집은 필요할 때 직접 실행하고, 그때마다 마감된 공고는 저장소에서 삭제합니다.

> **개인 용도로만 쓰세요.** 수집한 채용정보를 다른 사람에게 공개하거나 서비스로 제공하지 마세요.
> 자세한 내용은 [이용 안내](#이용-안내)를 확인하세요.

## 빠른 시작

필요한 것: Python 3.11 이상, Google Chrome(또는 Chromium)

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

```bash
.venv/bin/python -m jdc scrape
```

```bash
.venv/bin/python -m jdc serve
```

`scrape`는 지금 바로 수집합니다. 첫 실행은 모든 공고의 상세 정보까지 받느라 20~30분쯤 걸리고,
이후에는 새 공고만 상세 조회해서 훨씬 빨라집니다.
`serve`는 <http://127.0.0.1:8000>에 화면을 띄웁니다. 자동 수집은 없고, 새로 받고 싶을 때
`scrape`를 다시 실행하거나 화면의 "지금 수집" 버튼을 누르면 됩니다.

## 동작 방식

```
jdc scrape  또는  화면의 "지금 수집" 버튼
  └─ 전용 Chrome  (headless, --remote-debugging-port=9333, 프로필: .data/chrome-profile)
       └─ browser-harness 데몬  (CDP로 Chrome 제어)
            └─ 탭 하나로 사이트를 차례로 옮겨 가며, 그 페이지 안에서 fetch()로 사이트 자체 API를 호출
  → SQLite (.data/jobs.sqlite3)  → FastAPI (/api/*)  → 웹 화면 (web/)
```

- **전용 Chrome을 따로 띄웁니다.** 평소 쓰는 Chrome에 붙지 않으니 "원격 디버깅 허용" 창이 뜨지 않고,
  개인 탭·로그인 정보도 건드리지 않습니다. 이미 9333 포트에 Chrome이 떠 있으면 그대로 재사용하고,
  직접 띄운 경우에는 수집이 끝나면 종료합니다.
- **페이지 안에서 사이트 자체 API를 부릅니다.** 각 사이트의 프론트엔드가 쓰는 요청을 실제 브라우저에서,
  그 사이트 출처(쿠키·CORS 포함)로 보내므로 마감일·상태 같은 값을 구조화된 형태로 정확하게 받습니다.
  화면 HTML만 주는 사람인·잡코리아는 페이지 안에서 `DOMParser`로 필요한 값만 뽑습니다.

### 사이트별 수집 범위

| 사이트 | 범위 | 목록 | 상세 (새 공고만) | 마감 판단 |
|---|---|---|---|---|
| 원티드 | 개발 직군 전체 | `/api/v4/jobs` 100건씩 | Next.js 데이터 라우트(등록일·본문) | `status`, `due_time`, 404 |
| 리멤버 | SW개발 + AI·데이터 | `job_postings/search` 50건씩, 본문 포함 | 필요 없음 | `published`/`closed`, 404 |
| 잡플래닛 | 개발 + 데이터 | `/api/v3/job/postings` 100건씩 | `/api/v1/job/postings/{id}` | `open` 여부, 빈 응답 |
| 점핏 | 전체 (개발자 전용) | `/api/positions` 100건씩 | `/api/position/{id}` | 숨김 여부, 없는 공고 |
| 사람인 | IT개발·데이터 | 직무별 목록 HTML 100건씩 | 없음 (본문 대부분이 이미지) | `view-ajax`의 '마감되었습니다'·마감일 |
| 잡코리아 | AI·개발·데이터 | `_GI_List` HTML 100건씩 | 없음 (본문 대부분이 이미지) | 404, JSON-LD `validThrough` |

### 마감된 공고를 지우는 규칙

마감으로 판단한 공고는 수집할 때 DB(`.data/jobs.sqlite3`)에서 바로 삭제합니다.

1. 목록이 마감으로 표시하거나 **마감일이 지난 공고**는 삭제합니다. 검색할 때도 마감일을 확인하므로
   수집하지 않은 날에도 날짜가 지난 공고는 화면에 나오지 않고, 다음 수집 때 삭제됩니다.
2. 목록을 **끝까지 정상적으로 읽었는데 빠진 공고**는 상세 페이지로 다시 확인해서 마감·삭제가 확인되면 삭제합니다.
3. 재확인이 3번 연속 결론이 안 나면 삭제합니다. 요청이 막혀 응답이 아예 없었던 경우는 세지 않습니다.
4. 목록 수집이 중간에 실패했거나 건수가 갑자기 절반 아래로 줄면 2·3번을 건너뜁니다.
   사이트 장애 때문에 멀쩡한 공고가 통째로 지워지지 않도록 하기 위해서입니다.
5. 지운 공고가 마감 연장 등으로 목록에 다시 나타나면 새 공고로 다시 저장됩니다.

## 화면에서 할 수 있는 것

- **키워드**: 띄어 쓴 단어가 모두 들어간 공고(AND)를 제목·회사·기술스택·직무·본문에서 찾습니다.
  `go`, `ai`, `c`처럼 짧은 영문은 단어 단위로 찾고, `java`는 `javascript`와 구분합니다.
  "제목·기술스택에서만"을 켜면 본문은 빼고 찾습니다.
- **제외 키워드**: 제목·회사명·기술스택에 들어 있으면 뺍니다 (예: `SI 파견 프리랜서`).
- **내 경력**: 그 연차로 지원할 수 있는 공고만 보여줍니다 (최소 경력 ≤ 내 연차 ≤ 최대 경력).
  경력 조건이 없는 공고는 포함합니다.
- **지역**: 시/도 여러 개를 고를 수 있고, 하나만 고르면 구·시 단위로 좁힐 수 있습니다.
- **사이트**, **등록일**(3·7·14일 이내), **최신순 / 마감순**
- **같은 공고 합치기**: 회사명과 제목이 같은 공고는 한 줄로 보여주고, 다른 사이트 링크는 `└ also`에 붙입니다.
- 검색 조건이 URL에 남아서 북마크해 두고 다음에도 같은 조건으로 볼 수 있습니다.
- 단축키: `/` 검색, `j`·`k` 이동, `⏎` 원문 열기, `␣` 상세 펼치기, `[`·`]` 페이지, `s` 정렬, `m` 합치기, `t` 테마, `?` 도움말

## 명령어

| 명령 | 설명 |
|---|---|
| `python -m jdc scrape` | 지금 수집합니다. `--source wanted --source jumpit`처럼 일부만, `--no-details`로 상세 조회 생략 |
| `python -m jdc serve` | 웹 화면을 띄웁니다. `--host`, `--port`로 주소를 바꿀 수 있습니다 |
| `python -m jdc stats` | 사이트별 노출 중·저장된 공고 수와 최근 수집 결과 |
| `python -m jdc reindex` | 지역·검색어·중복 판단을 저장된 데이터로 다시 계산 (정규화 규칙을 고친 뒤, 다시 수집하지 않고 반영) |

CLI와 서버가 동시에 수집하지 않도록 파일 락(`.data/scrape.lock`)을 씁니다.
화면 오른쪽 아래 "지금 수집" 버튼으로도 수집할 수 있고, "수집 현황"에서 사이트별 결과와 오류를 볼 수 있습니다.

## 설정

`.env.example`을 `.env`로 복사해서 바꿉니다. 모두 생략할 수 있습니다.

| 변수 | 기본값 | 설명 |
|---|---|---|
| `JDC_DATA_DIR` | `.data` | DB, 전용 Chrome 프로필, browser-harness 상태 |
| `JDC_HOST` / `JDC_PORT` | `127.0.0.1` / `8000` | 웹 서버 주소 |
| `JDC_SOURCES` | 여섯 곳 모두 | `wanted,remember,jobplanet,jumpit,saramin,jobkorea` 중 일부 |
| `JDC_CHROME_PATH` | 자동 탐색 | Chrome 실행 파일 경로 |
| `JDC_CDP_PORT` | `9333` | 전용 Chrome의 원격 디버깅 포트 |
| `JDC_HEADLESS` | `1` | `0`이면 Chrome 창을 띄워 수집 과정을 볼 수 있습니다 |
| `JDC_CLOSE_BROWSER` | `1` | 직접 띄운 Chrome을 수집 후 종료 |
| `JDC_REQUEST_DELAY` | `0.7` | 목록 요청 사이 대기(초), 실제로는 0.7~1.05초 |
| `JDC_DETAIL_CONCURRENCY` | `3` | 상세 조회 동시 요청 수 |
| `JDC_MAX_DETAILS` | `6000` | 한 번에 사이트별로 새로 받을 상세 정보 수 (남은 건 다음 날) |
| `JDC_VERIFY_LIMIT` | `600` | 목록에서 빠진 공고를 사이트별로 몇 건까지 재확인할지 |

서버는 기본적으로 내 컴퓨터(`127.0.0.1`)에서만 열립니다. "지금 수집" API에 인증이 없으니
`JDC_HOST=0.0.0.0`으로 외부에 열 때는 주의하세요.

## browser-harness 연동

수집기는 시작할 때 아래 환경 변수를 설정한 뒤 `browser_harness`를 불러옵니다.

| 변수 | 값 | 이유 |
|---|---|---|
| `BU_CDP_URL` | `http://127.0.0.1:9333` | 평소 쓰는 Chrome 대신 전용 Chrome에 연결 |
| `BU_NAME` | `jdc` | 이 서비스 전용 데몬 이름 |
| `BH_HOME` | `.data/browser-harness` | 데몬 로그·상태를 프로젝트 안에 보관 |
| `BH_RUNTIME_DIR` | `/tmp/jdc-bh-<uid>` | macOS 소켓 경로 길이 제한(104바이트) 회피 |
| `BH_TELEMETRY` / `BH_TAB_MARKER` | `0` | 익명 통계 끔, 탭 제목에 🐴 표시 안 함 |

사용하는 browser-harness 기능은 `admin.ensure_daemon` · `restart_daemon`, `helpers.new_tab` ·
`switch_tab` · `goto_url` · `wait_for_load` · `close_tab`, 그리고 페이지 안 코드를 실행하는
`cdp("Runtime.evaluate")`입니다 (`jdc/browser.py`).

사이트 구조를 직접 살펴볼 때는 같은 설정으로 browser-harness CLI를 쓰면 됩니다.
데몬 하나는 브라우저 하나를 같이 쓰므로, 수집이 돌고 있지 않을 때만 사용하세요.

```bash
BU_CDP_URL=http://127.0.0.1:9333 BU_NAME=jdc BH_HOME=.data/browser-harness BH_RUNTIME_DIR=/tmp/jdc-bh-$(id -u) .venv/bin/browser-harness <<'PY'
new_tab("https://www.wanted.co.kr/wdlist/518")
print(page_info())
PY
```

## 프로젝트 구조

```
jdc/
  browser.py       전용 Chrome 실행 + browser-harness 탭에서 fetch 실행
  scrapers/        사이트별 수집기 (목록 페이징, 상세 조회, 응답 파싱)
  pipeline.py      수집 한 번의 흐름과 마감 공고 판단
  db.py            SQLite 저장, 병합, 검색 쿼리
  normalize.py     지역·경력·날짜·회사명 정규화
  api.py           FastAPI (/api/jobs, /api/jobs/{id}, /api/meta, /api/scrape)
  cli.py           python -m jdc scrape | serve | stats | reindex
web/               화면 (HTML/CSS/JS, 빌드 없음)
tests/             파서·DB·파이프라인·API 테스트
```

```bash
.venv/bin/python -m pytest
```

## 이용 안내

- 이 프로젝트는 개인이 자기 컴퓨터에서 채용공고를 찾아보기 위한 개인·학습용 도구입니다.
  각 채용 사이트와 제휴하거나 승인받은 프로젝트가 아닙니다.
- 수집되는 채용공고에 대한 권리는 각 채용 사이트와 공고를 올린 회사에 있습니다.
  수집한 데이터를 다른 사람에게 공개하거나, 재배포하거나, 서비스·영업에 쓰지 마세요.
  국내에는 경쟁 채용 사이트의 공고를 반복적으로 수집해 게재한 행위를 데이터베이스제작자의 권리 침해로 본
  판결(서울고법 2016나2019365)이 있습니다.
- 각 사이트의 이용약관과 robots.txt를 확인하고 지키는 것은 사용자의 책임입니다.
  사이트가 자동 수집을 금지하거나 중단을 요청하면 `JDC_SOURCES`에서 그 사이트를 빼세요.
- 사이트에 부담을 주지 않도록 수집은 하루 한 번 이하로 실행하세요. 요청 간격(0.7초 이상, 리멤버는 2.6초)과
  동시 요청 수(3)도 보수적으로 잡아 두었으니 낮추지 마세요.
- 웹 화면은 기본적으로 내 컴퓨터(`127.0.0.1`)에서만 열립니다. 인터넷에 공개하지 마세요.
- 코드는 있는 그대로 제공되며, 사용으로 생기는 문제에 대한 책임은 사용자에게 있습니다.

## 알아둘 점

- 사이트 구조가 바뀌면 그 사이트만 "실패"로 기록되고 나머지는 계속 수집됩니다.
  "수집 현황"에서 오류를 확인하고 `jdc/scrapers/<사이트>.py`를 고치면 됩니다.
- macOS + Python 3.13에서 `.venv/bin/jdc`가 `No module named 'jdc'`로 실패하면, 시스템이 `.venv` 안 파일에
  hidden 플래그를 붙여 Python이 editable 설치용 `.pth` 파일을 건너뛴 것입니다.
  프로젝트 폴더에서 `python -m jdc ...`로 실행하면 영향이 없습니다.

# dev-jobs — 개발자 채용공고 모아보기

원티드 · 리멤버 · 잡플래닛 · 점핏 · 사람인 · 잡코리아의 개발 직군 채용공고를
[browser-harness](https://github.com/browser-use/browser-harness)로 수집해서,
키워드 · 지역 · 경력 같은 조건으로 한 번에 찾는 개인용 서비스입니다.

수집과 조회가 나뉘어 있습니다. **수집은 맥북에서** 필요할 때 직접 실행하고, 끝나면 결과가 Supabase로 올라갑니다.
**조회는 웹앱에서** 합니다. 웹앱은 Supabase만 읽으니 맥북이 꺼져 있어도 폰에서 볼 수 있습니다.

> **개인 용도로만 쓰세요.** 수집한 채용정보를 다른 사람에게 공개하거나 서비스로 제공하지 마세요.
> 자세한 내용은 [이용 안내](#이용-안내)를 확인하세요.

## 화면

PC에서는 왼쪽에서 조건을 고르고 오른쪽 목록에서 공고를 고릅니다. 공고를 누르면 상세 정보와 본문이 펼쳐집니다.

![PC 화면: 공고 목록](docs/screenshots/desktop.png)

![PC 화면: 키워드로 찾은 공고의 상세 정보](docs/screenshots/desktop-detail.png)

폰에서는 홈 화면에 설치해 앱처럼 씁니다. 왼쪽 위의 ≡ 버튼으로 검색 조건을 엽니다.

<p>
  <img src="docs/screenshots/mobile.png" width="260" alt="폰 화면: 공고 목록">
  <img src="docs/screenshots/mobile-filters.png" width="260" alt="폰 화면: 검색 조건">
  <img src="docs/screenshots/mobile-detail.png" width="260" alt="폰 화면: 공고 상세">
</p>

> 캡처에 나오는 회사와 공고는 화면을 보여 주려고 만든 예시 데이터입니다. 실제로 수집한 공고는 저장소에 올리지 않습니다.

## 구성

```
[MacBook · 수집]                                    [클라우드 · 조회]
python -m jdc scrape                                Supabase (Postgres)
  사이트 6곳 수집 → 로컬 SQLite (.data/) ── 업로드 ──▶  공고 테이블 · 검색 함수 · RLS
                                                          ▲ 읽기만, 로그인한 본인만
                                  폰·PC 브라우저 ──▶ 웹앱 (Next.js 정적 파일, Vercel)
```

- **수집기** (`jdc/`, Python): 수집과 마감 판단을 모두 로컬에서 끝냅니다. SQLite는 수집기의 작업용 저장소로,
  목록에서 빠진 횟수 같은 판단 기록까지 들어 있습니다.
- **업로드** (`jdc/sync.py`): 수집이 끝나면 바뀐 공고만 올리고, 로컬에서 지운 공고는 Supabase에서도 지웁니다.
  한 트랜잭션으로 반영하므로 웹앱에 반쯤 올라간 상태가 보이지 않습니다.
- **Supabase** (`supabase/`): 화면에 필요한 열만 담은 테이블과, 검색 규칙이 들어 있는 Postgres 함수가 있습니다.
- **웹앱** (`viewer/`, Next.js): 정적 파일이고 서버 코드가 없습니다. 브라우저가 Supabase를 직접 호출하므로
  나중에 네이티브 앱을 만들어도 같은 함수를 부르면 됩니다.

## 처음 설정

필요한 것: Python 3.11 이상, Node.js, Google Chrome(또는 Chromium), Supabase·Vercel 계정(무료)

### 1. 수집기 설치

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

```bash
cp .env.example .env
```

### 2. Supabase 준비

1. [Supabase](https://supabase.com/dashboard)에서 프로젝트를 만듭니다. 리전은 `Northeast Asia (Seoul)`을 고릅니다.
2. 대시보드 위쪽 **Connect**에서 **Session pooler** 연결 문자열을 복사해 `.env`의 `JDC_SUPABASE_DB_URL`에 넣고,
   `[YOUR-PASSWORD]`를 DB 비밀번호로 바꿉니다. 비밀번호에 특수문자가 있으면 URL 인코딩이 필요합니다.
3. 테이블과 검색 함수를 만듭니다. 대시보드의 SQL Editor에
   `supabase/migrations/` 안의 SQL을 붙여 넣어 실행해도 됩니다.

   ```bash
   npx supabase db push --remote="<위에서 만든 연결 문자열>"
   ```

4. **Authentication > Users > Add user**에서 로그인할 계정을 만듭니다. Auto Confirm User를 켜고 만듭니다.
5. 그 계정에 조회 권한을 줍니다. 허용 목록에 있는 계정만 공고를 읽을 수 있습니다.

   ```bash
   .venv/bin/python -m jdc grant <이메일>
   ```

6. **Authentication > Sign In / Providers**에서 **Allow new users to sign up**을 끕니다.
   켜 둔 채 누가 가입해도 허용 목록에 없으면 공고를 읽을 수 없지만, 받을 이유가 없습니다.

### 3. 첫 수집

```bash
caffeinate -i .venv/bin/python -m jdc scrape
```

첫 실행은 모든 공고의 상세 정보까지 받느라 20~30분쯤 걸립니다. 자세한 내용은 [수집하기](#수집하기)에 있습니다.

### 4. 웹앱 배포

1. [Vercel](https://vercel.com/new)에서 이 GitHub 저장소를 가져오고 **Root Directory**를 `viewer`로 지정합니다.
2. **Environment Variables**에 아래 두 값을 넣고 배포합니다. Supabase의 **Project Settings > API Keys**에 있습니다.

   | 이름 | 값 |
   |---|---|
   | `NEXT_PUBLIC_SUPABASE_URL` | `https://<프로젝트ID>.supabase.co` |
   | `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | `sb_publishable_...` (secret 키가 아닙니다) |

3. 배포된 주소에서 2단계에서 만든 계정으로 로그인합니다.

### 5. 폰에 설치

안드로이드 Chrome에서 웹앱 주소를 열고 메뉴의 **앱 설치**(또는 **홈 화면에 추가**)를 누르면 앱처럼 전체 화면으로 실행됩니다.

## 수집하기

수집은 자동으로 돌지 않습니다. 새 공고를 받고 싶을 때 맥북의 프로젝트 폴더에서 직접 실행합니다.

```bash
caffeinate -i .venv/bin/python -m jdc scrape
```

`caffeinate -i`는 수집하는 동안 맥북이 잠들지 않게 해 줍니다. 수집은 30분 넘게 걸리기도 하는데,
중간에 잠들면 요청이 끊겨 그 사이트가 실패로 남을 수 있습니다. 덮개를 닫으면 잠들 수 있으니 열어 두세요.

### 수집 한 번에 일어나는 일

1. 화면 없는(headless) 전용 Chrome을 띄웁니다. 평소 쓰는 Chrome과는 따로 돌아갑니다.
2. 사이트 6곳을 차례로 돌며 목록을 끝까지 읽습니다. 처음 보는 공고는 새로 저장하고, 이미 있는 공고는 정보를 고칩니다.
3. 새 공고의 상세 정보(본문, 등록일, 정확한 근무지)를 받습니다. 원티드·잡플래닛·점핏이 해당되고,
   리멤버는 목록에 본문이 들어 있고 사람인·잡코리아는 본문이 대부분 이미지라 받지 않습니다.
4. 이번 목록에서 빠진 공고는 상세 페이지에서 마감됐는지 확인하고, 마감이면 지웁니다.
   자세한 기준은 [마감된 공고를 지우는 규칙](#마감된-공고를-지우는-규칙)에 있습니다.
5. 마감일이 지난 공고를 지웁니다.
6. 바뀐 공고를 Supabase에 올리고, 지운 공고는 Supabase에서도 지웁니다. 웹앱에는 이때부터 보입니다.

### 걸리는 시간

| 상황 | 시간 |
|---|---|
| 첫 수집 | 20~30분 (모든 공고의 상세 정보를 받습니다) |
| 일주일 만의 수집 | 30~40분 (새 공고 상세 조회와 빠진 공고 확인이 늘어납니다) |
| 사이트 하나만 | 1~12분. 리멤버가 요청 간격 제한 때문에 가장 오래 걸립니다 |
| Supabase 업로드 | 10초 안팎 |

### 결과 보기

끝나면 터미널에 사이트별 결과가 나옵니다.

```
사이트       상태            목록     신규    마감 삭제     상세    재확인
wanted    ok          2641    301      229    301    229
saramin   ok         11535   3542      597      0    600

Supabase 업로드: 신규·변경 14,806건, 삭제 1,126건 (전체 33,710건)
```

| 열 | 뜻 |
|---|---|
| 상태 | `ok` 정상, `partial` 목록을 끝까지 못 읽어 이번에는 마감 확인을 건너뜀, `failed` 실패 |
| 목록 | 이번에 목록에서 읽은 공고 수 |
| 신규 | 처음 본 공고 수 |
| 마감 삭제 | 마감으로 판단해 지운 공고 수 |
| 상세 | 상세 정보를 새로 받은 공고 수 |
| 재확인 | 목록에서 빠져서 상세 페이지로 마감 여부를 확인한 공고 수 |

같은 내용은 웹앱 오른쪽 아래의 **수집 현황**에서도 볼 수 있습니다. 사이트별로 저장된 공고 수는
`python -m jdc stats`로 확인합니다.

### 일부 사이트만 수집하기

```bash
caffeinate -i .venv/bin/python -m jdc scrape --source saramin --source jobkorea
```

- `--source`: 지정한 사이트만 수집합니다. 여러 번 쓸 수 있고, 이름은 `wanted` `remember` `jobplanet` `jumpit` `saramin` `jobkorea`입니다.
- `--no-details`: 새 공고의 상세 정보를 건너뛰고 목록만 빨리 받습니다.
- `--no-sync`: Supabase에 올리지 않습니다. 나중에 `python -m jdc sync`로 올립니다.
- `.env`에서 `JDC_HEADLESS=0`으로 바꾸면 Chrome 창을 띄워 수집 과정을 볼 수 있습니다.

### 얼마나 자주 수집할까

- 사이트에 부담을 주지 않도록 **하루 한 번 이하**로 실행하세요. 일주일에 한두 번이면 충분합니다.
- 목록에서 빠진 공고는 한 번 수집할 때 사이트당 `JDC_VERIFY_LIMIT`건까지만 확인합니다(기본 600건, 리멤버는 150건).
  확인하지 못한 공고는 다음 수집까지 웹앱에 남아 있습니다. 일주일에 한 번 수집하면 사람인에서만 1,400건 정도가
  목록에서 빠지니, `.env`에서 `JDC_VERIFY_LIMIT=2000`으로 올려 두세요. 확인할 공고 수 자체는 같고, 한 번에
  처리하는 양만 늘어납니다.

### 문제가 생겼을 때

| 증상 | 할 일 |
|---|---|
| 사이트 하나가 `failed` | 나머지 사이트는 그대로 수집됩니다. 터미널의 `!` 줄이나 웹앱의 수집 현황에서 오류를 확인하고, 일시적인 문제면 `--source <사이트>`로 그 사이트만 다시 수집합니다. 사이트 구조가 바뀐 경우에는 `jdc/scrapers/<사이트>.py`를 고쳐야 합니다 |
| `Supabase 업로드에 실패했습니다` | 수집 결과는 로컬에 남아 있습니다. 네트워크를 확인한 뒤 `python -m jdc sync`로 다시 올립니다. Supabase 프로젝트가 일시 정지됐다면 대시보드에서 다시 켠 뒤 올립니다 |
| `업로드를 멈췄습니다` (절반 넘게 지우게 됨) | 로컬 데이터 폴더(`JDC_DATA_DIR`)가 맞는지 확인합니다. 정말 지울 생각이면 `python -m jdc sync --force`를 씁니다 |
| `다른 수집이 이미 진행 중입니다` | 다른 터미널에서 수집이나 업로드가 돌고 있습니다. 끝난 뒤 다시 실행합니다 |
| 마감된 공고가 웹앱에 남아 있음 | 목록에서 빠진 공고는 확인 한도까지만 처리합니다. 다음 수집 때 정리되며, 한도는 위의 `JDC_VERIFY_LIMIT`로 조정합니다 |

## 동작 방식

```
jdc scrape
  └─ 전용 Chrome  (headless, --remote-debugging-port=9333, 프로필: .data/chrome-profile)
       └─ browser-harness 데몬  (CDP로 Chrome 제어)
            └─ 탭 하나로 사이트를 차례로 옮겨 가며, 그 페이지 안에서 fetch()로 사이트 자체 API를 호출
  → SQLite (.data/jobs.sqlite3)  → Supabase  → 웹앱 (viewer/)
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
| 잡코리아 | AI·개발·데이터 | `_GI_List` HTML 100건씩 | 없음 (본문 대부분이 이미지) | 404, '마감되었습니다' 문구, JSON-LD `validThrough` |

### 마감된 공고를 지우는 규칙

마감으로 판단한 공고는 수집할 때 로컬 DB(`.data/jobs.sqlite3`)에서 바로 삭제하고, 이어지는 업로드에서 Supabase에서도 삭제합니다.

1. 목록이 마감으로 표시하거나 **마감일이 지난 공고**는 삭제합니다. 검색할 때도 마감일을 확인하므로
   수집하지 않은 날에도 날짜가 지난 공고는 웹앱에 나오지 않고, 다음 수집 때 삭제됩니다.
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
- **수집 현황**: 사이트별 최근 수집 결과와 오류, 마지막 업로드 시각을 볼 수 있습니다.
- 단축키: `/` 검색, `j`·`k` 이동, `⏎` 원문 열기, `␣` 상세 펼치기, `[`·`]` 페이지, `s` 정렬, `m` 합치기, `t` 테마, `?` 도움말

## 명령어

| 명령 | 설명 |
|---|---|
| `python -m jdc scrape` | 지금 수집하고 Supabase에 올립니다. `--source wanted --source jumpit`처럼 일부만, `--no-details`로 상세 조회 생략, `--no-sync`로 업로드 생략 |
| `python -m jdc sync` | 로컬의 공고를 Supabase에 올립니다. Supabase의 공고를 절반 넘게 지우게 되면 멈추고, `--force`를 붙이면 진행합니다 |
| `python -m jdc grant <이메일>` | Supabase 계정에 공고 조회 권한을 줍니다 |
| `python -m jdc stats` | 사이트별 노출 중·저장된 공고 수와 최근 수집 결과 |
| `python -m jdc reindex` | 지역·검색어·중복 판단을 저장된 데이터로 다시 계산 (정규화 규칙을 고친 뒤, 다시 수집하지 않고 반영. 웹앱에는 다음 `sync` 때 반영) |

수집과 업로드가 겹치지 않도록 파일 락(`.data/scrape.lock`)을 씁니다.

## 설정

`.env.example`을 `.env`로 복사해서 바꿉니다. 모두 생략할 수 있습니다.

| 변수 | 기본값 | 설명 |
|---|---|---|
| `JDC_DATA_DIR` | `.data` | DB, 전용 Chrome 프로필, browser-harness 상태 |
| `JDC_SUPABASE_DB_URL` | 없음 | 업로드할 Supabase DB 연결 문자열. 없으면 로컬에만 저장합니다 |
| `JDC_SOURCES` | 여섯 곳 모두 | `wanted,remember,jobplanet,jumpit,saramin,jobkorea` 중 일부 |
| `JDC_CHROME_PATH` | 자동 탐색 | Chrome 실행 파일 경로 |
| `JDC_CDP_PORT` | `9333` | 전용 Chrome의 원격 디버깅 포트 |
| `JDC_HEADLESS` | `1` | `0`이면 Chrome 창을 띄워 수집 과정을 볼 수 있습니다 |
| `JDC_CLOSE_BROWSER` | `1` | 직접 띄운 Chrome을 수집 후 종료 |
| `JDC_REQUEST_DELAY` | `0.7` | 목록 요청 사이 대기(초), 실제로는 0.7~1.05초 |
| `JDC_DETAIL_CONCURRENCY` | `3` | 상세 조회 동시 요청 수 |
| `JDC_MAX_DETAILS` | `6000` | 한 번에 사이트별로 새로 받을 상세 정보 수 (남은 건 다음 수집 때) |
| `JDC_VERIFY_LIMIT` | `600` | 목록에서 빠진 공고를 사이트별로 몇 건까지 재확인할지 (리멤버는 최대 150). 일주일에 한 번 수집한다면 `2000`을 권장합니다 |

`JDC_SUPABASE_DB_URL`에는 DB 비밀번호가 들어 있습니다. `.env`는 Git에 올라가지 않으니 다른 곳에 옮겨 적지 마세요.

### 무료 플랜으로 충분한지

- **Supabase Free**: DB 500MB, 전송량 월 5GB, 활성 프로젝트 2개. 공고 약 3만 2천 건을 올린 DB 전체가 95MB이고,
  검색 한 번(50건)은 약 34KB입니다.
- **일시 정지**: Supabase 무료 프로젝트는 1주일 동안 쓰지 않으면 일시 정지됩니다. 데이터는 남아 있고
  대시보드에서 다시 켜면 됩니다. 수집하거나 웹앱을 쓰면 활동으로 칩니다.
- **Vercel Hobby**: 무료이고 개인·비상업 용도로만 쓸 수 있습니다. 정적 파일만 배포하므로 서버 사용량이 없습니다.

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
jdc/                 수집기 (Python)
  browser.py         전용 Chrome 실행 + browser-harness 탭에서 fetch 실행
  scrapers/          사이트별 수집기 (목록 페이징, 상세 조회, 응답 파싱)
  pipeline.py        수집 한 번의 흐름과 마감 공고 판단
  db.py              SQLite 저장과 병합
  sync.py            Supabase 업로드, 조회 권한 부여
  normalize.py       지역·경력·날짜·회사명 정규화
  cli.py             python -m jdc scrape | sync | grant | stats | reindex
supabase/
  migrations/        테이블, RLS, 검색 함수 (search_jobs, jobs_meta)
  seed.sql           로컬 개발용 테스트 계정 (실제 프로젝트에는 올라가지 않습니다)
viewer/              웹앱 (Next.js 정적 내보내기)
  components/        화면
  lib/               Supabase 호출, 검색 조건, 표시 형식
tests/               파서·DB·파이프라인·업로드·검색 함수 테스트
```

## 개발

로컬 Supabase는 Docker로 띄웁니다. 필요한 서비스만 켜도 됩니다. 멈출 때는 `npx supabase stop`입니다.

```bash
npx supabase start -x realtime,storage-api,imgproxy,edge-runtime,logflare,vector,mailpit,studio,postgres-meta,supavisor
```

수집기 테스트입니다. `JDC_TEST_DB_URL`이 없으면 검색 함수와 업로드 테스트는 건너뜁니다.
테스트는 트랜잭션 안에서 돌고 되돌리므로 로컬 DB의 데이터는 그대로입니다.

```bash
JDC_TEST_DB_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres .venv/bin/python -m pytest
```

로컬 데이터를 로컬 Supabase에 올립니다.

```bash
JDC_SUPABASE_DB_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres .venv/bin/python -m jdc sync
```

웹앱입니다. `viewer/.env.example`을 `viewer/.env.local`로 복사하고 `npx supabase status -o env`의 `API_URL`,
`PUBLISHABLE_KEY` 값을 넣은 뒤 실행합니다. 테스트 계정은 `supabase/seed.sql`에 있습니다.

```bash
npm --prefix viewer install
```

```bash
npm --prefix viewer run dev
```

```bash
npm --prefix viewer test
```

## 이용 안내

- 이 프로젝트는 개인이 혼자 채용공고를 찾아보기 위한 개인·학습용 도구입니다.
  각 채용 사이트와 제휴하거나 승인받은 프로젝트가 아닙니다.
- 수집되는 채용공고에 대한 권리는 각 채용 사이트와 공고를 올린 회사에 있습니다.
  수집한 데이터를 다른 사람에게 공개하거나, 재배포하거나, 서비스·영업에 쓰지 마세요.
  국내에는 경쟁 채용 사이트의 공고를 반복적으로 수집해 게재한 행위를 데이터베이스제작자의 권리 침해로 본
  판결(서울고법 2016나2019365)이 있습니다.
- 각 사이트의 이용약관과 robots.txt를 확인하고 지키는 것은 사용자의 책임입니다.
  사이트가 자동 수집을 금지하거나 중단을 요청하면 `JDC_SOURCES`에서 그 사이트를 빼세요.
- 사이트에 부담을 주지 않도록 수집은 하루 한 번 이하로 실행하세요. 요청 간격(0.7초 이상, 리멤버는 2.6초)과
  동시 요청 수(3)도 보수적으로 잡아 두었으니 낮추지 마세요.
- 웹앱은 로그인한 본인만 공고를 읽도록 되어 있습니다. 다른 사람을 허용 목록에 넣거나, RLS를 풀거나,
  공개 사이트로 바꾸지 마세요. 그렇게 하면 수집한 데이터를 다른 사람에게 제공하는 것이 됩니다.
- 코드는 있는 그대로 제공되며, 사용으로 생기는 문제에 대한 책임은 사용자에게 있습니다.

## 알아둘 점

- 사이트 구조가 바뀌면 그 사이트만 "실패"로 기록되고 나머지는 계속 수집됩니다.
  웹앱의 "수집 현황"에서 오류를 확인하고 `jdc/scrapers/<사이트>.py`를 고치면 됩니다.
- 비밀번호를 잊었다면 Supabase 대시보드의 Authentication > Users에서 바꿉니다. 웹앱에는 비밀번호 찾기가 없습니다.
- `viewer/AGENTS.md`는 `next dev`가 만들어 넣는 파일입니다. 지워도 다시 생깁니다.
- macOS + Python 3.13에서 `.venv/bin/jdc`가 `No module named 'jdc'`로 실패하면, 시스템이 `.venv` 안 파일에
  hidden 플래그를 붙여 Python이 editable 설치용 `.pth` 파일을 건너뛴 것입니다.
  프로젝트 폴더에서 `python -m jdc ...`로 실행하면 영향이 없습니다.

"""Turn each site's wording (지역, 경력, 날짜, 회사명) into comparable values."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

REGIONS = (
    "서울", "경기", "인천", "부산", "대구", "광주", "대전", "울산", "세종",
    "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
)
_REGION_ALIASES = {
    "서울특별시": "서울", "서울시": "서울",
    "경기도": "경기",
    "인천광역시": "인천", "인천시": "인천",
    "부산광역시": "부산", "부산시": "부산",
    "대구광역시": "대구", "대구시": "대구",
    "광주광역시": "광주",
    "대전광역시": "대전", "대전시": "대전",
    "울산광역시": "울산", "울산시": "울산",
    "세종특별자치시": "세종", "세종시": "세종",
    "강원도": "강원", "강원특별자치도": "강원",
    "충청북도": "충북", "충청남도": "충남",
    "전라북도": "전북", "전북특별자치도": "전북", "전라남도": "전남",
    "경상북도": "경북", "경상남도": "경남",
    "제주도": "제주", "제주특별자치도": "제주",
}
_REMOTE_WORDS = ("재택", "원격", "리모트", "remote")
_ABROAD_WORDS = (
    "해외", "아시아", "중동", "북미", "중미", "남미", "유럽", "아프리카", "오세아니아", "멕시코",
    "미국", "일본", "중국", "대만", "홍콩", "베트남", "싱가포르", "인도", "말레이시아", "태국", "필리핀",
    "캐나다", "호주", "독일", "영국", "프랑스",
)
# Addresses that skip the 시/도: only names that exist in a single region are listed.
_SEOUL_GU = (
    "강남구 강동구 강북구 관악구 광진구 구로구 금천구 노원구 도봉구 동대문구 동작구 마포구 서대문구 서초구 "
    "성동구 성북구 송파구 양천구 영등포구 용산구 은평구 종로구 중랑구"
).split()
_GYEONGGI_SI = (
    "수원시 성남시 용인시 고양시 화성시 부천시 안산시 안양시 남양주시 평택시 의정부시 시흥시 파주시 김포시 "
    "광명시 군포시 하남시 오산시 이천시 안성시 구리시 의왕시 양주시 포천시 여주시 동두천시 과천시"
).split()
_DISTRICT_REGION = {
    **{gu: "서울" for gu in _SEOUL_GU},
    **{si: "경기" for si in _GYEONGGI_SI},
}
_LANDMARKS = {"판교": "경기 성남시", "분당": "경기 성남시", "여의도": "서울 영등포구"}


def now_kst() -> datetime:
    return datetime.now(KST).replace(microsecond=0)


def today_kst() -> str:
    return now_kst().date().isoformat()


def _region_of(token: str, nxt: str) -> str | None:
    if token in REGIONS:
        return token
    if token in _REGION_ALIASES:
        return _REGION_ALIASES[token]
    # 전남광주(통합특별시): its 구 are the former 광주, its 시·군 the former 전남.
    if token.startswith("전남광주"):
        return "광주" if nxt.endswith("구") else "전남"
    if token.endswith("전체") and len(token) > 2:  # '서울전체'
        return _region_of(token[:-2], nxt)
    # Truncated forms such as '서울특별' or '부산광역'
    if token[:2] in REGIONS and token[2:4] in ("특별", "광역"):
        return token[:2]
    return None


def normalize_location(raw: str) -> tuple[str | None, str | None]:
    """'주소: 서울특별시 송파구 석촌호수로 272' -> ('서울', '서울 송파구')."""
    text = re.sub(r"\s+", " ", (raw or "").strip())
    if not text:
        return None, None
    tokens = [t.strip("():[]·") for t in re.split(r"[\s/,]+", text)]
    tokens = [t for t in tokens if t]
    for i, token in enumerate(tokens):
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if region := _region_of(token, nxt):
            district = f"{region} {nxt}" if re.fullmatch(r"[가-힣]+(구|시|군)", nxt) else None
            return region, district
    for token in tokens[:3]:
        if token in _DISTRICT_REGION:
            region = _DISTRICT_REGION[token]
            return region, f"{region} {token}"
        for landmark, district in _LANDMARKS.items():
            if token.startswith(landmark):
                return district.split(" ", 1)[0], district
    lowered = text.lower()
    if any(word in lowered for word in _REMOTE_WORDS):
        return "원격", None
    if any(word in text for word in _ABROAD_WORDS):
        return "해외", None
    if tokens and tokens[0] == "전국":
        return "전국", None
    return "기타", None


def career_from_text(text: str | None) -> tuple[int | None, int | None]:
    """Parse wording like '경력무관', '신입·경력', '경력3년↑', '경력1~3년'."""
    if not text:
        return None, None
    t = re.sub(r"\s+", "", text)
    newcomer = "신입" in t or "인턴" in t
    if re.search(r"(년수|연차|년차)무관", t):  # 경력(년수무관): experienced, any number of years
        return (0 if newcomer else 1), None
    if "무관" in t:
        return 0, None
    if m := re.search(r"(\d+)\s*[~∼-]\s*(\d+)년", t):
        lo, hi = int(m.group(1)), int(m.group(2))
        return (0 if newcomer else lo), hi
    if m := re.search(r"(\d+)년(↑|이상|\+)", t):
        return (0 if newcomer else int(m.group(1))), None
    if m := re.search(r"(\d+)년(↓|이하)", t):
        return (0 if newcomer else 1), int(m.group(1))
    if newcomer and "경력" in t:
        return 0, None
    if newcomer:
        return 0, 0
    if m := re.search(r"경력(\d+)년", t):
        n = int(m.group(1))
        return n, n
    if "경력" in t:
        return 1, None
    return None, None


def career_label(career_min: int | None, career_max: int | None, fallback: str | None = None) -> str:
    if career_min is None and career_max is None:
        return fallback or "경력 정보 없음"
    lo = career_min or 0
    if career_max is None:
        return "경력무관" if lo == 0 else f"{lo}년 이상"
    if career_max == 0:
        return "신입"
    if lo == 0:
        return f"신입~{career_max}년"
    if lo == career_max:
        return f"{lo}년"
    return f"{lo}~{career_max}년"


def to_date(value) -> str | None:
    """Accept 'YYYY-MM-DD', 'YYYY.MM.DD' or ISO datetimes; return a KST date string.

    Far-future placeholders (2069+) that sites use for 상시채용 become None.
    """
    if not value:
        return None
    text = str(value).strip()
    parsed: date | None = None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        parsed = (dt.astimezone(KST) if dt.tzinfo else dt).date()
    except ValueError:
        if m := re.match(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", text):
            parsed = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    if parsed is None or parsed.year >= 2069:
        return None
    return parsed.isoformat()


def month_day_to_date(month: int, day: int, today: date | None = None) -> str:
    """Resolve '~01/02' style deadlines to the nearest upcoming date."""
    today = today or now_kst().date()
    candidate = date(today.year, month, day)
    if candidate < today - timedelta(days=31):
        candidate = date(today.year + 1, month, day)
    return candidate.isoformat()


def deadline_from_text(text: str | None, today: date | None = None) -> str | None:
    """'~01/02(토)', '~11.13(금)', 'D-7', '오늘마감', '내일마감' -> date; 상시채용·채용시 -> None."""
    today = today or now_kst().date()
    t = (text or "").replace(" ", "")
    if "오늘마감" in t:
        return today.isoformat()
    if "내일마감" in t:
        return (today + timedelta(days=1)).isoformat()
    if m := re.search(r"D-(\d+)", t):
        return (today + timedelta(days=int(m.group(1)))).isoformat()
    if m := re.search(r"~(\d{1,2})[./](\d{1,2})", t):
        return month_day_to_date(int(m.group(1)), int(m.group(2)), today)
    return None


EMPLOYMENT = re.compile(r"정규직|계약직|인턴|프리랜서|파견직|병역특례|위촉직|아르바이트|교육생|전환형")


_COMPANY_NOISE = re.compile(
    r"\(주\)|㈜|주식회사|\(유\)|유한회사|\(재\)|재단법인|\(사\)|사단법인"
    r"|\bco\.,?\s*ltd\b\.?|\binc\b\.?|\bcorp\b\.?|\bcorporation\b",
    re.I,
)
_NON_WORD = re.compile(r"[^0-9a-z가-힣]+")


def dedupe_key(company: str, title: str) -> str:
    """Same company + same title on different sites collapse into one result."""
    c = _NON_WORD.sub("", _COMPANY_NOISE.sub("", (company or "").lower()))
    t = _NON_WORD.sub("", (title or "").lower())
    return f"{c}|{t}"


def unique(items) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        item = (item or "").strip()
        key = item.casefold()
        if item and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def fold(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").casefold()).strip()

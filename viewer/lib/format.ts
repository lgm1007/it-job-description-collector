// Display helpers. Free of app imports so `node --test` can load them directly.

export const SOURCES = [
  { key: "wanted", label: "원티드" },
  { key: "remember", label: "리멤버" },
  { key: "jobplanet", label: "잡플래닛" },
  { key: "jumpit", label: "점핏" },
  { key: "saramin", label: "사람인" },
  { key: "jobkorea", label: "잡코리아" },
];

export const REGION_ORDER = [
  "서울", "경기", "인천", "부산", "대구", "광주", "대전", "울산", "세종",
  "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
];

/** Hiring steps as public.jobs.process stores them, in display order. */
export const STEPS = [
  { key: "coding", label: "코딩테스트" },
  { key: "assignment", label: "사전과제" },
  { key: "interview1", label: "1차면접" },
  { key: "interview2", label: "2차면접" },
  { key: "reference", label: "레퍼런스체크" },
];

export const stepLabel = (key: string) => STEPS.find((s) => s.key === key)?.label ?? key;

/** '1차면접 · 2차면접 (없음: 코딩테스트, 사전과제, 레퍼런스체크)'; null means the posting doesn't say. */
export function processText(process: string[] | null): string {
  if (process === null) return "알 수 없음 (공고에 채용 절차가 적혀 있지 않습니다)";
  const has = STEPS.filter((s) => process.includes(s.key)).map((s) => s.label);
  const lacks = STEPS.filter((s) => !process.includes(s.key)).map((s) => s.label);
  if (!has.length) return `${lacks.join(", ")} 없음`;
  return lacks.length ? `${has.join(" · ")} (없음: ${lacks.join(", ")})` : has.join(" · ");
}

const looseKey = (s: string) => s.toLowerCase().replace(/[^0-9a-z가-힣+#]/g, "");

// 'springboot' is Spring and 'postgres' PostgreSQL, but 'c++' is not C.
const sameStack = (a: string, b: string) => {
  const [short, long] = a.length <= b.length ? [a, b] : [b, a];
  return short === long || (short.length >= 2 && long.startsWith(short) && /^[a-z]+$/.test(long.slice(short.length)));
};

/** The site's own tags that aren't one of the stacks, such as 유지보수 or SI개발. 'Spring Boot' counts as Spring. */
export function otherTags(skills: string[], stacks: string[]): string[] {
  const keys = stacks.map(looseKey);
  return skills.filter((skill) => !keys.some((key) => sameStack(looseKey(skill), key)));
}

export const sourceLabel = (key: string) => SOURCES.find((s) => s.key === key)?.label ?? key;

const pad = (n: number) => String(n).padStart(2, "0");

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const t = new Date(iso);
  return `${pad(t.getMonth() + 1)}.${pad(t.getDate())} ${pad(t.getHours())}:${pad(t.getMinutes())}`;
}

export function careerShort(min: number | null, max: number | null): string {
  if (min === null && max === null) return "—";
  const lo = min ?? 0;
  if (max === null) return lo === 0 ? "무관" : `${lo}년↑`;
  if (max === 0) return "신입";
  if (lo === 0) return `~${max}년`;
  return lo === max ? `${lo}년` : `${lo}~${max}년`;
}

export function dueLabel(daysLeft: number | null, deadline: string | null): { text: string; cls: string; title: string } {
  if (daysLeft === null) return { text: "상시", cls: "always", title: "상시채용 / 채용 시 마감" };
  if (daysLeft === 0) return { text: "오늘", cls: "soon", title: `${deadline} 마감` };
  const cls = daysLeft <= 3 ? "soon" : daysLeft <= 7 ? "week" : "";
  return { text: `D-${daysLeft}`, cls, title: `${deadline} 마감` };
}

/** Links come from scraped pages, so only ever open web addresses. */
export function safeHref(url: string): string | undefined {
  return /^https?:\/\//i.test(url) ? url : undefined;
}

export const toggled = <T,>(list: T[], value: T): T[] =>
  list.includes(value) ? list.filter((v) => v !== value) : [...list, value];

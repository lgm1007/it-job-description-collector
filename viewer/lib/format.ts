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

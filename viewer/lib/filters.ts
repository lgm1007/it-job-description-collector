// The search conditions, kept in the URL so a search can be bookmarked and the back button works.

export type Filters = {
  q: string;
  exclude: string;
  titleOnly: boolean;
  years: string; // "" means any
  region: string[];
  district: string[];
  source: string[]; // empty means all
  days: string; // "" means any
  sort: "latest" | "deadline";
  dedupe: boolean;
  page: number;
};

export const NO_FILTERS: Filters = {
  q: "",
  exclude: "",
  titleOnly: false,
  years: "",
  region: [],
  district: [],
  source: [],
  days: "",
  sort: "latest",
  dedupe: true,
  page: 1,
};

export function parseFilters(search: string): Filters {
  const p = new URLSearchParams(search);
  const list = (key: string) =>
    (p.get(key) ?? "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  return {
    q: p.get("q") ?? "",
    exclude: p.get("exclude") ?? "",
    titleOnly: p.get("title_only") === "1",
    years: p.get("years") ?? "",
    region: list("region"),
    district: list("district"),
    source: list("source"),
    days: p.get("days") ?? "",
    sort: p.get("sort") === "deadline" ? "deadline" : "latest",
    dedupe: p.get("dedupe") !== "0",
    page: Math.max(1, parseInt(p.get("page") ?? "1", 10) || 1),
  };
}

export function filtersToQuery(f: Filters): string {
  const p = new URLSearchParams();
  if (f.q) p.set("q", f.q);
  if (f.exclude) p.set("exclude", f.exclude);
  if (f.titleOnly) p.set("title_only", "1");
  if (f.years !== "") p.set("years", f.years);
  if (f.region.length) p.set("region", f.region.join(","));
  if (f.district.length) p.set("district", f.district.join(","));
  if (f.source.length) p.set("source", f.source.join(","));
  if (f.days) p.set("days", f.days);
  if (f.sort !== "latest") p.set("sort", f.sort);
  if (!f.dedupe) p.set("dedupe", "0");
  if (f.page > 1) p.set("page", String(f.page));
  return p.toString();
}

/** The arguments of public.search_jobs. */
export function searchArgs(f: Filters, size: number) {
  return {
    p_q: f.q || null,
    p_exclude: f.exclude || null,
    p_title_only: f.titleOnly,
    p_regions: f.region.length ? f.region : null,
    p_districts: f.district.length ? f.district : null,
    p_years: f.years === "" ? null : Number(f.years),
    p_sources: f.source.length ? f.source : null,
    p_days: f.days ? Number(f.days) : null,
    p_sort: f.sort,
    p_dedupe: f.dedupe,
    p_page: f.page,
    p_size: size,
  };
}

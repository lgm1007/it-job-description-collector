// The shapes returned by the Postgres functions in supabase/migrations.

export type OtherCopy = { id: number; source: string; url: string };

export type Job = {
  id: number;
  source: string;
  url: string;
  title: string;
  company: string;
  location: string;
  career: string;
  career_min: number | null;
  career_max: number | null;
  skills: string[];
  categories: string[];
  deadline: string | null;
  days_left: number | null;
  listed_at: string | null;
  is_new: boolean;
  also_on: OtherCopy[];
};

export type SearchResult = { total: number; page: number; size: number; items: Job[] };

export type JobDetail = {
  id: number;
  url: string;
  company: string;
  locations: string[];
  location_text: string;
  career: string;
  skills: string[];
  categories: string[];
  employment_type: string | null;
  deadline: string | null;
  posted_at: string | null;
  description: string | null;
};

export type Facet = { name: string; count: number };

export type Run = {
  source: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  listed: number;
  added: number;
  closed: number;
  error: string | null;
};

export type Meta = {
  viewer: boolean;
  total: number;
  unique_total: number;
  sources: Record<string, number>;
  regions: Facet[];
  districts: Record<string, Facet[]>;
  runs: Run[];
  synced_at: string | null;
};

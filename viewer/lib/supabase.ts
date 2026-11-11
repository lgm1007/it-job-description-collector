import { createClient } from "@supabase/supabase-js";

import { type Filters, searchArgs } from "./filters";
import type { JobDetail, Meta, SearchResult } from "./types";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;

// The publishable key is meant to be public: row level security decides who reads what.
export const supabase = url && key ? createClient(url, key) : null;

function client() {
  if (!supabase) throw new Error("Supabase 설정이 없습니다");
  return supabase;
}

export const PAUSED_HINT = "1주일 넘게 쓰지 않았다면 Supabase 대시보드에서 프로젝트를 다시 켜 주세요.";

export async function searchJobs(filters: Filters, size: number): Promise<SearchResult> {
  const { data, error } = await client().rpc("search_jobs", searchArgs(filters, size));
  if (error) throw new Error(error.message);
  return data as SearchResult;
}

export async function fetchMeta(): Promise<Meta> {
  const { data, error } = await client().rpc("jobs_meta");
  if (error) throw new Error(error.message);
  return data as Meta;
}

export async function fetchJob(id: number): Promise<JobDetail> {
  const { data, error } = await client()
    .from("jobs")
    .select("id, url, company, locations, location_text, career, skills, categories, employment_type, deadline, posted_at, description")
    .eq("id", id)
    .single();
  if (error) throw new Error(error.message);
  return data as JobDetail;
}

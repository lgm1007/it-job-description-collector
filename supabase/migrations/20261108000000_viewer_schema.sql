-- The viewing copy of the job postings.
--
-- The collector on the MacBook owns this data: it connects as the database owner (RLS does not
-- apply) and mirrors its local SQLite here after each scrape. The web app only reads, as a
-- signed-in account on the allow-list below. The publishable key is public by design, so these
-- policies are what keep the data private; nothing is readable without being on the list.

create schema private;
revoke all on schema private from public;
grant usage on schema private to authenticated;

-- Accounts allowed to read. Kept outside the API-exposed schemas, and checked even though sign-ups
-- are turned off, so a sign-up setting left on by mistake exposes nothing.
create table private.viewers (
  user_id uuid primary key references auth.users (id) on delete cascade
);

create table public.jobs (
  id bigint generated always as identity primary key,
  source text not null,
  source_id text not null,
  -- Which copy represents a posting that appears on several sites: the lowest wins.
  source_rank integer generated always as (
    coalesce(array_position(array['wanted', 'remember', 'jumpit', 'jobplanet', 'saramin', 'jobkorea'], source), 9)
  ) stored,
  url text not null,
  title text not null,
  company text not null,
  locations text[] not null default '{}',
  location_text text not null default '',
  regions text[] not null default '{}',
  districts text[] not null default '{}',
  career_min integer,
  career_max integer,
  career text not null default '',
  skills text[] not null default '{}',
  categories text[] not null default '{}',
  employment_type text,
  deadline date,                          -- inclusive; null means no fixed deadline
  posted_at date,
  listed_at date,                         -- posted_at, or the day the collector first saw it
  description text,
  title_text text not null default '',    -- case-folded title, company, skills, categories
  search_text text not null default '',   -- the above plus employment type and description
  dedupe_key text not null,               -- same company + title on different sites
  content_hash text not null,             -- lets the collector upload only what changed
  unique (source, source_id)
);
create index jobs_dedupe_key_idx on public.jobs (dedupe_key);

-- The latest scrape of each site.
create table public.scrape_runs (
  source text primary key,
  status text not null,                   -- ok | partial | failed
  started_at timestamptz not null,
  finished_at timestamptz,
  listed integer not null default 0,
  added integer not null default 0,
  closed integer not null default 0,      -- postings deleted as closed
  error text
);

create table public.sync_state (
  id boolean primary key default true check (id),  -- a single row
  synced_at timestamptz not null
);

-- -- access ---------------------------------------------------------------------------------

create function private.is_viewer() returns boolean
language sql stable security definer set search_path = ''
as $$
  select exists (select 1 from private.viewers where user_id = auth.uid());
$$;

alter table public.jobs enable row level security;
alter table public.scrape_runs enable row level security;
alter table public.sync_state enable row level security;

create policy "viewers can read" on public.jobs
  for select to authenticated using ((select private.is_viewer()));
create policy "viewers can read" on public.scrape_runs
  for select to authenticated using ((select private.is_viewer()));
create policy "viewers can read" on public.sync_state
  for select to authenticated using ((select private.is_viewer()));

revoke all on public.jobs, public.scrape_runs, public.sync_state from anon, authenticated;
revoke all on sequence public.jobs_id_seq from anon, authenticated;
grant select on public.jobs, public.scrape_runs, public.sync_state to authenticated;

-- -- search helpers -----------------------------------------------------------------------

-- Posting dates and deadlines are Korean calendar days.
create function private.today_kst() returns date
language sql stable set search_path = ''
as $$
  select (now() at time zone 'Asia/Seoul')::date;
$$;

-- Splits a query into terms that must each match. Korean and longer terms match as plain
-- substrings, which Korean text with attached particles needs. Short ASCII terms match as whole
-- words, so 'go' skips 'google'; 'java' is the one longer term that needs it, to skip 'javascript'.
create function private.search_terms(query text)
returns table (like_pattern text, regex text)
language sql immutable set search_path = ''
as $$
  select
    '%' || replace(replace(replace(term, '\', '\\'), '%', '\%'), '_', '\_') || '%',
    case
      when octet_length(term) <> char_length(term) then null
      when char_length(term) <= 3 then
        '(?<![a-z0-9])' || regexp_replace(term, '([^a-z0-9])', '\\\1', 'g') || '(?![a-z0-9+#])'
      when term = 'java' then 'java(?!script)'
    end
  from unnest(string_to_array(btrim(regexp_replace(lower(coalesce(query, '')), '[[:space:],]+', ' ', 'g')), ' ')) as term;
$$;

-- -- what the web app calls ---------------------------------------------------------------

create function public.search_jobs(
  p_q text default null,
  p_exclude text default null,
  p_title_only boolean default false,
  p_regions text[] default null,
  p_districts text[] default null,
  p_years integer default null,
  p_sources text[] default null,
  p_days integer default null,            -- only postings listed within the last N days
  p_sort text default 'latest',           -- latest | deadline
  p_dedupe boolean default true,
  p_page integer default 1,
  p_size integer default 30
) returns jsonb
language plpgsql stable set search_path = ''
as $$
declare
  today date := private.today_kst();
  page_no integer := greatest(coalesce(p_page, 1), 1);
  page_size integer := least(greatest(coalesce(p_size, 30), 1), 100);
  result jsonb;
begin
  with wanted as materialized (
    select * from private.search_terms(p_q)
  ), unwanted as materialized (
    select * from private.search_terms(p_exclude)
  ), filtered as materialized (
    select j.id, j.source, j.source_rank, j.url, j.title, j.company, j.location_text, j.career, j.career_min, j.career_max,
           j.skills, j.categories, j.deadline, j.listed_at, j.dedupe_key
    from public.jobs j
    where (j.deadline is null or j.deadline >= today)
      and (coalesce(cardinality(p_sources), 0) = 0 or j.source = any (p_sources))
      and (coalesce(cardinality(p_regions), 0) = 0 or j.regions && p_regions)
      and (coalesce(cardinality(p_districts), 0) = 0 or j.districts && p_districts)
      and (p_years is null or ((j.career_min is null or j.career_min <= p_years)
                               and (j.career_max is null or j.career_max >= p_years)))
      and (coalesce(p_days, 0) <= 0 or j.listed_at >= today - p_days)
      and not exists (
        select 1 from wanted t, lateral (
          select case when p_title_only then j.title_text else j.search_text end as haystack
        ) h
        where not (h.haystack like t.like_pattern and (t.regex is null or h.haystack ~ t.regex))
      )
      and not exists (
        select 1 from unwanted x
        where j.title_text like x.like_pattern and (x.regex is null or j.title_text ~ x.regex)
      )
  ), ranked as materialized (
    select f.*, row_number() over (
      partition by case when p_dedupe then f.dedupe_key else f.id::text end
      order by f.source_rank, f.id
    ) as copy_rank
    from filtered f
  ), page_rows as (
    select r.*, row_number() over (
      order by case when p_sort = 'deadline' then r.deadline end nulls last, r.listed_at desc nulls last, r.id desc
    ) as position
    from ranked r
    where r.copy_rank = 1
    order by position
    limit page_size offset (page_no - 1) * page_size
  )
  select jsonb_build_object(
    'total', (select count(*) from ranked where copy_rank = 1),
    'page', page_no,
    'size', page_size,
    'items', coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', p.id,
        'source', p.source,
        'url', p.url,
        'title', p.title,
        'company', p.company,
        'location', p.location_text,
        'career', p.career,
        'career_min', p.career_min,
        'career_max', p.career_max,
        'skills', p.skills,
        'categories', p.categories,
        'deadline', p.deadline,
        'days_left', p.deadline - today,
        'listed_at', p.listed_at,
        'is_new', coalesce(p.listed_at >= today - 2, false),
        'also_on', coalesce(a.also_on, '[]'::jsonb)
      ) order by p.position)
      from page_rows p
      left join lateral (
        select jsonb_agg(jsonb_build_object('id', o.id, 'source', o.source, 'url', o.url)
                         order by o.source_rank, o.id) as also_on
        from public.jobs o
        where p_dedupe and o.dedupe_key = p.dedupe_key and o.id <> p.id
          and (o.deadline is null or o.deadline >= today)
      ) a on true
    ), '[]'::jsonb)
  ) into result;
  return result;
end;
$$;

-- Counts for the filter panel, and the state of the last scrape.
create function public.jobs_meta() returns jsonb
language sql stable set search_path = ''
as $$
  with visible as materialized (
    select source, regions, districts, dedupe_key
    from public.jobs
    where deadline is null or deadline >= private.today_kst()
  ), district_counts as (
    select d.name, split_part(d.name, ' ', 1) as region, count(*) as n
    from visible v cross join lateral unnest(v.districts) as d(name)
    group by d.name
  )
  select jsonb_build_object(
    'viewer', private.is_viewer(),
    'total', (select count(*) from visible),
    'unique_total', (select count(distinct dedupe_key) from visible),
    'sources', coalesce((
      select jsonb_object_agg(c.source, c.n)
      from (select source, count(*) as n from visible group by source) c
    ), '{}'::jsonb),
    'regions', coalesce((
      select jsonb_agg(jsonb_build_object('name', c.name, 'count', c.n) order by c.n desc, c.name)
      from (
        select r.name, count(*) as n
        from visible v cross join lateral unnest(v.regions) as r(name)
        group by r.name
      ) c
    ), '[]'::jsonb),
    'districts', coalesce((
      select jsonb_object_agg(c.region, c.items)
      from (
        select region, jsonb_agg(jsonb_build_object('name', name, 'count', n) order by n desc, name) as items
        from district_counts
        group by region
      ) c
    ), '{}'::jsonb),
    'runs', coalesce((
      select jsonb_agg(to_jsonb(r) order by r.source) from public.scrape_runs r
    ), '[]'::jsonb),
    'synced_at', (select synced_at from public.sync_state)
  );
$$;

revoke all on function private.is_viewer(), private.today_kst(), private.search_terms(text) from public, anon;
grant execute on function private.is_viewer(), private.today_kst(), private.search_terms(text) to authenticated;

revoke all on function
  public.search_jobs(text, text, boolean, text[], text[], integer, text[], integer, text, boolean, integer, integer),
  public.jobs_meta()
  from public, anon;
grant execute on function
  public.search_jobs(text, text, boolean, text[], text[], integer, text[], integer, text, boolean, integer, integer),
  public.jobs_meta()
  to authenticated;

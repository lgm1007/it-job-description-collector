-- Filters by tech stack and by hiring step (issue #1).
--
-- Both are worked out by the collector (jdc/stacks.py, jdc/hiring.py) and uploaded as is.
--
-- No new indexes: search_jobs reads every visible row in one pass anyway (keyword matching needs
-- it), each condition is written so an empty filter switches it off, which keeps the planner from
-- using a GIN index on these arrays, and the table holds a few tens of thousands of rows.

alter table public.jobs
  add column stacks text[] not null default '{}',  -- one spelling per technology: 'Spring', 'Node.js'
  -- Steps the hiring process includes: coding | assignment | interview1 | interview2 | reference.
  -- Null when the posting doesn't describe its process; '{}' when it does and has none of them.
  add column process text[];

-- -- what the web app calls ---------------------------------------------------------------

drop function public.search_jobs(text, text, boolean, text[], text[], integer, text[], integer, text, boolean, integer, integer);

create function public.search_jobs(
  p_q text default null,
  p_exclude text default null,
  p_title_only boolean default false,
  p_regions text[] default null,
  p_districts text[] default null,
  p_years integer default null,
  p_sources text[] default null,
  p_days integer default null,            -- only postings listed within the last N days
  p_stacks text[] default null,           -- postings using any of these
  p_steps text[] default null,            -- postings whose process includes all of these
  p_no_steps text[] default null,         -- postings whose process is known and includes none of these
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
           j.skills, j.stacks, j.categories, j.deadline, j.listed_at, j.dedupe_key
    from public.jobs j
    where (j.deadline is null or j.deadline >= today)
      and (coalesce(cardinality(p_sources), 0) = 0 or j.source = any (p_sources))
      and (coalesce(cardinality(p_regions), 0) = 0 or j.regions && p_regions)
      and (coalesce(cardinality(p_districts), 0) = 0 or j.districts && p_districts)
      and (p_years is null or ((j.career_min is null or j.career_min <= p_years)
                               and (j.career_max is null or j.career_max >= p_years)))
      and (coalesce(p_days, 0) <= 0 or j.listed_at >= today - p_days)
      and (coalesce(cardinality(p_stacks), 0) = 0 or j.stacks && p_stacks)
      and (coalesce(cardinality(p_steps), 0) = 0 or j.process @> p_steps)
      and (coalesce(cardinality(p_no_steps), 0) = 0 or (j.process is not null and not (j.process && p_no_steps)))
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
        'stacks', p.stacks,
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
create or replace function public.jobs_meta() returns jsonb
language sql stable set search_path = ''
as $$
  with visible as materialized (
    select source, regions, districts, stacks, process, dedupe_key
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
    'stacks', coalesce((
      select jsonb_agg(jsonb_build_object('name', c.name, 'count', c.n) order by c.n desc, c.name)
      from (
        select s.name, count(*) as n
        from visible v cross join lateral unnest(v.stacks) as s(name)
        group by s.name
      ) c
    ), '[]'::jsonb),
    -- 'known': postings that describe their process; 'steps': how many of those include each step.
    'process', jsonb_build_object(
      'known', (select count(*) from visible where process is not null),
      'steps', coalesce((
        select jsonb_object_agg(c.name, c.n)
        from (
          select s.name, count(*) as n
          from visible v cross join lateral unnest(v.process) as s(name)
          group by s.name
        ) c
      ), '{}'::jsonb)
    ),
    'runs', coalesce((
      select jsonb_agg(to_jsonb(r) order by r.source) from public.scrape_runs r
    ), '[]'::jsonb),
    'synced_at', (select synced_at from public.sync_state)
  );
$$;

revoke all on function
  public.search_jobs(text, text, boolean, text[], text[], integer, text[], integer, text[], text[], text[], text, boolean, integer, integer)
  from public, anon;
grant execute on function
  public.search_jobs(text, text, boolean, text[], text[], integer, text[], integer, text[], text[], text[], text, boolean, integer, integer)
  to authenticated;

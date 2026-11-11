"use client";

import { type ReactNode, useEffect, useState } from "react";

import { careerShort, dueLabel, safeHref, sourceLabel } from "@/lib/format";
import { fetchJob } from "@/lib/supabase";
import type { Job, JobDetail } from "@/lib/types";

function ExternalLink({ url, className, style, children }: { url: string; className?: string; style?: React.CSSProperties; children: ReactNode }) {
  return (
    <a className={className} style={style} href={safeHref(url)} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  );
}

function Detail({ job }: { job: Job }) {
  const [data, setData] = useState<JobDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    fetchJob(job.id).then(
      (detail) => live && setData(detail),
      (e: Error) => live && setError(e.message),
    );
    return () => {
      live = false;
    };
  }, [job.id]);

  if (error) return <>상세 정보를 불러오지 못했습니다 ({error}).</>;
  if (!data) return <>불러오는 중…</>;

  const rows: [string, ReactNode][] = [
    ["url", <ExternalLink key="url" url={data.url}>{data.url}</ExternalLink>],
    ["company", data.company],
    ["location", data.locations.length ? data.locations.join(" / ") : data.location_text],
    ["exp", data.career],
    ["type", data.employment_type],
    ["posted", data.posted_at],
    ["deadline", data.deadline ? `${data.deadline} (${dueLabel(job.days_left, job.deadline).text})` : "상시채용"],
    ["stack", data.skills.join(", ")],
    ["role", data.categories.join(", ")],
  ];
  return (
    <>
      <dl className="kv">
        {rows
          .filter(([, value]) => value)
          .map(([key, value]) => (
            <div key={key} className="kv-row">
              <dt>{key}</dt>
              <dd>{value}</dd>
            </div>
          ))}
      </dl>
      <pre className="desc">{data.description || "저장된 상세 설명이 없습니다. 원문 공고에서 확인해 주세요."}</pre>
    </>
  );
}

export default function JobRow({ job, selected, open, onClick }: { job: Job; selected: boolean; open: boolean; onClick: () => void }) {
  const due = dueLabel(job.days_left, job.deadline);
  const stack = (job.skills.length ? job.skills : job.categories).slice(0, 6);
  // Stays mounted once opened, so closing and reopening doesn't fetch again.
  const [everOpened, setEverOpened] = useState(open);
  if (open && !everOpened) setEverOpened(true);

  return (
    <li
      className={`row${selected ? " sel" : ""}`}
      onClick={(e) => {
        if (!(e.target as Element).closest("a")) onClick();
      }}
    >
      <div className="line">
        <span className="src" style={{ color: `var(--src-${job.source})` }} title={sourceLabel(job.source)}>
          {job.source}
        </span>
        <span className="new">{job.is_new ? "new" : ""}</span>
        <span className={`due ${due.cls}`} title={due.title}>
          {due.text}
        </span>
        <span className="pos" title={job.title}>
          <ExternalLink url={job.url} className="title">
            {job.title}
          </ExternalLink>
          <span className="stack">{stack.map((s) => s.toLowerCase()).join(" · ")}</span>
        </span>
        <span className="co" title={job.company}>
          {job.company}
        </span>
        <span className="loc">{job.location || "—"}</span>
        <span className="exp" title={job.career}>
          {careerShort(job.career_min, job.career_max)}
        </span>
      </div>
      {job.also_on.length > 0 && (
        <div className="also">
          └ also
          {job.also_on.map((other) => (
            <ExternalLink key={other.id} url={other.url} style={{ color: `var(--src-${other.source})` }}>
              {other.source}
            </ExternalLink>
          ))}
        </div>
      )}
      {everOpened && (
        <div className="detail" hidden={!open}>
          <Detail job={job} />
        </div>
      )}
    </li>
  );
}

"use client";

import { useCallback, useEffect, useEffectEvent, useRef, useState } from "react";

import { type Filters, filtersToQuery, NO_FILTERS, parseFilters } from "@/lib/filters";
import { fmtDateTime } from "@/lib/format";
import { fetchMeta, PAUSED_HINT, searchJobs, supabase } from "@/lib/supabase";
import { toggleTheme } from "@/lib/theme";
import type { Job, Meta } from "@/lib/types";

import { HelpDialog, RunsDialog } from "./Dialogs";
import FilterPanel from "./FilterPanel";
import JobRow from "./JobRow";
import Pager from "./Pager";
import QueryEcho from "./QueryEcho";

const PAGE_SIZE = 50;
const STALE_AFTER_MS = 10 * 60 * 1000; // an app left open on a phone picks up new scrapes on return

type List = { jobs: Job[]; total: number; seq: number };

export default function JobsApp({ email }: { email?: string }) {
  const [filters, setFilters] = useState<Filters>(() => parseFilters(window.location.search));
  const [meta, setMeta] = useState<Meta | null>(null);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [list, setList] = useState<List | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [cursor, setCursor] = useState(-1);
  const [expanded, setExpanded] = useState<ReadonlySet<number>>(new Set());
  const [panelOpen, setPanelOpen] = useState(false);
  const [dataVersion, setDataVersion] = useState(0);

  const filtersRef = useRef(filters); // a debounced input may commit after other conditions changed
  const requestSeq = useRef(0);
  const selectAfterLoad = useRef(-1);
  const scrollToCursor = useRef(false);
  const lastLoaded = useRef(0);
  const runsDialog = useRef<HTMLDialogElement>(null);
  const helpDialog = useRef<HTMLDialogElement>(null);

  const jobs = list?.jobs ?? [];
  const total = list?.total ?? 0;
  const pages = Math.ceil(total / PAGE_SIZE);

  const update = useCallback((patch: Partial<Filters>, keepCursor = false) => {
    const next = { ...filtersRef.current, ...patch };
    if (!("page" in patch)) next.page = 1;
    filtersRef.current = next;
    const query = filtersToQuery(next);
    window.history.pushState(null, "", query ? `?${query}` : window.location.pathname);
    selectAfterLoad.current = keepCursor ? 0 : -1;
    setFilters(next);
  }, []);

  useEffect(() => {
    const onPopState = () => {
      const next = parseFilters(window.location.search);
      filtersRef.current = next;
      selectAfterLoad.current = -1;
      setFilters(next);
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    const seq = ++requestSeq.current;
    searchJobs(filters, PAGE_SIZE).then(
      (data) => {
        if (seq !== requestSeq.current) return; // a newer search is already on its way
        lastLoaded.current = Date.now();
        setList({ jobs: data.items, total: data.total, seq });
        setListError(null);
        setExpanded(new Set());
        const selectAfter = data.items.length ? selectAfterLoad.current : -1;
        scrollToCursor.current = selectAfter >= 0;
        selectAfterLoad.current = -1;
        setCursor(selectAfter);
      },
      (e: Error) => {
        if (seq !== requestSeq.current) return;
        setList({ jobs: [], total: 0, seq });
        setListError(e.message);
      },
    );
  }, [filters, dataVersion]);

  useEffect(() => {
    fetchMeta().then(
      (data) => {
        setMeta(data);
        setMetaError(null);
      },
      (e: Error) => setMetaError(e.message),
    );
  }, [dataVersion]);

  useEffect(() => {
    const onVisible = () => {
      if (!document.hidden && Date.now() - lastLoaded.current > STALE_AFTER_MS) setDataVersion((v) => v + 1);
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, []);

  useEffect(() => {
    if (!scrollToCursor.current) return;
    scrollToCursor.current = false;
    document.querySelector(".row.sel")?.scrollIntoView({ block: "nearest" });
  }, [cursor, list]);

  function select(index: number, scroll = false) {
    if (!jobs.length) return;
    scrollToCursor.current = scroll;
    setCursor(Math.max(0, Math.min(jobs.length - 1, index)));
  }

  function toggleDetail(index: number, force?: boolean) {
    const job = jobs[index];
    if (!job) return;
    setExpanded((current) => {
      const next = new Set(current);
      if (force ?? !next.has(job.id)) next.add(job.id);
      else next.delete(job.id);
      return next;
    });
  }

  function goPage(page: number) {
    if (page < 1 || page > pages || page === filters.page) return;
    update({ page }, true);
    window.scrollTo({ top: 0 });
  }

  function openOriginal() {
    const job = jobs[cursor];
    if (job) window.open(job.url, "_blank", "noopener");
  }

  const onKey = useEffectEvent((e: KeyboardEvent) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const target = e.target instanceof Element ? e.target : null;
    const typing = !!target?.matches("input, textarea, select");
    if (e.key === "Escape") {
      if (typing) (target as HTMLElement).blur();
      setPanelOpen(false);
      return;
    }
    if (typing) {
      if (e.key === "Enter" && (target as HTMLInputElement).type === "search") {
        (target as HTMLElement).blur();
        setPanelOpen(false);
        selectAfterLoad.current = 0; // if results are still on their way, select in those
        select(0, true);
      }
      return;
    }
    if (document.querySelector("dialog[open]")) return;
    // Enter/Space on a focused button or link should press it, not act on the selected row.
    if ((e.key === "Enter" || e.key === " ") && target?.closest("button, a")) return;
    const selected = cursor >= 0;
    const keys: Record<string, () => void> = {
      "/": () => document.getElementById("q")?.focus(),
      j: () => select(cursor + 1, true),
      ArrowDown: () => select(cursor + 1, true),
      k: () => select(cursor - 1, true),
      ArrowUp: () => select(cursor - 1, true),
      Enter: () => selected && openOriginal(),
      o: () => selected && openOriginal(),
      " ": () => selected && toggleDetail(cursor),
      l: () => selected && toggleDetail(cursor, true),
      ArrowRight: () => selected && toggleDetail(cursor, true),
      h: () => selected && toggleDetail(cursor, false),
      ArrowLeft: () => selected && toggleDetail(cursor, false),
      "]": () => goPage(filters.page + 1),
      "[": () => goPage(filters.page - 1),
      s: () => update({ sort: filters.sort === "latest" ? "deadline" : "latest" }),
      m: () => update({ dedupe: !filters.dedupe }),
      t: toggleTheme,
      "?": () => helpDialog.current?.showModal(),
    };
    const action = keys[e.key];
    if (!action) return;
    e.preventDefault();
    action();
  });

  // Subscribed once: replacing the listener while a key press is being handled would lose that key,
  // because React handles events on the same `document` and renders before this listener's turn.
  useEffect(() => {
    const listener = (e: KeyboardEvent) => onKey(e);
    document.addEventListener("keydown", listener);
    return () => document.removeEventListener("keydown", listener);
  }, []);

  const runs = meta?.runs ?? [];
  const finished = runs
    .map((r) => r.finished_at)
    .filter(Boolean)
    .sort()
    .pop();
  const failed = runs.some((r) => r.status === "failed") || !!metaError;
  const statusText = metaError ? "연결 오류" : !meta ? "connecting…" : finished ? `최근 수집 ${fmtDateTime(finished)}` : "아직 수집 전";

  const from = total ? (filters.page - 1) * PAGE_SIZE + 1 : 0;
  const emptyText = listError
    ? `error: 공고를 불러오지 못했습니다 (${listError}). ${PAUSED_HINT}`
    : meta && !meta.viewer
      ? "이 계정에는 조회 권한이 없습니다. 맥북에서 python -m jdc grant <이메일>을 실행해 주세요."
      : meta && meta.total === 0
        ? "아직 올라온 공고가 없습니다. 맥북에서 python -m jdc scrape를 실행해 주세요."
        : list
          ? "no match — 조건에 맞는 공고가 없습니다."
          : "불러오는 중…";

  return (
    <>
      <div className="app">
        <FilterPanel
          filters={filters}
          meta={meta}
          open={panelOpen}
          email={email}
          onChange={update}
          onReset={() => update(NO_FILTERS)}
          onClose={() => setPanelOpen(false)}
          onLogout={() => supabase?.auth.signOut()}
        />
        {panelOpen && <button type="button" className="scrim only-mobile" aria-label="검색 조건 닫기" onClick={() => setPanelOpen(false)} />}

        <main className="main">
          <header className="cmdline">
            <button type="button" className="ghost only-mobile" aria-label="검색 조건" onClick={() => setPanelOpen(true)}>
              ≡
            </button>
            <QueryEcho filters={filters} />
            <span className="hits">
              <b>{total.toLocaleString()}</b> hits
            </span>
          </header>

          <div className="listbar">
            <span className="dim">
              {jobs.length > 0 &&
                `${from.toLocaleString()}–${(from + jobs.length - 1).toLocaleString()} 표시${filters.dedupe ? " · 여러 사이트의 같은 공고는 한 줄로" : ""}`}
            </span>
            <div className="listbar-right">
              <label className="flag">
                <input type="checkbox" checked={filters.dedupe} onChange={(e) => update({ dedupe: e.target.checked })} /> 같은 공고 합치기
              </label>
              <div className="seg">
                {(["latest", "deadline"] as const).map((sort) => (
                  <button key={sort} type="button" aria-pressed={filters.sort === sort} onClick={() => update({ sort })}>
                    {sort === "latest" ? "최신순" : "마감순"}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="colhead line" aria-hidden="true">
            <span>site</span>
            <span></span>
            <span>due</span>
            <span>position</span>
            <span>company</span>
            <span>location</span>
            <span className="exp">exp</span>
          </div>
          <ol className="rows">
            {jobs.map((job, index) => (
              <JobRow
                key={`${list?.seq}-${job.id}`}
                job={job}
                selected={index === cursor}
                open={expanded.has(job.id)}
                onClick={() => {
                  select(index);
                  toggleDetail(index);
                }}
              />
            ))}
          </ol>
          {jobs.length === 0 && <p className="empty">{emptyText}</p>}
          <Pager page={filters.page} pages={pages} onGo={goPage} />
        </main>
      </div>

      <footer className={`statusbar${failed ? " failed" : ""}`}>
        <span className="st">
          {statusText}
          {meta && <span className="only-desktop total">· 공고 {meta.unique_total.toLocaleString()}건</span>}
        </span>
        <span className="spacer"></span>
        <span className="keys-hint dim">
          <kbd>/</kbd> 검색 <kbd>j</kbd>
          <kbd>k</kbd> 이동 <kbd>⏎</kbd> 열기 <kbd>␣</kbd> 상세
        </span>
        <button type="button" className="sb-btn" onClick={() => runsDialog.current?.showModal()}>
          수집 현황
        </button>
        <button type="button" className="sb-btn" title="테마 전환 (t)" aria-label="테마 전환" onClick={toggleTheme}>
          ◐
        </button>
        <button type="button" className="sb-btn only-desktop" title="단축키 (?)" aria-label="단축키" onClick={() => helpDialog.current?.showModal()}>
          ?
        </button>
      </footer>

      <RunsDialog ref={runsDialog} runs={runs} syncedAt={meta?.synced_at ?? null} />
      <HelpDialog ref={helpDialog} />
    </>
  );
}

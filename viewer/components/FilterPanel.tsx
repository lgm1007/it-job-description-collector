"use client";

import { useRef, useState } from "react";

import type { Filters } from "@/lib/filters";
import { REGION_ORDER, SOURCES, STEPS, toggled } from "@/lib/format";
import type { Facet, Meta } from "@/lib/types";

const YEARS: [string, string][] = [
  ["", "전체"],
  ["0", "신입"],
  ...[1, 2, 3, 4, 5, 6, 7, 8, 9].map((n): [string, string] => [String(n), `${n}y`]),
  ["10", "10y+"],
];
const DAYS: [string, string][] = [
  ["", "전체"],
  ["3", "3d"],
  ["7", "7d"],
  ["14", "14d"],
];
const MAX_DISTRICTS = 40;
const MAX_STACKS = 24; // the rest behind "더 보기"
const STEP_STATES: ["" | "has" | "lacks", string][] = [
  ["", "전체"],
  ["has", "있음"],
  ["lacks", "없음"],
];
const DEBOUNCE_MS = 350;

function Token({ label, count, pressed, onClick }: { label: string; count?: number; pressed: boolean; onClick: () => void }) {
  return (
    <button type="button" className="tok" aria-pressed={pressed} onClick={onClick}>
      {label}
      {count !== undefined && <span className="n">{count.toLocaleString()}</span>}
    </button>
  );
}

/** Commits what was typed after a pause, while following changes from elsewhere (reset, back button). */
function SearchInput(props: { id: string; sign: string; placeholder: string; value: string; onCommit: (value: string) => void }) {
  const { id, sign, placeholder, value, onCommit } = props;
  const [draft, setDraft] = useState(value);
  const [lastValue, setLastValue] = useState(value);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  if (value !== lastValue) {
    setLastValue(value);
    if (value !== draft.trim()) setDraft(value);
  }

  function commitNow(text: string) {
    clearTimeout(timer.current);
    if (text.trim() !== value) onCommit(text.trim());
  }

  return (
    <label className="prompt">
      <span className="ps">{sign}</span>
      <input
        id={id}
        type="search"
        placeholder={placeholder}
        enterKeyHint="search"
        spellCheck={false}
        value={draft}
        onChange={(e) => {
          const text = e.target.value;
          setDraft(text);
          clearTimeout(timer.current);
          timer.current = setTimeout(() => commitNow(text), DEBOUNCE_MS);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") commitNow(draft);
        }}
      />
    </label>
  );
}

export default function FilterPanel(props: {
  filters: Filters;
  meta: Meta | null;
  open: boolean;
  email?: string;
  onChange: (patch: Partial<Filters>) => void;
  onReset: () => void;
  onClose: () => void;
  onLogout: () => void;
}) {
  const { filters, meta, open, email, onChange, onReset, onClose, onLogout } = props;
  const [allStacks, setAllStacks] = useState(false);

  const stacks: Facet[] = meta?.stacks ?? [];
  // Chosen stacks stay visible when folded away, or when no posting uses them any more.
  const shownStacks = allStacks
    ? stacks
    : [...stacks.slice(0, MAX_STACKS), ...stacks.slice(MAX_STACKS).filter((s) => filters.stack.includes(s.name))];
  const goneStacks = filters.stack.filter((name) => !stacks.some((s) => s.name === name));

  const stepState = (key: string) => (filters.steps.includes(key) ? "has" : filters.noSteps.includes(key) ? "lacks" : "");
  const setStep = (key: string, state: string) => {
    const keys = (list: string[], want: string) =>
      STEPS.map((s) => s.key).filter((k) => (k === key ? state === want : list.includes(k)));
    onChange({ steps: keys(filters.steps, "has"), noSteps: keys(filters.noSteps, "lacks") });
  };
  const known = meta?.process?.known ?? 0;

  const rank = (name: string) => {
    const i = REGION_ORDER.indexOf(name);
    return i < 0 ? 99 : i;
  };
  const regions = [...(meta?.regions ?? [])].sort((a, b) => rank(a.name) - rank(b.name));
  const singleRegion = filters.region.length === 1 ? filters.region[0] : null;
  const districts = (singleRegion && meta?.districts[singleRegion]) || [];
  const allSources = SOURCES.map((s) => s.key);
  const activeSources = filters.source.length ? filters.source : allSources;

  return (
    <aside className={`panel${open ? " open" : ""}`} aria-label="검색 조건">
      <div className="panel-head">
        <span className="logo">
          dev-jobs<span className="dim">.kr</span>
        </span>
        <button type="button" className="ghost only-mobile" aria-label="닫기" onClick={onClose}>
          ×
        </button>
      </div>

      <section>
        <h3>키워드</h3>
        <SearchInput id="q" sign="$" placeholder="kotlin spring 백엔드" value={filters.q} onCommit={(q) => onChange({ q })} />
        <p className="hint">띄어 쓴 단어가 모두 들어간 공고만. go·ai 같은 짧은 영문은 단어 단위로 찾습니다.</p>
        <label className="flag">
          <input type="checkbox" checked={filters.titleOnly} onChange={(e) => onChange({ titleOnly: e.target.checked })} /> 제목·기술스택에서만
        </label>
      </section>

      <section>
        <h3>제외</h3>
        <SearchInput id="exclude" sign="!" placeholder="SI 파견 프리랜서" value={filters.exclude} onCommit={(exclude) => onChange({ exclude })} />
        <p className="hint">제목·회사명·기술스택에 들어 있으면 뺍니다.</p>
      </section>

      <section>
        <h3>
          기술스택{" "}
          <button type="button" className="link" onClick={() => onChange({ stack: [] })}>
            전체
          </button>
        </h3>
        <div className="tokens">
          {shownStacks.map((s) => (
            <Token
              key={s.name}
              label={s.name}
              count={s.count}
              pressed={filters.stack.includes(s.name)}
              onClick={() => onChange({ stack: toggled(filters.stack, s.name) })}
            />
          ))}
          {goneStacks.map((name) => (
            <Token key={name} label={name} count={0} pressed onClick={() => onChange({ stack: toggled(filters.stack, name) })} />
          ))}
          {stacks.length > MAX_STACKS && (
            <button type="button" className="link more" onClick={() => setAllStacks(!allStacks)}>
              {allStacks ? "접기" : `+${stacks.length - MAX_STACKS} 더 보기`}
            </button>
          )}
        </div>
        <p className="hint">고른 것 중 하나라도 쓰는 공고. 기술스택 항목과 제목·본문에서 찾습니다.</p>
      </section>

      <section>
        <h3>내 경력</h3>
        <div className="years">
          {YEARS.map(([value, label]) => (
            <Token key={value} label={label} pressed={filters.years === value} onClick={() => onChange({ years: value })} />
          ))}
        </div>
        <p className="hint">이 연차로 지원 가능한 공고만. 경력 조건이 없는 공고는 포함합니다.</p>
      </section>

      <section>
        <h3>
          채용 절차{" "}
          <button type="button" className="link" onClick={() => onChange({ steps: [], noSteps: [] })}>
            전체
          </button>
        </h3>
        <div className="steps">
          {STEPS.map((step) => {
            const has = meta?.process?.steps[step.key] ?? 0;
            return (
              <div key={step.key} className="step" role="group" aria-label={step.label}>
                <span className="name">{step.label}</span>
                <div className="seg">
                  {STEP_STATES.map(([state, label]) => (
                    <button
                      key={state}
                      type="button"
                      aria-pressed={stepState(step.key) === state}
                      title={state === "has" ? `${has.toLocaleString()}건` : state === "lacks" ? `${(known - has).toLocaleString()}건` : undefined}
                      onClick={() => setStep(step.key, state)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
        <p className="hint">
          절차가 적힌 공고 {known.toLocaleString()}건 중에서 찾고, &apos;추가될 수 있음&apos;도 있음으로 봅니다. 사람인·잡코리아는 본문이 이미지라
          대부분 알 수 없습니다.
        </p>
      </section>

      <section>
        <h3>
          지역{" "}
          <button type="button" className="link" onClick={() => onChange({ region: [], district: [] })}>
            전체
          </button>
        </h3>
        <div className="tokens">
          {regions.map((r) => (
            <Token
              key={r.name}
              label={r.name}
              count={r.count}
              pressed={filters.region.includes(r.name)}
              onClick={() => {
                const region = toggled(filters.region, r.name);
                const district = filters.district.filter((d) => region.length === 1 && d.startsWith(`${region[0]} `));
                onChange({ region, district });
              }}
            />
          ))}
        </div>
        {districts.length > 0 && (
          <div className="tokens districts">
            {districts.slice(0, MAX_DISTRICTS).map((d) => (
              <Token
                key={d.name}
                label={d.name.slice((singleRegion as string).length + 1)}
                count={d.count}
                pressed={filters.district.includes(d.name)}
                onClick={() => onChange({ district: toggled(filters.district, d.name) })}
              />
            ))}
          </div>
        )}
      </section>

      <section>
        <h3>사이트</h3>
        <div className="sources">
          {SOURCES.map((s) => (
            <label key={s.key} className="flag">
              <input
                type="checkbox"
                checked={activeSources.includes(s.key)}
                onChange={(e) => {
                  const next = e.target.checked ? [...activeSources, s.key] : activeSources.filter((k) => k !== s.key);
                  onChange({ source: next.length === allSources.length || next.length === 0 ? [] : next });
                }}
              />
              <span className="key" style={{ color: `var(--src-${s.key})` }}>
                {s.key}
              </span>
              <span>{s.label}</span>
              <span className="count">{(meta?.sources[s.key] ?? 0).toLocaleString()}</span>
            </label>
          ))}
        </div>
      </section>

      <section>
        <h3>등록일</h3>
        <div className="seg wide">
          {DAYS.map(([value, label]) => (
            <button key={value} type="button" aria-pressed={filters.days === value} onClick={() => onChange({ days: value })}>
              {label}
            </button>
          ))}
        </div>
      </section>

      <button type="button" className="ghost wide" onClick={onReset}>
        조건 초기화
      </button>
      <button type="button" className="ghost wide" onClick={onLogout}>
        로그아웃
      </button>
      {email && <p className="hint">{email}</p>}
    </aside>
  );
}

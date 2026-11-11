"use client";

import type { Ref } from "react";

import { fmtDateTime } from "@/lib/format";
import type { Run } from "@/lib/types";

const RUN_STATUS: Record<string, string> = { ok: "완료", partial: "일부 완료", failed: "실패" };

export function RunsDialog({ ref, runs, syncedAt }: { ref: Ref<HTMLDialogElement>; runs: Run[]; syncedAt: string | null }) {
  return (
    <dialog ref={ref}>
      <h2>사이트별 최근 수집</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>site</th>
              <th>상태</th>
              <th>시작</th>
              <th>목록</th>
              <th>신규</th>
              <th>마감 삭제</th>
              <th>메모</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.source}>
                <td style={{ color: `var(--src-${r.source})` }}>{r.source}</td>
                <td className={`st-${r.status}`}>{RUN_STATUS[r.status] ?? r.status}</td>
                <td>{fmtDateTime(r.started_at)}</td>
                <td>{r.listed.toLocaleString()}</td>
                <td>{r.added.toLocaleString()}</td>
                <td>{r.closed.toLocaleString()}</td>
                <td className={r.error ? "err" : ""}>{r.error}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="hint">
        {syncedAt && `마지막 업로드 ${fmtDateTime(syncedAt)}. `}수집은 맥북에서 <code>python -m jdc scrape</code>로 직접 실행하고, 끝나면 이곳으로 올라옵니다. 마감일이
        지났거나, 목록에서 사라진 뒤 상세 페이지에서 마감·삭제가 확인된 공고는 수집할 때 삭제합니다.
      </p>
      <form method="dialog">
        <button className="ghost">닫기</button>
      </form>
    </dialog>
  );
}

const SHORTCUTS: [string[], string][] = [
  [["/"], "키워드 입력"],
  [["j", "↓"], "다음 공고"],
  [["k", "↑"], "이전 공고"],
  [["⏎", "o"], "원문 공고 새 탭으로 열기"],
  [["␣", "→"], "상세 펼치기/접기"],
  [["]", "["], "다음/이전 페이지"],
  [["s"], "최신순 ↔ 마감순"],
  [["m"], "같은 공고 합치기 켜기/끄기"],
  [["t"], "다크/라이트 테마"],
  [["esc"], "입력창 빠져나오기"],
];

export function HelpDialog({ ref }: { ref: Ref<HTMLDialogElement> }) {
  return (
    <dialog ref={ref}>
      <h2>단축키</h2>
      <dl className="kv">
        {SHORTCUTS.map(([keys, what]) => (
          <div key={what} className="kv-row">
            <dt>
              {keys.map((key) => (
                <kbd key={key}>{key}</kbd>
              ))}
            </dt>
            <dd>{what}</dd>
          </div>
        ))}
      </dl>
      <form method="dialog">
        <button className="ghost">닫기</button>
      </form>
    </dialog>
  );
}

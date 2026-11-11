"use client";

export default function Pager({ page, pages, onGo }: { page: number; pages: number; onGo: (page: number) => void }) {
  if (pages <= 1) return null;
  const from = Math.max(1, page - 3);
  const to = Math.min(pages, page + 3);
  const nearby = Array.from({ length: to - from + 1 }, (_, i) => from + i);
  const number = (n: number) => (
    <button key={n} type="button" aria-current={n === page ? "page" : undefined} onClick={() => onGo(n)}>
      {n}
    </button>
  );
  return (
    <nav className="pager" aria-label="페이지">
      <button type="button" aria-label="이전 페이지" disabled={page === 1} onClick={() => onGo(page - 1)}>
        [
      </button>
      {from > 1 && number(1)}
      {from > 2 && <span className="dim">…</span>}
      {nearby.map(number)}
      {to < pages - 1 && <span className="dim">…</span>}
      {to < pages && number(pages)}
      <button type="button" aria-label="다음 페이지" disabled={page === pages} onClick={() => onGo(page + 1)}>
        ]
      </button>
    </nav>
  );
}

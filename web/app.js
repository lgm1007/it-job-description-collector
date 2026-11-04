'use strict';

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const PAGE_SIZE = 50;
const YEARS = [['', '전체'], ['0', '신입'], ...[1, 2, 3, 4, 5, 6, 7, 8, 9].map((n) => [String(n), `${n}y`]), ['10', '10y+']];
const RUN_STATUS = { ok: '완료', partial: '일부 완료', failed: '실패', running: '수집 중' };

let state = readState();
let meta = null;
let labels = {};
let jobs = [];
let total = 0;
let cursor = -1;
let pollTimer = null;
let requestSeq = 0;

// -- URL state ---------------------------------------------------------------------

function readState() {
  const p = new URLSearchParams(location.search);
  const list = (key) => (p.get(key) || '').split(',').map((s) => s.trim()).filter(Boolean);
  return {
    q: p.get('q') || '',
    exclude: p.get('exclude') || '',
    title_only: p.get('title_only') === '1',
    years: p.get('years') || '',
    region: list('region'),
    district: list('district'),
    source: list('source'),
    days: p.get('days') || '',
    sort: p.get('sort') === 'deadline' ? 'deadline' : 'latest',
    dedupe: p.get('dedupe') !== '0',
    page: Math.max(1, parseInt(p.get('page') || '1', 10) || 1),
  };
}

function toParams(s, forApi) {
  const p = new URLSearchParams();
  if (s.q) p.set('q', s.q);
  if (s.exclude) p.set('exclude', s.exclude);
  if (s.title_only) p.set('title_only', forApi ? 'true' : '1');
  if (s.years !== '') p.set('years', s.years);
  if (s.region.length) p.set('region', s.region.join(','));
  if (s.district.length) p.set('district', s.district.join(','));
  if (s.source.length) p.set('source', s.source.join(','));
  if (s.days) p.set('days', s.days);
  if (s.sort !== 'latest') p.set('sort', s.sort);
  if (!s.dedupe) p.set('dedupe', forApi ? 'false' : '0');
  if (s.page > 1) p.set('page', String(s.page));
  return p;
}

function update(patch, { keepCursor = false } = {}) {
  state = { ...state, ...patch };
  if (!('page' in patch)) state.page = 1;
  const qs = toParams(state, false).toString();
  history.pushState(null, '', qs ? `?${qs}` : location.pathname);
  syncControls();
  loadJobs(keepCursor ? 0 : -1);
}

window.addEventListener('popstate', () => {
  state = readState();
  syncControls();
  loadJobs();
});

// -- small helpers -----------------------------------------------------------------

const pad = (n) => String(n).padStart(2, '0');
function fmtDateTime(iso) {
  if (!iso) return '';
  const t = new Date(iso);
  return `${pad(t.getMonth() + 1)}.${pad(t.getDate())} ${pad(t.getHours())}:${pad(t.getMinutes())}`;
}
function el(tag, attrs = {}, text) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') node.className = v;
    else if (k === 'style') node.style.cssText = v;
    else node.setAttribute(k, v);
  }
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}
const srcColor = (key) => `color: var(--src-${key})`;
const toggle = (list, value) => (list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);
function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

function careerShort(min, max) {
  if (min === null && max === null) return '—';
  const lo = min || 0;
  if (max === null) return lo === 0 ? '무관' : `${lo}년↑`;
  if (max === 0) return '신입';
  if (lo === 0) return `~${max}년`;
  return lo === max ? `${lo}년` : `${lo}~${max}년`;
}

function due(job) {
  if (job.days_left === null) return { text: '상시', cls: 'always', title: '상시채용 / 채용 시 마감' };
  if (job.days_left === 0) return { text: '오늘', cls: 'soon', title: `${job.deadline} 마감` };
  const cls = job.days_left <= 3 ? 'soon' : job.days_left <= 7 ? 'week' : '';
  return { text: `D-${job.days_left}`, cls, title: `${job.deadline} 마감` };
}

// -- filter panel ------------------------------------------------------------------

function tok(label, count, pressed, onClick) {
  const b = el('button', { type: 'button', class: 'tok', 'aria-pressed': String(pressed) }, label);
  if (count !== undefined) b.append(el('span', { class: 'n' }, count.toLocaleString()));
  b.addEventListener('click', onClick);
  return b;
}

function renderYears() {
  $('#years-grid').replaceChildren(...YEARS.map(([value, label]) => tok(label, undefined, state.years === value, () => update({ years: value }))));
}

function renderRegions() {
  const box = $('#region-chips');
  box.replaceChildren();
  if (!meta) return;
  const order = meta.region_order;
  const rank = (name) => (order.indexOf(name) < 0 ? 99 : order.indexOf(name));
  for (const r of [...meta.regions].sort((a, b) => rank(a.name) - rank(b.name))) {
    box.append(tok(r.name, r.count, state.region.includes(r.name), () => {
      const region = toggle(state.region, r.name);
      const district = state.district.filter((d) => region.length === 1 && d.startsWith(`${region[0]} `));
      update({ region, district });
    }));
  }
  const districtBox = $('#district-chips');
  districtBox.replaceChildren();
  const region = state.region.length === 1 ? state.region[0] : null;
  const districts = (region && meta.districts[region]) || [];
  districtBox.hidden = districts.length === 0;
  for (const d of districts.slice(0, 40)) {
    districtBox.append(tok(d.name.slice(region.length + 1), d.count, state.district.includes(d.name),
      () => update({ district: toggle(state.district, d.name) })));
  }
}

function renderSources() {
  const box = $('#source-checks');
  box.replaceChildren();
  if (!meta) return;
  const all = meta.sources.map((s) => s.key);
  const active = state.source.length ? state.source : all;
  for (const s of meta.sources) {
    const label = el('label', { class: 'flag' });
    const input = el('input', { type: 'checkbox' });
    input.checked = active.includes(s.key);
    input.addEventListener('change', () => {
      const next = input.checked ? [...active, s.key] : active.filter((k) => k !== s.key);
      update({ source: next.length === all.length || next.length === 0 ? [] : next });
    });
    label.append(input, el('span', { class: 'key', style: srcColor(s.key) }, s.key), el('span', {}, s.label),
      el('span', { class: 'count' }, s.count.toLocaleString()));
    box.append(label);
  }
}

function renderEcho() {
  const box = $('#query-echo');
  box.replaceChildren(el('span', { class: 'cmd' }, 'jobs'), el('span', { class: 'arrow' }, '▸'));
  const add = (k, v) => box.append(el('span', { class: 'k' }, `${k}=`), el('span', { class: 'v' }, v));
  if (state.q) add('q', `"${state.q}"`);
  if (state.exclude) add('not', `"${state.exclude}"`);
  if (state.title_only) add('in', 'title');
  if (state.years !== '') add('exp', state.years === '0' ? '신입' : `${state.years}y`);
  if (state.region.length) add('region', state.region.join(','));
  if (state.district.length) add('district', state.district.map((d) => d.split(' ')[1]).join(','));
  if (state.source.length) add('site', state.source.join(','));
  if (state.days) add('since', `${state.days}d`);
  if (state.sort !== 'latest') add('sort', state.sort);
  if (!state.dedupe) add('merge', 'off');
  if (state.page > 1) add('page', String(state.page));
  box.append(el('span', { class: 'cursor' }));
}

function syncControls() {
  if (document.activeElement !== $('#q')) $('#q').value = state.q;
  if (document.activeElement !== $('#exclude')) $('#exclude').value = state.exclude;
  $('#title_only').checked = state.title_only;
  $('#dedupe').checked = state.dedupe;
  for (const b of $$('#sort-seg button')) b.setAttribute('aria-pressed', String(b.dataset.sort === state.sort));
  for (const b of $$('#days-seg button')) b.setAttribute('aria-pressed', String(b.dataset.days === state.days));
  renderYears();
  renderRegions();
  renderSources();
  renderEcho();
}

// -- result rows -------------------------------------------------------------------

function renderRow(job, index) {
  const node = $('#row-tpl').content.firstElementChild.cloneNode(true);
  node.dataset.index = String(index);
  const src = $('.src', node);
  src.textContent = job.source;
  src.style.cssText = srcColor(job.source);
  src.title = labels[job.source] || job.source;
  $('.new', node).textContent = job.is_new ? 'new' : '';
  const d = due(job);
  const dueCell = $('.due', node);
  dueCell.textContent = d.text;
  dueCell.title = d.title;
  if (d.cls) dueCell.classList.add(d.cls);

  const title = $('.title', node);
  title.href = job.url;
  title.textContent = job.title;
  const stack = [...job.skills, ...(job.skills.length ? [] : job.categories)].slice(0, 6);
  $('.stack', node).textContent = stack.map((s) => s.toLowerCase()).join(' · ');
  $('.pos', node).title = job.title;
  $('.co', node).textContent = job.company;
  $('.co', node).title = job.company;
  $('.loc', node).textContent = job.location || '—';
  $('.exp', node).textContent = careerShort(job.career_min, job.career_max);
  $('.exp', node).title = job.career;

  if (job.also_on.length) {
    const also = $('.also', node);
    also.hidden = false;
    also.append(document.createTextNode('└ also'));
    for (const o of job.also_on) {
      also.append(el('a', { href: o.url, target: '_blank', rel: 'noopener noreferrer', style: srcColor(o.source) }, o.source));
    }
  }

  node.addEventListener('click', (e) => {
    if (e.target.closest('a')) return;
    select(index);
    toggleDetail(index);
  });
  return node;
}

function rowAt(index) {
  return $(`#rows .row[data-index="${index}"]`);
}

function select(index, scroll = false) {
  if (!jobs.length) return;
  cursor = Math.max(0, Math.min(jobs.length - 1, index));
  for (const r of $$('#rows .row.sel')) r.classList.remove('sel');
  const row = rowAt(cursor);
  row.classList.add('sel');
  if (scroll) row.scrollIntoView({ block: 'nearest' });
}

async function toggleDetail(index, force) {
  const row = rowAt(index);
  if (!row) return;
  const detail = $('.detail', row);
  const open = force !== undefined ? force : detail.hidden;
  detail.hidden = !open;
  if (!open || detail.dataset.loaded) return;
  detail.textContent = '불러오는 중…';
  try {
    const res = await fetch(`/api/jobs/${jobs[index].id}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    renderDetail(detail, await res.json(), jobs[index]);
    detail.dataset.loaded = '1';
  } catch (e) {
    detail.textContent = `상세 정보를 불러오지 못했습니다 (${e.message}).`;
  }
}

function renderDetail(box, data, job) {
  const kv = el('dl', { class: 'kv' });
  const add = (k, v) => {
    if (v === null || v === undefined || v === '' || (Array.isArray(v) && !v.length)) return;
    const dd = el('dd');
    if (v instanceof Node) dd.append(v);
    else dd.textContent = Array.isArray(v) ? v.join(', ') : v;
    kv.append(el('dt', {}, k), dd);
  };
  add('url', el('a', { href: data.url, target: '_blank', rel: 'noopener noreferrer' }, data.url));
  add('company', data.company);
  add('location', data.locations.length ? data.locations.join(' / ') : data.location);
  add('exp', data.career);
  add('type', data.employment_type);
  add('posted', data.posted_at);
  add('deadline', data.deadline ? `${data.deadline} (${due(job).text})` : '상시채용');
  add('stack', data.skills);
  add('role', data.categories);
  box.replaceChildren(kv, el('pre', { class: 'desc' }, data.description || '저장된 상세 설명이 없습니다. 원문 공고에서 확인해 주세요.'));
}

function renderPager() {
  const pager = $('#pager');
  pager.replaceChildren();
  const pages = Math.ceil(total / PAGE_SIZE);
  if (pages <= 1) return;
  const btn = (label, page, { current = false, disabled = false } = {}) => {
    const b = el('button', { type: 'button' }, label);
    if (current) b.setAttribute('aria-current', 'page');
    b.disabled = disabled;
    b.addEventListener('click', () => goPage(page));
    pager.append(b);
  };
  btn('[', state.page - 1, { disabled: state.page === 1 });
  const from = Math.max(1, state.page - 3);
  const to = Math.min(pages, state.page + 3);
  if (from > 1) { btn('1', 1); if (from > 2) pager.append(el('span', { class: 'dim' }, '…')); }
  for (let p = from; p <= to; p++) btn(String(p), p, { current: p === state.page });
  if (to < pages) { if (to < pages - 1) pager.append(el('span', { class: 'dim' }, '…')); btn(String(pages), pages); }
  btn(']', state.page + 1, { disabled: state.page === pages });
}

function goPage(page) {
  const pages = Math.ceil(total / PAGE_SIZE);
  if (page < 1 || page > pages || page === state.page) return;
  update({ page }, { keepCursor: true });
  window.scrollTo({ top: 0 });
}

async function loadJobs(selectAfter = -1) {
  const seq = ++requestSeq;
  const params = toParams(state, true);
  params.set('size', String(PAGE_SIZE));
  let data;
  try {
    const res = await fetch(`/api/jobs?${params}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    data = await res.json();
  } catch (e) {
    if (seq !== requestSeq) return;
    jobs = [];
    $('#rows').replaceChildren();
    $('#empty').hidden = false;
    $('#empty').textContent = `error: 공고를 불러오지 못했습니다 (${e.message})`;
    return;
  }
  if (seq !== requestSeq) return; // a newer request is already in flight
  jobs = data.items;
  total = data.total;
  cursor = -1;
  $('#total').textContent = total.toLocaleString();
  const from = total ? (state.page - 1) * PAGE_SIZE + 1 : 0;
  $('#total-note').textContent = `${from.toLocaleString()}–${(from + jobs.length - 1).toLocaleString()} 표시`
    + (state.dedupe ? ' · 여러 사이트의 같은 공고는 한 줄로' : '');
  $('#rows').replaceChildren(...jobs.map(renderRow));
  const empty = $('#empty');
  empty.hidden = jobs.length > 0;
  empty.textContent = meta && meta.total === 0
    ? '아직 수집된 공고가 없습니다. 아래 상태바의 "지금 수집"을 눌러 주세요.'
    : 'no match — 조건에 맞는 공고가 없습니다.';
  renderPager();
  if (selectAfter >= 0 && jobs.length) select(selectAfter, true);
}

// -- status bar --------------------------------------------------------------------

function renderStatus() {
  const bar = $('#statusbar');
  const running = meta.scrape.running;
  const lastRuns = meta.runs.filter((r) => r.status !== 'running');
  bar.classList.toggle('running', running);
  bar.classList.toggle('failed', !running && lastRuns.some((r) => r.status === 'failed'));
  $('#scrape-btn').disabled = running;
  if (running) {
    const where = meta.scrape.source || '';
    $('#status-text').textContent = `scraping ${where}${meta.scrape.phase ? ` · ${meta.scrape.phase}` : ''}`;
  } else {
    const finished = lastRuns.map((r) => r.finished_at).filter(Boolean).sort().pop();
    const parts = [finished ? `최근 수집 ${fmtDateTime(finished)}` : '아직 수집 전'];
    parts.push(`공고 ${meta.unique_total.toLocaleString()}건`);
    $('#status-text').textContent = parts.join(' · ');
  }

  const body = $('#runs-body');
  body.replaceChildren();
  for (const r of meta.runs) {
    const tr = el('tr');
    tr.append(
      el('td', { style: srcColor(r.source) }, r.source),
      el('td', { class: `st-${r.status}` }, RUN_STATUS[r.status] || r.status),
      el('td', {}, fmtDateTime(r.started_at)),
      el('td', {}, (r.listed || 0).toLocaleString()),
      el('td', {}, (r.new || 0).toLocaleString()),
      el('td', {}, (r.closed || 0).toLocaleString()),
      el('td', { class: r.error ? 'err' : '' }, r.error || ''),
    );
    body.append(tr);
  }
}

async function loadMeta() {
  const res = await fetch('/api/meta');
  meta = await res.json();
  labels = Object.fromEntries(meta.sources.map((s) => [s.key, s.label]));
  renderStatus();
  syncControls();
  clearTimeout(pollTimer);
  if (meta.scrape.running) {
    pollTimer = setTimeout(async () => {
      await loadMeta();
      if (!meta.scrape.running) loadJobs();
    }, 4000);
  }
}

async function startScrape() {
  $('#scrape-btn').disabled = true;
  const res = await fetch('/api/scrape', { method: 'POST' });
  if (res.status === 409) $('#status-text').textContent = '이미 수집 중입니다';
  setTimeout(loadMeta, 800);
}

// -- theme & keyboard --------------------------------------------------------------

function toggleTheme() {
  const next = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem('jdc-theme', next); } catch (e) { /* private mode */ }
}

function onKey(e) {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const typing = e.target instanceof Element && e.target.matches('input, textarea, select');
  if (e.key === 'Escape') {
    if (typing) e.target.blur();
    $('#panel').classList.remove('open');
    return;
  }
  if (typing) {
    if (e.key === 'Enter' && e.target.type === 'search') {
      e.target.blur();
      if (jobs.length) select(0, true);
    }
    return;
  }
  if ($('dialog[open]')) return;
  // Enter/Space on a focused button or link should press it, not act on the selected row.
  if ((e.key === 'Enter' || e.key === ' ') && e.target instanceof Element && e.target.closest('button, a')) return;
  const keys = {
    '/': () => $('#q').focus(),
    j: () => select(cursor + 1, true), ArrowDown: () => select(cursor + 1, true),
    k: () => select(cursor - 1, true), ArrowUp: () => select(cursor - 1, true),
    Enter: () => cursor >= 0 && window.open(jobs[cursor].url, '_blank', 'noopener'),
    o: () => cursor >= 0 && window.open(jobs[cursor].url, '_blank', 'noopener'),
    ' ': () => cursor >= 0 && toggleDetail(cursor),
    l: () => cursor >= 0 && toggleDetail(cursor, true), ArrowRight: () => cursor >= 0 && toggleDetail(cursor, true),
    h: () => cursor >= 0 && toggleDetail(cursor, false), ArrowLeft: () => cursor >= 0 && toggleDetail(cursor, false),
    ']': () => goPage(state.page + 1),
    '[': () => goPage(state.page - 1),
    s: () => update({ sort: state.sort === 'latest' ? 'deadline' : 'latest' }),
    m: () => update({ dedupe: !state.dedupe }),
    t: toggleTheme,
    '?': () => $('#help-dialog').showModal(),
  };
  const action = keys[e.key];
  if (!action) return;
  e.preventDefault();
  action();
}

function bindControls() {
  $('#q').addEventListener('input', debounce(() => update({ q: $('#q').value.trim() }), 350));
  $('#exclude').addEventListener('input', debounce(() => update({ exclude: $('#exclude').value.trim() }), 350));
  $('#title_only').addEventListener('change', (e) => update({ title_only: e.target.checked }));
  $('#dedupe').addEventListener('change', (e) => update({ dedupe: e.target.checked }));
  $('#clear-region').addEventListener('click', () => update({ region: [], district: [] }));
  for (const b of $$('#sort-seg button')) b.addEventListener('click', () => update({ sort: b.dataset.sort }));
  for (const b of $$('#days-seg button')) b.addEventListener('click', () => update({ days: b.dataset.days }));
  $('#reset').addEventListener('click', () => {
    $('#q').value = '';
    $('#exclude').value = '';
    update({ q: '', exclude: '', title_only: false, years: '', region: [], district: [], source: [], days: '', sort: 'latest', dedupe: true });
  });
  $('#open-panel').addEventListener('click', () => $('#panel').classList.add('open'));
  $('#close-panel').addEventListener('click', () => $('#panel').classList.remove('open'));
  $('#scrape-btn').addEventListener('click', startScrape);
  $('#runs-btn').addEventListener('click', () => $('#runs-dialog').showModal());
  $('#help-btn').addEventListener('click', () => $('#help-dialog').showModal());
  $('#theme-btn').addEventListener('click', toggleTheme);
  document.addEventListener('keydown', onKey);
}

// -- boot --------------------------------------------------------------------------

bindControls();
syncControls();
loadMeta().catch(() => {}).finally(() => loadJobs());

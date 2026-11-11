import assert from "node:assert/strict";
import { test } from "node:test";

import { filtersToQuery, NO_FILTERS, parseFilters, searchArgs } from "./filters.ts";

test("no conditions make an empty query and back", () => {
  assert.equal(filtersToQuery(NO_FILTERS), "");
  assert.deepEqual(parseFilters(""), NO_FILTERS);
});

test("conditions survive the round trip through the URL", () => {
  const filters = {
    ...NO_FILTERS,
    q: "kotlin spring",
    exclude: "si",
    titleOnly: true,
    years: "0",
    region: ["서울", "경기"],
    district: ["서울 강남구"],
    source: ["wanted", "jumpit"],
    days: "7",
    sort: "deadline" as const,
    dedupe: false,
    page: 3,
  };
  assert.deepEqual(parseFilters(`?${filtersToQuery(filters)}`), filters);
});

test("bad URL values fall back to defaults", () => {
  const f = parseFilters("?page=abc&sort=oldest&region=,서울,,");
  assert.equal(f.page, 1);
  assert.equal(f.sort, "latest");
  assert.deepEqual(f.region, ["서울"]);
  assert.equal(parseFilters("?page=-2").page, 1);
});

test("empty conditions reach the database as null, and zero years stays zero", () => {
  const args = searchArgs(NO_FILTERS, 50);
  assert.equal(args.p_q, null);
  assert.equal(args.p_regions, null);
  assert.equal(args.p_years, null);
  assert.equal(args.p_days, null);
  assert.equal(args.p_size, 50);
  assert.equal(searchArgs({ ...NO_FILTERS, years: "0" }, 50).p_years, 0);
});

import assert from "node:assert/strict";
import { test } from "node:test";

import { careerShort, dueLabel, otherTags, processText, safeHref, toggled } from "./format.ts";

test("site tags already shown as stacks are left out", () => {
  assert.deepEqual(otherTags(["Spring Boot", "kotlin", "ReactJS", "postgres", "유지보수", "SI개발"], ["Spring", "Kotlin", "React", "PostgreSQL"]), [
    "유지보수",
    "SI개발",
  ]);
  assert.deepEqual(otherTags(["C++", "C#"], ["C"]), ["C++", "C#"]);
  assert.deepEqual(otherTags([], ["Java"]), []);
});

test("career ranges", () => {
  assert.equal(careerShort(null, null), "—");
  assert.equal(careerShort(0, null), "무관");
  assert.equal(careerShort(3, null), "3년↑");
  assert.equal(careerShort(0, 0), "신입");
  assert.equal(careerShort(0, 3), "~3년");
  assert.equal(careerShort(2, 2), "2년");
  assert.equal(careerShort(2, 5), "2~5년");
});

test("deadlines", () => {
  assert.equal(dueLabel(null, null).text, "상시");
  assert.deepEqual(dueLabel(0, "2026-11-08"), { text: "오늘", cls: "soon", title: "2026-11-08 마감" });
  assert.equal(dueLabel(3, "2026-11-11").cls, "soon");
  assert.equal(dueLabel(7, "2026-11-15").cls, "week");
  assert.equal(dueLabel(8, "2026-11-16").cls, "");
  assert.equal(dueLabel(8, "2026-11-16").text, "D-8");
});

test("only web addresses become links", () => {
  assert.equal(safeHref("https://www.wanted.co.kr/wd/1"), "https://www.wanted.co.kr/wd/1");
  assert.equal(safeHref("javascript:alert(1)"), undefined);
  assert.equal(safeHref("data:text/html,x"), undefined);
});

test("toggling adds and removes", () => {
  assert.deepEqual(toggled(["a"], "b"), ["a", "b"]);
  assert.deepEqual(toggled(["a", "b"], "a"), ["b"]);
});

test("hiring process: unknown, none, and some steps", () => {
  assert.match(processText(null), /^알 수 없음/);
  assert.equal(processText([]), "코딩테스트, 사전과제, 1차면접, 2차면접, 레퍼런스체크 없음");
  assert.equal(processText(["interview2", "coding", "interview1"]), "코딩테스트 · 1차면접 · 2차면접 (없음: 사전과제, 레퍼런스체크)");
  assert.equal(
    processText(["coding", "assignment", "interview1", "interview2", "reference"]),
    "코딩테스트 · 사전과제 · 1차면접 · 2차면접 · 레퍼런스체크",
  );
});

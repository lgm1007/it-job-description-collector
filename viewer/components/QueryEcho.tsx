"use client";

import { Fragment } from "react";

import type { Filters } from "@/lib/filters";

/** The current conditions, written out like a command. */
export default function QueryEcho({ filters: f }: { filters: Filters }) {
  const parts: [string, string][] = [];
  if (f.q) parts.push(["q", `"${f.q}"`]);
  if (f.exclude) parts.push(["not", `"${f.exclude}"`]);
  if (f.titleOnly) parts.push(["in", "title"]);
  if (f.years !== "") parts.push(["exp", f.years === "0" ? "신입" : `${f.years}y`]);
  if (f.region.length) parts.push(["region", f.region.join(",")]);
  if (f.district.length) parts.push(["district", f.district.map((d) => d.split(" ")[1]).join(",")]);
  if (f.source.length) parts.push(["site", f.source.join(",")]);
  if (f.days) parts.push(["since", `${f.days}d`]);
  if (f.sort !== "latest") parts.push(["sort", f.sort]);
  if (!f.dedupe) parts.push(["merge", "off"]);
  if (f.page > 1) parts.push(["page", String(f.page)]);
  return (
    <code className="echo">
      <span className="cmd">jobs</span>
      <span className="arrow">▸</span>
      {parts.map(([key, value]) => (
        <Fragment key={key}>
          <span className="k">{key}=</span>
          <span className="v">{value}</span>
        </Fragment>
      ))}
      <span className="cursor"></span>
    </code>
  );
}

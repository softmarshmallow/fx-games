import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { NextRequest } from "next/server";
import { runDirFor, viewKey } from "@/lib/shell/runs";
import { type ViewerEnv, viewerEnv } from "@/lib/test-support/viewer-env";
import { GET } from "./route";

let env: ViewerEnv;
const TEMPLATE = `views/${"a".repeat(64)}.html`;
const SHOWN = `views/files/${"b".repeat(64)}.png`;

beforeAll(async () => {
  env = await viewerEnv();
  const run = await env.write("runs~flow~2026-10-06-1", {
    "plan.json": { kind: "fx-graph-v1", view_origins: ["https://cdn.example.com"] },
    "events.jsonl": "",
  });
  const runDir = runDirFor(run);
  await mkdir(path.join(runDir, "files", "draw#2"), { recursive: true });
  await writeFile(path.join(runDir, "files", "draw#2", "image.png"), "second take");
  const cached = path.join(env.base, "views", viewKey(runDir));
  await mkdir(path.join(cached, "views", "files"), { recursive: true });
  await writeFile(path.join(cached, TEMPLATE), "<!doctype html><p>view</p>");
  await writeFile(path.join(cached, SHOWN), "shown");
  // A run folder never serves a view of its own, even one at the cache's path.
  await mkdir(path.join(runDir, "views"), { recursive: true });
  await writeFile(path.join(runDir, TEMPLATE), "<!doctype html><p>planted</p>");
});

afterAll(async () => {
  await env.restore();
});

async function get(relative: string, host?: string): Promise<Response> {
  const run = env.run("runs~flow~2026-10-06-1");
  const url = `http://localhost:3000/api/assets/${run.root}/${run.tag}/${relative
    .split("/")
    .map(encodeURIComponent)
    .join("/")}`;
  return GET(new NextRequest(url, { headers: host ? { host } : {} }), {
    params: Promise.resolve({ root: run.root, tag: run.tag, path: relative.split("/") }),
  });
}

describe("the asset route", () => {
  test("serves a take's file from its own folder", async () => {
    const response = await get("files/draw#2/image.png");
    expect(response.status).toBe(200);
    expect(await response.text()).toBe("second take");
  });

  test("serves a view's template and files from the run's view cache, sandboxed", async () => {
    const template = await get(TEMPLATE);
    expect(template.status).toBe(200);
    expect(await template.text()).toBe("<!doctype html><p>view</p>");
    const policy = template.headers.get("content-security-policy") ?? "";
    expect(policy).toContain("sandbox allow-scripts");
    expect(policy).toContain("/_views/view.js https://cdn.example.com");
    const asked = await get(TEMPLATE, "127.0.0.1:3000");
    expect(asked.headers.get("content-security-policy")).toContain("http://127.0.0.1:3000/_views/view.js");
    const shown = await get(SHOWN);
    expect(await shown.text()).toBe("shown");
    expect(shown.headers.get("access-control-allow-origin")).toBe("*");
  });

  test("a view the cache does not hold, or no cache at all, is not found", async () => {
    expect((await get(`views/${"c".repeat(64)}.html`)).status).toBe(404);
    const saved = process.env.STAGE_GEN_VIEW_CACHE;
    delete process.env.STAGE_GEN_VIEW_CACHE;
    try {
      expect((await get(TEMPLATE)).status).toBe(404);
    } finally {
      process.env.STAGE_GEN_VIEW_CACHE = saved;
    }
  });

  test("other HTML, hidden files and escapes are refused", async () => {
    expect((await get("files/page.html")).status).toBe(403);
    expect((await get("files/draw/.0123456789abcdef.part")).status).toBe(403);
    expect((await get("../outside.png")).status).toBe(403);
  });
});

import assert from "node:assert/strict";
import test from "node:test";

const workerUrl = new URL("../dist/server/index.js", import.meta.url);
workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
const { default: worker } = await import(workerUrl.href);

const assets = {
  async fetch(request) {
    const pathname = new URL(request.url).pathname;
    if (pathname === "/index.html" || pathname === "/") {
      return new Response(
        '<!doctype html><html lang="zh-CN"><head><title>多直播间小时数据驾驶舱</title></head><body><div id="root"></div></body></html>',
        { headers: { "Content-Type": "text/html; charset=utf-8" } },
      );
    }
    return new Response("not found", { status: 404 });
  },
};

const context = {
  waitUntil() {},
  passThroughOnException() {},
};

test("built Sites worker serves the dashboard at the root", async () => {
  const response = await worker.fetch(
    new Request("https://dashboard.example.com/"),
    { ASSETS: assets },
    context,
  );
  assert.equal(response.status, 200);
  assert.match(await response.text(), /多直播间小时数据驾驶舱/);
  assert.equal(response.headers.get("cache-control"), "no-store");
});

test("built Sites worker keeps dashboard deep links refreshable", async () => {
  const response = await worker.fetch(
    new Request(
      "https://dashboard.example.com/anchors?start=2026-07-30&end=2026-07-30",
    ),
    { ASSETS: assets },
    context,
  );
  assert.equal(response.status, 200);
  assert.match(await response.text(), /id="root"/);
});

test("built Sites worker fails closed before cloud API configuration", async () => {
  const response = await worker.fetch(
    new Request("https://dashboard.example.com/ready"),
    { ASSETS: assets },
    context,
  );
  assert.equal(response.status, 503);
  assert.match((await response.json()).detail, /BACKEND_ORIGIN/);
});

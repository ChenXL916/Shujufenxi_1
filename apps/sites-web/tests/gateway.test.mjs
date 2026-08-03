import assert from "node:assert/strict";
import test from "node:test";

import { createGatewayHandler, gatewayInternals } from "../worker/gateway.mjs";

function createAssets(files = {}) {
  return {
    async fetch(request) {
      const path = new URL(request.url).pathname;
      const entry = files[path];
      if (!entry) return new Response("not found", { status: 404 });
      return new Response(entry.body, {
        status: 200,
        headers: { "Content-Type": entry.type },
      });
    },
  };
}

function createHandler() {
  return createGatewayHandler({
    async fetch() {
      return new Response("vinext fallback", { status: 418 });
    },
  });
}

const context = {
  waitUntil() {},
  passThroughOnException() {},
};

test("recognizes only API, auth, and health proxy paths", () => {
  assert.equal(gatewayInternals.isProxyPath("/api/v1/overview"), true);
  assert.equal(gatewayInternals.isProxyPath("/auth/password/login"), true);
  assert.equal(gatewayInternals.isProxyPath("/health"), true);
  assert.equal(gatewayInternals.isProxyPath("/ready"), true);
  assert.equal(gatewayInternals.isProxyPath("/healthz"), false);
  assert.equal(gatewayInternals.isProxyPath("/overview"), false);
});

test("accepts public HTTPS origins and rejects unsafe origin shapes", () => {
  assert.equal(
    gatewayInternals.parseBackendOrigin("https://api.example.com")?.href,
    "https://api.example.com/",
  );
  assert.equal(
    gatewayInternals.parseBackendOrigin("http://127.0.0.1:8000")?.href,
    "http://127.0.0.1:8000/",
  );
  assert.equal(
    gatewayInternals.parseBackendOrigin("http://api.example.com"),
    null,
  );
  assert.equal(
    gatewayInternals.parseBackendOrigin("https://user:pass@api.example.com"),
    null,
  );
  assert.equal(
    gatewayInternals.parseBackendOrigin("https://api.example.com/v1"),
    null,
  );
  assert.equal(
    gatewayInternals.parseRegistryUrl(
      "https://raw.githubusercontent.com/example/runtime.json",
    )?.href,
    "https://raw.githubusercontent.com/example/runtime.json",
  );
  assert.equal(
    gatewayInternals.parseRegistryUrl("http://example.com/runtime.json"),
    null,
  );
});

test("resolves the latest quick tunnel from the runtime registry", async () => {
  gatewayInternals.resetRuntimeOriginCacheForTests();
  let registryRequests = 0;
  let upstreamUrl;
  const response = await createHandler().fetch(
    new Request("https://dashboard.example.com/ready"),
    {
      ASSETS: createAssets(),
      BACKEND_ORIGIN: "https://expired-tunnel.trycloudflare.com",
      BACKEND_ORIGIN_REGISTRY: {
        async fetch() {
          registryRequests += 1;
          return Response.json({
            origin: "https://current-tunnel.trycloudflare.com",
          });
        },
      },
      BACKEND: {
        async fetch(url) {
          upstreamUrl = String(url);
          return Response.json({ status: "ready" });
        },
      },
    },
    context,
  );

  assert.equal(response.status, 200);
  assert.equal(registryRequests, 1);
  assert.equal(upstreamUrl, "https://current-tunnel.trycloudflare.com/ready");
});

test("falls back to the configured quick tunnel when the registry is unavailable", async () => {
  gatewayInternals.resetRuntimeOriginCacheForTests();
  let upstreamUrl;
  const response = await createHandler().fetch(
    new Request("https://dashboard.example.com/health"),
    {
      ASSETS: createAssets(),
      BACKEND_ORIGIN: "https://fallback-tunnel.trycloudflare.com",
      BACKEND_ORIGIN_REGISTRY: {
        async fetch() {
          return new Response("unavailable", { status: 503 });
        },
      },
      BACKEND: {
        async fetch(url) {
          upstreamUrl = String(url);
          return Response.json({ status: "ok" });
        },
      },
    },
    context,
  );

  assert.equal(response.status, 200);
  assert.equal(upstreamUrl, "https://fallback-tunnel.trycloudflare.com/health");
});

test("serves hashed static assets with immutable caching", async () => {
  const response = await createHandler().fetch(
    new Request("https://dashboard.example.com/assets/app-123.js"),
    {
      ASSETS: createAssets({
        "/assets/app-123.js": {
          body: "console.log('ok')",
          type: "application/javascript",
        },
      }),
    },
    context,
  );
  assert.equal(response.status, 200);
  assert.equal(
    response.headers.get("cache-control"),
    "public, max-age=31536000, immutable",
  );
  assert.equal(response.headers.get("x-content-type-options"), "nosniff");
});

test("falls back React Router deep links to the dashboard index", async () => {
  const response = await createHandler().fetch(
    new Request(
      "https://dashboard.example.com/overview?start=2026-07-30&end=2026-07-30",
    ),
    {
      ASSETS: createAssets({
        "/index.html": {
          body: "<!doctype html><title>多直播间小时数据驾驶舱</title>",
          type: "text/html; charset=utf-8",
        },
      }),
    },
    context,
  );
  assert.equal(response.status, 200);
  assert.match(await response.text(), /多直播间小时数据驾驶舱/);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.match(
    response.headers.get("content-security-policy") ?? "",
    /connect-src 'self'/,
  );
});

test("does not turn a missing static file into the SPA", async () => {
  const response = await createHandler().fetch(
    new Request("https://dashboard.example.com/assets/missing.js"),
    {
      ASSETS: createAssets({
        "/index.html": {
          body: "<title>dashboard</title>",
          type: "text/html",
        },
      }),
    },
    context,
  );
  assert.equal(response.status, 418);
  assert.equal(await response.text(), "vinext fallback");
});

test("fails closed when the cloud API origin is not configured", async () => {
  const response = await createHandler().fetch(
    new Request("https://dashboard.example.com/api/v1/overview"),
    { ASSETS: createAssets() },
    context,
  );
  assert.equal(response.status, 503);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.match((await response.json()).detail, /BACKEND_ORIGIN/);
});

test("proxies API requests without losing query, cookies, or set-cookie", async () => {
  let captured;
  const response = await createHandler().fetch(
    new Request(
      "https://dashboard.example.com/api/v1/overview?start=2026-07-30",
      {
        headers: {
          Cookie: "live_ops_session=signed",
          "X-Request-ID": "request-1",
        },
      },
    ),
    {
      ASSETS: createAssets(),
      BACKEND_ORIGIN: "https://api.example.com",
      BACKEND_GATEWAY_TOKEN: "server-only-token",
      BACKEND: {
        async fetch(url, init) {
          captured = { url: String(url), init };
          return new Response('{"ok":true}', {
            status: 200,
            headers: {
              "Content-Type": "application/json",
              "Set-Cookie":
                "live_ops_session=renewed; Path=/; Secure; HttpOnly; SameSite=Lax",
            },
          });
        },
      },
    },
    context,
  );
  assert.equal(response.status, 200);
  assert.equal(
    captured.url,
    "https://api.example.com/api/v1/overview?start=2026-07-30",
  );
  assert.equal(captured.init.headers.get("cookie"), "live_ops_session=signed");
  assert.equal(
    captured.init.headers.get("x-forwarded-host"),
    "dashboard.example.com",
  );
  assert.equal(
    captured.init.headers.get("x-liveops-gateway-token"),
    "server-only-token",
  );
  assert.match(response.headers.get("set-cookie") ?? "", /renewed/);
  assert.equal(response.headers.get("x-liveops-gateway"), "sites");
});

test("returns a clear 502 instead of stale or mock data on upstream failure", async () => {
  const response = await createHandler().fetch(
    new Request("https://dashboard.example.com/ready"),
    {
      ASSETS: createAssets(),
      BACKEND_ORIGIN: "https://api.example.com",
      BACKEND: {
        async fetch() {
          throw new Error("upstream unavailable");
        },
      },
    },
    context,
  );
  assert.equal(response.status, 502);
  assert.match((await response.json()).detail, /暂时不可达/);
});

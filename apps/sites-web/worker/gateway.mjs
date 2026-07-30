const PROXY_EXACT_PATHS = new Set(["/health", "/ready"]);
const PROXY_PREFIXES = ["/api/", "/auth/"];
const STATIC_ASSET_PATTERN =
  /\.(?:avif|css|csv|gif|ico|jpe?g|js|json|map|mp4|png|svg|txt|webmanifest|webp|woff2?)$/i;
const UPSTREAM_TIMEOUT_MS = 65_000;

function isProxyPath(pathname) {
  return (
    PROXY_EXACT_PATHS.has(pathname) ||
    PROXY_PREFIXES.some((prefix) => pathname.startsWith(prefix))
  );
}

function jsonError(status, detail) {
  return Response.json(
    {
      detail,
      gateway: "sites",
    },
    {
      status,
      headers: {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
      },
    },
  );
}

function parseBackendOrigin(value) {
  if (!value) return null;
  try {
    const url = new URL(value);
    const isLocalDevelopment =
      url.protocol === "http:" &&
      ["127.0.0.1", "localhost"].includes(url.hostname);
    if (
      (url.protocol !== "https:" && !isLocalDevelopment) ||
      url.username ||
      url.password ||
      url.search ||
      url.hash ||
      (url.pathname !== "/" && url.pathname !== "")
    ) {
      return null;
    }
    url.pathname = "/";
    return url;
  } catch {
    return null;
  }
}

function withStaticSecurityHeaders(response, pathname) {
  const headers = new Headers(response.headers);
  headers.set("X-Content-Type-Options", "nosniff");
  headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  headers.set(
    "Permissions-Policy",
    "accelerometer=(), camera=(), geolocation=(), gyroscope=(), microphone=(), payment=(), usb=()",
  );
  headers.set("X-Frame-Options", "DENY");
  if ((headers.get("content-type") ?? "").includes("text/html")) {
    headers.set("Cache-Control", "no-store");
    headers.set(
      "Content-Security-Policy",
      "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; worker-src 'self' blob:",
    );
  } else if (pathname.startsWith("/assets/")) {
    headers.set("Cache-Control", "public, max-age=31536000, immutable");
  }
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

async function proxyToBackend(request, env) {
  const origin = parseBackendOrigin(env.BACKEND_ORIGIN);
  if (!origin) {
    return jsonError(
      503,
      "云端 API 尚未配置或地址无效，请联系管理员完成 BACKEND_ORIGIN 配置。",
    );
  }

  const publicUrl = new URL(request.url);
  const upstreamUrl = new URL(
    `${publicUrl.pathname}${publicUrl.search}`,
    origin,
  );
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("x-liveops-gateway-token");
  headers.set("X-Forwarded-Host", publicUrl.host);
  headers.set("X-Forwarded-Proto", "https");
  headers.set("X-LiveOps-Gateway", "sites");
  if (env.BACKEND_GATEWAY_TOKEN) {
    headers.set("X-LiveOps-Gateway-Token", env.BACKEND_GATEWAY_TOKEN);
  }

  const init = {
    method: request.method,
    headers,
    redirect: "manual",
    signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
  };
  if (!["GET", "HEAD"].includes(request.method)) {
    init.body = request.body;
  }

  const backendFetcher = env.BACKEND?.fetch
    ? env.BACKEND.fetch.bind(env.BACKEND)
    : fetch;
  try {
    const response = await backendFetcher(upstreamUrl, init);
    const responseHeaders = new Headers(response.headers);
    responseHeaders.set("X-LiveOps-Gateway", "sites");
    responseHeaders.set("Cache-Control", "no-store");
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch {
    return jsonError(
      502,
      "云端 API 暂时不可达，Sites 网关未返回旧数据或模拟数据，请稍后重试。",
    );
  }
}

export function createGatewayHandler(nextHandler) {
  return {
    async fetch(request, env = {}, ctx) {
      const url = new URL(request.url);
      if (isProxyPath(url.pathname)) {
        return proxyToBackend(request, env);
      }

      if (!env.ASSETS) {
        return nextHandler.fetch(request, env, ctx);
      }

      const asset = await env.ASSETS.fetch(request);
      if (asset.status !== 404) {
        return withStaticSecurityHeaders(asset, url.pathname);
      }

      if (
        request.method === "GET" &&
        !STATIC_ASSET_PATTERN.test(url.pathname) &&
        !url.pathname.startsWith("/_next/") &&
        !url.pathname.startsWith("/_vinext/")
      ) {
        for (const fallbackPath of ["/index.html", "/"]) {
          const indexUrl = new URL(fallbackPath, request.url);
          const index = await env.ASSETS.fetch(
            new Request(indexUrl.href, {
              method: "GET",
              headers: { Accept: "text/html" },
            }),
          );
          if (index.status !== 404) {
            return withStaticSecurityHeaders(index, "/index.html");
          }
        }
      }

      return nextHandler.fetch(request, env, ctx);
    },
  };
}

export const gatewayInternals = {
  isProxyPath,
  parseBackendOrigin,
};

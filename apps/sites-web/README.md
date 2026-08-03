# Live Ops Sites host

This package is the OpenAI Sites host for the existing `apps/web` Vite dashboard.

- `npm run build` builds `apps/web`, stages its immutable production assets, and creates a vinext/Sites Worker build.
- The Worker serves Vite assets and returns `index.html` for React Router deep links.
- `/api/*`, `/auth/*`, `/health`, and `/ready` are proxied to `BACKEND_ORIGIN`.
- When `BACKEND_ORIGIN` is a Cloudflare Quick Tunnel, the Worker reads the latest validated `*.trycloudflare.com` origin from the public runtime registry and caches it for 15 seconds. If the registry is unavailable, it safely falls back to `BACKEND_ORIGIN`.
- `BACKEND_ORIGIN_REGISTRY_URL` can override the registry URL; set it to an empty string to disable runtime resolution for a stable origin.
- `BACKEND_GATEWAY_TOKEN`, when configured as a Sites secret, is added only by the Worker and is required by the cloud Caddy gateway.
- Missing or unreachable backends return explicit 503/502 JSON; the gateway never substitutes fixture, mock, or stale data.

Runtime values belong in Sites environment variables. Do not put credentials in `.openai/hosting.json`, source files, build output, or Git.

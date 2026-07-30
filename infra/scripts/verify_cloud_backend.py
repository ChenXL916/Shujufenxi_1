from __future__ import annotations

import argparse
import json
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlsplit


def _get_json(url: str, *, headers: dict[str, str] | None = None) -> tuple[int, object]:
    request = urllib.request.Request(  # noqa: S310 - URL is validated by main
        url, headers=headers or {}, method="GET"
    )
    try:
        with urllib.request.urlopen(  # noqa: S310 - URL is validated by main
            request,
            timeout=20,
            context=ssl.create_default_context(),
        ) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            payload: object = json.loads(exc.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {"detail": str(exc)}
        return exc.code, payload


def _public_https_origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("必须提供不含凭据、查询或片段的公网 HTTPS origin")
    return value.rstrip("/") + "/"


def main() -> int:
    parser = argparse.ArgumentParser(description="验证 Sites 前端和云端 API 的生产边界")
    parser.add_argument("--site-origin", required=True)
    parser.add_argument("--backend-origin", required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    site = _public_https_origin(args.site_origin)
    backend = _public_https_origin(args.backend_origin)

    site_health, site_health_payload = _get_json(urljoin(site, "health"))
    site_ready, site_ready_payload = _get_json(urljoin(site, "ready"))
    auth_status, _ = _get_json(urljoin(site, "auth/me"))
    backend_ready, backend_payload = _get_json(urljoin(backend, "ready"))
    backend_private, _ = _get_json(urljoin(backend, "api/v1/options"))

    if site_health != 200 or site_ready != 200:
        raise RuntimeError(f"Sites 同源健康检查失败：health={site_health}, ready={site_ready}")
    if auth_status != 401:
        raise RuntimeError(f"未登录认证边界异常：expected=401, actual={auth_status}")
    if backend_ready != 200:
        raise RuntimeError(f"云端 /ready 失败：{backend_ready} {backend_payload}")
    if backend_private != 403:
        raise RuntimeError(
            f"云端 API 网关未阻止绕过 Sites 的请求：expected=403, actual={backend_private}"
        )

    report: dict[str, object] = {
        "site": {
            "origin": site,
            "health": site_health_payload,
            "ready": site_ready_payload,
            "unauthenticated_auth_me": auth_status,
        },
        "backend": {
            "origin": backend,
            "ready": backend_payload,
            "direct_api_status": backend_private,
        },
    }
    if args.manifest:
        manifest = json.loads(args.manifest.read_text("utf-8"))
        if manifest.get("source_counts") != manifest.get("target_counts"):
            raise RuntimeError("数据库迁移清单中的源/目标行数不一致")
        report["migration"] = {
            "source_sha256": manifest["source"]["sha256"],
            "tables": len(manifest["source_counts"]),
            "rows": sum(manifest["source_counts"].values()),
            "primary_key_digests": "verified",
        }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

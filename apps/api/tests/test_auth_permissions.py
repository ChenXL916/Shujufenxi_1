from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import AccessScope, get_access_scope
from app.auth.login_limiter import LoginAttemptLimiter, login_attempt_limiter
from app.auth.oauth import (
    FeishuIdentity,
    FeishuOAuthClient,
    FeishuOAuthGrant,
    FeishuTokenBundle,
)
from app.auth.passwords import hash_password, verify_password
from app.auth.session import SessionCodec
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.integrations.feishu.oauth_store import FeishuOAuthStore
from app.main import app
from app.models.entities import PermissionAuditLog, Role, Room, SystemSetting, User, UserRole


def test_password_hash_is_salted_and_verifiable() -> None:
    first = hash_password("correct horse battery staple")
    second = hash_password("correct horse battery staple")

    assert first != second
    assert "correct horse" not in first
    assert verify_password("correct horse battery staple", first)
    assert not verify_password("wrong password", first)
    assert not verify_password("correct horse battery staple", "invalid")


def test_password_login_issues_session_and_uses_generic_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(
            feishu_user_id=None,
            username="web.viewer",
            name="网页查看账号",
            email=None,
            password_hash=hash_password("A-secure-password-2026"),
            role_name="viewer",
            status="active",
            room_scope_mode="role",
            active=True,
        )
        disabled = User(
            feishu_user_id=None,
            username="disabled.viewer",
            name="停用账号",
            email=None,
            password_hash=hash_password("A-secure-password-2026"),
            role_name="viewer",
            status="disabled",
            room_scope_mode="role",
            active=False,
        )
        session.add_all([user, disabled])
        session.commit()
        user_id = user.id
    settings = Settings(
        app_env="test",
        dev_auth_bypass=False,
        jwt_secret="password-login-test-secret",  # noqa: S106
        redis_url="redis://127.0.0.1:1/0",
    )

    def override_db():  # type: ignore[no-untyped-def]
        with Session(engine) as session:
            yield session

    def unavailable_redis(_self: LoginAttemptLimiter, _settings: Settings):
        from redis.exceptions import RedisError

        raise RedisError("test redis unavailable")

    monkeypatch.setattr(LoginAttemptLimiter, "_redis", unavailable_redis)
    monkeypatch.setattr("app.auth.router.load_runtime_settings", lambda _db: settings)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    login_attempt_limiter.reset_for_testing()
    client = TestClient(app)
    try:
        unknown = client.post(
            "/auth/password/login",
            json={"username": "unknown", "password": "A-secure-password-2026"},
        )
        wrong = client.post(
            "/auth/password/login",
            json={"username": "web.viewer", "password": "A-secure-password-wrong"},
        )
        disabled_response = client.post(
            "/auth/password/login",
            json={"username": "disabled.viewer", "password": "A-secure-password-2026"},
        )
        success = client.post(
            "/auth/password/login",
            json={"username": " WEB.VIEWER ", "password": "A-secure-password-2026"},
        )
        me = client.get("/auth/me")
        with Session(engine) as session:
            audit = session.scalar(
                select(PermissionAuditLog).where(
                    PermissionAuditLog.action == "password_login_succeeded"
                )
            )
            stored_user = session.get(User, user_id)
            assert stored_user is not None
            last_login_at = stored_user.last_login_at
    finally:
        login_attempt_limiter.reset_for_testing()
        app.dependency_overrides.clear()
        engine.dispose()

    assert unknown.status_code == 401
    assert wrong.status_code == 401
    assert disabled_response.status_code == 401
    assert {
        unknown.json()["detail"],
        wrong.json()["detail"],
        disabled_response.json()["detail"],
    } == {"账号或密码错误"}
    assert success.status_code == 200
    assert success.json() == {"authenticated": True, "redirect_url": "/overview"}
    assert "HttpOnly" in success.headers["set-cookie"]
    assert me.status_code == 200
    assert me.json()["auth_mode"] == "password"
    assert me.json()["name"] == "网页查看账号"
    assert last_login_at is not None
    assert audit is not None
    assert audit.after_value == {"auth_mode": "password"}


def test_password_login_rate_limits_repeated_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    settings = Settings(
        app_env="test",
        jwt_secret="password-rate-limit-test-secret",  # noqa: S106
        redis_url="redis://127.0.0.1:1/0",
    )

    def override_db():  # type: ignore[no-untyped-def]
        with Session(engine) as session:
            yield session

    def unavailable_redis(_self: LoginAttemptLimiter, _settings: Settings):
        from redis.exceptions import RedisError

        raise RedisError("test redis unavailable")

    monkeypatch.setattr(LoginAttemptLimiter, "_redis", unavailable_redis)
    monkeypatch.setattr("app.auth.router.load_runtime_settings", lambda _db: settings)
    app.dependency_overrides[get_db] = override_db
    login_attempt_limiter.reset_for_testing()
    client = TestClient(app)
    payload = {"username": "limited.user", "password": "A-secure-password-wrong"}
    try:
        failures = [client.post("/auth/password/login", json=payload) for _ in range(5)]
        blocked = client.post("/auth/password/login", json=payload)
    finally:
        login_attempt_limiter.reset_for_testing()
        app.dependency_overrides.clear()
        engine.dispose()

    assert all(response.status_code == 401 for response in failures)
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "300"


def test_signed_session_and_oauth_state_reject_tampering() -> None:
    codec = SessionCodec(
        Settings(app_env="test", jwt_secret="test-session-secret")  # noqa: S106
    )
    session = codec.dumps({"user_id": str(uuid4()), "csrf": "csrf-value"})
    state = codec.dumps_state("expected-state")
    assert codec.loads(session) is not None
    assert codec.loads_state(state) == "expected-state"
    assert codec.loads(f"{session}x") is None
    assert codec.loads_state(f"{state}x") is None


@pytest.mark.asyncio
async def test_feishu_oauth_exchanges_code_and_reads_identity() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth/token"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "access_token": "user-token",
                    "expires_in": 7200,
                    "refresh_token": "refresh-token",
                    "refresh_token_expires_in": 604800,
                    "scope": "bitable:app:readonly offline_access",
                },
            )
        assert request.headers["Authorization"] == "Bearer user-token"
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "open_id": "ou_123",
                    "name": "测试用户",
                    "email": "viewer@example.com",
                },
            },
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        app_env="test",
        feishu_app_id="cli_test",
        feishu_app_secret="app-secret",  # noqa: S106
        jwt_secret="test-session-secret",  # noqa: S106
    )
    client = FeishuOAuthClient(settings, http)
    authorization_url = client.authorization_url("state-value")
    assert "state=state-value" in authorization_url
    assert "offline_access" in authorization_url
    grant = await client.exchange_authorization("authorization-code")
    assert grant.identity.user_id == "ou_123"
    assert grant.identity.email == "viewer@example.com"
    assert grant.tokens.refresh_token == "refresh-token"  # noqa: S105
    await client.close()


@pytest.mark.asyncio
async def test_oauth_tokens_are_encrypted_and_refresh_token_is_rotated() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = Settings(
        app_env="test",
        feishu_app_id="cli_test",
        feishu_app_secret="app-secret",  # noqa: S106
        field_encryption_key="test-encryption-key",  # noqa: S106
    )
    store = FeishuOAuthStore(settings)
    grant = FeishuOAuthGrant(
        identity=FeishuIdentity("ou_123", "测试用户", None, None),
        tokens=FeishuTokenBundle(
            "old-access",
            1,
            "old-refresh",
            604800,
            "bitable:app:readonly offline_access",
        ),
    )

    class RefreshClient:
        async def refresh_tokens(self, refresh_token: str) -> FeishuTokenBundle:
            assert refresh_token == "old-refresh"  # noqa: S105
            return FeishuTokenBundle(
                "new-access",
                7200,
                "new-refresh",
                604800,
                "bitable:app:readonly offline_access",
            )

    with Session(engine) as session:
        store.save_grant(session, grant, None)
        row = session.get(SystemSetting, "feishu_user_oauth")
        assert row is not None
        assert row.value["access_token"] != "old-access"  # noqa: S105
        token = await store.valid_access_token(
            session,
            oauth_client=RefreshClient(),  # type: ignore[arg-type]
        )
        assert token == "new-access"  # noqa: S105
        stored = store.load(session)
        assert stored is not None
        assert stored.refresh_token == "new-refresh"  # noqa: S105


def test_feishu_callback_rejects_an_uninvited_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    settings = Settings(
        app_env="test",
        app_base_url="http://testserver",
        feishu_app_id="cli_test",
        feishu_app_secret="app-secret",  # noqa: S106
        jwt_secret="test-session-secret",  # noqa: S106
    )
    grant = FeishuOAuthGrant(
        identity=FeishuIdentity("ou_uninvited", "未邀请用户", None, "new@example.com"),
        tokens=FeishuTokenBundle(
            "access-token",
            7200,
            "refresh-token",
            604800,
            "offline_access",
        ),
    )

    async def exchange_authorization(_self: FeishuOAuthClient, _code: str) -> FeishuOAuthGrant:
        return grant

    def override_db():  # type: ignore[no-untyped-def]
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(FeishuOAuthClient, "exchange_authorization", exchange_authorization)
    monkeypatch.setattr("app.auth.router.load_runtime_settings", lambda _db: settings)
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    state = "expected-state"
    client.cookies.set("live_ops_oauth_state", SessionCodec(settings).dumps_state(state))
    try:
        response = client.get(
            f"/auth/feishu/callback?code=authorization-code&state={state}",
            follow_redirects=False,
        )
        with Session(engine) as session:
            user_count = len(session.scalars(select(User)).all())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"] == "该飞书账号尚未被邀请使用本系统"
    assert user_count == 0


def test_feishu_callback_binds_an_active_email_invitation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        invited = User(
            name="受邀用户",
            email="Invited@Example.com",
            feishu_user_id=f"pending:{uuid4()}",
            role_name="viewer",
            active=True,
        )
        session.add(invited)
        session.commit()
        invited_id = invited.id
    settings = Settings(
        app_env="test",
        app_base_url="http://testserver",
        feishu_app_id="cli_test",
        feishu_app_secret="app-secret",  # noqa: S106
        jwt_secret="test-session-secret",  # noqa: S106
    )
    grant = FeishuOAuthGrant(
        identity=FeishuIdentity("ou_invited", "已绑定用户", None, " invited@example.com "),
        tokens=FeishuTokenBundle(
            "access-token",
            7200,
            "refresh-token",
            604800,
            "offline_access",
        ),
    )

    async def exchange_authorization(_self: FeishuOAuthClient, _code: str) -> FeishuOAuthGrant:
        return grant

    def override_db():  # type: ignore[no-untyped-def]
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(FeishuOAuthClient, "exchange_authorization", exchange_authorization)
    monkeypatch.setattr("app.auth.router.load_runtime_settings", lambda _db: settings)
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    state = "expected-state"
    client.cookies.set("live_ops_oauth_state", SessionCodec(settings).dumps_state(state))
    try:
        response = client.get(
            f"/auth/feishu/callback?code=authorization-code&state={state}",
            follow_redirects=False,
        )
        with Session(engine) as session:
            users = session.scalars(select(User)).all()
            bound = session.get(User, invited_id)
            assert bound is not None
            bound_feishu_user_id = bound.feishu_user_id
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 307
    assert response.headers["location"].startswith("http://testserver/overview?")
    assert len(users) == 1
    assert bound_feishu_user_id == "ou_invited"


def test_feishu_callback_auto_provisions_a_separate_default_role_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            Role(
                name="live_manager",
                role_code="live_manager",
                role_name="直播主管",
                description="共享链接默认只读业务角色",
                all_permissions=False,
                system_role=True,
                active=True,
            )
        )
        session.commit()
    settings = Settings(
        app_env="test",
        app_base_url="http://testserver",
        feishu_app_id="cli_test",
        feishu_app_secret="app-secret",  # noqa: S106
        jwt_secret="test-session-secret",  # noqa: S106
        feishu_auto_provision_enabled=True,
        feishu_auto_provision_role="live_manager",
    )
    grant = FeishuOAuthGrant(
        identity=FeishuIdentity("ou_colleague", "新同事", None, None),
        tokens=FeishuTokenBundle(
            "access-token",
            7200,
            "refresh-token",
            604800,
            "offline_access",
        ),
    )

    async def exchange_authorization(_self: FeishuOAuthClient, _code: str) -> FeishuOAuthGrant:
        return grant

    def override_db():  # type: ignore[no-untyped-def]
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(FeishuOAuthClient, "exchange_authorization", exchange_authorization)
    monkeypatch.setattr("app.auth.router.load_runtime_settings", lambda _db: settings)
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    state = "expected-state"
    client.cookies.set("live_ops_oauth_state", SessionCodec(settings).dumps_state(state))
    try:
        response = client.get(
            f"/auth/feishu/callback?code=authorization-code&state={state}",
            follow_redirects=False,
        )
        with Session(engine) as session:
            user = session.scalar(select(User).where(User.feishu_user_id == "ou_colleague"))
            assert user is not None
            role_code = session.scalar(
                select(Role.role_code)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == user.id)
            )
            audit = session.scalar(
                select(PermissionAuditLog).where(
                    PermissionAuditLog.action == "feishu_user_auto_provisioned"
                )
            )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    assert response.status_code == 307
    assert response.headers["location"].startswith("http://testserver/overview?")
    assert role_code == "live_manager"
    assert audit is not None


def test_room_scope_and_admin_endpoints_are_enforced_server_side() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        allowed = Room(
            name="授权直播间",
            brand=None,
            category=None,
            active=True,
            confirmed=True,
            source_aliases=[],
        )
        blocked = Room(
            name="未授权直播间",
            brand=None,
            category=None,
            active=True,
            confirmed=True,
            source_aliases=[],
        )
        session.add_all([allowed, blocked])
        session.commit()
        allowed_id = allowed.id

    def override_db():  # type: ignore[no-untyped-def]
        with Session(engine) as session:
            yield session

    def viewer_access() -> AccessScope:
        return AccessScope(
            uuid4(),
            "viewer",
            frozenset({allowed_id}),
            False,
            permission_codes=frozenset({"dashboard.view"}),
        )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_access_scope] = viewer_access
    client = TestClient(app)
    try:
        options = client.get("/api/v1/filters/options")
        export = client.post("/api/v1/exports")
        admin = client.get("/api/v1/admin/settings")
        acknowledge = client.post(
            f"/api/v1/alerts/events/{uuid4()}/acknowledge",
            json={"resolution_note": "viewer 不应有权处理"},
        )
        retry_push = client.post(f"/api/v1/alerts/events/{uuid4()}/retry-push")
    finally:
        app.dependency_overrides.clear()

    assert options.status_code == 200
    assert [room["name"] for room in options.json()["rooms"]] == ["授权直播间"]
    assert export.status_code == 403
    assert admin.status_code == 403
    assert acknowledge.status_code == 403
    assert retry_push.status_code == 403

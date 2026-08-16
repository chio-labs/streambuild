from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from streambuild.auth.classes.control_store import ControlStore
from streambuild.auth.exceptions import AuthConfigurationError
from streambuild.auth.models import AuthSettings, UserAccount
from streambuild.auth.types import AuthenticationMode, UnknownUserPolicy
from tests.unit.src.streambuild.auth._test_types import AuthTestCase
from tests.unit.src.streambuild.auth.helpers import build_auth_client, build_control_store


@pytest.mark.parametrize(
    "test_case",
    [AuthTestCase(description="local administrator", expected_result=200)],
    ids=lambda case: case.description,
)
def test_given_local_mode_when_reading_me_then_deterministic_admin_is_returned(
    test_case: AuthTestCase, tmp_path: Path
) -> None:
    store: ControlStore = build_control_store(tmp_path=tmp_path)
    client: TestClient = build_auth_client(
        settings=AuthSettings(
            mode=AuthenticationMode.DISABLED,
            control_store_url="unused",
        ),
        store=store,
    )

    response: Response = client.get("/api/auth/me")

    assert response.status_code == test_case.expected_result
    assert response.json()["user"]["username"] == "local"
    assert response.json()["roles"] == ["admin"]
    store.close()


@pytest.mark.parametrize(
    "test_case",
    [AuthTestCase(description="new proxy viewer", expected_result=200)],
    ids=lambda case: case.description,
)
def test_given_proxy_mode_when_identity_is_new_then_viewer_is_provisioned(
    test_case: AuthTestCase, tmp_path: Path
) -> None:
    store: ControlStore = build_control_store(tmp_path=tmp_path)
    settings: AuthSettings = AuthSettings(
        mode=AuthenticationMode.TRUSTED_PROXY,
        control_store_url="unused",
        username_header="X-Mustard-User",
    )
    client: TestClient = build_auth_client(settings=settings, store=store)

    missing: Response = client.get("/api/auth/me")
    first: Response = client.get("/api/auth/me", headers={"X-Mustard-User": "Alice"})
    second: Response = client.get("/api/auth/me", headers={"X-Mustard-User": "alice"})

    assert missing.status_code == 401
    assert first.status_code == test_case.expected_result
    assert first.json()["roles"] == ["viewer"]
    assert first.json()["user"]["id"] == second.json()["user"]["id"]
    assert len(store.list_users()) == 1
    store.close()


@pytest.mark.parametrize(
    "test_case",
    [AuthTestCase(description="unknown proxy denied", expected_result=403)],
    ids=lambda case: case.description,
)
def test_given_proxy_deny_policy_when_identity_is_new_then_request_is_forbidden(
    test_case: AuthTestCase, tmp_path: Path
) -> None:
    store: ControlStore = build_control_store(tmp_path=tmp_path)
    client: TestClient = build_auth_client(
        settings=AuthSettings(
            mode=AuthenticationMode.TRUSTED_PROXY,
            control_store_url="unused",
            unknown_user_policy=UnknownUserPolicy.DENY,
        ),
        store=store,
    )

    response: Response = client.get("/api/protected", headers={"X-Mustard-User": "alice"})

    assert response.status_code == test_case.expected_result
    assert store.list_users() == ()
    store.close()


@pytest.mark.parametrize(
    "test_case",
    [AuthTestCase(description="valid proxy mutation proof", expected_result=200)],
    ids=lambda case: case.description,
)
def test_given_proxy_principal_when_posting_then_request_proof_is_required(
    test_case: AuthTestCase, tmp_path: Path
) -> None:
    store: ControlStore = build_control_store(tmp_path=tmp_path)
    client: TestClient = build_auth_client(
        settings=AuthSettings(
            mode=AuthenticationMode.TRUSTED_PROXY,
            control_store_url="unused",
        ),
        store=store,
    )
    headers: dict[str, str] = {"X-Mustard-User": "alice"}
    assert client.get("/api/auth/me", headers=headers).status_code == 200

    rejected: Response = client.post("/api/protected", headers=headers)
    accepted: Response = client.post(
        "/api/protected",
        headers={**headers, "X-StreamBuild-CSRF": "trusted-proxy"},
    )

    assert rejected.status_code == 403
    assert accepted.status_code == test_case.expected_result
    store.close()


@pytest.mark.parametrize(
    "test_case",
    [AuthTestCase(description="password session created", expected_result=200)],
    ids=lambda case: case.description,
)
def test_given_password_mode_when_logging_in_then_cookie_and_csrf_protect_session(
    test_case: AuthTestCase, tmp_path: Path
) -> None:
    store: ControlStore = build_control_store(tmp_path=tmp_path)
    store.create_user(
        username="alice",
        password="correct horse battery staple",
        roles=("viewer",),
    )
    client: TestClient = build_auth_client(
        settings=AuthSettings(
            mode=AuthenticationMode.PASSWORD,
            control_store_url="unused",
            session_cookie_secure=False,
        ),
        store=store,
    )

    unauthenticated: Response = client.get("/api/protected")
    login: Response = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "correct horse battery staple"},
    )
    me: Response = client.get("/api/auth/me")
    rejected_logout: Response = client.post("/api/auth/logout")
    logout: Response = client.post(
        "/api/auth/logout",
        headers={"X-StreamBuild-CSRF": login.json()["csrfToken"]},
    )

    assert unauthenticated.status_code == 401
    assert login.status_code == test_case.expected_result
    assert "streambuild_session=" in login.headers["set-cookie"]
    assert me.json()["user"]["authenticationSource"] == "password"
    assert rejected_logout.status_code == 403
    assert logout.status_code == 200
    assert client.get("/api/protected").status_code == 401
    store.close()


@pytest.mark.parametrize(
    "test_case",
    [AuthTestCase(description="secure session cookie", expected_result=200)],
    ids=lambda case: case.description,
)
def test_given_password_mode_when_logging_in_then_session_cookie_is_secure_by_default(
    test_case: AuthTestCase, tmp_path: Path
) -> None:
    store: ControlStore = build_control_store(tmp_path=tmp_path)
    store.create_user(
        username="alice",
        password="correct horse battery staple",
        roles=("viewer",),
    )
    client: TestClient = build_auth_client(
        settings=AuthSettings(
            mode=AuthenticationMode.PASSWORD,
            control_store_url="unused",
        ),
        store=store,
    )

    response: Response = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "correct horse battery staple"},
    )

    assert response.status_code == test_case.expected_result
    assert "Secure" in response.headers["set-cookie"]
    store.close()


@pytest.mark.parametrize(
    "test_case",
    [
        AuthTestCase(
            description="canonical username throttling",
            expected_result=(401, 401, 401, 401, 401, 429),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_username_variants_when_login_keeps_failing_then_shared_limit_applies(
    test_case: AuthTestCase, tmp_path: Path
) -> None:
    store: ControlStore = build_control_store(tmp_path=tmp_path)
    store.create_user(
        username="alice",
        password="correct horse battery staple",
        roles=("viewer",),
    )
    client: TestClient = build_auth_client(
        settings=AuthSettings(
            mode=AuthenticationMode.PASSWORD,
            control_store_url="unused",
            session_cookie_secure=False,
        ),
        store=store,
    )

    attempts: list[Response] = [
        client.post(
            "/api/auth/login",
            json={"username": username, "password": "incorrect password"},
        )
        for username in ("alice", " alice", "alice ", "ALICE", " Alice ", "  alice")
    ]

    assert tuple(response.status_code for response in attempts) == test_case.expected_result
    store.close()


@pytest.mark.parametrize(
    "test_case",
    [
        AuthTestCase(
            description="successful account login preserves IP failures", expected_result=429
        )
    ],
    ids=lambda case: case.description,
)
def test_given_ip_failures_when_one_login_succeeds_then_ip_limit_still_applies(
    test_case: AuthTestCase, tmp_path: Path
) -> None:
    store: ControlStore = build_control_store(tmp_path=tmp_path)
    store.create_user(
        username="alice",
        password="correct horse battery staple",
        roles=("viewer",),
    )
    client: TestClient = build_auth_client(
        settings=AuthSettings(
            mode=AuthenticationMode.PASSWORD,
            control_store_url="unused",
            session_cookie_secure=False,
        ),
        store=store,
    )
    for index in range(19):
        response: Response = client.post(
            "/api/auth/login",
            json={"username": f"unknown-{index}", "password": "incorrect password"},
        )
        assert response.status_code == 401
    assert (
        client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "correct horse battery staple"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/auth/login",
            json={"username": "another-unknown", "password": "incorrect password"},
        ).status_code
        == 401
    )

    blocked: Response = client.post(
        "/api/auth/login",
        json={"username": "last-unknown", "password": "incorrect password"},
    )

    assert blocked.status_code == test_case.expected_result
    store.close()


@pytest.mark.parametrize(
    "test_case",
    [
        AuthTestCase(description="admin auto-provisioning role", expected_result="admin"),
        AuthTestCase(description="unknown auto-provisioning role", expected_result="operator"),
    ],
    ids=lambda case: case.description,
)
def test_given_unsafe_proxy_default_role_when_configuring_then_configuration_is_rejected(
    test_case: AuthTestCase,
) -> None:
    with pytest.raises(AuthConfigurationError, match="default role must be 'viewer'"):
        AuthSettings(
            mode=AuthenticationMode.TRUSTED_PROXY,
            control_store_url="unused",
            default_role=str(test_case.expected_result),
        )


@pytest.mark.parametrize(
    "test_case",
    [AuthTestCase(description="account created and audited", expected_result=200)],
    ids=lambda case: case.description,
)
def test_given_local_admin_when_managing_account_then_api_persists_and_audits(
    test_case: AuthTestCase, tmp_path: Path
) -> None:
    store: ControlStore = build_control_store(tmp_path=tmp_path)
    client: TestClient = build_auth_client(
        settings=AuthSettings(
            mode=AuthenticationMode.DISABLED,
            control_store_url="unused",
        ),
        store=store,
    )

    created: Response = client.post(
        "/api/admin/users",
        json={
            "username": "alice",
            "authenticationSource": "password",
            "password": "correct horse battery staple",
            "roles": ["viewer"],
        },
    )
    users: Response = client.get("/api/admin/users")
    audit: Response = client.get("/api/admin/audit")

    assert created.status_code == test_case.expected_result
    assert users.json()[0]["username"] == "alice"
    assert users.json()[0]["authenticationSources"] == ["password"]
    assert any(record["operation"] == "user.created" for record in audit.json())
    store.close()


@pytest.mark.parametrize(
    "test_case",
    [AuthTestCase(description="short initial password", expected_result=400)],
    ids=lambda case: case.description,
)
def test_given_short_initial_password_when_creating_account_then_validation_is_returned(
    test_case: AuthTestCase, tmp_path: Path
) -> None:
    store: ControlStore = build_control_store(tmp_path=tmp_path)
    client: TestClient = build_auth_client(
        settings=AuthSettings(
            mode=AuthenticationMode.DISABLED,
            control_store_url="unused",
        ),
        store=store,
    )

    response: Response = client.post(
        "/api/admin/users",
        json={
            "username": "alice",
            "authenticationSource": "password",
            "password": "short",
            "roles": ["viewer"],
        },
    )

    assert response.status_code == test_case.expected_result
    assert response.json()["detail"] == "Password must contain at least 12 characters"
    assert store.list_users() == ()
    store.close()


@pytest.mark.parametrize(
    "test_case",
    [AuthTestCase(description="project role granted, listed, and revoked", expected_result=200)],
    ids=lambda case: case.description,
)
def test_given_local_admin_when_managing_project_roles_then_assignments_round_trip(
    test_case: AuthTestCase, tmp_path: Path
) -> None:
    store: ControlStore = build_control_store(tmp_path=tmp_path)
    account: UserAccount = store.create_user(username="alice", roles=("viewer",))
    client: TestClient = build_auth_client(
        settings=AuthSettings(
            mode=AuthenticationMode.DISABLED,
            control_store_url="unused",
        ),
        store=store,
    )

    granted: Response = client.post(
        f"/api/admin/users/{account.user_id}/project-roles",
        json={"projectName": "analytics", "role": "operator", "targetName": "prod"},
    )
    duplicate: Response = client.post(
        f"/api/admin/users/{account.user_id}/project-roles",
        json={"projectName": "analytics", "role": "operator", "targetName": "prod"},
    )
    listed: Response = client.get(
        f"/api/admin/users/{account.user_id}/project-roles",
        params={"project": "analytics"},
    )
    revoked: Response = client.delete(f"/api/admin/project-roles/{granted.json()['assignmentId']}")
    after_revoke: Response = client.get(
        f"/api/admin/users/{account.user_id}/project-roles",
        params={"project": "analytics"},
    )

    assert granted.status_code == test_case.expected_result
    assert granted.json()["role"] == "operator"
    assert granted.json()["targetName"] == "prod"
    assert duplicate.status_code == 409
    assert [item["assignmentId"] for item in listed.json()] == [granted.json()["assignmentId"]]
    assert revoked.status_code == 200
    assert revoked.json()["revokedAt"] is not None
    assert after_revoke.json() == []
    store.close()


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])

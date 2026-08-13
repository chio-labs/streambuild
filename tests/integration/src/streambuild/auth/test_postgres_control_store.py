import pytest
from testcontainers.postgres import PostgresContainer

from streambuild.auth.classes.control_store import ControlStore
from streambuild.auth.models import ProjectRoleAssignment, SessionCredentials, UserAccount
from streambuild.auth.types import AuthenticationSource
from tests.integration.src.streambuild.auth._test_types import PostgresControlStoreTestCase


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        PostgresControlStoreTestCase(
            description="PostgreSQL account lifecycle", expected_username="alice"
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_store_when_using_accounts_then_matches_sqlite_contract(
    test_case: PostgresControlStoreTestCase,
) -> None:
    with PostgresContainer("postgres:16-alpine") as postgres:
        store: ControlStore = ControlStore(url=postgres.get_connection_url(driver="psycopg"))
        account: UserAccount = store.create_user(
            username="alice",
            password="correct horse battery staple",
            roles=("viewer",),
        )

        login: tuple[UserAccount, SessionCredentials] | None = store.authenticate_password(
            username="alice",
            password="correct horse battery staple",
            session_ttl_seconds=3600,
        )

        assert login is not None
        reloaded, credentials = login
        assert reloaded.username == test_case.expected_username
        assert reloaded.user_id == account.user_id
        assert reloaded.authentication_sources == (AuthenticationSource.PASSWORD,)
        assert store.resolve_session(token=credentials.token) is not None

        store.grant_role(user_id=account.user_id, role_name="admin", actor_user_id=None)
        store.create_user(username="recovery-admin", roles=("admin",))
        store.set_user_active(
            user_id=account.user_id,
            is_active=False,
            actor_user_id=None,
        )

        assert store.resolve_session(token=credentials.token) is None
        disabled: UserAccount | None = store.get_user_by_id(user_id=account.user_id)
        assert disabled is not None
        assert disabled.is_active is False

        assignment: ProjectRoleAssignment = store.grant_project_role(
            user_id=account.user_id,
            project_name="analytics",
            role_name="operator",
            target_name="prod",
            actor_user_id=None,
        )
        assert store.list_project_role_assignments(
            user_id=account.user_id, project_name="analytics"
        ) == (assignment,)

        revoked: ProjectRoleAssignment = store.revoke_project_role(
            assignment_id=assignment.assignment_id, actor_user_id=None
        )
        assert (
            store.list_project_role_assignments(user_id=account.user_id, project_name="analytics")
            == ()
        )
        assert store.list_project_role_assignments(
            user_id=account.user_id,
            project_name="analytics",
            include_revoked=True,
        ) == (revoked,)
        store.close()


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])

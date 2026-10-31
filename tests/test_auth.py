import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.auth import new_user_session
from app.models import AuditLog, LoginAttempt, User, UserRole, UserSession
from app.security import hash_password, hash_session_id

PASSWORD = "correct horse battery staple"
CSRF_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')


def create_user(test_db, *, role=UserRole.USER, active=True, email="member@example.com"):
    with test_db() as db:
        user = User(
            id=uuid.uuid4(),
            full_name="Test Account",
            email=email,
            password_hash=hash_password(PASSWORD),
            role=role,
            is_active=active,
        )
        db.add(user)
        db.commit()
        return user.id


def get_csrf(response) -> str:
    match = CSRF_PATTERN.search(response.text)
    assert match is not None
    return match.group(1)


def sign_in(client, email="member@example.com", password=PASSWORD):
    page = client.get("/login")
    response = client.post(
        "/login",
        data={"email": email, "password": password, "csrf_token": get_csrf(page)},
    )
    return response


def test_database_backed_login_and_csrf_protected_logout(client, test_db) -> None:
    user_id = create_user(test_db)
    page = client.get("/login")
    csrf_token = get_csrf(page)

    rejected = client.post(
        "/login",
        data={"email": "member@example.com", "password": PASSWORD, "csrf_token": "wrong"},
    )
    assert rejected.status_code == 403

    response = client.post(
        "/login",
        data={"email": "MEMBER@example.com", "password": PASSWORD, "csrf_token": csrf_token},
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    session_id = response.cookies["session_id"]
    assert session_id
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "secure" not in cookie
    with test_db() as db:
        session = db.get(UserSession, hash_session_id(session_id))
        assert session is not None
        assert session.id != session_id
        assert session.user_id == user_id

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    logout = client.post(
        "/logout",
        data={"csrf_token": get_csrf(dashboard)},
    )
    assert logout.status_code == 303
    assert logout.headers["location"] == "/login"
    with test_db() as db:
        assert db.get(UserSession, hash_session_id(session_id)) is None


def test_first_admin_can_be_created_through_one_time_setup(client, test_db) -> None:
    login_page = client.get("/login")
    assert 'href="/setup"' in login_page.text

    setup_page = client.get("/setup")
    response = client.post(
        "/setup",
        data={
            "csrf_token": get_csrf(setup_page),
            "full_name": "Initial Administrator",
            "email": "ADMIN@example.com",
            "password": PASSWORD,
            "password_confirmation": PASSWORD,
        },
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert 'href="/admin/users"' in dashboard.text
    with test_db() as db:
        administrator = db.scalar(select(User).where(User.email == "admin@example.com"))
        assert administrator is not None
        assert administrator.role == UserRole.ADMIN
        assert administrator.is_active
        session_id = client.cookies.get("session_id")
        assert session_id is not None
        stored_session = db.get(UserSession, hash_session_id(session_id))
        assert stored_session is not None
        assert stored_session.user_id == administrator.id
        event = db.scalar(
            select(AuditLog).where(AuditLog.action == "user.bootstrap_admin_created")
        )
        assert event is not None
        assert event.entity_id == str(administrator.id)

    assert 'href="/setup"' not in client.get("/login").text
    assert client.get("/setup").headers["location"] == "/login"


def test_first_admin_setup_validates_input_and_csrf(client, test_db) -> None:
    setup_page = client.get("/setup")
    csrf_token = get_csrf(setup_page)

    csrf_rejected = client.post(
        "/setup",
        data={
            "csrf_token": "invalid",
            "full_name": "Initial Administrator",
            "email": "admin@example.com",
            "password": PASSWORD,
            "password_confirmation": PASSWORD,
        },
    )
    assert csrf_rejected.status_code == 403

    invalid_password = client.post(
        "/setup",
        data={
            "csrf_token": csrf_token,
            "full_name": "Initial Administrator",
            "email": "admin@example.com",
            "password": "short",
            "password_confirmation": "different",
        },
    )
    assert invalid_password.status_code == 400
    assert "matching passwords" in invalid_password.text
    with test_db() as db:
        assert db.scalar(select(User.id).where(User.role == UserRole.ADMIN)) is None


def test_first_admin_setup_rejects_existing_email_and_stale_setup(client, test_db) -> None:
    create_user(test_db, email="existing@example.com")
    setup_page = client.get("/setup")
    csrf_token = get_csrf(setup_page)

    duplicate_email = client.post(
        "/setup",
        data={
            "csrf_token": csrf_token,
            "full_name": "Initial Administrator",
            "email": "existing@example.com",
            "password": PASSWORD,
            "password_confirmation": PASSWORD,
        },
    )
    assert duplicate_email.status_code == 409
    assert "already in use" in duplicate_email.text

    create_user(test_db, role=UserRole.ADMIN, email="admin@example.com")
    stale_setup = client.post(
        "/setup",
        data={
            "csrf_token": csrf_token,
            "full_name": "Second Administrator",
            "email": "second-admin@example.com",
            "password": PASSWORD,
            "password_confirmation": PASSWORD,
        },
    )
    assert stale_setup.status_code == 303
    assert stale_setup.headers["location"] == "/login"
    with test_db() as db:
        administrators = db.scalars(
            select(User).where(User.role == UserRole.ADMIN)
        ).all()
        assert len(administrators) == 1


def test_expired_session_is_rejected_and_removed(client, test_db) -> None:
    user_id = create_user(test_db)
    user_session, raw_session_id = new_user_session(user_id)
    user_session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    with test_db() as db:
        db.add(user_session)
        db.commit()
    client.cookies.set("session_id", raw_session_id)

    response = client.get("/dashboard")

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    with test_db() as db:
        assert db.get(UserSession, hash_session_id(raw_session_id)) is None


def test_invalid_and_inactive_accounts_cannot_sign_in(client, test_db) -> None:
    create_user(test_db, active=False)
    page = client.get("/login")
    csrf_token = get_csrf(page)

    for email, password in [
        ("member@example.com", PASSWORD),
        ("missing@example.com", PASSWORD),
        ("member@example.com", "wrong password"),
    ]:
        response = client.post(
            "/login",
            data={"email": email, "password": password, "csrf_token": csrf_token},
        )
        assert response.status_code == 400
        assert "Unable to sign in" in response.text


def test_login_rate_limit_blocks_after_five_failures(client, test_db) -> None:
    create_user(test_db)
    page = client.get("/login")
    csrf_token = get_csrf(page)
    for _ in range(5):
        response = client.post(
            "/login",
            data={"email": "member@example.com", "password": "not the password", "csrf_token": csrf_token},
        )
        assert response.status_code == 400

    blocked = client.post(
        "/login",
        data={"email": "member@example.com", "password": PASSWORD, "csrf_token": csrf_token},
    )
    assert blocked.status_code == 400
    with test_db() as db:
        assert db.scalar(select(LoginAttempt.failed_attempts)) == 5


def test_non_admin_cannot_access_account_management(client, test_db) -> None:
    create_user(test_db)
    assert sign_in(client).status_code == 303

    response = client.get("/admin/users")

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("role", "email", "admin_links_visible"),
    [
        (UserRole.USER, "member@example.com", False),
        (UserRole.ADMIN, "admin@example.com", True),
    ],
)
def test_shared_header_shows_role_appropriate_navigation(
    client, test_db, role, email, admin_links_visible
) -> None:
    create_user(test_db, role=role, email=email)
    login_page = client.get("/login")
    assert 'class="header-navigation"' not in login_page.text

    assert sign_in(client, email=email).status_code == 303
    dashboard = client.get("/dashboard")

    for href in ("/dashboard", "/contributions", "/expenses"):
        assert f'href="{href}"' in dashboard.text
    assert ('href="/admin/users"' in dashboard.text) is admin_links_visible


def test_admin_can_create_update_and_deactivate_accounts(client, test_db) -> None:
    create_user(test_db, role=UserRole.ADMIN, email="admin@example.com")
    assert sign_in(client, email="admin@example.com").status_code == 303
    page = client.get("/admin/users")
    csrf_token = get_csrf(page)

    csrf_rejected = client.post(
        "/admin/users",
        data={
            "csrf_token": "invalid",
            "full_name": "Invalid",
            "email": "invalid@example.com",
            "password": "a sufficiently long password",
            "role": "USER",
        },
    )
    assert csrf_rejected.status_code == 403

    created = client.post(
        "/admin/users",
        data={
            "csrf_token": csrf_token,
            "full_name": "New Contributor",
            "email": "new@example.com",
            "password": "a sufficiently long password",
            "role": "USER",
        },
    )
    assert created.status_code == 303
    duplicate = client.post(
        "/admin/users",
        data={
            "csrf_token": csrf_token,
            "full_name": "Duplicate Contributor",
            "email": "new@example.com",
            "password": "a sufficiently long password",
            "role": "USER",
        },
    )
    assert duplicate.status_code == 409
    assert "already in use" in duplicate.text
    with test_db() as db:
        user = db.scalar(select(User).where(User.email == "new@example.com"))
        assert user is not None
        user_id = user.id
        stored_session, raw_session_id = new_user_session(user_id)
        db.add(stored_session)
        db.commit()

    updated = client.post(
        f"/admin/users/{user_id}",
        data={
            "csrf_token": csrf_token,
            "full_name": "Updated Contributor",
            "email": "updated@example.com",
            "role": "ADMIN",
            "password": "",
        },
    )
    assert updated.status_code == 303
    with test_db() as db:
        user = db.get(User, user_id)
        assert user is not None
        assert user.full_name == "Updated Contributor"
        assert user.email == "updated@example.com"
        assert user.role == UserRole.ADMIN
        assert user.is_active is False
        assert db.get(UserSession, hash_session_id(raw_session_id)) is None
        events = db.scalars(select(AuditLog).where(AuditLog.entity_id == str(user_id))).all()
        assert [event.action for event in events] == ["user.created", "user.updated"]


def test_last_active_admin_cannot_be_demoted(client, test_db) -> None:
    admin_id = create_user(test_db, role=UserRole.ADMIN, email="admin@example.com")
    assert sign_in(client, email="admin@example.com").status_code == 303
    page = client.get("/admin/users")
    csrf_token = get_csrf(page)

    response = client.post(
        f"/admin/users/{admin_id}",
        data={
            "csrf_token": csrf_token,
            "full_name": "Test Account",
            "email": "admin@example.com",
            "role": "USER",
            "is_active": "on",
            "password": "",
        },
    )

    assert response.status_code == 409
    assert "last active administrator" in response.text
    with test_db() as db:
        assert db.get(User, admin_id).role == UserRole.ADMIN

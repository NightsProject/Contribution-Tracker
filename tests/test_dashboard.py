from datetime import UTC, date, datetime, timedelta
from io import BytesIO
import re
import uuid

from PIL import Image
from sqlalchemy import select

from app.config import Settings
from app.models import (
    AuditLog,
    Contribution,
    ContributionStatus,
    Expense,
    ExpenseStatus,
    PaymentSettings,
    User,
    UserRole,
)
from app.security import hash_password

PASSWORD = "correct horse battery staple"
CSRF_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')


def create_user(test_db, *, role=UserRole.USER, email="member@example.com"):
    with test_db() as db:
        user = User(
            id=uuid.uuid4(),
            full_name="Test Account",
            email=email,
            password_hash=hash_password(PASSWORD),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        return user.id


def csrf_from(response) -> str:
    match = CSRF_PATTERN.search(response.text)
    assert match is not None
    return match.group(1)


def sign_in(client, email="member@example.com"):
    page = client.get("/login")
    return client.post(
        "/login",
        data={
            "email": email,
            "password": PASSWORD,
            "csrf_token": csrf_from(page),
        },
    )


def test_dashboard_shows_pool_summary_and_combined_history(client, test_db):
    member_id = create_user(test_db)
    create_user(test_db, role=UserRole.ADMIN, email="admin@example.com")
    with test_db() as db:
        db.add_all(
            [
                Contribution(
                    user_id=member_id,
                    amount_centavos=8_000,
                    payment_reference="TXN-APPROVED",
                    payment_date=date.today(),
                    status=ContributionStatus.APPROVED,
                ),
                Contribution(
                    user_id=member_id,
                    amount_centavos=2_000,
                    payment_reference="TXN-PENDING",
                    payment_date=date.today(),
                    status=ContributionStatus.PENDING,
                ),
                Expense(
                    description="Internet",
                    category="Utilities",
                    amount_centavos=1_500,
                    expense_date=date.today(),
                    status=ExpenseStatus.POSTED,
                ),
                Expense(
                    description="Reversed expense",
                    category="Utilities",
                    amount_centavos=100,
                    expense_date=date.today(),
                    status=ExpenseStatus.REVERSED,
                ),
            ]
        )
        db.add(
            PaymentSettings(
                id=1,
                payment_method="Bank transfer",
                account_name="Pool Account",
                account_identifier="123-456",
                instructions="Use your name as reference.",
            )
        )
        db.commit()

    assert sign_in(client).status_code == 303
    dashboard = client.get("/dashboard")

    assert dashboard.status_code == 200
    assert "₱65.00" in dashboard.text
    assert "₱80.00" in dashboard.text
    assert "₱15.00" in dashboard.text
    assert "1</p>" in dashboard.text
    assert "TXN-APPROVED" in dashboard.text
    assert "TXN-PENDING" in dashboard.text
    assert "Internet" in dashboard.text
    assert "Reversed expense" in dashboard.text
    assert "Bank transfer" in dashboard.text
    assert "Use your name as reference." in dashboard.text
    assert "Payment settings" not in dashboard.text


def test_dashboard_filters_by_type_status_search_account_and_date(client, test_db):
    member_id = create_user(test_db)
    with test_db() as db:
        db.add_all(
            [
                Contribution(
                    user_id=member_id,
                    amount_centavos=8_000,
                    payment_reference="TXN-ALPHA",
                    payment_date=date.today(),
                    status=ContributionStatus.APPROVED,
                ),
                Contribution(
                    user_id=member_id,
                    amount_centavos=2_000,
                    payment_reference="TXN-PENDING",
                    payment_date=date.today(),
                    status=ContributionStatus.PENDING,
                ),
                Expense(
                    description="Internet",
                    category="Utilities",
                    amount_centavos=1_500,
                    expense_date=date.today(),
                    status=ExpenseStatus.POSTED,
                ),
            ]
        )
        db.commit()

    assert sign_in(client).status_code == 303
    by_type = client.get("/dashboard?type=expense")
    assert "Internet" in by_type.text
    assert "TXN-ALPHA" not in by_type.text

    by_search = client.get("/dashboard?q=alpha")
    assert "TXN-ALPHA" in by_search.text
    assert "Internet" not in by_search.text

    by_status = client.get("/dashboard?status=PENDING")
    assert "TXN-PENDING" in by_status.text
    assert "TXN-ALPHA" not in by_status.text
    assert "Internet" not in by_status.text

    by_account = client.get("/dashboard?account=Test")
    assert "TXN-ALPHA" in by_account.text
    assert "Internet" not in by_account.text
    by_schedule = client.get("/dashboard?account=Scheduled")
    assert "Internet" in by_schedule.text

    by_date = client.get(f"/dashboard?from_date={date.today().isoformat()}&to_date={date.today().isoformat()}")
    assert "TXN-ALPHA" in by_date.text
    assert client.get("/dashboard?from_date=invalid").status_code == 400
    assert client.get("/dashboard?from_date=2026-10-31&to_date=2026-10-30").status_code == 400


def test_dashboard_paginates_and_admin_sees_all_contributions(client, test_db):
    member_id = create_user(test_db)
    create_user(test_db, role=UserRole.ADMIN, email="admin@example.com")
    other_id = create_user(test_db, email="other@example.com")
    with test_db() as db:
        db.add_all(
            [
                Contribution(
                    user_id=other_id,
                    amount_centavos=100,
                    payment_reference=f"TXN-{index:02d}",
                    payment_date=date.today(),
                    status=ContributionStatus.APPROVED,
                    created_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index),
                )
                for index in range(25)
            ]
        )
        db.add(
            Contribution(
                user_id=member_id,
                amount_centavos=100,
                payment_reference="TXN-OWN-PENDING",
                payment_date=date.today(),
                status=ContributionStatus.PENDING,
            )
        )
        db.commit()

    assert sign_in(client).status_code == 303
    member_dashboard = client.get("/dashboard")
    assert "TXN-OWN-PENDING" in member_dashboard.text
    assert "Page 1 of 2" in member_dashboard.text
    assert "TXN-24" in member_dashboard.text
    assert "TXN-00" not in member_dashboard.text
    assert "TXN-00" in client.get("/dashboard?page=2").text

    client.post("/logout", data={"csrf_token": csrf_from(client.get("/dashboard"))})
    assert sign_in(client, email="admin@example.com").status_code == 303
    admin_dashboard = client.get("/dashboard")
    assert "TXN-OWN-PENDING" in admin_dashboard.text
    assert "Payment settings" in admin_dashboard.text


def image_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (4, 4), color="purple").save(output, format="PNG")
    return output.getvalue()


def test_admin_payment_settings_are_audited_and_qr_is_private(
    client, test_db, monkeypatch, tmp_path
):
    import app.routes.payment_settings as payment_routes
    import app.services.file_storage as file_storage

    settings = Settings(uploads_dir=str(tmp_path))
    monkeypatch.setattr(payment_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(file_storage, "get_settings", lambda: settings)
    admin_id = create_user(test_db, role=UserRole.ADMIN, email="admin@example.com")
    create_user(test_db)
    assert sign_in(client, email="admin@example.com").status_code == 303
    page = client.get("/admin/payment-settings")
    response = client.post(
        "/admin/payment-settings",
        data={
            "csrf_token": csrf_from(page),
            "payment_method": "E-wallet",
            "account_name": "Shared Pool",
            "account_identifier": "wallet-123",
            "instructions": "Include your full name.",
        },
        files={"qr_image": ("qr.png", image_bytes(), "image/png")},
    )

    assert response.status_code == 303
    with test_db() as db:
        saved = db.get(PaymentSettings, 1)
        assert saved is not None
        assert saved.payment_method == "E-wallet"
        assert saved.updated_by == admin_id
        qr_key = saved.qr_file_key
        assert qr_key is not None
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "payment_settings.updated",
                AuditLog.entity_id == "1",
            )
        )
        assert audit is not None
        assert audit.details["payment_method"] == "E-wallet"
        assert audit.actor_user_id == admin_id
    assert (tmp_path / qr_key).stat().st_mode & 0o777 == 0o600

    qr_response = client.get("/admin/payment-settings/qr")
    assert qr_response.status_code == 200
    assert qr_response.headers["content-type"] == "image/png"
    assert qr_response.headers["x-content-type-options"] == "nosniff"

    client.post("/logout", data={"csrf_token": csrf_from(client.get("/admin/payment-settings"))})
    assert sign_in(client).status_code == 303
    dashboard = client.get("/dashboard")
    assert "E-wallet" in dashboard.text
    assert "wallet-123" in dashboard.text
    assert "Include your full name." in dashboard.text
    assert "/admin/payment-settings/qr" in dashboard.text
    assert client.get("/admin/payment-settings").status_code == 403


def test_invalid_qr_upload_does_not_replace_current_settings(
    client, test_db, monkeypatch, tmp_path
):
    import app.routes.payment_settings as payment_routes
    import app.services.file_storage as file_storage

    settings = Settings(uploads_dir=str(tmp_path), max_upload_size_bytes=32)
    monkeypatch.setattr(payment_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(file_storage, "get_settings", lambda: settings)
    create_user(test_db, role=UserRole.ADMIN, email="admin@example.com")
    assert sign_in(client, email="admin@example.com").status_code == 303
    page = client.get("/admin/payment-settings")
    invalid = client.post(
        "/admin/payment-settings",
        data={
            "csrf_token": csrf_from(page),
            "payment_method": "E-wallet",
        },
        files={"qr_image": ("qr.svg", b"<svg></svg>", "image/svg+xml")},
    )
    assert invalid.status_code == 400
    oversized = client.post(
        "/admin/payment-settings",
        data={
            "csrf_token": csrf_from(page),
            "payment_method": "E-wallet",
        },
        files={"qr_image": ("qr.png", image_bytes(), "image/png")},
    )
    assert oversized.status_code == 413
    assert list(tmp_path.iterdir()) == []
    with test_db() as db:
        saved = db.get(PaymentSettings, 1)
        assert saved is not None
        assert saved.payment_method is None


def test_payment_settings_require_admin_and_csrf(client, test_db):
    create_user(test_db)
    assert sign_in(client).status_code == 303
    assert client.get("/admin/payment-settings").status_code == 403
    assert client.get("/admin/payment-settings/qr").status_code == 404


def test_dashboard_requires_sign_in(client):
    assert client.get("/dashboard").status_code == 303

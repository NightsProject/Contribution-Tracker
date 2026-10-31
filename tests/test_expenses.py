from datetime import date
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
    login_page = client.get("/login")
    return client.post(
        "/login",
        data={
            "email": email,
            "password": PASSWORD,
            "csrf_token": csrf_from(login_page),
        },
    )


def image_bytes(image_format="PNG") -> bytes:
    output = BytesIO()
    Image.new("RGB", (4, 4), color="green").save(output, format=image_format)
    return output.getvalue()


def add_contribution(db, user_id, amount=10_000):
    db.add(
        Contribution(
            user_id=user_id,
            amount_centavos=amount,
            payment_reference=f"TXN-{uuid.uuid4()}",
            payment_date=date.today(),
            status=ContributionStatus.APPROVED,
        )
    )
    db.commit()


def expense_data(csrf_token: str, **overrides):
    data = {
        "csrf_token": csrf_token,
        "description": "Office supplies",
        "category": "Supplies",
        "amount": "25.50",
        "expense_date": date.today().isoformat(),
    }
    data.update(overrides)
    return data


def test_admin_can_post_expense_and_users_can_view_history(client, test_db):
    admin_id = create_user(test_db, role=UserRole.ADMIN, email="admin@example.com")
    create_user(test_db)
    with test_db() as db:
        add_contribution(db, admin_id)
    assert sign_in(client, email="admin@example.com").status_code == 303
    page = client.get("/expenses")
    response = client.post(
        "/admin/expenses",
        data=expense_data(csrf_from(page)),
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/expenses?created=1"
    history = client.get("/expenses")
    assert "Office supplies" in history.text
    assert "−₱25.50" in history.text
    assert "₱74.50" in history.text

    with test_db() as db:
        expense = db.scalar(select(Expense))
        assert expense is not None
        assert expense.created_by == admin_id
        assert expense.amount_centavos == 2550
        assert expense.status == ExpenseStatus.POSTED
        assert db.scalar(select(AuditLog.action).where(AuditLog.entity_id == str(expense.id))) == (
            "expense.posted"
        )

    client.post("/logout", data={"csrf_token": csrf_from(client.get("/expenses"))})
    assert sign_in(client).status_code == 303
    user_history = client.get("/expenses")
    assert "Office supplies" in user_history.text
    assert "Record an expense" not in user_history.text
    forbidden = client.post(
        "/admin/expenses",
        data=expense_data(csrf_from(user_history)),
    )
    assert forbidden.status_code == 403


def test_overspending_invalid_amount_and_csrf_are_rejected(
    client, test_db, monkeypatch, tmp_path
):
    import app.routes.expenses as expense_routes
    import app.services.file_storage as file_storage

    settings = Settings(uploads_dir=str(tmp_path))
    monkeypatch.setattr(expense_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(file_storage, "get_settings", lambda: settings)
    admin_id = create_user(test_db, role=UserRole.ADMIN, email="admin@example.com")
    with test_db() as db:
        add_contribution(db, admin_id, amount=5_000)
    assert sign_in(client, email="admin@example.com").status_code == 303
    csrf_token = csrf_from(client.get("/expenses"))

    for amount in ["0", "-1", "1.001", "999999999.99"]:
        response = client.post(
            "/admin/expenses",
            data=expense_data(csrf_token, amount=amount),
        )
        assert response.status_code == 400
        assert "positive PHP amount" in response.text

    overspent = client.post(
        "/admin/expenses",
        data=expense_data(csrf_token, amount="50.01"),
        files={"receipt": ("receipt.png", image_bytes("PNG"), "image/png")},
    )
    assert overspent.status_code == 400
    assert "exceeds the available pool balance" in overspent.text
    assert list(tmp_path.iterdir()) == []
    bad_csrf = client.post(
        "/admin/expenses",
        data=expense_data("invalid"),
    )
    assert bad_csrf.status_code == 403
    with test_db() as db:
        assert db.scalar(select(Expense.id)) is None


def test_receipt_upload_is_normalized_private_and_authenticated(
    client, test_db, monkeypatch, tmp_path
):
    import app.routes.expenses as expense_routes
    import app.services.file_storage as file_storage

    settings = Settings(uploads_dir=str(tmp_path))
    monkeypatch.setattr(expense_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(file_storage, "get_settings", lambda: settings)
    admin_id = create_user(test_db, role=UserRole.ADMIN, email="admin@example.com")
    with test_db() as db:
        add_contribution(db, admin_id)
    assert sign_in(client, email="admin@example.com").status_code == 303
    response = client.post(
        "/admin/expenses",
        data=expense_data(csrf_from(client.get("/expenses"))),
        files={"receipt": ("wrong.jpg", image_bytes("PNG"), "image/jpeg")},
    )

    assert response.status_code == 303
    with test_db() as db:
        expense = db.scalar(select(Expense))
        assert expense is not None
        assert expense.receipt_file_key.endswith(".png")
        key = expense.receipt_file_key
        expense_id = expense.id
        audit = db.scalar(select(AuditLog).where(AuditLog.entity_id == str(expense_id)))
        assert audit is not None
        assert audit.details["receipt_attached"] is True
    assert (tmp_path / key).stat().st_mode & 0o777 == 0o600
    receipt_response = client.get(f"/expenses/{expense_id}/receipt")
    assert receipt_response.status_code == 200
    assert receipt_response.headers["content-type"] == "image/png"
    assert receipt_response.headers["x-content-type-options"] == "nosniff"

    client.post("/logout", data={"csrf_token": csrf_from(client.get("/expenses"))})
    assert client.get(f"/expenses/{expense_id}/receipt").status_code == 303


def test_invalid_or_oversized_receipt_does_not_post_or_leave_files(
    client, test_db, monkeypatch, tmp_path
):
    import app.routes.expenses as expense_routes
    import app.services.file_storage as file_storage

    settings = Settings(uploads_dir=str(tmp_path), max_upload_size_bytes=32)
    monkeypatch.setattr(expense_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(file_storage, "get_settings", lambda: settings)
    admin_id = create_user(test_db, role=UserRole.ADMIN, email="admin@example.com")
    with test_db() as db:
        add_contribution(db, admin_id)
    assert sign_in(client, email="admin@example.com").status_code == 303
    csrf_token = csrf_from(client.get("/expenses"))

    oversized = client.post(
        "/admin/expenses",
        data=expense_data(csrf_token),
        files={"receipt": ("receipt.png", image_bytes("PNG"), "image/png")},
    )
    assert oversized.status_code == 413
    invalid = client.post(
        "/admin/expenses",
        data=expense_data(csrf_token),
        files={"receipt": ("receipt.svg", b"<svg></svg>", "image/svg+xml")},
    )
    assert invalid.status_code == 400
    assert list(tmp_path.iterdir()) == []
    with test_db() as db:
        assert db.scalar(select(Expense.id)) is None


def test_expenses_page_requires_sign_in(client):
    response = client.get("/expenses")
    assert response.status_code == 303
    assert response.headers["location"] == "/login"

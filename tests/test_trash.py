from datetime import date
import re
import uuid

from sqlalchemy import select

from app.auth import new_user_session
from app.models import (
    AuditLog,
    Contribution,
    ContributionStatus,
    Expense,
    ExpenseStatus,
    User,
    UserRole,
    UserSession,
)
from app.security import hash_password, hash_session_id
from app.services.accounting import get_pool_balance

PASSWORD = "correct horse battery staple"
CSRF_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')


def create_user(test_db, *, email: str, role: UserRole) -> uuid.UUID:
    with test_db() as db:
        user = User(
            full_name=email.split("@")[0],
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


def sign_in(client, email: str) -> None:
    page = client.get("/login")
    response = client.post(
        "/login",
        data={
            "email": email,
            "password": PASSWORD,
            "csrf_token": csrf_from(page),
        },
    )
    assert response.status_code == 303


def test_admin_can_trash_and_restore_account_without_deleting_history(client, test_db):
    admin_id = create_user(test_db, email="admin@example.com", role=UserRole.ADMIN)
    account_id = create_user(test_db, email="member@example.com", role=UserRole.USER)
    user_session, raw_session_id = new_user_session(account_id)
    with test_db() as db:
        db.add(user_session)
        db.add(
            Contribution(
                user_id=account_id,
                amount_centavos=5000,
                payment_reference="PRESERVED-REFERENCE",
                payment_date=date.today(),
                status=ContributionStatus.APPROVED,
            )
        )
        db.commit()

    sign_in(client, "admin@example.com")
    page = client.get("/admin/users")
    response = client.post(
        f"/admin/trash/accounts/{account_id}",
        data={"csrf_token": csrf_from(page)},
    )

    assert response.status_code == 303
    with test_db() as db:
        account = db.get(User, account_id)
        assert account is not None
        assert account.is_active is False
        assert account.trashed_at is not None
        assert db.get(UserSession, hash_session_id(raw_session_id)) is None
        assert db.scalar(select(Contribution.id).where(Contribution.user_id == account_id))
        assert db.scalar(
            select(AuditLog.action).where(
                AuditLog.entity_id == str(account_id),
                AuditLog.action == "user.trashed",
            )
        )

    assert "member@example.com" not in client.get("/admin/users").text
    assert "member@example.com" in client.get("/admin/trash").text
    restored = client.post(
        f"/admin/trash/accounts/{account_id}/restore",
        data={"csrf_token": csrf_from(client.get("/admin/trash"))},
    )
    assert restored.status_code == 303
    with test_db() as db:
        account = db.get(User, account_id)
        assert account is not None
        assert account.trashed_at is None
        assert account.is_active is False
        assert db.scalar(
            select(AuditLog.action).where(
                AuditLog.entity_id == str(account_id),
                AuditLog.action == "user.restored_from_trash",
            )
        )

    assert "member@example.com" in client.get("/admin/users").text
    assert admin_id != account_id


def test_admin_can_void_refund_and_reverse_with_required_reasons(client, test_db):
    admin_id = create_user(test_db, email="admin@example.com", role=UserRole.ADMIN)
    member_id = create_user(test_db, email="member@example.com", role=UserRole.USER)
    with test_db() as db:
        approved_contribution = Contribution(
            user_id=member_id,
            amount_centavos=10_000,
            payment_reference="APPROVED-CONTRIBUTION",
            payment_date=date.today(),
            status=ContributionStatus.APPROVED,
        )
        pending_contribution = Contribution(
            user_id=member_id,
            amount_centavos=5_000,
            payment_reference="PENDING-CONTRIBUTION",
            payment_date=date.today(),
            status=ContributionStatus.PENDING,
        )
        expense = Expense(
            description="Test posted expense",
            category="Other",
            amount_centavos=2500,
            expense_date=date.today(),
            created_by=admin_id,
            status=ExpenseStatus.POSTED,
        )
        db.add_all([approved_contribution, pending_contribution, expense])
        db.commit()
        approved_contribution_id = approved_contribution.id
        pending_contribution_id = pending_contribution.id
        expense_id = expense.id
        assert get_pool_balance(db).available_centavos == 7500

    sign_in(client, "admin@example.com")
    dashboard = client.get("/dashboard")
    csrf_token = csrf_from(dashboard)
    assert "Void submission" in dashboard.text
    assert "Record refund" in dashboard.text
    assert "Reverse expense" in dashboard.text

    voided = client.post(
        f"/admin/contributions/{pending_contribution_id}/void",
        data={"csrf_token": csrf_token, "reason": "Duplicate pending payment record."},
    )
    assert voided.status_code == 303
    assert "transaction_action=voided" in voided.headers["location"]

    reversed_expense = client.post(
        f"/admin/expenses/{expense_id}/reverse",
        data={"csrf_token": csrf_token, "reason": "Expense was entered twice."},
    )
    assert reversed_expense.status_code == 303
    assert "transaction_action=expense_reversed" in reversed_expense.headers["location"]

    refunded = client.post(
        f"/admin/contributions/{approved_contribution_id}/refund",
        data={"csrf_token": csrf_token, "reason": "Payment was returned to the contributor."},
    )
    assert refunded.status_code == 303
    assert "transaction_action=refunded" in refunded.headers["location"]

    with test_db() as db:
        assert get_pool_balance(db).available_centavos == 0
        voided_contribution = db.get(Contribution, pending_contribution_id)
        assert voided_contribution.status == ContributionStatus.VOIDED
        assert voided_contribution.void_reason == "Duplicate pending payment record."
        refunded_contribution = db.get(Contribution, approved_contribution_id)
        assert refunded_contribution.status == ContributionStatus.REVERSED
        assert db.scalar(
            select(AuditLog.action).where(
                AuditLog.entity_id == str(pending_contribution_id),
                AuditLog.action == "contribution.voided",
            )
        )
        assert db.scalar(
            select(AuditLog.action).where(
                AuditLog.entity_id == str(approved_contribution_id),
                AuditLog.action == "contribution.refunded",
            )
        )
        assert db.scalar(
            select(AuditLog.action).where(
                AuditLog.entity_id == str(expense_id),
                AuditLog.action == "expense.reversed",
            )
        )

    dashboard = client.get("/dashboard")
    assert "Duplicate pending payment record." in dashboard.text
    assert "Payment was returned to the contributor." in dashboard.text
    assert "Process any actual payment refund separately." in client.get(
        refunded.headers["location"]
    ).text
    assert "Expense was entered twice." in dashboard.text
    expense_history = client.get("/expenses")
    assert "Expense was entered twice." in expense_history.text
    client.post("/logout", data={"csrf_token": csrf_from(dashboard)})
    sign_in(client, "member@example.com")
    contribution_history = client.get("/contributions")
    assert "VOIDED" in contribution_history.text
    assert "Duplicate pending payment record." in contribution_history.text
    member_dashboard = client.get("/dashboard")
    assert "Payment was returned to the contributor." in member_dashboard.text


def test_trash_requires_admin_and_csrf_and_prevents_self_trash(client, test_db):
    create_user(test_db, email="member@example.com", role=UserRole.USER)
    admin_id = create_user(test_db, email="admin@example.com", role=UserRole.ADMIN)
    sign_in(client, "member@example.com")
    member_page = client.get("/dashboard")
    forbidden = client.post(
        f"/admin/trash/accounts/{admin_id}",
        data={"csrf_token": csrf_from(member_page)},
    )
    assert forbidden.status_code == 403

    client.post("/logout", data={"csrf_token": csrf_from(member_page)})
    sign_in(client, "admin@example.com")
    admin_page = client.get("/admin/users")
    csrf_token = csrf_from(admin_page)
    csrf_rejected = client.post(
        f"/admin/trash/accounts/{admin_id}",
        data={"csrf_token": "invalid"},
    )
    assert csrf_rejected.status_code == 403
    self_trash = client.post(
        f"/admin/trash/accounts/{admin_id}",
        data={"csrf_token": csrf_token},
    )
    assert self_trash.status_code == 409
    with test_db() as db:
        assert db.get(User, admin_id).trashed_at is None


def test_voided_pending_contribution_cannot_be_reviewed(client, test_db):
    create_user(test_db, email="admin@example.com", role=UserRole.ADMIN)
    member_id = create_user(test_db, email="member@example.com", role=UserRole.USER)
    with test_db() as db:
        contribution = Contribution(
            user_id=member_id,
            amount_centavos=5000,
            payment_reference="VOIDED-PENDING",
            payment_date=date.today(),
            status=ContributionStatus.PENDING,
        )
        db.add(contribution)
        db.commit()
        contribution_id = contribution.id

    sign_in(client, "admin@example.com")
    dashboard = client.get("/dashboard")
    voided = client.post(
        f"/admin/contributions/{contribution_id}/void",
        data={
            "csrf_token": csrf_from(dashboard),
            "reason": "This pending record was submitted in error.",
        },
    )
    assert voided.status_code == 303
    pending_page = client.get("/admin/contributions/pending")
    assert "VOIDED-PENDING" not in pending_page.text
    review = client.post(
        f"/admin/contributions/{contribution_id}/approve",
        data={"csrf_token": csrf_from(pending_page)},
    )
    assert review.status_code == 409

    with test_db() as db:
        contribution = db.get(Contribution, contribution_id)
        assert contribution is not None
        assert contribution.status == ContributionStatus.VOIDED
        assert contribution.void_reason == "This pending record was submitted in error."

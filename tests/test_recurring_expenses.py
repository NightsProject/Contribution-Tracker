from datetime import UTC, date, datetime, timedelta
from io import BytesIO
import re
import uuid

from sqlalchemy import select

import pytest
from app.models import (
    AuditLog,
    Contribution,
    ContributionStatus,
    Expense,
    ExpenseStatus,
    OccurrenceStatus,
    RecurringExpense,
    RecurringExpenseStatus,
    RecurringOccurrence,
    User,
    UserRole,
)
from app.scheduler.worker import process_due_schedules_once
from app.security import hash_password
from app.services.recurring_expenses import as_utc, process_next_occurrence
from app.services.recurring_expenses import RecurringExpenseStateError

PASSWORD = "correct horse battery staple"
CSRF_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')


def create_user(test_db, *, role=UserRole.ADMIN, email="admin@example.com"):
    with test_db() as db:
        user = User(
            id=uuid.uuid4(),
            full_name="Test Admin",
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


def sign_in(client, email="admin@example.com"):
    page = client.get("/login")
    return client.post(
        "/login",
        data={
            "email": email,
            "password": PASSWORD,
            "csrf_token": csrf_from(page),
        },
    )


def add_contributions(db, user_id, amount: int) -> None:
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


def make_schedule(
    db,
    user_id,
    *,
    amount=2_000,
    interval_days=1,
    start_date: datetime,
    end_date=None,
):
    schedule = RecurringExpense(
        name="Internet",
        description="Monthly service",
        amount_centavos=amount,
        category="Utilities",
        interval_days=interval_days,
        start_date=start_date,
        end_date=end_date,
        next_due_at=start_date,
        status=RecurringExpenseStatus.ACTIVE,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(schedule)
    db.commit()
    return schedule.id


def test_worker_posts_missed_occurrences_in_order_and_stops_when_blocked(test_db):
    user_id = create_user(test_db)
    now = datetime(2026, 10, 31, 7, tzinfo=UTC)
    start = now - timedelta(days=3)
    with test_db() as db:
        add_contributions(db, user_id, 5_000)
        schedule_id = make_schedule(db, user_id, start_date=start)

    assert process_due_schedules_once(test_db, now=now) == 2
    with test_db() as db:
        schedule = db.get(RecurringExpense, schedule_id)
        assert schedule is not None
        assert as_utc(schedule.next_due_at) == start + timedelta(days=2)
        occurrences = db.scalars(
            select(RecurringOccurrence)
            .where(RecurringOccurrence.recurring_expense_id == schedule_id)
            .order_by(RecurringOccurrence.scheduled_for)
        ).all()
        assert [item.status for item in occurrences] == [
            OccurrenceStatus.POSTED,
            OccurrenceStatus.POSTED,
            OccurrenceStatus.BLOCKED,
        ]
        assert [as_utc(item.scheduled_for) for item in occurrences] == [
            start,
            start + timedelta(days=1),
            start + timedelta(days=2),
        ]
        expenses = db.scalars(
            select(Expense)
            .where(Expense.recurring_expense_id == schedule_id)
            .order_by(Expense.scheduled_for)
        ).all()
        assert len(expenses) == 2
        assert all(expense.status == ExpenseStatus.POSTED for expense in expenses)

    assert process_due_schedules_once(test_db, now=now) == 0
    with test_db() as db:
        assert db.scalar(
            select(RecurringOccurrence.id).where(
                RecurringOccurrence.recurring_expense_id == schedule_id,
                RecurringOccurrence.status == OccurrenceStatus.BLOCKED,
            )
        ) is not None


def test_blocked_occurrence_retry_posts_once_and_advances_from_scheduled_time(test_db):
    user_id = create_user(test_db)
    now = datetime(2026, 10, 31, 7, tzinfo=UTC)
    start = now - timedelta(days=2)
    with test_db() as db:
        add_contributions(db, user_id, 2_500)
        schedule_id = make_schedule(db, user_id, amount=2_000, start_date=start)

    assert process_due_schedules_once(test_db, now=now) == 1
    with test_db() as db:
        add_contributions(db, user_id, 2_000)
        blocked = db.scalar(
            select(RecurringOccurrence).where(
                RecurringOccurrence.recurring_expense_id == schedule_id,
                RecurringOccurrence.status == OccurrenceStatus.BLOCKED,
            )
        )
        assert blocked is not None
        blocked_id = blocked.id
        assert (
            process_next_occurrence(
                db,
                schedule_id=schedule_id,
                now=now,
                retry_blocked=True,
                actor_user_id=user_id,
            )
            == OccurrenceStatus.POSTED
        )
        assert db.get(RecurringOccurrence, blocked_id).status == OccurrenceStatus.POSTED
        schedule = db.get(RecurringExpense, schedule_id)
        assert as_utc(schedule.next_due_at) == start + timedelta(days=2)
        posted_count = db.scalar(
            select(Expense.id).where(Expense.recurring_expense_id == schedule_id)
        )
        assert posted_count is not None
        retry_audits = db.scalars(
            select(AuditLog).where(AuditLog.action == "recurring_occurrence.posted")
        ).all()
        assert any(item.actor_user_id == user_id for item in retry_audits)

        with pytest.raises(RecurringExpenseStateError):
            process_next_occurrence(
                db,
                schedule_id=schedule_id,
                now=now,
                retry_blocked=True,
                actor_user_id=user_id,
            )
        assert len(
            db.scalars(
                select(Expense).where(Expense.recurring_expense_id == schedule_id)
            ).all()
        ) == 2


def test_schedule_end_date_includes_final_planned_occurrence(test_db):
    user_id = create_user(test_db)
    now = datetime(2026, 10, 31, 7, tzinfo=UTC)
    start = now - timedelta(days=3)
    with test_db() as db:
        add_contributions(db, user_id, 10_000)
        schedule_id = make_schedule(
            db,
            user_id,
            start_date=start,
            end_date=start + timedelta(days=1),
        )

    assert process_due_schedules_once(test_db, now=now) == 2
    with test_db() as db:
        schedule = db.get(RecurringExpense, schedule_id)
        assert schedule is not None
        assert schedule.status == RecurringExpenseStatus.ENDED
        assert len(
            db.scalars(
                select(RecurringOccurrence).where(
                    RecurringOccurrence.recurring_expense_id == schedule_id
                )
            ).all()
        ) == 2


def test_admin_can_retry_blocked_occurrence_after_contribution(client, test_db):
    admin_id = create_user(test_db)
    now = datetime.now(UTC)
    start = now - timedelta(days=2)
    with test_db() as db:
        add_contributions(db, admin_id, 1_000)
        schedule_id = make_schedule(
            db,
            admin_id,
            amount=2_000,
            start_date=start,
        )
    assert process_due_schedules_once(test_db, now=now) == 0
    with test_db() as db:
        blocked = db.scalar(
            select(RecurringOccurrence).where(
                RecurringOccurrence.recurring_expense_id == schedule_id,
                RecurringOccurrence.status == OccurrenceStatus.BLOCKED,
            )
        )
        assert blocked is not None
        occurrence_id = blocked.id

    assert sign_in(client).status_code == 303
    page = client.get("/admin/recurring-expenses")
    assert "Blocked occurrences" in page.text
    assert "Insufficient funds." in page.text
    retry_url = f"/admin/recurring-expenses/occurrences/{occurrence_id}/retry"
    still_blocked = client.post(
        retry_url,
        data={"csrf_token": csrf_from(page)},
    )
    assert still_blocked.status_code == 303
    assert "still+blocked" in still_blocked.headers["location"]

    with test_db() as db:
        add_contributions(db, admin_id, 2_000)
    page = client.get("/admin/recurring-expenses")
    retried = client.post(
        retry_url,
        data={"csrf_token": csrf_from(page)},
    )
    assert retried.status_code == 303
    with test_db() as db:
        occurrence = db.get(RecurringOccurrence, occurrence_id)
        assert occurrence is not None
        assert occurrence.status == OccurrenceStatus.POSTED
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "recurring_occurrence.posted",
                AuditLog.entity_id == str(occurrence_id),
            )
        )
        assert audit is not None
        assert audit.actor_user_id == admin_id


def test_schedule_management_create_edit_pause_resume_end_and_audit(client, test_db):
    admin_id = create_user(test_db)
    assert sign_in(client).status_code == 303
    page = client.get("/admin/recurring-expenses")
    csrf_token = csrf_from(page)
    start = datetime.now().astimezone().replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M")
    created = client.post(
        "/admin/recurring-expenses",
        data={
            "csrf_token": csrf_token,
            "name": "Rent",
            "description": "Office rent",
            "category": "Facilities",
            "amount": "4500.00",
            "interval_days": "30",
            "start_date": start,
            "end_date": "",
        },
    )
    assert created.status_code == 303
    page = client.get("/admin/recurring-expenses")
    assert "Rent" in page.text
    assert "An interval change takes effect after the next currently scheduled occurrence." in page.text
    with test_db() as db:
        schedule = db.scalar(select(RecurringExpense))
        assert schedule is not None
        schedule_id = schedule.id

    edited = client.post(
        f"/admin/recurring-expenses/{schedule_id}/edit",
        data={
            "csrf_token": csrf_token,
            "name": "Updated rent",
            "description": "Updated",
            "category": "Facilities",
            "amount": "4700.00",
            "interval_days": "31",
            "end_date": "",
        },
    )
    assert edited.status_code == 303
    paused = client.post(
        f"/admin/recurring-expenses/{schedule_id}/pause",
        data={"csrf_token": csrf_token},
    )
    assert paused.status_code == 303
    assert process_due_schedules_once(
        test_db,
        now=datetime.now(UTC) + timedelta(days=365),
    ) == 0
    with test_db() as db:
        schedule = db.get(RecurringExpense, schedule_id)
        assert schedule is not None
        assert schedule.name == "Updated rent"
        assert schedule.amount_centavos == 470_000
        assert schedule.interval_days == 31
        assert schedule.status == RecurringExpenseStatus.PAUSED
        assert schedule.updated_by == admin_id
        assert db.scalar(
            select(RecurringOccurrence.id).where(
                RecurringOccurrence.recurring_expense_id == schedule_id
            )
        ) is None

    assert client.post(
        f"/admin/recurring-expenses/{schedule_id}/resume",
        data={"csrf_token": csrf_token},
    ).status_code == 303
    assert client.post(
        f"/admin/recurring-expenses/{schedule_id}/end",
        data={"csrf_token": csrf_token},
    ).status_code == 303
    assert client.post(
        f"/admin/recurring-expenses/{schedule_id}/resume",
        data={"csrf_token": csrf_token},
    ).status_code == 409
    with test_db() as db:
        actions = db.scalars(
            select(AuditLog.action).where(AuditLog.entity_id == str(schedule_id))
        ).all()
        assert actions == [
            "recurring_schedule.created",
            "recurring_schedule.updated",
            "recurring_schedule.paused",
            "recurring_schedule.active",
            "recurring_schedule.ended",
        ]


def test_non_admin_cannot_manage_recurring_expenses(client, test_db):
    create_user(test_db, role=UserRole.USER, email="member@example.com")
    assert sign_in(client, email="member@example.com").status_code == 303
    assert client.get("/admin/recurring-expenses").status_code == 403

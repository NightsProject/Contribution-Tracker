import logging
from datetime import UTC, datetime
from threading import Event
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from app.database import SessionLocal
from app.models import RecurringExpense, RecurringExpenseStatus
from app.services.recurring_expenses import process_schedule

logger = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = 30


def process_due_schedules_once(session_factory=SessionLocal, now: datetime | None = None) -> int:
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=ZoneInfo("UTC"))
    current_time = current_time.astimezone(UTC)

    with session_factory() as db:
        due_schedule_ids = db.scalars(
            select(RecurringExpense.id)
            .where(
                RecurringExpense.status == RecurringExpenseStatus.ACTIVE,
                RecurringExpense.next_due_at <= current_time,
            )
            .order_by(RecurringExpense.next_due_at, RecurringExpense.id)
        ).all()

    posted_count = 0
    for schedule_id in due_schedule_ids:
        try:
            with session_factory() as db:
                posted_count += process_schedule(
                    db,
                    schedule_id=schedule_id,
                    now=current_time,
                )
        except Exception:
            logger.exception("Failed processing recurring expense schedule %s", schedule_id)
    return posted_count


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        process_due_schedules_once,
        trigger="interval",
        seconds=POLL_INTERVAL_SECONDS,
        id="process-due-recurring-expenses",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info("Recurring expense worker started; polling every %s seconds.", POLL_INTERVAL_SECONDS)
    try:
        Event().wait()
    except KeyboardInterrupt:
        scheduler.shutdown(wait=True)
        logger.info("Recurring expense worker stopped.")


if __name__ == "__main__":
    main()

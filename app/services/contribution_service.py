from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import AuditLog, Contribution, ContributionStatus
from app.models.common import utc_now
from app.services.accounting import acquire_accounting_lock


class ContributionStateError(Exception):
    pass


def review_contribution(
    db: Session,
    *,
    contribution_id: UUID,
    administrator_id: UUID,
    approved: bool,
    rejection_reason: str | None = None,
) -> None:
    new_status = ContributionStatus.APPROVED if approved else ContributionStatus.REJECTED
    reviewed_at = datetime.now(UTC)
    update_values = {
        "status": new_status,
        "reviewed_by": administrator_id,
        "reviewed_at": reviewed_at,
        "updated_at": utc_now(),
        "rejection_reason": None if approved else rejection_reason,
        "posted_at": reviewed_at if approved else None,
    }
    if approved:
        acquire_accounting_lock(db)
    result = db.execute(
        update(Contribution)
        .where(
            Contribution.id == contribution_id,
            Contribution.status == ContributionStatus.PENDING,
        )
        .values(**update_values)
    )
    if result.rowcount != 1:
        db.rollback()
        raise ContributionStateError("Contribution is no longer pending review.")

    db.add(
        AuditLog(
            actor_user_id=administrator_id,
            action="contribution.approved" if approved else "contribution.rejected",
            entity_type="contribution",
            entity_id=str(contribution_id),
            details={
                "status": new_status.value,
                "rejection_reason": None if approved else rejection_reason,
            },
        )
    )
    db.commit()

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import AuditLog, Contribution, ContributionStatus
from app.models.common import utc_now
from app.services.accounting import InvalidFinancialRecordError, acquire_accounting_lock


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


def void_contribution(
    db: Session,
    *,
    contribution_id: UUID,
    administrator_id: UUID,
    reason: str,
) -> None:
    normalized_reason = reason.strip()
    if not normalized_reason or len(normalized_reason) > 1000:
        raise InvalidFinancialRecordError("A void reason of 1 to 1000 characters is required.")

    acquire_accounting_lock(db)
    contribution = db.scalar(
        select(Contribution)
        .where(Contribution.id == contribution_id)
        .with_for_update()
    )
    if contribution is None or contribution.status != ContributionStatus.PENDING:
        db.rollback()
        raise ContributionStateError("Only a pending contribution can be voided.")

    reviewed_at = datetime.now(UTC)
    contribution.status = ContributionStatus.VOIDED
    contribution.reviewed_by = administrator_id
    contribution.reviewed_at = reviewed_at
    contribution.void_reason = normalized_reason
    contribution.updated_at = utc_now()
    db.add(
        AuditLog(
            actor_user_id=administrator_id,
            action="contribution.voided",
            entity_type="contribution",
            entity_id=str(contribution.id),
            details={"reason": normalized_reason},
        )
    )
    db.commit()

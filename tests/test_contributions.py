from datetime import date
from io import BytesIO
import re
import uuid

from PIL import Image
from sqlalchemy import select

from app.auth import new_user_session
from app.config import Settings
from app.models import (
    AuditLog,
    Contribution,
    ContributionStatus,
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
    response = client.post(
        "/login",
        data={
            "email": email,
            "password": PASSWORD,
            "csrf_token": csrf_from(login_page),
        },
    )
    return response


def image_bytes(image_format="PNG") -> bytes:
    image = Image.new("RGB", (4, 4), color="blue")
    output = BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


def submission_data(csrf_token: str, **overrides):
    data = {
        "csrf_token": csrf_token,
        "amount": "125.50",
        "payment_reference": "TXN-123",
        "payment_date": date.today().isoformat(),
    }
    data.update(overrides)
    return data


def test_submission_is_pending_and_only_appears_in_owner_history(client, test_db) -> None:
    user_id = create_user(test_db)
    create_user(test_db, email="other@example.com")
    assert sign_in(client).status_code == 303
    page = client.get("/contributions")

    response = client.post(
        "/contributions",
        data=submission_data(csrf_from(page)),
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/contributions?submitted=1"
    with test_db() as db:
        contribution = db.scalar(select(Contribution))
        assert contribution is not None
        assert contribution.user_id == user_id
        assert contribution.amount_centavos == 12550
        assert contribution.status == ContributionStatus.PENDING
        assert contribution.posted_at is None
        assert db.scalar(select(AuditLog.action)) == "contribution.submitted"

    history = client.get("/contributions")
    assert "PENDING" in history.text
    assert "₱125.50" in history.text


def test_invalid_amount_and_csrf_do_not_create_contributions(client, test_db) -> None:
    create_user(test_db)
    assert sign_in(client).status_code == 303
    page = client.get("/contributions")
    csrf_token = csrf_from(page)

    for amount in ["0", "-1", "1.001", "1e3", "999999999.99"]:
        response = client.post(
            "/contributions",
            data=submission_data(csrf_token, amount=amount),
        )
        assert response.status_code == 400
        assert "positive PHP amount" in response.text

    csrf_rejected = client.post(
        "/contributions",
        data=submission_data("invalid"),
    )
    assert csrf_rejected.status_code == 403
    with test_db() as db:
        assert db.scalar(select(Contribution.id)) is None


def test_submission_requires_sign_in(client) -> None:
    response = client.get("/contributions")

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_proof_upload_is_validated_private_and_owner_scoped(client, test_db, monkeypatch, tmp_path) -> None:
    import app.services.file_storage as file_storage

    monkeypatch.setattr(
        file_storage,
        "get_settings",
        lambda: Settings(uploads_dir=str(tmp_path)),
    )
    owner_id = create_user(test_db)
    create_user(test_db, email="other@example.com")
    create_user(test_db, role=UserRole.ADMIN, email="admin@example.com")
    assert sign_in(client).status_code == 303
    page = client.get("/contributions")
    response = client.post(
        "/contributions",
        data=submission_data(csrf_from(page)),
        files={"proof": ("not-actually-jpeg.jpg", image_bytes("PNG"), "image/jpeg")},
    )

    assert response.status_code == 303
    with test_db() as db:
        contribution = db.scalar(select(Contribution))
        assert contribution is not None
        assert contribution.user_id == owner_id
        assert contribution.proof_file_key.endswith(".png")
        proof_key = contribution.proof_file_key
        contribution_id = contribution.id
    assert (tmp_path / proof_key).is_file()
    assert (tmp_path / proof_key).stat().st_mode & 0o777 == 0o600
    assert proof_key not in {"not-actually-jpeg.jpg"}
    own_proof = client.get(f"/contributions/{contribution_id}/proof")
    assert own_proof.status_code == 200
    assert own_proof.headers["x-content-type-options"] == "nosniff"

    client.post("/logout", data={"csrf_token": csrf_from(client.get("/contributions"))})
    assert sign_in(client, email="other@example.com").status_code == 303
    assert client.get(f"/contributions/{contribution_id}/proof").status_code == 404
    client.post("/logout", data={"csrf_token": csrf_from(client.get("/contributions"))})
    assert sign_in(client, email="admin@example.com").status_code == 303
    assert client.get(f"/contributions/{contribution_id}/proof").status_code == 200


def test_invalid_proof_image_is_rejected(client, test_db, monkeypatch, tmp_path) -> None:
    import app.services.file_storage as file_storage

    monkeypatch.setattr(
        file_storage,
        "get_settings",
        lambda: Settings(uploads_dir=str(tmp_path)),
    )
    create_user(test_db)
    assert sign_in(client).status_code == 303
    page = client.get("/contributions")
    response = client.post(
        "/contributions",
        data=submission_data(csrf_from(page)),
        files={"proof": ("proof.svg", b"<svg></svg>", "image/svg+xml")},
    )

    assert response.status_code == 400
    assert "JPEG, PNG, or WebP" in response.text
    assert list(tmp_path.iterdir()) == []
    with test_db() as db:
        assert db.scalar(select(Contribution.id)) is None


def test_oversized_proof_is_rejected_before_storage(client, test_db, monkeypatch, tmp_path) -> None:
    import app.routes.contributions as contribution_routes
    import app.services.file_storage as file_storage

    limited_settings = Settings(uploads_dir=str(tmp_path), max_upload_size_bytes=32)
    monkeypatch.setattr(contribution_routes, "get_settings", lambda: limited_settings)
    monkeypatch.setattr(file_storage, "get_settings", lambda: limited_settings)
    create_user(test_db)
    assert sign_in(client).status_code == 303
    page = client.get("/contributions")
    response = client.post(
        "/contributions",
        data=submission_data(csrf_from(page)),
        files={"proof": ("proof.png", image_bytes("PNG"), "image/png")},
    )

    assert response.status_code == 413
    assert "upload limit" in response.text
    assert list(tmp_path.iterdir()) == []
    with test_db() as db:
        assert db.scalar(select(Contribution.id)) is None


def test_admin_approval_posts_exactly_once_and_is_audited(client, test_db) -> None:
    user_id = create_user(test_db)
    admin_id = create_user(test_db, role=UserRole.ADMIN, email="admin@example.com")
    contribution = Contribution(
        user_id=user_id,
        amount_centavos=5000,
        payment_reference="TXN-APPROVE",
        payment_date=date.today(),
        status=ContributionStatus.PENDING,
    )
    with test_db() as db:
        db.add(contribution)
        db.commit()
        contribution_id = contribution.id

    assert sign_in(client, email="admin@example.com").status_code == 303
    page = client.get("/admin/contributions/pending")
    assert "TXN-APPROVE" in page.text
    csrf_token = csrf_from(page)

    approved = client.post(
        f"/admin/contributions/{contribution_id}/approve",
        data={"csrf_token": csrf_token},
    )
    assert approved.status_code == 303
    duplicate = client.post(
        f"/admin/contributions/{contribution_id}/approve",
        data={"csrf_token": csrf_token},
    )
    assert duplicate.status_code == 409

    with test_db() as db:
        stored = db.get(Contribution, contribution_id)
        assert stored is not None
        assert stored.status == ContributionStatus.APPROVED
        assert stored.reviewed_by == admin_id
        assert stored.reviewed_at is not None
        assert stored.posted_at is not None
        assert stored.rejection_reason is None
        actions = db.scalars(
            select(AuditLog.action).where(AuditLog.entity_id == str(contribution_id))
        ).all()
        assert actions == ["contribution.approved"]
        assert db.scalar(
            select(Contribution.amount_centavos).where(
                Contribution.status == ContributionStatus.APPROVED
            )
        ) == 5000


def test_admin_rejection_requires_reason_and_does_not_post(client, test_db) -> None:
    user_id = create_user(test_db)
    create_user(test_db, role=UserRole.ADMIN, email="admin@example.com")
    contribution = Contribution(
        user_id=user_id,
        amount_centavos=5000,
        payment_reference="TXN-REJECT",
        payment_date=date.today(),
        status=ContributionStatus.PENDING,
    )
    with test_db() as db:
        db.add(contribution)
        db.commit()
        contribution_id = contribution.id

    assert sign_in(client, email="admin@example.com").status_code == 303
    csrf_token = csrf_from(client.get("/admin/contributions/pending"))
    empty_reason = client.post(
        f"/admin/contributions/{contribution_id}/reject",
        data={"csrf_token": csrf_token, "reason": "  "},
    )
    assert empty_reason.status_code == 400
    rejected = client.post(
        f"/admin/contributions/{contribution_id}/reject",
        data={"csrf_token": csrf_token, "reason": "Reference does not match payment."},
    )
    assert rejected.status_code == 303

    with test_db() as db:
        stored = db.get(Contribution, contribution_id)
        assert stored is not None
        assert stored.status == ContributionStatus.REJECTED
        assert stored.rejection_reason == "Reference does not match payment."
        assert stored.posted_at is None
        audit = db.scalar(select(AuditLog).where(AuditLog.entity_id == str(contribution_id)))
        assert audit is not None
        assert audit.action == "contribution.rejected"
        assert audit.details["rejection_reason"] == "Reference does not match payment."

    client.post(
        "/logout",
        data={"csrf_token": csrf_from(client.get("/admin/contributions/pending"))},
    )
    assert sign_in(client).status_code == 303
    owner_history = client.get("/contributions")
    assert "REJECTED" in owner_history.text
    assert "Reference does not match payment." not in owner_history.text


def test_non_admin_cannot_review_contributions(client, test_db) -> None:
    create_user(test_db)
    assert sign_in(client).status_code == 303

    response = client.get("/admin/contributions/pending")

    assert response.status_code == 403


def test_private_image_path_rejects_traversal(tmp_path, monkeypatch) -> None:
    import pytest

    import app.services.file_storage as file_storage

    monkeypatch.setattr(
        file_storage,
        "get_settings",
        lambda: Settings(uploads_dir=str(tmp_path)),
    )

    with pytest.raises(ValueError):
        file_storage.private_image_path("../outside.png")


def test_unapproved_or_rejected_submissions_do_not_contribute_to_posted_total(test_db) -> None:
    owner_id = create_user(test_db)
    with test_db() as db:
        db.add_all(
            [
                Contribution(
                    user_id=owner_id,
                    amount_centavos=1000,
                    payment_reference="PENDING",
                    payment_date=date.today(),
                    status=ContributionStatus.PENDING,
                ),
                Contribution(
                    user_id=owner_id,
                    amount_centavos=2000,
                    payment_reference="REJECTED",
                    payment_date=date.today(),
                    status=ContributionStatus.REJECTED,
                ),
            ]
        )
        db.commit()
        approved_total = db.scalar(
            select(Contribution.amount_centavos).where(
                Contribution.status == ContributionStatus.APPROVED
            )
        )
        assert approved_total is None

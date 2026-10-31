import argparse
import getpass

from sqlalchemy import select

from app.database import SessionLocal
from app.models import AuditLog, User, UserRole
from app.security import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, hash_password


def create_admin() -> None:
    full_name = input("Administrator name: ").strip()
    email = input("Administrator email: ").strip().lower()
    password = getpass.getpass("Password (minimum 12 characters): ")
    confirmation = getpass.getpass("Confirm password: ")

    if not full_name or len(full_name) > 200:
        raise SystemExit("Name is required and must be 200 characters or fewer.")
    if (
        len(email) > 320
        or email.count("@") != 1
        or any(char.isspace() for char in email)
        or not email.split("@")[0]
        or "." not in email.split("@")[1]
        or email.split("@")[1].startswith(".")
        or email.split("@")[1].endswith(".")
    ):
        raise SystemExit("Enter a valid email address.")
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise SystemExit(
            f"Password must be between {MIN_PASSWORD_LENGTH} and {MAX_PASSWORD_LENGTH} characters."
        )
    if password != confirmation:
        raise SystemExit("Passwords do not match.")

    with SessionLocal() as db:
        existing_admin = db.scalar(
            select(User.id).where(User.role == UserRole.ADMIN, User.is_active.is_(True)).limit(1)
        )
        if existing_admin is not None:
            raise SystemExit("An active administrator already exists; use the admin account manager.")
        if db.scalar(select(User.id).where(User.email == email)) is not None:
            raise SystemExit("That email address is already in use.")
        user = User(
            full_name=full_name,
            email=email,
            password_hash=hash_password(password),
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(user)
        db.flush()
        db.add(
            AuditLog(
                action="user.bootstrap_admin_created",
                entity_type="user",
                entity_id=str(user.id),
                details={"email": email, "role": UserRole.ADMIN.value},
            )
        )
        db.commit()
    print(f"Administrator account created for {email}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Contribution Tracker administration commands")
    parser.add_argument("command", choices=["create-admin"])
    args = parser.parse_args()
    if args.command == "create-admin":
        create_admin()


if __name__ == "__main__":
    main()

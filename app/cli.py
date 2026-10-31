import argparse
import getpass

from app.database import SessionLocal
from app.security import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, valid_email
from app.services.accounts import EmailAlreadyInUseError
from app.services.bootstrap import (
    AdminAlreadyExistsError,
    create_initial_admin,
)


def create_admin() -> None:
    full_name = input("Administrator name: ").strip()
    email = input("Administrator email: ").strip().lower()
    password = getpass.getpass("Password (minimum 12 characters): ")
    confirmation = getpass.getpass("Confirm password: ")

    if not full_name or len(full_name) > 200:
        raise SystemExit("Name is required and must be 200 characters or fewer.")
    if not valid_email(email):
        raise SystemExit("Enter a valid email address.")
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise SystemExit(
            f"Password must be between {MIN_PASSWORD_LENGTH} and {MAX_PASSWORD_LENGTH} characters."
        )
    if password != confirmation:
        raise SystemExit("Passwords do not match.")

    with SessionLocal() as db:
        try:
            create_initial_admin(
                db,
                full_name=full_name,
                email=email,
                password=password,
            )
            db.commit()
        except AdminAlreadyExistsError as error:
            db.rollback()
            raise SystemExit(
                "An administrator account already exists; use the admin account manager."
            ) from error
        except EmailAlreadyInUseError as error:
            db.rollback()
            raise SystemExit("That email address is already in use.") from error
    print(f"Administrator account created for {email}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Contribution Tracker administration commands")
    parser.add_argument("command", choices=["create-admin"])
    args = parser.parse_args()
    if args.command == "create-admin":
        create_admin()


if __name__ == "__main__":
    main()

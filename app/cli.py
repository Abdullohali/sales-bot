"""Management commands.

python -m app.cli create-admin <username> [--role admin|accountant]
"""

import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select

from app.admin.auth import ROLES, hash_password
from app.db.models import AdminUser
from app.db.session import SessionLocal, engine


async def create_admin(username: str, role: str, password: str) -> None:
    async with SessionLocal() as session:
        user = await session.scalar(select(AdminUser).where(AdminUser.username == username))
        if user:
            user.password_hash = hash_password(password)
            user.role = role
            user.active = True
            action = "updated"
        else:
            session.add(AdminUser(username=username, password_hash=hash_password(password), role=role))
            action = "created"
        await session.commit()
    await engine.dispose()
    print(f"Admin user {username!r} ({role}) {action}.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create-admin", help="create or reset an admin panel user")
    p.add_argument("username")
    p.add_argument("--role", choices=ROLES, default="admin")
    args = parser.parse_args()

    if args.cmd == "create-admin":
        password = getpass.getpass("Password (min 8 chars): ")
        if len(password) < 8 or password != getpass.getpass("Repeat: "):
            sys.exit("Passwords do not match or too short.")
        asyncio.run(create_admin(args.username, args.role, password))


if __name__ == "__main__":
    main()

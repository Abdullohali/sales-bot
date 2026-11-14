import bcrypt
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy import select
from starlette.requests import Request

from app.db.models import AdminUser
from app.db.session import SessionLocal

ROLES = ("admin", "accountant")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def current_role(request: Request) -> str | None:
    return request.session.get("role")


def current_user(request: Request) -> str | None:
    return request.session.get("username")


def is_admin(request: Request) -> bool:
    return current_role(request) == "admin"


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = str(form.get("username", "")).strip()
        password = str(form.get("password", ""))
        async with SessionLocal() as session:
            user = await session.scalar(select(AdminUser).where(AdminUser.username == username))
        if not user or not user.active or not verify_password(password, user.password_hash):
            return False
        request.session.update({"username": user.username, "role": user.role})
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        # Re-check on every request so a deactivated user is kicked out immediately.
        username = current_user(request)
        if not username:
            return False
        async with SessionLocal() as session:
            user = await session.scalar(select(AdminUser).where(AdminUser.username == username))
        if not user or not user.active:
            request.session.clear()
            return False
        request.session["role"] = user.role
        return True

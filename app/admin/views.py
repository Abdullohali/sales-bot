from fastapi import HTTPException
from markupsafe import Markup
from sqladmin import ModelView, action
from sqladmin.filters import BooleanFilter, OperationColumnFilter
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from starlette.requests import Request
from starlette.responses import RedirectResponse
from wtforms import PasswordField, SelectField
from wtforms.validators import Optional

from app.admin.auth import ROLES, current_user, hash_password, is_admin
from app.admin.i18n import lazy, pt
from app.db.models import AdminUser, Client, Courier, Product, Sale, SaleItem, Staff
from app.services.catalog import STAFF_ROLES, delete_blocker, normalize_phone, revoke_staff_access


class ActiveFilter(BooleanFilter):
    """sqladmin's BooleanFilter with translated All / Yes / No."""

    async def lookups(self, request, model, run_query):
        return [("all", pt("p.all")), ("true", pt("p.yes")), ("false", pt("p.no"))]


class DateFilter(OperationColumnFilter):
    """sqladmin's OperationColumnFilter with translated operation names."""

    input_type = "date"  # our operation_filter.html shows a date picker

    def get_operation_options(self, column_obj):
        return [(op, pt(f"p.op.{op}")) for op, _ in super().get_operation_options(column_obj)]


class LocalizedView:
    """sqladmin builds the search placeholder with ", ".join(labels): lazy labels must become str first."""

    def search_placeholder(self) -> str:
        return ", ".join(str(self._column_labels.get(f, f)) for f in self._search_fields)


class FileImport:
    """Adds the "Import from file" button and modal to the list page (admins only)."""

    list_template = "list_import.html"
    import_kind: str = ""


class SafeDelete:
    """Hard delete for admins only, and only when nothing references the row
    (`catalog.delete_blocker`). Rows used in invoices must be deactivated instead;
    the reason is shown on the list page. The database foreign keys are the last line of defence."""

    can_delete = True

    def _can_delete_any(self, request: Request) -> bool:
        return is_admin(request) and super()._can_delete_any(request)

    async def check_can_delete(self, request: Request, model) -> bool:
        return is_admin(request) and await super().check_can_delete(request, model)

    async def on_model_delete(self, model, request: Request) -> None:
        if not is_admin(request):
            raise HTTPException(status_code=403, detail=pt("p.err.admin_only"))
        async with self.session_maker() as session:
            blocker = await delete_blocker(session, model, by_username=current_user(request))
        if blocker is not None:
            key, params = blocker
            raise ValueError(pt(key, **params))
        await super().on_model_delete(model, request)

    async def delete_model(self, request: Request, pk) -> None:
        """Bulk delete: sqladmin stops at the first error, leaving the rest of the selection untouched.
        Here blocked rows are skipped, the others are deleted, and all reasons are reported together
        after the last selected row (the list page shows them as one error)."""
        errors: list[str] = getattr(request.state, "delete_errors", [])
        request.state.delete_errors = errors
        try:
            await super().delete_model(request, pk)
        except ValueError as e:
            errors.append(str(e))
        pks = [p for p in request.query_params.get("pks", "").split(",") if p]
        if errors and (not pks or str(pk) == pks[-1]):
            raise ValueError(" ".join(dict.fromkeys(errors)))


class WriteGuard(SafeDelete):
    """Accountants can browse everything, only admins can change data."""

    can_import = False

    def _guard(self, request: Request) -> None:
        if not is_admin(request):
            raise HTTPException(status_code=403, detail=pt("p.err.admin_only"))

    async def insert_model(self, request: Request, data: dict):
        self._guard(request)
        return await super().insert_model(request, data)

    async def update_model(self, request: Request, pk: str, data: dict):
        self._guard(request)
        return await super().update_model(request, pk, data)


class ClientAdmin(FileImport, LocalizedView, WriteGuard, ModelView, model=Client):
    import_kind = "clients"
    name = lazy("p.client")
    name_plural = lazy("p.clients")
    icon = "fa-solid fa-store"
    column_list = [Client.id, Client.name, Client.active]
    column_searchable_list = [Client.name]
    column_sortable_list = [Client.name, Client.active]
    column_filters = [ActiveFilter(Client.active, title=lazy("p.f.active"))]
    column_default_sort = [(Client.name, False)]
    column_labels = {Client.name: lazy("p.f.name"), Client.active: lazy("p.f.active")}
    form_columns = [Client.name, Client.active]


class ProductAdmin(FileImport, LocalizedView, WriteGuard, ModelView, model=Product):
    import_kind = "products"
    name = lazy("p.product")
    name_plural = lazy("p.products")
    icon = "fa-solid fa-apple-whole"
    column_list = [Product.id, Product.name, Product.unit, Product.ikpu, Product.unit_code, Product.active]
    column_searchable_list = [Product.name, Product.ikpu]
    column_sortable_list = [Product.name, Product.active]
    column_filters = [ActiveFilter(Product.active, title=lazy("p.f.active"))]
    column_default_sort = [(Product.name, False)]
    column_labels = {
        Product.name: lazy("p.f.name"),
        Product.unit: lazy("p.f.unit"),
        Product.ikpu: lazy("p.f.ikpu"),
        Product.unit_code: lazy("p.f.unit_code"),
        Product.active: lazy("p.f.active"),
    }
    form_columns = [Product.name, Product.unit, Product.ikpu, Product.unit_code, Product.active]


class CourierAdmin(FileImport, LocalizedView, WriteGuard, ModelView, model=Courier):
    import_kind = "couriers"
    name = lazy("p.courier")
    name_plural = lazy("p.couriers")
    icon = "fa-solid fa-truck"
    column_list = [Courier.tg_id, Courier.name, Courier.active]
    column_searchable_list = [Courier.name]
    column_filters = [ActiveFilter(Courier.active, title=lazy("p.f.active"))]
    column_labels = {
        Courier.tg_id: lazy("p.f.tg_id"),
        Courier.name: lazy("p.f.person_name"),
        Courier.active: lazy("p.f.active"),
    }
    form_columns = [Courier.tg_id, Courier.name, Courier.active]
    form_include_pk = True


class StaffAdmin(LocalizedView, WriteGuard, ModelView, model=Staff):
    """People who may use the bot. They sign in by sharing their phone number in the bot;
    the Telegram ID is filled automatically on the first login."""

    name = lazy("p.staff")
    name_plural = lazy("p.staff_plural")
    icon = "fa-solid fa-users"
    column_list = [Staff.id, Staff.name, Staff.phone, Staff.role, Staff.tg_id, Staff.active]
    column_searchable_list = [Staff.name, Staff.phone]
    column_sortable_list = [Staff.name, Staff.role, Staff.active]
    column_filters = [ActiveFilter(Staff.active, title=lazy("p.f.active"))]
    column_default_sort = [(Staff.name, False)]
    column_labels = {
        Staff.name: lazy("p.f.person_name"),
        Staff.phone: lazy("p.f.phone"),
        Staff.role: lazy("p.f.role"),
        Staff.tg_id: lazy("p.f.tg_id"),
        Staff.active: lazy("p.f.active"),
    }
    column_formatters = {Staff.role: lambda m, a: pt(f"p.role.{m.role}")}
    column_formatters_detail = column_formatters
    form_columns = [Staff.name, Staff.phone, Staff.role, Staff.active]
    form_overrides = {"role": SelectField}
    form_args = {"role": {"choices": [("courier", lazy("p.role.courier")), ("admin", lazy("p.role.admin"))]}}

    async def on_model_change(self, data: dict, model: Staff, is_created: bool, request: Request) -> None:
        if data.get("role") not in STAFF_ROLES:
            raise ValueError(pt("p.err.unknown_role"))
        phone = normalize_phone(data.get("phone"))
        if phone is None:
            raise ValueError(pt("p.err.bad_phone"))
        data["phone"] = phone
        async with self.session_maker() as session:
            taken = await session.scalar(select(Staff.id).where(Staff.phone == phone, Staff.id != model.id))
        if taken is not None:
            raise ValueError(pt("p.err.phone_taken"))
        if not is_created and model.phone != phone:
            model.tg_id = None  # new number = possibly a new person: they must log in again

    async def on_model_delete(self, model: Staff, request: Request) -> None:
        await super().on_model_delete(model, request)
        async with self.session_maker() as session:
            await revoke_staff_access(session, model)

    async def after_model_change(self, data: dict, model: Staff, is_created: bool, request: Request) -> None:
        """Keep the linked `couriers` row (used by sales and reports) in sync with the staff record."""
        if model.tg_id is None:
            return
        async with self.session_maker() as session:
            courier = await session.get(Courier, model.tg_id)
            if courier is not None:
                courier.name = model.name
                courier.active = model.active and model.role == "courier"
                await session.commit()


def _local_time(value) -> str:
    """Timestamps are stored in UTC with microseconds: show local time to the minute."""
    if value is None:
        return ""
    from app.services.clock import local_tz

    return value.astimezone(local_tz()).strftime("%Y-%m-%d %H:%M") if value.tzinfo else value.strftime("%Y-%m-%d %H:%M")


class SaleAdmin(LocalizedView, ModelView, model=Sale):
    """Invoices are read-only in the panel; the only change allowed is a soft delete (with audit).
    Never hard-deleted: invoice numbers are a continuous sequence the accountants rely on."""

    name = lazy("p.invoice")
    name_plural = lazy("p.invoices")
    icon = "fa-solid fa-file-invoice"
    can_create = False
    can_edit = False
    can_delete = False
    can_import = False
    column_list = [Sale.id, Sale.sale_date, Sale.client, Sale.courier, "total_display", Sale.is_deleted]
    column_details_list = [
        Sale.id, Sale.sale_date, Sale.created_at, Sale.client, Sale.courier, "lines_display", "total_display",
        Sale.is_deleted, Sale.deleted_by, Sale.deleted_at,
    ]  # fmt: skip
    column_sortable_list = [Sale.id, Sale.sale_date]
    column_default_sort = [(Sale.id, True)]
    column_formatters_detail = {
        Sale.created_at: lambda m, a: _local_time(m.created_at),
        Sale.deleted_at: lambda m, a: _local_time(m.deleted_at),
        # one invoice line per row instead of a single run-on string (Markup.join escapes each line)
        "lines_display": lambda m, a: Markup("<br>").join(m.lines_list),
    }
    column_filters = [
        ActiveFilter(Sale.is_deleted, title=lazy("p.f.deleted")),
        DateFilter(Sale.sale_date, title=lazy("p.f.date")),
    ]
    column_labels = {
        Sale.id: lazy("p.f.no"),
        Sale.sale_date: lazy("p.f.date"),
        Sale.created_at: lazy("p.f.created"),
        Sale.client: lazy("p.f.client"),
        Sale.courier: lazy("p.f.courier"),
        "total_display": lazy("p.f.total"),
        "lines_display": lazy("p.f.lines"),
        Sale.is_deleted: lazy("p.f.deleted"),
        Sale.deleted_by: lazy("p.f.deleted_by"),
        Sale.deleted_at: lazy("p.f.deleted_at"),
    }

    def list_query(self, request: Request):
        return select(Sale).options(
            selectinload(Sale.items).selectinload(SaleItem.product),
            selectinload(Sale.client),
            selectinload(Sale.courier),
        )

    def details_query(self, request: Request):
        return self.form_details_query(request).options(selectinload(Sale.items).selectinload(SaleItem.product))

    @action(
        name="soft_delete",
        label=lazy("p.action.soft_delete"),
        confirmation_message=lazy("p.action.soft_delete_confirm"),
        add_in_detail=True,
        add_in_list=True,
    )
    async def soft_delete(self, request: Request):
        if not is_admin(request):
            raise HTTPException(status_code=403, detail=pt("p.err.admin_only"))
        from app.services.sales import soft_delete_sale

        pks = [int(p) for p in request.query_params.get("pks", "").split(",") if p.strip().isdigit()]
        async with self.session_maker() as session:
            for pk in pks:
                await soft_delete_sale(session, pk, by=f"web:{current_user(request)}")
        return RedirectResponse(request.url_for("admin:list", identity=self.identity), status_code=302)


class AdminUserAdmin(SafeDelete, LocalizedView, ModelView, model=AdminUser):
    """You cannot delete yourself or the last active administrator."""

    name = lazy("p.panel_user")
    name_plural = lazy("p.panel_users")
    icon = "fa-solid fa-user-shield"
    can_import = False
    column_list = [AdminUser.id, AdminUser.username, AdminUser.role, AdminUser.active]
    column_details_exclude_list = [AdminUser.password_hash]
    column_labels = {
        AdminUser.username: lazy("p.f.username"),
        AdminUser.role: lazy("p.f.role"),
        AdminUser.active: lazy("p.f.active"),
    }
    form_columns = [AdminUser.username, AdminUser.role, AdminUser.active]
    form_overrides = {"role": SelectField}
    form_args = {"role": {"choices": [("admin", lazy("p.role.admin")), ("accountant", lazy("p.role.accountant"))]}}

    def is_accessible(self, request: Request) -> bool:
        return is_admin(request)

    def is_visible(self, request: Request) -> bool:
        return is_admin(request)

    async def scaffold_form(self, rules=None):
        form_class = await super().scaffold_form(rules)
        form_class.new_password = PasswordField(lazy("p.f.new_password"), validators=[Optional()])
        return form_class

    async def on_model_change(self, data: dict, model: AdminUser, is_created: bool, request: Request) -> None:
        password = data.pop("new_password", None)
        if data.get("role") not in ROLES:
            raise ValueError(pt("p.err.unknown_role"))
        if password:
            if len(password) < 8:
                raise ValueError(pt("p.err.pw_short"))
            model.password_hash = hash_password(password)
        elif is_created:
            raise ValueError(pt("p.err.pw_required"))


ALL_VIEWS = [SaleAdmin, ClientAdmin, ProductAdmin, StaffAdmin, CourierAdmin, AdminUserAdmin]

from fastapi import HTTPException
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
from app.db.models import AdminUser, Client, Courier, Product, Sale, SaleItem


class ActiveFilter(BooleanFilter):
    """sqladmin's BooleanFilter with translated All / Yes / No."""

    async def lookups(self, request, model, run_query):
        return [("all", pt("p.all")), ("true", pt("p.yes")), ("false", pt("p.no"))]


class DateFilter(OperationColumnFilter):
    """sqladmin's OperationColumnFilter with translated operation names."""

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


class WriteGuard:
    """Accountants can browse everything, only admins can change data.
    Hard deletes are disabled everywhere: directories use active=False (soft delete)."""

    can_delete = False
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


class SaleAdmin(LocalizedView, ModelView, model=Sale):
    """Invoices are read-only in the panel; the only change allowed is a soft delete (with audit)."""

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


class AdminUserAdmin(LocalizedView, ModelView, model=AdminUser):
    name = lazy("p.panel_user")
    name_plural = lazy("p.panel_users")
    icon = "fa-solid fa-user-shield"
    can_delete = False
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


ALL_VIEWS = [SaleAdmin, ClientAdmin, ProductAdmin, CourierAdmin, AdminUserAdmin]

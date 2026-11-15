from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Numeric, String, false, func, true
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    active: Mapped[bool] = mapped_column(default=True, server_default=true())  # soft delete

    def __str__(self) -> str:
        return self.name


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    unit: Mapped[str] = mapped_column(String(20), default="кг", server_default="кг")
    # 17 digits expected; longer column so an invalid value can still be saved (with a warning)
    ikpu: Mapped[str | None] = mapped_column(String(32))
    unit_code: Mapped[str | None] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(default=True, server_default=true())

    def __str__(self) -> str:
        return self.name


class Courier(Base):
    __tablename__ = "couriers"

    tg_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(default=True, server_default=true())

    def __str__(self) -> str:
        return self.name


class Sale(Base):
    """Invoice (накладная). `id` is the through invoice number, issued by a DB sequence."""

    __tablename__ = "sales"
    __table_args__ = (Index("ix_sales_date_deleted", "sale_date", "is_deleted"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_date: Mapped[date]  # local (Asia/Tashkent) business date
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    courier_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("couriers.tg_id"))
    is_deleted: Mapped[bool] = mapped_column(default=False, server_default=false())
    # audit: "tg:<id>" for bot, "web:<username>" for admin panel
    deleted_by: Mapped[str | None] = mapped_column(String(100))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items: Mapped[list["SaleItem"]] = relationship(
        back_populates="sale", order_by="SaleItem.id", cascade="all, delete-orphan"
    )
    client: Mapped[Client] = relationship()
    courier: Mapped[Courier] = relationship()

    def __str__(self) -> str:
        return f"№{self.id} ({self.sale_date})"

    # Read-only display helpers for the admin panel (items must be eager-loaded).
    @property
    def total_display(self) -> str:
        from app.services.formatting import fmt_money
        from app.services.sales import sale_totals

        return fmt_money(sale_totals(self).total)

    @property
    def lines_display(self) -> str:
        return "; ".join(self.lines_list)

    @property
    def lines_list(self) -> list[str]:
        from app.admin.i18n import pt
        from app.services.formatting import fmt_money, fmt_price, fmt_qty
        from app.services.sales import item_amounts

        rows = []
        for n, i in enumerate(self.items, start=1):
            a = item_amounts(i)
            extra = (
                f" ({pt('draft.entered_with_vat', price=fmt_price(i.entered_price))})"
                if i.entered_mode == "with_vat"
                else ""
            )
            rows.append(
                pt(
                    "p.line",
                    n=n,
                    name=i.product.name,
                    qty=fmt_qty(i.qty),
                    unit=i.product.unit,
                    price=fmt_price(i.price_ex_vat),
                    extra=extra,
                    ex=fmt_money(a.ex),
                    vat_word=pt("vat"),
                    vat=fmt_money(a.vat),
                    total=fmt_money(a.total),
                )
            )
        return rows


class SaleItem(Base):
    __tablename__ = "sale_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    price_ex_vat: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    entered_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    entered_mode: Mapped[str] = mapped_column(String(10))  # "with_vat" | "no_vat"
    # Snapshot of the VAT rate at the moment of sale: changing VAT_RATE later
    # must never recalculate historical invoices.
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))

    sale: Mapped[Sale] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()


class BotUser(Base):
    """Per-user bot settings. Any Telegram user who talked to the bot as admin or courier."""

    __tablename__ = "bot_users"

    tg_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    lang: Mapped[str] = mapped_column(String(5))  # uz | ru | en


class Staff(Base):
    """Bot users added by phone in the admin panel. On the first /start the person shares
    their contact; a matching active row gets linked to their Telegram ID and grants the role.
    role: "admin" | "courier"."""

    __tablename__ = "staff"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(20), unique=True)  # digits only, e.g. 998901234567
    role: Mapped[str] = mapped_column(String(20), default="courier", server_default="courier")
    tg_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)  # filled on first login
    active: Mapped[bool] = mapped_column(default=True, server_default=true())

    def __str__(self) -> str:
        return self.name


class AdminUser(Base):
    """Admin panel login. role: "admin" (full access) | "accountant" (read + reports)."""

    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), default="admin", server_default="admin")
    active: Mapped[bool] = mapped_column(default=True, server_default=true())

    def __str__(self) -> str:
        return self.username

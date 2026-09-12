# ============================================
# 🗃️ MODELS — Larizinha Store
# ============================================
# Todas as tabelas do banco (SQLAlchemy 2.0).
#
# REGRA DE OURO:
#   User.id = Integer (nunca UUID!)
#   Telegram IDs = BigInteger
#   Dinheiro = Numeric(10,2)
#   Datas = DateTime(timezone=True)
# ============================================

from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


# ============================================
# 🏷️ ENUMS
# ============================================

class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    BANNED = "banned"


class ProductStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    HIDDEN = "hidden"
    DELETED = "deleted"


class StockStatus(str, enum.Enum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    SOLD = "sold"
    DELIVERED = "delivered"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    EXPIRED = "expired"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class PaymentType(str, enum.Enum):
    RECHARGE = "recharge"
    PURCHASE = "purchase"


class WithdrawalStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PAID = "paid"
    REJECTED = "rejected"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class WithdrawalMethod(str, enum.Enum):
    PIX = "pix"
    BANK = "bank"


class GiftCardStatus(str, enum.Enum):
    AVAILABLE = "available"
    USED = "used"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class AlertType(str, enum.Enum):
    STOCK_LOW = "stock_low"
    STOCK_RESTOCKED = "stock_restocked"
    MAINTENANCE = "maintenance"
    PIX_EXPIRED = "pix_expired"
    PIX_PAID = "pix_paid"
    WITHDRAWAL = "withdrawal"


class BroadcastStatus(str, enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TicketStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING_USER = "waiting_user"
    CLOSED = "closed"


class VerificationCodeType(str, enum.Enum):
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RECOVERY = "password_recovery"
    PRODUCT_DELIVERY = "product_delivery"
    EMAIL_CHANGE = "email_change"
    WITHDRAWAL_CONFIRM = "withdrawal_confirm"


# ============================================
# ⚙️ CONFIG
# ============================================

class Config(Base):
    __tablename__ = "configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    value_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    value_type: Mapped[str] = mapped_column(String(20), default="string", nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="geral", index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_editable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


# ============================================
# 👮 ADMINS
# ============================================

class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    permissions: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    added_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


# ============================================
# 👤 USERS
# ============================================

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    language_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    whatsapp: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    balance: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    affiliate_balance: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    withdrawal_password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    referred_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    affiliate_code: Mapped[Optional[str]] = mapped_column(String(50), unique=True, nullable=True, index=True)

    status: Mapped[UserStatus] = mapped_column(SAEnum(UserStatus, name="user_status"), default=UserStatus.ACTIVE, nullable=False)
    is_blocked_bot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    total_spent: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    total_recharged: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    purchases_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    last_menu: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    last_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    flood_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    flood_blocked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    orders: Mapped[list["Order"]] = relationship("Order", back_populates="user", lazy="selectin")
    payments: Mapped[list["Payment"]] = relationship("Payment", back_populates="user", lazy="selectin")


# ============================================
# 📂 CATEGORIES
# ============================================

class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    emoji: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    products: Mapped[list["Product"]] = relationship("Product", back_populates="category", lazy="selectin")


# ============================================
# 📦 PRODUCTS
# ============================================

class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    emoji: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    warranty_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)

    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)

    status: Mapped[ProductStatus] = mapped_column(SAEnum(ProductStatus, name="product_status"), default=ProductStatus.ACTIVE, nullable=False)
    min_quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_quantity: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allow_search: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    stock_alert_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    stock_alert_threshold: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    delivery_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    total_sold: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    category: Mapped[Optional["Category"]] = relationship("Category", back_populates="products", lazy="selectin")
    stock_items: Mapped[list["StockItem"]] = relationship("StockItem", back_populates="product", lazy="selectin")


# ============================================
# 🔐 STOCK ITEMS
# ============================================

class StockItem(Base):
    __tablename__ = "stock_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)

    email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    password: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    code: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    extra_data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[StockStatus] = mapped_column(SAEnum(StockStatus, name="stock_status"), default=StockStatus.AVAILABLE, nullable=False, index=True)
    reserved_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reserved_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    sold_to: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    order_id: Mapped[Optional[int]] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    sold_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    product: Mapped["Product"] = relationship("Product", back_populates="stock_items", lazy="selectin")


# ============================================
# 🛒 ORDERS
# ============================================

class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    user_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)

    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    status: Mapped[OrderStatus] = mapped_column(SAEnum(OrderStatus, name="order_status"), default=OrderStatus.PENDING, nullable=False, index=True)

    delivery_method: Mapped[str] = mapped_column(String(20), default="telegram", nullable=False)
    delivery_target: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="orders", lazy="selectin")


# ============================================
# 💳 PAYMENTS
# ============================================

class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payment_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    external_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    user_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    type: Mapped[PaymentType] = mapped_column(SAEnum(PaymentType, name="payment_type"), default=PaymentType.RECHARGE, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    bonus_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    total_credited: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)

    status: Mapped[PaymentStatus] = mapped_column(SAEnum(PaymentStatus, name="payment_status"), default=PaymentStatus.PENDING, nullable=False, index=True)

    qr_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    qr_code_image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    order_id: Mapped[Optional[int]] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    webhook_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="payments", lazy="selectin")


# ============================================
# 🎁 GIFT CARDS
# ============================================

class GiftCard(Base):
    __tablename__ = "gift_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    status: Mapped[GiftCardStatus] = mapped_column(SAEnum(GiftCardStatus, name="gift_card_status"), default=GiftCardStatus.AVAILABLE, nullable=False)

    redeemed_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    redeemed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    batch_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)

    created_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ============================================
# 🤝 AFFILIATE COMMISSIONS
# ============================================

class AffiliateCommission(Base):
    __tablename__ = "affiliate_commissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    affiliate_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    referred_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id", ondelete="CASCADE"), nullable=False)

    base_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    commission: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ============================================
# 💸 WITHDRAWALS
# ============================================

class Withdrawal(Base):
    __tablename__ = "withdrawals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    user_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    method: Mapped[WithdrawalMethod] = mapped_column(SAEnum(WithdrawalMethod, name="withdrawal_method"), nullable=False)

    status: Mapped[WithdrawalStatus] = mapped_column(SAEnum(WithdrawalStatus, name="withdrawal_status"), default=WithdrawalStatus.PENDING, nullable=False, index=True)

    pix_key: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    pix_key_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    bank_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    approved_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    external_transaction_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ============================================
# 🏦 BANK ACCOUNTS
# ============================================

class BankAccount(Base):
    __tablename__ = "bank_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    bank_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    bank_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    agency: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    account: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    account_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    holder_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    holder_document: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ============================================
# 🔔 STOCK ALERTS
# ============================================

class StockAlert(Base):
    __tablename__ = "stock_alerts"
    __table_args__ = (
        UniqueConstraint("user_telegram_id", "product_id", name="uq_user_product_alert"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ============================================
# 📢 BROADCASTS
# ============================================

class Broadcast(Base):
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    message_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    media_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    media_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    buttons: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    target_audience: Mapped[str] = mapped_column(String(50), default="all", nullable=False)
    status: Mapped[BroadcastStatus] = mapped_column(SAEnum(BroadcastStatus, name="broadcast_status"), default=BroadcastStatus.DRAFT, nullable=False)

    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recurrence_rule: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    total_targets: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sent_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ============================================
# 🎧 TICKETS
# ============================================

class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    assigned_admin_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    subject: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    status: Mapped[TicketStatus] = mapped_column(SAEnum(TicketStatus, name="ticket_status"), default=TicketStatus.OPEN, nullable=False, index=True)

    messages: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


# ============================================
# 📝 MESSAGE TEMPLATES
# ============================================

class MessageTemplate(Base):
    __tablename__ = "message_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    parse_mode: Mapped[str] = mapped_column(String(20), default="HTML", nullable=False)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


# ============================================
# 🔘 BUTTON TEMPLATES
# ============================================

class ButtonTemplate(Base):
    __tablename__ = "button_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    menu: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    text: Mapped[str] = mapped_column(String(100), nullable=False)
    action_type: Mapped[str] = mapped_column(String(20), default="callback", nullable=False)
    action_data: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    row: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ============================================
# 🖼️ IMAGE TEMPLATES
# ============================================

class ImageTemplate(Base):
    __tablename__ = "image_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    telegram_file_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


# ============================================
# 📧 VERIFICATION CODES
# ============================================

class VerificationCode(Base):
    __tablename__ = "verification_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(200), nullable=False, index=True)

    code: Mapped[str] = mapped_column(String(10), nullable=False)
    type: Mapped[VerificationCodeType] = mapped_column(SAEnum(VerificationCodeType, name="verification_code_type"), nullable=False, index=True)

    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    extra_data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


# ============================================
# 📧 NOTIFICATION LOG
# ============================================

class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    recipient: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    subject: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    template: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="sent", nullable=False, index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


# ============================================
# 📋 AUDIT LOG
# ============================================

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    old_value: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ip_or_session: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


# ============================================
# 🛡️ FLOOD LOG
# ============================================

class FloodLog(Base):
    __tablename__ = "flood_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False)
    block_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    blocked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    unblocked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


# ============================================
# 🚫 BLOCKED USERS
# ============================================

class BlockedUser(Base):
    __tablename__ = "blocked_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    blocked_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    blocked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


# ============================================
# 📊 DAILY STATS
# ============================================

class DailyStats(Base):
    __tablename__ = "daily_stats"
    __table_args__ = (
        UniqueConstraint("date", name="uq_daily_stats_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    new_users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sales_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sales_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    recharges_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recharges_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    payments_pending: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    payments_expired: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    withdrawals_pending: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ============================================
# 🔍 ÍNDICES EXTRAS
# ============================================
Index("ix_users_status_created", User.status, User.created_at)
Index("ix_orders_status_created", Order.status, Order.created_at)
Index("ix_payments_status_expires", Payment.status, Payment.expires_at)
Index("ix_stock_product_status", StockItem.product_id, StockItem.status)
Index("ix_verification_email_type", VerificationCode.email, VerificationCode.type)
Index("ix_verification_expires", VerificationCode.expires_at, VerificationCode.used)
Index("ix_notification_channel_status", NotificationLog.channel, NotificationLog.status)

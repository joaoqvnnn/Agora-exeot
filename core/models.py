# ============================================
# 🗃️ MODELS — Larizinha Store
# ============================================
# Todas as tabelas do banco (SQLAlchemy 2.0).
#
# A REGRA DE OURO:
#   Se o admin pode editar no painel, tem uma
#   tabela (ou linha na tabela Config) pra isso.
#
# Como criar uma tabela nova:
#   1. Cria a classe herdando de Base
#   2. Define __tablename__
#   3. Define colunas com mapped_column
#   4. Roda "alembic revision --autogenerate"
#
# Tipos usados:
#   - BigInteger: IDs grandes (Telegram ID passa de 2 bilhões)
#   - Numeric(10,2): dinheiro (evita erro de float)
#   - JSONB: dados flexíveis (Postgres)
#   - DateTime(timezone=True): datas com fuso
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
# 🏷️ ENUMS (valores fixos do sistema)
# ============================================

class UserStatus(str, enum.Enum):
    """Status do usuário no sistema."""
    ACTIVE = "active"
    BLOCKED = "blocked"
    BANNED = "banned"


class ProductStatus(str, enum.Enum):
    """Status do produto."""
    ACTIVE = "active"
    PAUSED = "paused"
    HIDDEN = "hidden"
    DELETED = "deleted"


class StockStatus(str, enum.Enum):
    """Status de cada unidade de estoque (login)."""
    AVAILABLE = "available"
    RESERVED = "reserved"
    SOLD = "sold"
    DELIVERED = "delivered"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class OrderStatus(str, enum.Enum):
    """Status do pedido."""
    PENDING = "pending"
    PAID = "paid"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    EXPIRED = "expired"


class PaymentStatus(str, enum.Enum):
    """Status do pagamento Pix."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class PaymentType(str, enum.Enum):
    """Tipo do pagamento."""
    RECHARGE = "recharge"
    PURCHASE = "purchase"


class WithdrawalStatus(str, enum.Enum):
    """Status do saque."""
    PENDING = "pending"
    PROCESSING = "processing"
    PAID = "paid"
    REJECTED = "rejected"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class WithdrawalMethod(str, enum.Enum):
    """Método de saque."""
    PIX = "pix"
    BANK = "bank"


class GiftCardStatus(str, enum.Enum):
    """Status do gift card."""
    AVAILABLE = "available"
    USED = "used"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class AlertType(str, enum.Enum):
    """Tipo de alerta."""
    STOCK_LOW = "stock_low"
    STOCK_RESTOCKED = "stock_restocked"
    MAINTENANCE = "maintenance"
    PIX_EXPIRED = "pix_expired"
    PIX_PAID = "pix_paid"
    WITHDRAWAL = "withdrawal"


class BroadcastStatus(str, enum.Enum):
    """Status do broadcast."""
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TicketStatus(str, enum.Enum):
    """Status do ticket de atendimento."""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING_USER = "waiting_user"
    CLOSED = "closed"


class VerificationCodeType(str, enum.Enum):
    """Tipo de código de verificação."""
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RECOVERY = "password_recovery"
    PRODUCT_DELIVERY = "product_delivery"
    EMAIL_CHANGE = "email_change"
    WITHDRAWAL_CONFIRM = "withdrawal_confirm"


# ============================================
# ⚙️ CONFIG — Configurações editáveis pelo admin
# ============================================

class Config(Base):
    """Configurações globais do sistema (chave/valor)."""
    __tablename__ = "configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    key: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False,
        comment="Nome da configuração (ex: bot_name)",
    )
    value: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Valor em texto (convertido conforme necessário)",
    )
    value_json: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True,
        comment="Valor em JSON (pra listas/dicts complexos)",
    )
    value_type: Mapped[str] = mapped_column(
        String(20), default="string", nullable=False,
        comment="Tipo: string, int, float, bool, json",
    )
    category: Mapped[str] = mapped_column(
        String(50), default="geral", index=True, nullable=False,
        comment="Categoria (ex: geral, pix, bonus, antiflood)",
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Explicação do que essa config faz",
    )
    is_editable: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
        comment="Se pode ser editado pelo painel",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )


# ============================================
# 👮 ADMINS — Administradores do sistema
# ============================================

class Admin(Base):
    """Administradores com acesso ao painel."""
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    telegram_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, index=True, nullable=False,
        comment="ID do Telegram do admin",
    )
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    is_owner: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="Dono do bot (não pode ser removido)",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    permissions: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False,
        comment="Permissões específicas (users, finance, products, etc)",
    )

    added_by: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, comment="Quem adicionou este admin",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )


# ============================================
# 👤 USERS — Usuários do bot
# ============================================

class User(Base):
    """Usuário do bot (cliente)."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    telegram_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, index=True, nullable=False,
    )
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    language_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    whatsapp: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
    )
    email: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True,
    )
    email_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )

    balance: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False,
    )
    points: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    affiliate_balance: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False,
    )

    withdrawal_password_hash: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
    )

    referred_by: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, index=True,
    )
    affiliate_code: Mapped[Optional[str]] = mapped_column(
        String(50), unique=True, nullable=True, index=True,
    )

    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus, name="user_status"),
        default=UserStatus.ACTIVE, nullable=False,
    )
    is_blocked_bot: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )

    total_spent: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False,
    )
    total_recharged: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False,
    )
    purchases_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    last_menu: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
    )
    last_message_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True,
    )

    flood_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    flood_blocked_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    orders: Mapped[list["Order"]] = relationship(
        "Order", back_populates="user", lazy="selectin",
    )
    payments: Mapped[list["Payment"]] = relationship(
        "Payment", back_populates="user", lazy="selectin",
    )


# ============================================
# 📂 CATEGORIES — Categorias de produtos
# ============================================

class Category(Base):
    """Categoria que agrupa produtos."""
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    emoji: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    products: Mapped[list["Product"]] = relationship(
        "Product", back_populates="category", lazy="selectin",
    )


# ============================================
# 📦 PRODUCTS — Produtos / Serviços
# ============================================

class Product(Base):
    """Produto/serviço vendido no bot."""
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    emoji: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    warranty_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)

    category_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True,
    )

    status: Mapped[ProductStatus] = mapped_column(
        SAEnum(ProductStatus, name="product_status"),
        default=ProductStatus.ACTIVE, nullable=False,
    )
    min_quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_quantity: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allow_search: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    stock_alert_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )
    stock_alert_threshold: Mapped[int] = mapped_column(
        Integer, default=3, nullable=False,
    )

    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    delivery_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )

    total_sold: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )

    category: Mapped[Optional["Category"]] = relationship(
        "Category", back_populates="products", lazy="selectin",
    )
    stock_items: Mapped[list["StockItem"]] = relationship(
        "StockItem", back_populates="product", lazy="selectin",
    )


# ============================================
# 🔐 STOCK ITEMS — Unidades de estoque (logins)
# ============================================

class StockItem(Base):
    """Unidade individual de estoque (um login específico)."""
    __tablename__ = "stock_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    password: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    code: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    extra_data: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False,
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[StockStatus] = mapped_column(
        SAEnum(StockStatus, name="stock_status"),
        default=StockStatus.AVAILABLE, nullable=False, index=True,
    )
    reserved_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    reserved_by: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True,
    )

    sold_to: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, index=True,
    )
    order_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True,
    )
    sold_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    product: Mapped["Product"] = relationship(
        "Product", back_populates="stock_items", lazy="selectin",
    )


# ============================================
# 🛒 ORDERS — Pedidos / Compras
# ============================================

class Order(Base):
    """Pedido realizado por um usuário."""
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    order_code: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_telegram_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True,
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True,
    )
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)

    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(OrderStatus, name="order_status"),
        default=OrderStatus.PENDING, nullable=False, index=True,
    )

    delivery_method: Mapped[str] = mapped_column(
        String(20), default="telegram", nullable=False,
    )
    delivery_target: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True,
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    user: Mapped["User"] = relationship(
        "User", back_populates="orders", lazy="selectin",
    )


# ============================================
# 💳 PAYMENTS — Pagamentos Pix
# ============================================

class Payment(Base):
    """Pagamento Pix (recarga ou compra direta)."""
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    payment_id: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False,
    )
    external_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_telegram_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True,
    )

    type: Mapped[PaymentType] = mapped_column(
        SAEnum(PaymentType, name="payment_type"),
        default=PaymentType.RECHARGE, nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    bonus_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False,
    )
    total_credited: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False,
    )

    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus, name="payment_status"),
        default=PaymentStatus.PENDING, nullable=False, index=True,
    )

    qr_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    qr_code_image_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True,
    )

    order_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True,
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    webhook_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    user: Mapped["User"] = relationship(
        "User", back_populates="payments", lazy="selectin",
    )


# ============================================
# 🎁 GIFT CARDS
# ============================================

class GiftCard(Base):
    """Gift card resgatável por um usuário."""
    __tablename__ = "gift_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    code: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False,
    )
    value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    status: Mapped[GiftCardStatus] = mapped_column(
        SAEnum(GiftCardStatus, name="gift_card_status"),
        default=GiftCardStatus.AVAILABLE, nullable=False,
    )

    redeemed_by: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True,
    )
    redeemed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    batch_id: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, index=True,
    )

    created_by: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


# ============================================
# 🤝 AFFILIATE COMMISSIONS
# ============================================

class AffiliateCommission(Base):
    """Comissão gerada por uma recarga de indicado."""
    __tablename__ = "affiliate_commissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    affiliate_telegram_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True,
    )
    referred_telegram_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False,
    )

    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"), nullable=False,
    )

    base_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False,
    )
    percentage: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False,
    )
    commission: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


# ============================================
# 💸 WITHDRAWALS — Saques de afiliados
# ============================================

class Withdrawal(Base):
    """Solicitação de saque do saldo de afiliado."""
    __tablename__ = "withdrawals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    user_telegram_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True,
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    method: Mapped[WithdrawalMethod] = mapped_column(
        SAEnum(WithdrawalMethod, name="withdrawal_method"),
        nullable=False,
    )

    status: Mapped[WithdrawalStatus] = mapped_column(
        SAEnum(WithdrawalStatus, name="withdrawal_status"),
        default=WithdrawalStatus.PENDING, nullable=False, index=True,
    )

    pix_key: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    pix_key_type: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
    )
    bank_data: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True,
    )

    approved_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    external_transaction_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


# ============================================
# 🏦 BANK ACCOUNTS — Contas bancárias salvas
# ============================================

class BankAccount(Base):
    """Dados bancários salvos pelo usuário pra saque."""
    __tablename__ = "bank_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    bank_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    bank_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    agency: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    account: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    account_type: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
    )
    holder_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    holder_document: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


# ============================================
# 🔔 STOCK ALERTS — Alertas de estoque
# ============================================

class StockAlert(Base):
    """Usuário quer ser avisado quando um produto for reabastecido."""
    __tablename__ = "stock_alerts"
    __table_args__ = (
        UniqueConstraint("user_telegram_id", "product_id", name="uq_user_product_alert"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_telegram_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True,
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


# ============================================
# 📢 BROADCASTS — Mensagens em massa / agendadas
# ============================================

class Broadcast(Base):
    """Broadcast (mensagem em massa ou agendada)."""
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    message_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    media_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    media_type: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
    )
    buttons: Mapped[Optional[list]] = mapped_column(
        JSONB, nullable=True,
    )

    target_audience: Mapped[str] = mapped_column(
        String(50), default="all", nullable=False,
    )

    status: Mapped[BroadcastStatus] = mapped_column(
        SAEnum(BroadcastStatus, name="broadcast_status"),
        default=BroadcastStatus.DRAFT, nullable=False,
    )

    scheduled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True,
    )
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recurrence_rule: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
    )

    total_targets: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sent_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


# ============================================
# 🎧 TICKETS — Atendimento humano
# ============================================

class Ticket(Base):
    """Ticket de atendimento (IA → humano)."""
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_telegram_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True,
    )
    assigned_admin_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True,
    )

    subject: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    status: Mapped[TicketStatus] = mapped_column(
        SAEnum(TicketStatus, name="ticket_status"),
        default=TicketStatus.OPEN, nullable=False, index=True,
    )

    messages: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )


# ============================================
# 📝 MESSAGE TEMPLATES — Mensagens editáveis
# ============================================

class MessageTemplate(Base):
    """Template de mensagem editável pelo painel."""
    __tablename__ = "message_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    key: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False,
    )
    category: Mapped[str] = mapped_column(
        String(50), index=True, nullable=False,
    )
    title: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True,
    )
    text: Mapped[str] = mapped_column(
        Text, nullable=False,
    )
    parse_mode: Mapped[str] = mapped_column(
        String(20), default="HTML", nullable=False,
    )
    image_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )


# ============================================
# 🔘 BUTTON TEMPLATES — Botões editáveis
# ============================================

class ButtonTemplate(Base):
    """Botão editável pelo painel administrativo."""
    __tablename__ = "button_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    key: Mapped[str] = mapped_column(
        String(100), index=True, nullable=False,
    )
    menu: Mapped[str] = mapped_column(
        String(50), index=True, nullable=False,
    )
    text: Mapped[str] = mapped_column(
        String(100), nullable=False,
    )
    action_type: Mapped[str] = mapped_column(
        String(20), default="callback", nullable=False,
    )
    action_data: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True,
    )

    row: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    position: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


# ============================================
# 🖼️ IMAGE TEMPLATES — Imagens editáveis
# ============================================

class ImageTemplate(Base):
    """Imagem editável pelo painel (por categoria)."""
    __tablename__ = "image_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    key: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False,
    )
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    telegram_file_id: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )


# ============================================
# 📧 VERIFICATION CODE — Códigos de verificação
# ============================================
# Códigos usados para:
#   - Verificação de e-mail
#   - Recuperação de senha de saque
#   - Entrega de produto por e-mail
#   - Confirmação de identidade
#   - Confirmação de saque
#
# PERSISTENTE no banco (sobrevive a restarts).
# ============================================

class VerificationCode(Base):
    """Código de verificação por e-mail (persistente)."""
    __tablename__ = "verification_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    telegram_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, index=True,
        comment="ID do Telegram do usuário (se aplicável)",
    )
    email: Mapped[str] = mapped_column(
        String(200), nullable=False, index=True,
        comment="E-mail que vai receber o código",
    )

    code: Mapped[str] = mapped_column(
        String(10), nullable=False,
        comment="Código de 6 dígitos",
    )
    type: Mapped[VerificationCodeType] = mapped_column(
        SAEnum(VerificationCodeType, name="verification_code_type"),
        nullable=False, index=True,
    )

    attempts: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        comment="Tentativas já feitas",
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, default=5, nullable=False,
        comment="Máximo de tentativas permitidas",
    )
    used: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="Código já foi usado?",
    )

    extra_data: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False,
        comment="Dados extras (order_id, amount, etc)",
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True,
    )
    used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
        index=True,
    )


# ============================================
# 📧 NOTIFICATION LOG — Histórico de envios
# ============================================
# Registra todo e-mail/WhatsApp/Telegram enviado
# (auditoria + retry + estatísticas).
# ============================================

class NotificationLog(Base):
    """Log de notificações enviadas (e-mail, WhatsApp, Telegram)."""
    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    channel: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
        comment="Canal: email, whatsapp, telegram",
    )
    recipient: Mapped[str] = mapped_column(
        String(200), nullable=False, index=True,
        comment="Destinatário (email, telefone, telegram_id)",
    )
    subject: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True,
    )
    template: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        comment="Nome do template usado",
    )
    status: Mapped[str] = mapped_column(
        String(20), default="sent", nullable=False, index=True,
        comment="sent, failed, bounced",
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )
    telegram_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
        index=True,
    )


# ============================================
# 📋 AUDIT LOG — Auditoria de ações do admin
# ============================================

class AuditLog(Base):
    """Registra TODA ação administrativa (quem, o quê, quando)."""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    admin_telegram_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True,
    )
    action: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True,
    )
    target_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
    )
    target_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    old_value: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    ip_or_session: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
        index=True,
    )


# ============================================
# 🛡️ FLOOD LOG — Registro de anti-flood
# ============================================

class FloodLog(Base):
    """Histórico de bloqueios por flood."""
    __tablename__ = "flood_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_telegram_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True,
    )
    message_count: Mapped[int] = mapped_column(Integer, nullable=False)
    block_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    blocked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    unblocked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )


# ============================================
# 🚫 BLOCKED USERS — Bloqueios manuais
# ============================================

class BlockedUser(Base):
    """Usuário bloqueado manualmente pelo admin."""
    __tablename__ = "blocked_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_telegram_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True,
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    blocked_by: Mapped[int] = mapped_column(BigInteger, nullable=False)

    blocked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="NULL = permanente",
    )


# ============================================
# 📊 DAILY STATS — Estatísticas diárias (cache)
# ============================================

class DailyStats(Base):
    """Estatísticas agregadas por dia (pra dashboard)."""
    __tablename__ = "daily_stats"
    __table_args__ = (
        UniqueConstraint("date", name="uq_daily_stats_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True,
    )

    new_users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    sales_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sales_total: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False,
    )

    recharges_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recharges_total: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False,
    )

    payments_pending: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    payments_expired: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    withdrawals_pending: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


# ============================================
# 🔍 ÍNDICES EXTRAS (performance)
# ============================================
Index("ix_users_status_created", User.status, User.created_at)
Index("ix_orders_status_created", Order.status, Order.created_at)
Index("ix_payments_status_expires", Payment.status, Payment.expires_at)
Index("ix_stock_product_status", StockItem.product_id, StockItem.status)
Index("ix_verification_email_type", VerificationCode.email, VerificationCode.type)
Index("ix_verification_expires", VerificationCode.expires_at, VerificationCode.used)
Index("ix_notification_channel_status", NotificationLog.channel, NotificationLog.status)

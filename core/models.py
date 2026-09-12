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
    ACTIVE = "active"           # Ativo normal
    BLOCKED = "blocked"         # Bloqueado (anti-flood, ban manual)
    BANNED = "banned"           # Banido permanente


class ProductStatus(str, enum.Enum):
    """Status do produto."""
    ACTIVE = "active"           # Visível pra venda
    PAUSED = "paused"           # Pausado (não aparece)
    HIDDEN = "hidden"           # Oculto (só por link direto)
    DELETED = "deleted"         # Marcado como excluído


class StockStatus(str, enum.Enum):
    """Status de cada unidade de estoque (login)."""
    AVAILABLE = "available"     # Disponível pra venda
    RESERVED = "reserved"       # Reservado (alguém tá comprando)
    SOLD = "sold"               # Vendido
    DELIVERED = "delivered"     # Entregue ao cliente
    EXPIRED = "expired"         # Venceu
    CANCELLED = "cancelled"     # Cancelado


class OrderStatus(str, enum.Enum):
    """Status do pedido."""
    PENDING = "pending"         # Aguardando pagamento
    PAID = "paid"               # Pago
    DELIVERED = "delivered"     # Entregue
    CANCELLED = "cancelled"     # Cancelado
    REFUNDED = "refunded"       # Estornado
    EXPIRED = "expired"         # Expirado


class PaymentStatus(str, enum.Enum):
    """Status do pagamento Pix."""
    PENDING = "pending"         # Aguardando pagamento
    APPROVED = "approved"       # Aprovado
    REJECTED = "rejected"       # Rejeitado
    EXPIRED = "expired"         # Expirado
    REFUNDED = "refunded"       # Estornado
    CANCELLED = "cancelled"     # Cancelado


class PaymentType(str, enum.Enum):
    """Tipo do pagamento."""
    RECHARGE = "recharge"       # Recarga de saldo
    PURCHASE = "purchase"       # Compra de produto


class WithdrawalStatus(str, enum.Enum):
    """Status do saque."""
    PENDING = "pending"         # Aguardando aprovação
    PROCESSING = "processing"   # Processando
    PAID = "paid"               # Pago
    REJECTED = "rejected"       # Recusado
    REFUNDED = "refunded"       # Estornado (voltou pro saldo)
    CANCELLED = "cancelled"     # Cancelado pelo usuário


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
    DRAFT = "draft"             # Rascunho
    SCHEDULED = "scheduled"     # Agendado
    SENDING = "sending"         # Enviando
    SENT = "sent"               # Enviado
    FAILED = "failed"           # Falhou
    CANCELLED = "cancelled"     # Cancelado


class TicketStatus(str, enum.Enum):
    """Status do ticket de atendimento."""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING_USER = "waiting_user"
    CLOSED = "closed"


# ============================================
# ⚙️ CONFIG — Configurações editáveis pelo admin
# ============================================
# CORAÇÃO DO PAINEL ADMINISTRATIVO.
# Cada configuração é uma linha "chave → valor".
# Ex: "bot_name" → "Larizinha Store"
#     "pix_min"  → "4.00"
# O bot lê isso e aplica em tempo real.
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

    # Permissões granulares (JSON com lista de permissões)
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

    # Dados de contato
    whatsapp: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
        comment="Número de WhatsApp (DDD + número)",
    )
    email: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True,
    )
    email_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )

    # Saldo e pontos
    balance: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False,
    )
    points: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        comment="Pontos de indicação (convertíveis em saldo)",
    )
    affiliate_balance: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False,
        comment="Saldo de comissões de afiliado",
    )

    # Senha de saque (hash)
    withdrawal_password_hash: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
    )

    # Afiliado
    referred_by: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, index=True,
        comment="Telegram ID de quem indicou",
    )
    affiliate_code: Mapped[Optional[str]] = mapped_column(
        String(50), unique=True, nullable=True, index=True,
    )

    # Status e controle
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus, name="user_status"),
        default=UserStatus.ACTIVE, nullable=False,
    )
    is_blocked_bot: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="Bloqueou o bot no Telegram?",
    )

    # Estatísticas
    total_spent: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False,
    )
    total_recharged: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False,
    )
    purchases_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Controle de estado (última tela vista — pra editar mensagem)
    last_menu: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        comment="Última tela (start, catalogo, perfil, etc)",
    )
    last_message_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True,
        comment="ID da última mensagem do bot (pra editar in-place)",
    )

    # Anti-flood
    flood_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    flood_blocked_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Timestamps
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

    # Relacionamentos
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
    """Categoria que agrupa produtos (ex: Streaming, Design)."""
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    emoji: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    position: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="Ordem de exibição",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    # Relacionamentos
    products: Mapped[list["Product"]] = relationship(
        "Product", back_populates="category", lazy="selectin",
    )


# ============================================
# 📦 PRODUCTS — Produtos / Serviços
# ============================================

class Product(Base):
    """Produto/serviço vendido no bot (ex: HBO Max)."""
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    emoji: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False,
    )
    warranty_days: Mapped[int] = mapped_column(
        Integer, default=30, nullable=False,
        comment="Dias de garantia",
    )
    duration_days: Mapped[int] = mapped_column(
        Integer, default=30, nullable=False,
        comment="Duração do produto (validade do login)",
    )

    category_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True,
    )

    # Configurações de venda
    status: Mapped[ProductStatus] = mapped_column(
        SAEnum(ProductStatus, name="product_status"),
        default=ProductStatus.ACTIVE, nullable=False,
    )
    min_quantity: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False,
        comment="Quantidade mínima por compra",
    )
    max_quantity: Mapped[int] = mapped_column(
        Integer, default=10, nullable=False,
        comment="Quantidade máxima por compra",
    )
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allow_search: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
        comment="Aparece na pesquisa?",
    )

    # Alertas
    stock_alert_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )
    stock_alert_threshold: Mapped[int] = mapped_column(
        Integer, default=3, nullable=False,
        comment="Avisa o admin quando o estoque cair abaixo disso",
    )

    # Ordenação
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Mensagem de entrega (personalizável)
    delivery_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Mensagem enviada ao entregar (com variáveis {email} {senha} etc)",
    )

    # Estatísticas
    total_sold: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )

    # Relacionamentos
    category: Mapped[Optional["Category"]] = relationship(
        "Category", back_populates="products", lazy="selectin",
    )
    stock_items: Mapped[list["StockItem"]] = relationship(
        "StockItem", back_populates="product", lazy="selectin",
    )


# ============================================
# 🔐 STOCK ITEMS — Unidades de estoque (logins)
# ============================================
# Cada login é uma linha nesta tabela.
# Ex: HBO Max tem 4 unidades = 4 linhas com status "available".
# ============================================

class StockItem(Base):
    """Unidade individual de estoque (um login específico)."""
    __tablename__ = "stock_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Dados do login
    email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    password: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    code: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True,
        comment="Código/link de ativação",
    )
    extra_data: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False,
        comment="Dados extras (perfil, PIN, etc)",
    )
    note: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Observação pro cliente",
    )

    # Controle de venda
    status: Mapped[StockStatus] = mapped_column(
        SAEnum(StockStatus, name="stock_status"),
        default=StockStatus.AVAILABLE, nullable=False, index=True,
    )
    reserved_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Até quando tá reservado (se reservado)",
    )
    reserved_by: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True,
        comment="Telegram ID de quem reservou",
    )

    # Vínculo com venda
    sold_to: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, index=True,
        comment="Telegram ID de quem comprou",
    )
    order_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True,
    )
    sold_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Data de vencimento do produto",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    # Relacionamentos
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
        comment="Código visível do pedido (ex: 81c5465d...)",
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_telegram_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True,
        comment="Cache do telegram_id do usuário",
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True,
    )
    product_name: Mapped[str] = mapped_column(
        String(200), nullable=False,
        comment="Cópia do nome no momento da compra",
    )

    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(OrderStatus, name="order_status"),
        default=OrderStatus.PENDING, nullable=False, index=True,
    )

    # Entrega
    delivery_method: Mapped[str] = mapped_column(
        String(20), default="telegram", nullable=False,
        comment="telegram, whatsapp, email",
    )
    delivery_target: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True,
        comment="Onde entregar (email, whatsapp, telegram_id)",
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Vencimento do produto
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    # Relacionamentos
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
        comment="ID único do pagamento (gerado pelo sistema/MP)",
    )
    external_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True,
        comment="ID no Mercado Pago",
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
        comment="Valor + bônus (o que cai na carteira)",
    )

    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus, name="payment_status"),
        default=PaymentStatus.PENDING, nullable=False, index=True,
    )

    # Dados do Pix
    qr_code: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Pix copia e cola",
    )
    qr_code_image_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True,
    )

    # Para compra direta (não-recarga)
    order_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True,
    )

    # Expiração e prazos
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True,
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Webhook raw (pra debug)
    webhook_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    # Relacionamentos
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
        comment="Telegram ID de quem resgatou",
    )
    redeemed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    batch_id: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, index=True,
        comment="ID do lote (pra gerar em massa)",
    )

    created_by: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, comment="Admin que criou",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


# ============================================
# 🤝 AFFILIATES — Comissões de afiliado
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
        comment="Valor que o indicado recarregou",
    )
    percentage: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False,
        comment="Percentual aplicado",
    )
    commission: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False,
        comment="Comissão gerada",
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

    # Dados do destino
    pix_key: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    pix_key_type: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
        comment="cpf, cnpj, email, phone, random",
    )
    bank_data: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True,
        comment="Dados bancários (banco, agência, conta, titular)",
    )

    # Processamento
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
        String(20), nullable=True, comment="corrente, poupanca",
    )
    holder_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    holder_document: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


# ============================================
# 🔔 ALERTS — Alertas de estoque (usuário assina)
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
        String(20), nullable=True, comment="photo, video, document, none",
    )
    buttons: Mapped[Optional[list]] = mapped_column(
        JSONB, nullable=True,
        comment="Lista de botões inline",
    )

    target_audience: Mapped[str] = mapped_column(
        String(50), default="all", nullable=False,
        comment="all, active, inactive, buyers, affiliates, product_X",
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
        String(100), nullable=True, comment="Ex: daily, weekly, cron",
    )

    # Estatísticas de envio
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

    # Histórico de mensagens (JSON)
    messages: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )


# ============================================
# 📝 MESSAGE TEMPLATES — Mensagens editáveis pelo admin
# ============================================
# Aqui ficam TODAS as mensagens que o bot envia.
# O admin edita, e o bot lê em tempo real.
# Suporta variáveis como {BALANCE}, {PRODUCT_NAME} etc.
# ============================================

class MessageTemplate(Base):
    """Template de mensagem editável pelo painel."""
    __tablename__ = "message_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    key: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False,
        comment="Chave da mensagem (ex: start, catalogo, perfil)",
    )
    category: Mapped[str] = mapped_column(
        String(50), index=True, nullable=False,
        comment="Categoria: start, compra, pix, perfil, etc",
    )
    title: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True, comment="Nome amigável pro admin",
    )
    text: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="Texto com variáveis {USER_ID}, {BALANCE} etc",
    )
    parse_mode: Mapped[str] = mapped_column(
        String(20), default="HTML", nullable=False,
        comment="HTML, Markdown, MarkdownV2",
    )
    image_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True,
        comment="Imagem anexada (opcional)",
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
# Cada linha é um botão. O admin edita texto,
# ação, URL, posição, status.
# ============================================

class ButtonTemplate(Base):
    """Botão editável pelo painel administrativo."""
    __tablename__ = "button_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    key: Mapped[str] = mapped_column(
        String(100), index=True, nullable=False,
        comment="Identificador do botão (ex: btn_comprar)",
    )
    menu: Mapped[str] = mapped_column(
        String(50), index=True, nullable=False,
        comment="Em qual menu aparece (start, catalogo, perfil, etc)",
    )
    text: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="Texto do botão (com emoji)",
    )
    action_type: Mapped[str] = mapped_column(
        String(20), default="callback", nullable=False,
        comment="callback, url, webapp",
    )
    action_data: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True,
        comment="Callback data, URL ou URL do WebApp",
    )

    # Posição
    row: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="Linha do teclado",
    )
    position: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="Coluna na linha",
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
        comment="Identificador (ex: start_image, pix_image)",
    )
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    telegram_file_id: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True,
        comment="File ID do Telegram (evita re-upload)",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
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
        comment="Ex: add_balance, remove_product, block_user",
    )
    target_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="user, product, payment, etc",
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
# Guarda totais por dia pra dashboard rápido.
# Um cron diário atualiza isso.
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

# ============================================
# FIM — próximos arquivos:
#   - Alembic (criar tabelas)
#   - Bot base (main.py)
#   - Handlers /start, /admin
# ============================================

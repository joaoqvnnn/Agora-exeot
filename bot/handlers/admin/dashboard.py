# ============================================
# 📊 ADMIN DASHBOARD — Larizinha Store
# ============================================
# Dashboard REAL com métricas do banco.
# Todos os números vêm de consultas reais.
# ============================================

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import (
    Admin,
    GiftCard,
    GiftCardStatus,
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
    StockAlert,
    StockItem,
    StockStatus,
    Ticket,
    TicketStatus,
    User,
    UserStatus,
    Withdrawal,
    WithdrawalStatus,
)


router = Router(name="admin_dashboard")


# ============================================
# 🧰 AUXILIARES
# ============================================
async def _is_admin(session: AsyncSession, telegram_id: int) -> bool:
    stmt = select(Admin).where(
        Admin.telegram_id == telegram_id,
        Admin.is_active.is_(True),
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


def _format_brl(v) -> str:
    if v is None:
        return "0,00"
    return f"{float(v):.2f}".replace(".", ",")


# ============================================
# 📊 DASHBOARD — ENTRADA
# ============================================
@router.callback_query(F.data == "adm:actions")
async def cb_actions_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    """Ações rápidas."""
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text = (
        "⚡ <b>AÇÕES RÁPIDAS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Atalhos para as ações mais usadas:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Dashboard Completo", callback_data="adm_dash:full")],
            [InlineKeyboardButton(text="🛍 Últimas Vendas", callback_data="adm_dash:last_sales")],
            [InlineKeyboardButton(text="💳 Pagamentos Pendentes", callback_data="adm_dash:pending_payments")],
            [InlineKeyboardButton(text="💸 Saques Pendentes", callback_data="adm_wd:list:pending:0")],
            [InlineKeyboardButton(text="➕ Adicionar Estoque", callback_data="adm_stock:add")],
            [InlineKeyboardButton(text="📢 Broadcast", callback_data="adm_bc:menu")],
            [InlineKeyboardButton(text="🔧 Manutenção", callback_data="adm_gen:maintenance")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:dashboard")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 📊 DASHBOARD COMPLETO
# ============================================
@router.callback_query(F.data == "adm_dash:full")
async def cb_dashboard_full(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)

    # ===== USUÁRIOS =====
    total_users = await session.scalar(select(func.count(User.id))) or 0
    active_users = await session.scalar(
        select(func.count(User.id)).where(
            User.status == UserStatus.ACTIVE,
            User.is_blocked_bot.is_(False),
        )
    ) or 0
    new_users_today = await session.scalar(
        select(func.count(User.id)).where(User.created_at >= today_start)
    ) or 0
    new_users_month = await session.scalar(
        select(func.count(User.id)).where(User.created_at >= month_start)
    ) or 0

    # ===== SALDO TOTAL =====
    total_balance = await session.scalar(
        select(func.coalesce(func.sum(User.balance), 0))
    ) or Decimal("0.00")

    # ===== RECEITA =====
    total_revenue = await session.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.status == PaymentStatus.APPROVED
        )
    ) or Decimal("0.00")

    revenue_today = await session.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.status == PaymentStatus.APPROVED,
            Payment.paid_at >= today_start,
        )
    ) or Decimal("0.00")

    revenue_month = await session.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.status == PaymentStatus.APPROVED,
            Payment.paid_at >= month_start,
        )
    ) or Decimal("0.00")

    # ===== VENDAS =====
    total_sales = await session.scalar(
        select(func.count(Order.id)).where(
            Order.status.in_([OrderStatus.PAID, OrderStatus.DELIVERED])
        )
    ) or 0

    sales_today = await session.scalar(
        select(func.count(Order.id)).where(
            Order.status.in_([OrderStatus.PAID, OrderStatus.DELIVERED]),
            Order.created_at >= today_start,
        )
    ) or 0

    products_sold = await session.scalar(
        select(func.coalesce(func.sum(Order.quantity), 0)).where(
            Order.status.in_([OrderStatus.PAID, OrderStatus.DELIVERED])
        )
    ) or 0

    # ===== ESTOQUE =====
    total_stock = await session.scalar(
        select(func.count(StockItem.id)).where(
            StockItem.status == StockStatus.AVAILABLE
        )
    ) or 0

    # ===== PAGAMENTOS =====
    pending_payments = await session.scalar(
        select(func.count(Payment.id)).where(
            Payment.status == PaymentStatus.PENDING
        )
    ) or 0

    expired_payments = await session.scalar(
        select(func.count(Payment.id)).where(
            Payment.status == PaymentStatus.EXPIRED
        )
    ) or 0

    # ===== SAQUES =====
    pending_withdrawals = await session.scalar(
        select(func.count(Withdrawal.id)).where(
            Withdrawal.status == WithdrawalStatus.PENDING
        )
    ) or 0

    # ===== COMISSÕES =====
    from core.models import AffiliateCommission
    total_commissions = await session.scalar(
        select(func.coalesce(func.sum(AffiliateCommission.commission), 0))
    ) or Decimal("0.00")

    # ===== GIFT CARDS =====
    gift_used = await session.scalar(
        select(func.count(GiftCard.id)).where(
            GiftCard.status == GiftCardStatus.USED
        )
    ) or 0

    # ===== ALERTAS =====
    active_alerts = await session.scalar(
        select(func.count(StockAlert.id)).where(StockAlert.is_active.is_(True))
    ) or 0

    # ===== TICKETS =====
    open_tickets = await session.scalar(
        select(func.count(Ticket.id)).where(
            Ticket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS])
        )
    ) or 0

    text = (
        "📊 <b>DASHBOARD COMPLETO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "👥 <b>USUÁRIOS</b>\n"
        f"├ Total: <b>{total_users}</b>\n"
        f"├ Ativos: <b>{active_users}</b>\n"
        f"├ Novos hoje: <b>{new_users_today}</b>\n"
        f"└ Novos no mês: <b>{new_users_month}</b>\n\n"
        "💰 <b>FINANCEIRO</b>\n"
        f"├ Saldo total das carteiras: <b>R$ {_format_brl(total_balance)}</b>\n"
        f"├ Receita total: <b>R$ {_format_brl(total_revenue)}</b>\n"
        f"├ Receita hoje: <b>R$ {_format_brl(revenue_today)}</b>\n"
        f"└ Receita do mês: <b>R$ {_format_brl(revenue_month)}</b>\n\n"
        "🛒 <b>VENDAS</b>\n"
        f"├ Total de vendas: <b>{total_sales}</b>\n"
        f"├ Vendas hoje: <b>{sales_today}</b>\n"
        f"└ Produtos vendidos: <b>{products_sold}</b>\n\n"
        "📦 <b>ESTOQUE</b>\n"
        f"└ Logins disponíveis: <b>{total_stock}</b>\n\n"
        "💳 <b>PAGAMENTOS</b>\n"
        f"├ Pendentes: <b>{pending_payments}</b>\n"
        f"└ Expirados: <b>{expired_payments}</b>\n\n"
        "💸 <b>SAQUES PENDENTES</b>\n"
        f"└ Aguardando: <b>{pending_withdrawals}</b>\n\n"
        "🤝 <b>AFILIADOS</b>\n"
        f"└ Comissões geradas: <b>R$ {_format_brl(total_commissions)}</b>\n\n"
        "🎁 <b>GIFT CARDS</b>\n"
        f"└ Resgatados: <b>{gift_used}</b>\n\n"
        "🔔 <b>ALERTAS ATIVOS</b>\n"
        f"└ Total: <b>{active_alerts}</b>\n\n"
        "🎫 <b>TICKETS ABERTOS</b>\n"
        f"└ Total: <b>{open_tickets}</b>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Atualizar", callback_data="adm_dash:full")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:dashboard")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 🛍 ÚLTIMAS VENDAS
# ============================================
@router.callback_query(F.data == "adm_dash:last_sales")
async def cb_dashboard_last_sales(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    stmt = (
        select(Order)
        .where(Order.status.in_([OrderStatus.PAID, OrderStatus.DELIVERED]))
        .order_by(Order.created_at.desc())
        .limit(15)
    )
    result = await session.execute(stmt)
    orders = list(result.scalars().all())

    if not orders:
        text = (
            "🛍 <b>ÚLTIMAS VENDAS</b>\n\n"
            "Nenhuma venda registrada ainda."
        )
    else:
        lines = [
            "🛍 <b>ÚLTIMAS VENDAS</b>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "",
        ]
        for o in orders:
            date = o.created_at.strftime("%d/%m %H:%M") if o.created_at else "?"
            valor = _format_brl(o.total_price)
            lines.append(
                f"• <code>{o.order_code[:10]}...</code>\n"
                f"   {o.product_name} — R$ {valor}\n"
                f"   👤 {o.user_telegram_id} — {date}"
            )
        text = "\n".join(lines)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Atualizar", callback_data="adm_dash:last_sales")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:actions")],
        ]
    )

    if len(text) > 4000:
        text = text[:4000] + "\n\n<i>... (truncado)</i>"

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 💳 PAGAMENTOS PENDENTES
# ============================================
@router.callback_query(F.data == "adm_dash:pending_payments")
async def cb_dashboard_pending_payments(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    stmt = (
        select(Payment)
        .where(Payment.status == PaymentStatus.PENDING)
        .order_by(Payment.created_at.desc())
        .limit(20)
    )
    result = await session.execute(stmt)
    payments = list(result.scalars().all())

    if not payments:
        text = (
            "💳 <b>PAGAMENTOS PENDENTES</b>\n\n"
            "Nenhum pagamento pendente."
        )
    else:
        lines = [
            "💳 <b>PAGAMENTOS PENDENTES</b>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "",
        ]
        for p in payments:
            date = p.created_at.strftime("%d/%m %H:%M") if p.created_at else "?"
            exp = p.expires_at.strftime("%H:%M") if p.expires_at else "?"
            lines.append(
                f"• <code>{p.payment_id[:10]}...</code> — "
                f"R$ {_format_brl(p.amount)}\n"
                f"   👤 {p.user_telegram_id} — expira {exp}"
            )
        text = "\n".join(lines)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Atualizar", callback_data="adm_dash:pending_payments")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:actions")],
        ]
    )

    if len(text) > 4000:
        text = text[:4000] + "\n\n<i>... (truncado)</i>"

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()

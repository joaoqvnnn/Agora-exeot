# ============================================
# 📈 ADMIN STATS — Larizinha Store
# ============================================
# Estatísticas e gráficos (em texto) do negócio.
# Todos os botões funcionam de verdade.
#
# Cobre:
#   - Visão geral (hoje/semana/mês/total)
#   - Top produtos
#   - Top clientes
#   - Conversão Pix
#   - Ticket médio
#   - Crescimento de usuários
#   - Exportação
# ============================================

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO

from aiogram import F, Router
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import (
    Admin,
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
    PaymentType,
    User,
)


router = Router(name="admin_stats")


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
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm:stats")
async def cb_stats_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text = (
        "📈 <b>ESTATÍSTICAS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Escolha o relatório que deseja visualizar:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Visão Geral (Hoje/Semana/Mês)", callback_data="adm_st:overview")],
            [InlineKeyboardButton(text="🏆 Top Produtos", callback_data="adm_st:top_products")],
            [InlineKeyboardButton(text="👥 Top Clientes", callback_data="adm_st:top_clients")],
            [InlineKeyboardButton(text="💠 Conversão de Pix", callback_data="adm_st:pix_conversion")],
            [InlineKeyboardButton(text="💰 Ticket Médio", callback_data="adm_st:avg_ticket")],
            [InlineKeyboardButton(text="📈 Crescimento de Usuários", callback_data="adm_st:user_growth")],
            [InlineKeyboardButton(text="📥 Exportar Relatório", callback_data="adm_st:export")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:dashboard")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 📊 VISÃO GERAL
# ============================================
@router.callback_query(F.data == "adm_st:overview")
async def cb_stats_overview(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = now - timedelta(days=7)
    month = now - timedelta(days=30)

    async def _revenue(cutoff: datetime | None) -> Decimal:
        stmt = select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.status == PaymentStatus.APPROVED,
        )
        if cutoff:
            stmt = stmt.where(Payment.paid_at >= cutoff)
        return await session.scalar(stmt) or Decimal("0.00")

    async def _sales(cutoff: datetime | None) -> int:
        stmt = select(func.count(Order.id)).where(
            Order.status.in_([OrderStatus.PAID, OrderStatus.DELIVERED]),
        )
        if cutoff:
            stmt = stmt.where(Order.created_at >= cutoff)
        return await session.scalar(stmt) or 0

    async def _users(cutoff: datetime | None) -> int:
        stmt = select(func.count(User.id))
        if cutoff:
            stmt = stmt.where(User.created_at >= cutoff)
        return await session.scalar(stmt) or 0

    async def _recharges(cutoff: datetime | None) -> Decimal:
        stmt = select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.status == PaymentStatus.APPROVED,
            Payment.type == PaymentType.RECHARGE,
        )
        if cutoff:
            stmt = stmt.where(Payment.paid_at >= cutoff)
        return await session.scalar(stmt) or Decimal("0.00")

    text = (
        "📊 <b>VISÃO GERAL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📅 <b>HOJE</b>\n"
        f"├ 💰 Receita: <b>R$ {_format_brl(await _revenue(today))}</b>\n"
        f"├ 🛒 Vendas: <b>{await _sales(today)}</b>\n"
        f"├ 💳 Recargas: <b>R$ {_format_brl(await _recharges(today))}</b>\n"
        f"└ 🆕 Novos usuários: <b>{await _users(today)}</b>\n\n"
        "📆 <b>ÚLTIMOS 7 DIAS</b>\n"
        f"├ 💰 Receita: <b>R$ {_format_brl(await _revenue(week))}</b>\n"
        f"├ 🛒 Vendas: <b>{await _sales(week)}</b>\n"
        f"├ 💳 Recargas: <b>R$ {_format_brl(await _recharges(week))}</b>\n"
        f"└ 🆕 Novos usuários: <b>{await _users(week)}</b>\n\n"
        "📅 <b>ÚLTIMOS 30 DIAS</b>\n"
        f"├ 💰 Receita: <b>R$ {_format_brl(await _revenue(month))}</b>\n"
        f"├ 🛒 Vendas: <b>{await _sales(month)}</b>\n"
        f"├ 💳 Recargas: <b>R$ {_format_brl(await _recharges(month))}</b>\n"
        f"└ 🆕 Novos usuários: <b>{await _users(month)}</b>\n\n"
        "🌐 <b>TOTAL GERAL</b>\n"
        f"├ 💰 Receita: <b>R$ {_format_brl(await _revenue(None))}</b>\n"
        f"├ 🛒 Vendas: <b>{await _sales(None)}</b>\n"
        f"├ 💳 Recargas: <b>R$ {_format_brl(await _recharges(None))}</b>\n"
        f"└ 👥 Usuários: <b>{await _users(None)}</b>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Atualizar", callback_data="adm_st:overview")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:stats")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 🏆 TOP PRODUTOS
# ============================================
@router.callback_query(F.data == "adm_st:top_products")
async def cb_stats_top_products(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    stmt = (
        select(
            Order.product_name,
            func.sum(Order.quantity).label("qty"),
            func.sum(Order.total_price).label("revenue"),
            func.count(Order.id).label("orders"),
        )
        .where(Order.status.in_([OrderStatus.PAID, OrderStatus.DELIVERED]))
        .group_by(Order.product_name)
        .order_by(func.sum(Order.total_price).desc())
        .limit(15)
    )
    result = await session.execute(stmt)
    rows = list(result.all())

    lines = [
        "🏆 <b>TOP PRODUTOS</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    if not rows:
        lines.append("Nenhuma venda registrada.")
    else:
        for i, r in enumerate(rows, start=1):
            medal = "🥇🥈🥉"[i - 1] if i <= 3 else f"{i}°"
            lines.append(
                f"{medal} <b>{r.product_name}</b>\n"
                f"   🛒 {r.qty} un. em {r.orders} pedidos\n"
                f"   💰 R$ {_format_brl(r.revenue)}"
            )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Atualizar", callback_data="adm_st:top_products")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:stats")],
        ]
    )

    try:
        await callback.message.edit_text("\n".join(lines), reply_markup=keyboard)
    except Exception:
        await callback.message.answer("\n".join(lines), reply_markup=keyboard)

    await callback.answer()


# ============================================
# 👥 TOP CLIENTES
# ============================================
@router.callback_query(F.data == "adm_st:top_clients")
async def cb_stats_top_clients(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    stmt = (
        select(
            User.telegram_id,
            User.first_name,
            User.username,
            User.total_spent,
            User.purchases_count,
            User.total_recharged,
        )
        .where(User.total_spent > 0)
        .order_by(User.total_spent.desc())
        .limit(15)
    )
    result = await session.execute(stmt)
    rows = list(result.all())

    lines = [
        "👥 <b>TOP CLIENTES</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    if not rows:
        lines.append("Nenhum cliente com compras.")
    else:
        for i, r in enumerate(rows, start=1):
            medal = "🥇🥈🥉"[i - 1] if i <= 3 else f"{i}°"
            name = r.first_name or r.username or f"ID: {r.telegram_id}"
            lines.append(
                f"{medal} <b>{name}</b>\n"
                f"   💸 Gasto: R$ {_format_brl(r.total_spent)}\n"
                f"   🛒 Compras: {r.purchases_count}\n"
                f"   💳 Recarregou: R$ {_format_brl(r.total_recharged)}"
            )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Atualizar", callback_data="adm_st:top_clients")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:stats")],
        ]
    )

    try:
        await callback.message.edit_text("\n".join(lines), reply_markup=keyboard)
    except Exception:
        await callback.message.answer("\n".join(lines), reply_markup=keyboard)

    await callback.answer()


# ============================================
# 💠 CONVERSÃO DE PIX
# ============================================
@router.callback_query(F.data == "adm_st:pix_conversion")
async def cb_stats_pix_conversion(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    total = await session.scalar(select(func.count(Payment.id))) or 0

    approved = await session.scalar(
        select(func.count(Payment.id)).where(
            Payment.status == PaymentStatus.APPROVED
        )
    ) or 0

    pending = await session.scalar(
        select(func.count(Payment.id)).where(
            Payment.status == PaymentStatus.PENDING
        )
    ) or 0

    expired = await session.scalar(
        select(func.count(Payment.id)).where(
            Payment.status == PaymentStatus.EXPIRED
        )
    ) or 0

    rejected = await session.scalar(
        select(func.count(Payment.id)).where(
            Payment.status == PaymentStatus.REJECTED
        )
    ) or 0

    approved_amount = await session.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.status == PaymentStatus.APPROVED
        )
    ) or Decimal("0.00")

    # Taxa de conversão
    conversion = (approved / total * 100) if total > 0 else 0

    # Barra visual
    bar_filled = int(conversion / 5)
    bar = "█" * bar_filled + "░" * (20 - bar_filled)

    text = (
        "💠 <b>CONVERSÃO DE PIX</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 Total de Pix gerados: <b>{total}</b>\n\n"
        f"✅ Aprovados: <b>{approved}</b>\n"
        f"⏳ Pendentes: <b>{pending}</b>\n"
        f"⌛ Expirados: <b>{expired}</b>\n"
        f"❌ Rejeitados: <b>{rejected}</b>\n\n"
        f"💯 Taxa de conversão: <b>{conversion:.1f}%</b>\n"
        f"<code>{bar}</code>\n\n"
        f"💰 Valor total aprovado: <b>R$ {_format_brl(approved_amount)}</b>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Atualizar", callback_data="adm_st:pix_conversion")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:stats")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 💰 TICKET MÉDIO
# ============================================
@router.callback_query(F.data == "adm_st:avg_ticket")
async def cb_stats_avg_ticket(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = now - timedelta(days=7)
    month = now - timedelta(days=30)

    async def _avg_ticket(cutoff: datetime | None) -> Decimal:
        stmt = select(func.coalesce(func.avg(Payment.amount), 0)).where(
            Payment.status == PaymentStatus.APPROVED,
        )
        if cutoff:
            stmt = stmt.where(Payment.paid_at >= cutoff)
        return await session.scalar(stmt) or Decimal("0.00")

    async def _avg_recharge(cutoff: datetime | None) -> Decimal:
        stmt = select(func.coalesce(func.avg(Payment.amount), 0)).where(
            Payment.status == PaymentStatus.APPROVED,
            Payment.type == PaymentType.RECHARGE,
        )
        if cutoff:
            stmt = stmt.where(Payment.paid_at >= cutoff)
        return await session.scalar(stmt) or Decimal("0.00")

    text = (
        "💰 <b>TICKET MÉDIO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📅 <b>HOJE</b>\n"
        f"└ 💰 Ticket médio: <b>R$ {_format_brl(await _avg_ticket(today))}</b>\n\n"
        "📆 <b>ÚLTIMOS 7 DIAS</b>\n"
        f"└ 💰 Ticket médio: <b>R$ {_format_brl(await _avg_ticket(week))}</b>\n\n"
        "📅 <b>ÚLTIMOS 30 DIAS</b>\n"
        f"└ 💰 Ticket médio: <b>R$ {_format_brl(await _avg_ticket(month))}</b>\n\n"
        "🌐 <b>TOTAL GERAL</b>\n"
        f"└ 💰 Ticket médio: <b>R$ {_format_brl(await _avg_ticket(None))}</b>\n\n"
        "💳 <b>MÉDIA DE RECARGA</b>\n"
        f"├ Hoje: <b>R$ {_format_brl(await _avg_recharge(today))}</b>\n"
        f"├ 7 dias: <b>R$ {_format_brl(await _avg_recharge(week))}</b>\n"
        f"├ 30 dias: <b>R$ {_format_brl(await _avg_recharge(month))}</b>\n"
        f"└ Total: <b>R$ {_format_brl(await _avg_recharge(None))}</b>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Atualizar", callback_data="adm_st:avg_ticket")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:stats")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 📈 CRESCIMENTO DE USUÁRIOS
# ============================================
@router.callback_query(F.data == "adm_st:user_growth")
async def cb_stats_user_growth(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    now = datetime.now(timezone.utc)

    # Últimos 14 dias
    lines = [
        "📈 <b>CRESCIMENTO DE USUÁRIOS</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "📅 <b>Novos usuários por dia (14d):</b>",
        "",
    ]

    max_count = 0
    daily_data: list[tuple[str, int]] = []

    for i in range(13, -1, -1):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        count = await session.scalar(
            select(func.count(User.id)).where(
                User.created_at >= day_start,
                User.created_at < day_end,
            )
        ) or 0

        daily_data.append((day.strftime("%d/%m"), count))
        if count > max_count:
            max_count = count

    # Desenha barras proporcionais
    for date_str, count in daily_data:
        if max_count > 0:
            bar_len = int((count / max_count) * 15)
        else:
            bar_len = 0
        bar = "█" * bar_len + "░" * (15 - bar_len)
        lines.append(f"{date_str} {bar} <b>{count}</b>")

    # Totais
    total = await session.scalar(select(func.count(User.id))) or 0

    text = "\n".join(lines) + f"\n\n👥 <b>Total de usuários:</b> {total}"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Atualizar", callback_data="adm_st:user_growth")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:stats")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 📥 EXPORTAR RELATÓRIO
# ============================================
@router.callback_query(F.data == "adm_st:export")
async def cb_stats_export(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.answer("📥 Gerando relatório...", show_alert=False)

    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = now - timedelta(days=7)
    month = now - timedelta(days=30)

    async def _revenue(cutoff):
        stmt = select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.status == PaymentStatus.APPROVED,
        )
        if cutoff:
            stmt = stmt.where(Payment.paid_at >= cutoff)
        return await session.scalar(stmt) or Decimal("0.00")

    async def _sales(cutoff):
        stmt = select(func.count(Order.id)).where(
            Order.status.in_([OrderStatus.PAID, OrderStatus.DELIVERED]),
        )
        if cutoff:
            stmt = stmt.where(Order.created_at >= cutoff)
        return await session.scalar(stmt) or 0

    total_users = await session.scalar(select(func.count(User.id))) or 0
    total_stock = await session.scalar(
        select(func.count()).select_from(Payment)
    ) or 0

    lines = [
        "LARIZINHA STORE - RELATÓRIO DE ESTATÍSTICAS",
        "=" * 60,
        f"Gerado em: {now.strftime('%d/%m/%Y %H:%M:%S')} UTC",
        "=" * 60,
        "",
        "### RECEITA",
        f"Hoje:       R$ {_format_brl(await _revenue(today))}",
        f"7 dias:     R$ {_format_brl(await _revenue(week))}",
        f"30 dias:    R$ {_format_brl(await _revenue(month))}",
        f"Total:      R$ {_format_brl(await _revenue(None))}",
        "",
        "### VENDAS",
        f"Hoje:       {await _sales(today)}",
        f"7 dias:     {await _sales(week)}",
        f"30 dias:    {await _sales(month)}",
        f"Total:      {await _sales(None)}",
        "",
        "### USUÁRIOS",
        f"Total:      {total_users}",
        "",
    ]

    # Top produtos
    stmt = (
        select(
            Order.product_name,
            func.sum(Order.total_price).label("revenue"),
            func.sum(Order.quantity).label("qty"),
        )
        .where(Order.status.in_([OrderStatus.PAID, OrderStatus.DELIVERED]))
        .group_by(Order.product_name)
        .order_by(func.sum(Order.total_price).desc())
        .limit(20)
    )
    result = await session.execute(stmt)
    products = list(result.all())

    lines.append("### TOP PRODUTOS")
    for i, p in enumerate(products, start=1):
        lines.append(
            f"{i}°. {p.product_name} - {p.qty} un. - R$ {_format_brl(p.revenue)}"
        )

    content = "\n".join(lines).encode("utf-8")

    file = BufferedInputFile(
        content,
        filename=f"estatisticas_{now.strftime('%Y%m%d_%H%M')}.txt",
    )

    await callback.message.answer_document(
        file,
        caption=(
            f"📥 <b>Relatório gerado</b>\n\n"
            f"📊 Contém: receita, vendas, usuários e top produtos"
        ),
    )

# ============================================
# 💳 ADMIN TRANSACTIONS — Larizinha Store
# ============================================
# Lista e filtra transações (Pix, compras, bônus,
# comissões, saques, gift cards).
# Todos os botões funcionam de verdade.
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
    AffiliateCommission,
    GiftCard,
    GiftCardStatus,
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
    PaymentType,
    User,
    Withdrawal,
    WithdrawalStatus,
)


router = Router(name="admin_transactions")


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
@router.callback_query(F.data == "adm:transactions")
async def cb_transactions_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Totais de cada tipo
    pix_approved = await session.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.status == PaymentStatus.APPROVED,
        )
    ) or Decimal("0.00")

    pix_today = await session.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.status == PaymentStatus.APPROVED,
            Payment.paid_at >= today_start,
        )
    ) or Decimal("0.00")

    sales_count = await session.scalar(
        select(func.count(Order.id)).where(
            Order.status.in_([OrderStatus.PAID, OrderStatus.DELIVERED]),
        )
    ) or 0

    commissions = await session.scalar(
        select(func.coalesce(func.sum(AffiliateCommission.commission), 0))
    ) or Decimal("0.00")

    withdrawals_paid = await session.scalar(
        select(func.coalesce(func.sum(Withdrawal.amount), 0)).where(
            Withdrawal.status == WithdrawalStatus.PAID,
        )
    ) or Decimal("0.00")

    gift_used = await session.scalar(
        select(func.count(GiftCard.id)).where(
            GiftCard.status == GiftCardStatus.USED,
        )
    ) or 0

    text = (
        "💳 <b>TRANSAÇÕES</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📊 <b>Resumo geral:</b>\n\n"
        f"💠 Pix aprovados: <b>R$ {_format_brl(pix_approved)}</b>\n"
        f"📅 Pix hoje: <b>R$ {_format_brl(pix_today)}</b>\n"
        f"🛒 Vendas totais: <b>{sales_count}</b>\n"
        f"🤝 Comissões: <b>R$ {_format_brl(commissions)}</b>\n"
        f"💸 Saques pagos: <b>R$ {_format_brl(withdrawals_paid)}</b>\n"
        f"🎁 Gift Cards usados: <b>{gift_used}</b>\n\n"
        "Escolha um filtro:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💠 Pix", callback_data="adm_tx:list:pix:0")],
            [InlineKeyboardButton(text="🛒 Compras", callback_data="adm_tx:list:purchases:0")],
            [InlineKeyboardButton(text="💳 Recargas", callback_data="adm_tx:list:recharges:0")],
            [InlineKeyboardButton(text="🤝 Comissões", callback_data="adm_tx:list:commissions:0")],
            [InlineKeyboardButton(text="💸 Saques", callback_data="adm_tx:list:withdrawals:0")],
            [InlineKeyboardButton(text="🎁 Gift Cards", callback_data="adm_tx:list:gifts:0")],
            [InlineKeyboardButton(text="📊 Filtrar por período", callback_data="adm_tx:period")],
            [InlineKeyboardButton(text="📥 Exportar CSV", callback_data="adm_tx:export")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:dashboard")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 📋 LISTAGEM FILTRADA
# ============================================
@router.callback_query(F.data.startswith("adm_tx:list:"))
async def cb_transactions_list(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    parts = callback.data.split(":")
    filter_type = parts[2] if len(parts) > 2 else "pix"
    page = int(parts[3]) if len(parts) > 3 else 0

    await _show_transactions(callback, session, filter_type, page)


async def _show_transactions(
    callback: CallbackQuery,
    session: AsyncSession,
    filter_type: str,
    page: int = 0,
    cutoff: datetime | None = None,
) -> None:
    PER_PAGE = 15

    if filter_type == "pix":
        stmt = select(Payment).order_by(Payment.created_at.desc())
        if cutoff:
            stmt = stmt.where(Payment.created_at >= cutoff)
        total = await session.scalar(
            select(func.count()).select_from(stmt.subquery())
        ) or 0

        stmt = stmt.offset(page * PER_PAGE).limit(PER_PAGE)
        result = await session.execute(stmt)
        items = list(result.scalars().all())

        lines = [
            "💠 <b>TRANSAÇÕES PIX</b>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"📊 Total: <b>{total}</b>",
            "",
        ]

        for p in items:
            date = p.created_at.strftime("%d/%m %H:%M") if p.created_at else "?"
            emoji = {
                PaymentStatus.APPROVED: "✅",
                PaymentStatus.PENDING: "⏳",
                PaymentStatus.EXPIRED: "⌛",
                PaymentStatus.REJECTED: "❌",
                PaymentStatus.REFUNDED: "↩️",
            }.get(p.status, "❓")
            tipo = "💰" if p.type == PaymentType.RECHARGE else "🛒"
            lines.append(
                f"{emoji}{tipo} R$ {_format_brl(p.amount)} — "
                f"<code>{p.user_telegram_id}</code> — {date}"
            )

    elif filter_type in ("purchases", "recharges"):
        if filter_type == "purchases":
            stmt = select(Order).where(
                Order.status.in_([OrderStatus.PAID, OrderStatus.DELIVERED])
            ).order_by(Order.created_at.desc())
        else:
            stmt = select(Payment).where(
                Payment.type == PaymentType.RECHARGE,
                Payment.status == PaymentStatus.APPROVED,
            ).order_by(Payment.created_at.desc())

        if cutoff:
            if filter_type == "purchases":
                stmt = stmt.where(Order.created_at >= cutoff)
            else:
                stmt = stmt.where(Payment.paid_at >= cutoff)

        total = await session.scalar(
            select(func.count()).select_from(stmt.subquery())
        ) or 0

        stmt = stmt.offset(page * PER_PAGE).limit(PER_PAGE)
        result = await session.execute(stmt)
        items = list(result.scalars().all())

        label = "🛒 COMPRAS" if filter_type == "purchases" else "💳 RECARGAS"

        lines = [
            f"{label}",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"📊 Total: <b>{total}</b>",
            "",
        ]

        for it in items:
            date = it.created_at.strftime("%d/%m %H:%M") if it.created_at else "?"
            if filter_type == "purchases":
                lines.append(
                    f"🛒 {it.product_name} — R$ {_format_brl(it.total_price)} — "
                    f"<code>{it.user_telegram_id}</code> — {date}"
                )
            else:
                lines.append(
                    f"💳 R$ {_format_brl(it.amount)} — "
                    f"<code>{it.user_telegram_id}</code> — {date}"
                )

    elif filter_type == "commissions":
        stmt = select(AffiliateCommission).order_by(
            AffiliateCommission.created_at.desc()
        )
        if cutoff:
            stmt = stmt.where(AffiliateCommission.created_at >= cutoff)

        total = await session.scalar(
            select(func.count()).select_from(stmt.subquery())
        ) or 0

        stmt = stmt.offset(page * PER_PAGE).limit(PER_PAGE)
        result = await session.execute(stmt)
        items = list(result.scalars().all())

        lines = [
            "🤝 <b>COMISSÕES DE AFILIADOS</b>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"📊 Total: <b>{total}</b>",
            "",
        ]

        for c in items:
            date = c.created_at.strftime("%d/%m %H:%M") if c.created_at else "?"
            lines.append(
                f"🤝 R$ {_format_brl(c.commission)} "
                f"({c.percentage}% de R$ {_format_brl(c.base_amount)}) — "
                f"afil: <code>{c.affiliate_telegram_id}</code> — {date}"
            )

    elif filter_type == "withdrawals":
        stmt = select(Withdrawal).order_by(Withdrawal.created_at.desc())
        if cutoff:
            stmt = stmt.where(Withdrawal.created_at >= cutoff)

        total = await session.scalar(
            select(func.count()).select_from(stmt.subquery())
        ) or 0

        stmt = stmt.offset(page * PER_PAGE).limit(PER_PAGE)
        result = await session.execute(stmt)
        items = list(result.scalars().all())

        lines = [
            "💸 <b>SAQUES</b>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"📊 Total: <b>{total}</b>",
            "",
        ]

        for w in items:
            date = w.created_at.strftime("%d/%m %H:%M") if w.created_at else "?"
            emoji = {
                WithdrawalStatus.PENDING: "⏳",
                WithdrawalStatus.PAID: "✅",
                WithdrawalStatus.REJECTED: "❌",
                WithdrawalStatus.REFUNDED: "↩️",
            }.get(w.status, "❓")
            lines.append(
                f"{emoji} R$ {_format_brl(w.amount)} — "
                f"<code>{w.user_telegram_id}</code> — {w.method.value} — {date}"
            )

    elif filter_type == "gifts":
        stmt = select(GiftCard).order_by(GiftCard.redeemed_at.desc().nullslast())
        if cutoff:
            stmt = stmt.where(GiftCard.created_at >= cutoff)

        total = await session.scalar(
            select(func.count()).select_from(stmt.subquery())
        ) or 0

        stmt = stmt.offset(page * PER_PAGE).limit(PER_PAGE)
        result = await session.execute(stmt)
        items = list(result.scalars().all())

        lines = [
            "🎁 <b>GIFT CARDS</b>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"📊 Total: <b>{total}</b>",
            "",
        ]

        for g in items:
            emoji = {
                GiftCardStatus.AVAILABLE: "🟢",
                GiftCardStatus.USED: "✅",
                GiftCardStatus.EXPIRED: "⌛",
                GiftCardStatus.CANCELLED: "🚫",
            }.get(g.status, "❓")
            used_info = f" — por <code>{g.redeemed_by}</code>" if g.redeemed_by else ""
            lines.append(
                f"{emoji} <code>{g.code}</code> — R$ {_format_brl(g.value)}{used_info}"
            )

    else:
        lines = ["❌ Filtro desconhecido."]
        items = []

    # Navegação
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE) if total else 1
    rows: list[list[InlineKeyboardButton]] = []

    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                text="⬅️",
                callback_data=f"adm_tx:list:{filter_type}:{page - 1}",
            ))
        nav.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="adm:noop",
        ))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(
                text="➡️",
                callback_data=f"adm_tx:list:{filter_type}:{page + 1}",
            ))
        rows.append(nav)

    rows.append([
        InlineKeyboardButton(text="📊 Filtros", callback_data="adm_tx:period")
    ])
    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:transactions")
    ])

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n<i>... (truncado)</i>"

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 📊 FILTRO POR PERÍODO
# ============================================
@router.callback_query(F.data == "adm_tx:period")
async def cb_transactions_period(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text = (
        "📊 <b>FILTRO POR PERÍODO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Escolha o período:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 Hoje", callback_data="adm_tx:period_apply:1")],
            [InlineKeyboardButton(text="📅 Últimos 7 dias", callback_data="adm_tx:period_apply:7")],
            [InlineKeyboardButton(text="📅 Últimos 30 dias", callback_data="adm_tx:period_apply:30")],
            [InlineKeyboardButton(text="📅 Últimos 90 dias", callback_data="adm_tx:period_apply:90")],
            [InlineKeyboardButton(text="📅 Todo o período", callback_data="adm_tx:period_apply:0")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:transactions")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


@router.callback_query(F.data.startswith("adm_tx:period_apply:"))
async def cb_transactions_period_apply(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    try:
        days = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        days = 0

    cutoff = None
    if days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Filtra Pix por padrão
    await _show_transactions(
        callback, session,
        filter_type="pix",
        page=0,
        cutoff=cutoff,
    )


# ============================================
# 📥 EXPORTAR CSV
# ============================================
@router.callback_query(F.data == "adm_tx:export")
async def cb_transactions_export(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.answer("📥 Gerando CSV...", show_alert=False)

    # Últimos 1000 pagamentos
    stmt = (
        select(Payment)
        .order_by(Payment.created_at.desc())
        .limit(1000)
    )
    result = await session.execute(stmt)
    payments = list(result.scalars().all())

    lines = [
        "id;payment_id;user_telegram_id;tipo;valor;status;criado_em;pago_em",
    ]

    for p in payments:
        created = p.created_at.strftime("%d/%m/%Y %H:%M:%S") if p.created_at else ""
        paid = p.paid_at.strftime("%d/%m/%Y %H:%M:%S") if p.paid_at else ""
        lines.append(
            f"{p.id};{p.payment_id};{p.user_telegram_id};"
            f"{p.type.value};{p.amount};{p.status.value};{created};{paid}"
        )

    content = "\n".join(lines).encode("utf-8-sig")  # BOM pra Excel abrir certo

    file = BufferedInputFile(
        content,
        filename=f"transacoes_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
    )

    await callback.message.answer_document(
        file,
        caption=(
            f"📥 <b>Exportação concluída</b>\n\n"
            f"📊 Total: <b>{len(payments)}</b> transações\n"
            f"📅 Período: últimos 1000 registros"
        ),
    )

# ============================================
# 🏆 RANKING (CLIENTE) — Larizinha Store
# ============================================
# Ranking de clientes: serviços vendidos, recargas,
# compradores e saldo. Uma única mensagem editada.
# ============================================

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import (
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
    User,
)


router = Router(name="ranking_cliente")


# ============================================
# 🏅 MEDALHAS
# ============================================
MEDALS = ["🥇", "🥈", "🥉"]


# ============================================
# 🧰 AUXILIARES
# ============================================
def _format_brl(v) -> str:
    if v is None:
        return "0,00"
    return f"{float(v):.2f}".replace(".", ",")


async def _edit_or_send(callback: CallbackQuery, text: str, keyboard) -> None:
    try:
        await callback.message.edit_text(
            text, reply_markup=keyboard, disable_web_page_preview=True
        )
    except Exception:
        try:
            await callback.message.answer(
                text, reply_markup=keyboard, disable_web_page_preview=True
            )
        except Exception as e:
            logger.warning(f"⚠️ Falha ao exibir ranking: {e}")


async def _get_config_int(session: AsyncSession, key: str, default: int) -> int:
    from core.services import config as config_service
    return await config_service.get_int(session, key, default)


def _display_name(user_or_row) -> str:
    """Retorna nome amigável do usuário."""
    # Suporta tanto User quanto Row com first_name/username/telegram_id
    first_name = getattr(user_or_row, "first_name", None)
    username = getattr(user_or_row, "username", None)
    telegram_id = getattr(user_or_row, "telegram_id", None)

    if first_name:
        return first_name
    if username:
        return f"@{username}"
    if telegram_id:
        return f"ID: {telegram_id}"
    return "Usuário"


# ============================================
# 🏆 MENU PRINCIPAL DO RANKING
# ============================================
@router.callback_query(F.data == "menu:ranking")
async def cb_ranking_menu(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    """Abre o ranking com a categoria 'serviços' por padrão."""
    await _show_ranking(callback, user, session, category="services")
    await callback.answer()


@router.callback_query(F.data == "rank:servicos")
async def cb_rank_services(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    await _show_ranking(callback, user, session, category="services")
    await callback.answer()


@router.callback_query(F.data == "rank:recargas")
async def cb_rank_recharges(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    await _show_ranking(callback, user, session, category="recharges")
    await callback.answer()


@router.callback_query(F.data == "rank:compras")
async def cb_rank_buyers(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    await _show_ranking(callback, user, session, category="buyers")
    await callback.answer()


@router.callback_query(F.data == "rank:saldo")
async def cb_rank_balances(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    await _show_ranking(callback, user, session, category="balances")
    await callback.answer()


@router.callback_query(F.data == "rank:voltar")
async def cb_rank_back(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    from bot.keyboards.main_menu import build_main_menu
    from core.config import settings

    text = (
        f"🏆 <b>TOP COMPRADORES</b>\n\n"
        f"Escolha uma categoria abaixo para ver o ranking."
    )
    keyboard = await build_main_menu(session, webapp_url=settings.webapp_url)

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()


# ============================================
# 📊 EXIBIR RANKING
# ============================================
async def _show_ranking(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    category: str,
) -> None:
    """Exibe o ranking da categoria escolhida."""
    period_days = await _get_config_int(session, "ranking_period_days", 30)
    size = await _get_config_int(session, "ranking_size", 10)

    cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)

    if category == "services":
        text = await _build_ranking_services(session, cutoff, size)
    elif category == "recharges":
        text = await _build_ranking_recharges(session, cutoff, size, user)
    elif category == "buyers":
        text = await _build_ranking_buyers(session, cutoff, size, user)
    elif category == "balances":
        text = await _build_ranking_balances(session, size, user)
    else:
        text = "❌ Ranking desconhecido."

    # Botões de categorias (com check na ativa)
    services_icon = "☑️" if category == "services" else "✅"
    recharges_icon = "☑️" if category == "recharges" else "✅"
    buyers_icon = "☑️" if category == "compras" or category == "buyers" else "✅"
    balances_icon = "☑️" if category == "balances" else "✅"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{'🎯' if category == 'services' else '📦'} Serviços",
                    callback_data="rank:servicos",
                ),
                InlineKeyboardButton(
                    text=f"{'🎯' if category == 'recharges' else '💰'} Recargas",
                    callback_data="rank:recargas",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"{'🎯' if category == 'buyers' else '🛒'} Compras",
                    callback_data="rank:compras",
                ),
                InlineKeyboardButton(
                    text=f"{'🎯' if category == 'balances' else '💎'} Saldo",
                    callback_data="rank:saldo",
                ),
            ],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="menu:voltar")],
        ]
    )

    await _edit_or_send(callback, text, keyboard)

    user.last_menu = f"ranking_{category}"
    session.add(user)


# ============================================
# 🎬 RANKING: SERVIÇOS MAIS VENDIDOS
# ============================================
async def _build_ranking_services(
    session: AsyncSession,
    cutoff: datetime,
    size: int,
) -> str:
    stmt = (
        select(
            Order.product_name,
            func.sum(Order.quantity).label("total"),
        )
        .where(
            Order.status.in_([OrderStatus.PAID, OrderStatus.DELIVERED]),
            Order.created_at >= cutoff,
        )
        .group_by(Order.product_name)
        .order_by(func.sum(Order.quantity).desc())
        .limit(size)
    )
    result = await session.execute(stmt)
    rows = list(result.all())

    lines = [
        f"🏆 <b>Ranking dos serviços mais vendidos</b>",
        f"📅 (últimos {30} dias)" if False else f"📅 (deste mês)",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    if not rows:
        lines.append("Nenhuma venda registrada neste período.")
        return "\n".join(lines)

    for i, row in enumerate(rows, start=1):
        medal = MEDALS[i - 1] if i <= 3 else f"{i}°"
        lines.append(
            f"{medal} {row.product_name} — <b>{row.total}</b> pedidos"
        )

    return "\n".join(lines)


# ============================================
# 💰 RANKING: MAIORES RECARGAS
# ============================================
async def _build_ranking_recharges(
    session: AsyncSession,
    cutoff: datetime,
    size: int,
    current_user: User,
) -> str:
    stmt = (
        select(
            User.telegram_id,
            User.first_name,
            User.username,
            func.sum(Payment.amount).label("total"),
        )
        .join(Payment, Payment.user_id == User.id)
        .where(
            Payment.status == PaymentStatus.APPROVED,
            Payment.paid_at >= cutoff,
        )
        .group_by(User.telegram_id, User.first_name, User.username)
        .order_by(func.sum(Payment.amount).desc())
        .limit(size)
    )
    result = await session.execute(stmt)
    rows = list(result.all())

    lines = [
        f"🏆 <b>Ranking dos usuários que mais recarregaram</b>",
        f"📅 (deste mês)",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    if not rows:
        lines.append("Nenhuma recarga registrada neste período.")
        return "\n".join(lines)

    user_in_ranking = False
    for i, row in enumerate(rows, start=1):
        medal = MEDALS[i - 1] if i <= 3 else f"{i}°"
        name = _display_name(row)
        lines.append(f"{medal} {name}")

        if row.telegram_id == current_user.telegram_id:
            user_in_ranking = True

    # Se o usuário não estiver no ranking, calcula quanto falta
    if not user_in_ranking:
        last_total = rows[-1].total if rows else Decimal("0.00")
        user_total = await session.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.user_id == current_user.id,
                Payment.status == PaymentStatus.APPROVED,
                Payment.paid_at >= cutoff,
            )
        ) or Decimal("0.00")

        if last_total > 0:
            missing = (last_total - user_total + Decimal("0.01")).quantize(
                Decimal("0.01")
            )
            if missing > 0:
                lines.append("")
                lines.append(
                    f"💡 Você ainda não está no ranking. "
                    f"Adicione mais <b>R$ {_format_brl(missing)}</b> para aparecer!"
                )

    return "\n".join(lines)


# ============================================
# 🛒 RANKING: MAIORES COMPRADORES
# ============================================
async def _build_ranking_buyers(
    session: AsyncSession,
    cutoff: datetime,
    size: int,
    current_user: User,
) -> str:
    stmt = (
        select(
            User.telegram_id,
            User.first_name,
            User.username,
            func.sum(Order.quantity).label("total"),
        )
        .join(Order, Order.user_id == User.id)
        .where(
            Order.status.in_([OrderStatus.PAID, OrderStatus.DELIVERED]),
            Order.created_at >= cutoff,
        )
        .group_by(User.telegram_id, User.first_name, User.username)
        .order_by(func.sum(Order.quantity).desc())
        .limit(size)
    )
    result = await session.execute(stmt)
    rows = list(result.all())

    lines = [
        f"🏆 <b>Ranking dos usuários que mais compraram</b>",
        f"📅 (deste mês)",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    if not rows:
        lines.append("Nenhuma compra registrada neste período.")
        return "\n".join(lines)

    user_in_ranking = False
    for i, row in enumerate(rows, start=1):
        medal = MEDALS[i - 1] if i <= 3 else f"{i}°"
        name = _display_name(row)
        lines.append(f"{medal} {name}")

        if row.telegram_id == current_user.telegram_id:
            user_in_ranking = True

    if not user_in_ranking:
        last_total = rows[-1].total if rows else 0
        user_total = await session.scalar(
            select(func.coalesce(func.sum(Order.quantity), 0)).where(
                Order.user_id == current_user.id,
                Order.status.in_([OrderStatus.PAID, OrderStatus.DELIVERED]),
                Order.created_at >= cutoff,
            )
        ) or 0

        if last_total > 0 and user_total < last_total:
            missing = last_total - user_total + 1
            lines.append("")
            lines.append(
                f"💡 Você ainda não está no ranking. "
                f"Compre mais <b>{missing}</b> item(ns) para aparecer!"
            )

    return "\n".join(lines)


# ============================================
# 💎 RANKING: MAIORES SALDOS
# ============================================
async def _build_ranking_balances(
    session: AsyncSession,
    size: int,
    current_user: User,
) -> str:
    stmt = (
        select(
            User.telegram_id,
            User.first_name,
            User.username,
            User.balance,
        )
        .where(User.balance > 0)
        .order_by(User.balance.desc())
        .limit(size)
    )
    result = await session.execute(stmt)
    rows = list(result.all())

    lines = [
        f"🏆 <b>Ranking dos usuários com mais saldo</b>",
        f"📅 (atual)",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    if not rows:
        lines.append("Nenhum usuário com saldo positivo.")
        return "\n".join(lines)

    user_in_ranking = False
    for i, row in enumerate(rows, start=1):
        medal = MEDALS[i - 1] if i <= 3 else f"{i}°"
        name = _display_name(row)
        lines.append(f"{medal} {name}")

        if row.telegram_id == current_user.telegram_id:
            user_in_ranking = True

    if not user_in_ranking:
        last_balance = rows[-1].balance if rows else Decimal("0.00")
        user_balance = current_user.balance or Decimal("0.00")

        if last_balance > 0:
            missing = (last_balance - user_balance + Decimal("0.01")).quantize(
                Decimal("0.01")
            )
            if missing > 0:
                lines.append("")
                lines.append(
                    f"💡 Você ainda não está no ranking. "
                    f"Adicione mais <b>R$ {_format_brl(missing)}</b> para aparecer!"
                )

    return "\n".join(lines)


# ============================================
# 🔘 NOOP
# ============================================
@router.callback_query(F.data == "rank:noop")
async def cb_rank_noop(callback: CallbackQuery) -> None:
    await callback.answer()

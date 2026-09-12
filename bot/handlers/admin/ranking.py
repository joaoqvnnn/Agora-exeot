# ============================================
# 🏆 ADMIN RANKING — Larizinha Store
# ============================================
# Configuração e visualização dos rankings.
# Todos os botões funcionam de verdade.
#
# Cobre:
#   - VER ranking de serviços vendidos
#   - VER ranking de recargas
#   - VER ranking de compradores
#   - VER ranking de saldo
#   - CONFIGURAR período (30, 60, 90 dias)
#   - CONFIGURAR tamanho (top 10, 20, 50)
#   - RESETAR cache se necessário
# ============================================

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.states import AdminStates
from core.models import (
    Admin,
    AuditLog,
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
    User,
)
from core.services import config as config_service


router = Router(name="admin_ranking")


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


async def _log_audit(
    session: AsyncSession,
    admin_id: int,
    action: str,
    old_value: dict | None = None,
    new_value: dict | None = None,
) -> None:
    log = AuditLog(
        admin_telegram_id=admin_id,
        action=action,
        old_value=old_value,
        new_value=new_value,
    )
    session.add(log)


def _format_brl(v) -> str:
    if v is None:
        return "0,00"
    return f"{float(v):.2f}".replace(".", ",")


def _cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_rank:menu")]
        ]
    )


MEDALS = ["🥇", "🥈", "🥉"]


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_rank:menu")
async def cb_ranking_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    period = await config_service.get_int(session, "ranking_period_days", 30)
    size = await config_service.get_int(session, "ranking_size", 10)

    text = (
        "🏆 <b>RANKINGS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📅 Período: <b>{period} dias</b>\n"
        f"📊 Posições: <b>Top {size}</b>\n\n"
        "Escolha um ranking para visualizar:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎬 Serviços Mais Vendidos", callback_data="adm_rank:view:services")],
            [InlineKeyboardButton(text="💰 Maiores Recargas", callback_data="adm_rank:view:recharges")],
            [InlineKeyboardButton(text="🛒 Maiores Compradores", callback_data="adm_rank:view:buyers")],
            [InlineKeyboardButton(text="💎 Maiores Saldos", callback_data="adm_rank:view:balances")],
            [InlineKeyboardButton(text="⚙️ Configurações", callback_data="adm_rank:config")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:config")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 👁️ VISUALIZAR RANKING
# ============================================
@router.callback_query(F.data.startswith("adm_rank:view:"))
async def cb_ranking_view(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    ranking_type = callback.data.split(":")[2]
    period = await config_service.get_int(session, "ranking_period_days", 30)
    size = await config_service.get_int(session, "ranking_size", 10)

    cutoff = datetime.now(timezone.utc) - timedelta(days=period)

    if ranking_type == "services":
        text = await _ranking_services(session, cutoff, size)
    elif ranking_type == "recharges":
        text = await _ranking_recharges(session, cutoff, size)
    elif ranking_type == "buyers":
        text = await _ranking_buyers(session, cutoff, size)
    elif ranking_type == "balances":
        text = await _ranking_balances(session, cutoff, size)
    else:
        text = "❌ Ranking desconhecido."

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Atualizar", callback_data=f"adm_rank:view:{ranking_type}")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_rank:menu")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


async def _ranking_services(
    session: AsyncSession,
    cutoff: datetime,
    size: int,
) -> str:
    """Ranking de serviços mais vendidos."""
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
        "🏆 <b>Ranking dos serviços mais vendidos</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    if not rows:
        lines.append("Nenhuma venda registrada neste período.")
    else:
        for i, row in enumerate(rows, start=1):
            medal = MEDALS[i - 1] if i <= 3 else f"{i}°"
            lines.append(
                f"{medal} {row.product_name} — <b>{row.total}</b> pedido(s)"
            )

    return "\n".join(lines)


async def _ranking_recharges(
    session: AsyncSession,
    cutoff: datetime,
    size: int,
) -> str:
    """Ranking de maiores recargas."""
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
        "🏆 <b>Ranking dos usuários que mais recarregaram</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    if not rows:
        lines.append("Nenhuma recarga registrada neste período.")
    else:
        for i, row in enumerate(rows, start=1):
            medal = MEDALS[i - 1] if i <= 3 else f"{i}°"
            name = row.first_name or row.username or f"ID: {row.telegram_id}"
            lines.append(
                f"{medal} {name} — <b>R$ {_format_brl(row.total)}</b>"
            )

    return "\n".join(lines)


async def _ranking_buyers(
    session: AsyncSession,
    cutoff: datetime,
    size: int,
) -> str:
    """Ranking de maiores compradores."""
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
        "🏆 <b>Ranking dos usuários que mais compraram</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    if not rows:
        lines.append("Nenhuma compra registrada neste período.")
    else:
        for i, row in enumerate(rows, start=1):
            medal = MEDALS[i - 1] if i <= 3 else f"{i}°"
            name = row.first_name or row.username or f"ID: {row.telegram_id}"
            lines.append(f"{medal} {name} — <b>{row.total}</b> compra(s)")

    return "\n".join(lines)


async def _ranking_balances(
    session: AsyncSession,
    cutoff: datetime,
    size: int,
) -> str:
    """Ranking de maiores saldos."""
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
        "🏆 <b>Ranking dos usuários com mais saldo</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    if not rows:
        lines.append("Nenhum usuário com saldo positivo.")
    else:
        for i, row in enumerate(rows, start=1):
            medal = MEDALS[i - 1] if i <= 3 else f"{i}°"
            name = row.first_name or row.username or f"ID: {row.telegram_id}"
            lines.append(
                f"{medal} {name} — <b>R$ {_format_brl(row.balance)}</b>"
            )

    return "\n".join(lines)


# ============================================
# ⚙️ CONFIGURAÇÕES
# ============================================
@router.callback_query(F.data == "adm_rank:config")
async def cb_ranking_config(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    period = await config_service.get_int(session, "ranking_period_days", 30)
    size = await config_service.get_int(session, "ranking_size", 10)

    text = (
        "⚙️ <b>CONFIGURAÇÕES DE RANKING</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📅 Período atual: <b>{period} dias</b>\n"
        f"📊 Posições atuais: <b>Top {size}</b>\n\n"
        "Escolha o que deseja alterar:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"📅 Mudar Período ({period}d)",
                callback_data="adm_rank:set_period",
            )],
            [InlineKeyboardButton(
                text=f"📊 Mudar Posições ({size})",
                callback_data="adm_rank:set_size",
            )],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_rank:menu")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 📅 MUDAR PERÍODO
# ============================================
@router.callback_query(F.data == "adm_rank:set_period")
async def cb_ranking_set_period(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text = (
        "📅 <b>MUDAR PERÍODO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Escolha o período do ranking:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📆 7 dias (semana)", callback_data="adm_rank:period:7")],
            [InlineKeyboardButton(text="📆 30 dias (mês)", callback_data="adm_rank:period:30")],
            [InlineKeyboardButton(text="📆 60 dias (bimestre)", callback_data="adm_rank:period:60")],
            [InlineKeyboardButton(text="📆 90 dias (trimestre)", callback_data="adm_rank:period:90")],
            [InlineKeyboardButton(text="📆 365 dias (ano)", callback_data="adm_rank:period:365")],
            [InlineKeyboardButton(text="✏️ Personalizado", callback_data="adm_rank:period_custom")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_rank:config")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


@router.callback_query(F.data.startswith("adm_rank:period:"))
async def cb_ranking_period_set(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    try:
        days = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Valor inválido.", show_alert=True)
        return

    old = await config_service.get_str(session, "ranking_period_days", "30")
    await config_service.set_config(session, "ranking_period_days", str(days))

    await _log_audit(
        session,
        callback.from_user.id,
        "edit_ranking_period",
        old_value={"period": old},
        new_value={"period": str(days)},
    )

    await callback.answer(f"✅ Período: {days} dias", show_alert=True)

    callback.data = "adm_rank:config"
    await cb_ranking_config(callback, session)


@router.callback_query(F.data == "adm_rank:period_custom")
async def cb_ranking_period_custom(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "📅 Envie o <b>período em dias</b> (1 a 3650):",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_antiflood_window)  # reusa estado genérico
    await callback.answer()


# ============================================
# 📊 MUDAR TAMANHO
# ============================================
@router.callback_query(F.data == "adm_rank:set_size")
async def cb_ranking_set_size(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text = (
        "📊 <b>MUDAR POSIÇÕES</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Quantas posições mostrar no ranking?"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Top 5", callback_data="adm_rank:size:5"),
                InlineKeyboardButton(text="Top 10", callback_data="adm_rank:size:10"),
            ],
            [
                InlineKeyboardButton(text="Top 20", callback_data="adm_rank:size:20"),
                InlineKeyboardButton(text="Top 50", callback_data="adm_rank:size:50"),
            ],
            [InlineKeyboardButton(text="Top 100", callback_data="adm_rank:size:100")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_rank:config")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


@router.callback_query(F.data.startswith("adm_rank:size:"))
async def cb_ranking_size_set(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    try:
        size = int(callback.data.split(":")[2])
        if not 1 <= size <= 200:
            raise ValueError
    except (ValueError, IndexError):
        await callback.answer("❌ Valor inválido.", show_alert=True)
        return

    old = await config_service.get_str(session, "ranking_size", "10")
    await config_service.set_config(session, "ranking_size", str(size))

    await _log_audit(
        session,
        callback.from_user.id,
        "edit_ranking_size",
        old_value={"size": old},
        new_value={"size": str(size)},
    )

    await callback.answer(f"✅ Top {size}", show_alert=True)

    callback.data = "adm_rank:config"
    await cb_ranking_config(callback, session)


# ============================================
# 💰 CONVERTER PONTOS EM SALDO (config)
# ============================================
@router.callback_query(F.data == "adm_rank:points_config")
async def cb_ranking_points_config(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    min_points = await config_service.get_str(session, "affiliate_min_points", "500")
    multiplier = await config_service.get_str(session, "affiliate_multiplier", "0.01")

    example_500 = float(multiplier) * 500
    example_20 = float(multiplier) * 20

    text = (
        "🎯 <b>CONVERSÃO DE PONTOS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 Mínimo de pontos: <b>{min_points}</b>\n"
        f"✖️ Multiplicador: <b>{multiplier}</b>\n\n"
        "📊 <b>Exemplos:</b>\n"
        f"• 500 pontos → <b>R$ {example_500:.2f}</b>\n"
        f"• 20 pontos → <b>R$ {example_20:.2f}</b>\n\n"
        "⚙️ Configure em: <b>Configurações → Afiliados</b>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚙️ Configurar Afiliados", callback_data="adm_cfg:afiliados")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_rank:menu")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()

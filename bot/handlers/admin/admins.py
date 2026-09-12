# ============================================
# 👥 ADMIN USERS — Larizinha Store
# ============================================
# Gerenciamento REAL de usuários pelo painel admin.
# Todos os botões funcionam de verdade.
#
# Cobre:
#   - PESQUISAR USUÁRIO (por ID, username, email, whatsapp)
#   - VER DETALHES (saldo, compras, movimentações)
#   - ADICIONAR / REMOVER SALDO (com log de auditoria)
#   - BLOQUEAR / DESBLOQUEAR
#   - HISTÓRICO DE COMPRAS
#   - BÔNUS DE REGISTRO (config)
#   - TRANSMITIR A TODOS (broadcast simples)
# ============================================

from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from loguru import logger
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.states import AdminStates
from core.models import (
    Admin,
    AuditLog,
    BlockedUser,
    Order,
    OrderStatus,
    User,
    UserStatus,
)
from core.services import config as config_service


router = Router(name="admin_users")


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
    target_type: str | None = None,
    target_id: str | None = None,
    old_value: dict | None = None,
    new_value: dict | None = None,
) -> None:
    log = AuditLog(
        admin_telegram_id=admin_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        old_value=old_value,
        new_value=new_value,
    )
    session.add(log)


def _cancel_keyboard(back_data: str = "adm_cfg:usuarios") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancelar", callback_data=back_data)]
        ]
    )


def _format_brl(v) -> str:
    if v is None:
        return "0,00"
    return f"{float(v):.2f}".replace(".", ",")


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_cfg:usuarios")
async def cb_users_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    total = await session.scalar(select(func.count(User.id))) or 0

    # Bônus de registro atual
    bonus = await config_service.get_str(session, "register_bonus", "0.00")

    text = (
        "👥 <b>CONFIGURAR USUÁRIOS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 Total de usuários: <b>{total}</b>\n"
        f"🎁 Bônus de registro: <b>R$ {bonus}</b>\n\n"
        "Use os botões abaixo para gerenciar:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Pesquisar Usuário", callback_data="adm_user:search")],
            [InlineKeyboardButton(text="📢 Transmitir a Todos", callback_data="adm_user:broadcast")],
            [InlineKeyboardButton(text="🎁 Bônus de Registro", callback_data="adm_user:register_bonus")],
            [InlineKeyboardButton(text="🚫 Lista de Bloqueados", callback_data="adm_user:blocked_list")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:config")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 🔍 PESQUISAR USUÁRIO
# ============================================
@router.callback_query(F.data == "adm_user:search")
async def cb_users_search(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text = (
        "🔍 <b>PESQUISAR USUÁRIO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Envie um dos dados abaixo:\n\n"
        "• <b>ID do Telegram</b> (ex: <code>6995978182</code>)\n"
        "• <b>@username</b> (ex: <code>@joao</code>)\n"
        "• <b>E-mail</b>\n"
        "• <b>WhatsApp</b> (ex: <code>44999998888</code>)\n"
        "• <b>ID da compra</b> (ex: <code>81c5465d...</code>)\n"
    )

    await callback.message.answer(text, reply_markup=_cancel_keyboard())
    await state.set_state(AdminStates.searching_user)
    await callback.answer()


@router.message(AdminStates.searching_user)
async def msg_users_search(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    raw = (message.text or "").strip()
    if not raw:
        await message.answer("❌ Texto vazio.")
        return

    user = await _find_user(session, raw)

    if user is None:
        await message.answer(
            f"❌ Nenhum usuário encontrado para <code>{raw}</code>.\n\n"
            "Tente outro dado.",
        )
        return

    await _show_user_details(message, session, user)
    await state.clear()


async def _find_user(session: AsyncSession, query: str) -> User | None:
    """Busca usuário por ID, username, email, whatsapp ou order_code."""
    query = query.strip()

    # Por ID do Telegram
    if query.isdigit():
        stmt = select(User).where(User.telegram_id == int(query))
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            return user

    # Por username
    if query.startswith("@"):
        query = query[1:]
    stmt = select(User).where(func.lower(User.username) == query.lower())
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user:
        return user

    # Por e-mail
    if "@" in query:
        stmt = select(User).where(func.lower(User.email) == query.lower())
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            return user

    # Por WhatsApp
    digits = "".join(c for c in query if c.isdigit())
    if len(digits) >= 10:
        stmt = select(User).where(User.whatsapp == digits)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            return user

    # Por ID de compra
    stmt = select(Order).where(Order.order_code == query)
    result = await session.execute(stmt)
    order = result.scalar_one_or_none()
    if order:
        return await session.get(User, order.user_id)

    return None


# ============================================
# 👁️ DETALHES DO USUÁRIO
# ============================================
@router.callback_query(F.data.startswith("adm_user:view:"))
async def cb_user_view(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    user_id = int(callback.data.split(":")[2])
    user = await session.get(User, user_id)
    if user is None:
        await callback.answer("❌ Usuário não encontrado.", show_alert=True)
        return

    await _edit_user_details(callback, session, user)


async def _show_user_details(
    message: Message,
    session: AsyncSession,
    user: User,
) -> None:
    text = await _build_user_details_text(session, user)
    keyboard = _build_user_details_keyboard(user)
    await message.answer(text, reply_markup=keyboard)


async def _edit_user_details(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
) -> None:
    text = await _build_user_details_text(session, user)
    keyboard = _build_user_details_keyboard(user)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


async def _build_user_details_text(
    session: AsyncSession,
    user: User,
) -> str:
    # Conta compras
    stmt = select(func.count(Order.id)).where(
        Order.user_id == user.id,
        Order.status.in_([OrderStatus.PAID, OrderStatus.DELIVERED]),
    )
    purchases = await session.scalar(stmt) or 0

    status_emoji = {
        UserStatus.ACTIVE: "🟢 Ativo",
        UserStatus.BLOCKED: "🔴 Bloqueado",
        UserStatus.BANNED: "⛔ Banido",
    }.get(user.status, "❓")

    # Verifica se está bloqueado na tabela BlockedUser
    blocked_stmt = select(BlockedUser).where(
        BlockedUser.user_telegram_id == user.telegram_id
    )
    blocked = (await session.execute(blocked_stmt)).scalar_one_or_none()
    if blocked:
        status_emoji = "🔴 Bloqueado"

    username = f"@{user.username}" if user.username else "—"

    return (
        f"👤 <b>Usuário: {user.first_name or 'Sem nome'}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 Telegram ID: <code>{user.telegram_id}</code>\n"
        f"📛 Username: {username}\n"
        f"📲 WhatsApp: {user.whatsapp or '—'}\n"
        f"📧 E-mail: {user.email or '—'}\n"
        f"📊 Status: <b>{status_emoji}</b>\n\n"
        f"💰 Saldo: <b>R$ {_format_brl(user.balance)}</b>\n"
        f"🎁 Saldo de afiliado: <b>R$ {_format_brl(user.affiliate_balance)}</b>\n"
        f"🎯 Pontos: <b>{user.points or 0}</b>\n\n"
        f"🛒 Compras: <b>{purchases}</b>\n"
        f"💸 Total gasto: <b>R$ {_format_brl(user.total_spent)}</b>\n"
        f"💳 Total recarregado: <b>R$ {_format_brl(user.total_recharged)}</b>\n\n"
        f"👥 Indicado por: <code>{user.referred_by or '—'}</code>\n"
        f"🔗 Link de afiliado: <code>{user.affiliate_code or '—'}</code>"
    )


def _build_user_details_keyboard(user: User) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Adicionar Saldo", callback_data=f"adm_user:add_balance:{user.id}")],
            [InlineKeyboardButton(text="➖ Remover Saldo", callback_data=f"adm_user:remove_balance:{user.id}")],
            [InlineKeyboardButton(text="🛒 Ver Compras", callback_data=f"adm_user:orders:{user.id}")],
            [InlineKeyboardButton(text="💳 Ver Transações", callback_data=f"adm_user:transactions:{user.id}")],
            [
                InlineKeyboardButton(text="🔴 Bloquear", callback_data=f"adm_user:block:{user.id}"),
                InlineKeyboardButton(text="🟢 Desbloquear", callback_data=f"adm_user:unblock:{user.id}"),
            ],
            [InlineKeyboardButton(text="📩 Enviar Mensagem", callback_data=f"adm_user:send_msg:{user.id}")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_cfg:usuarios")],
        ]
    )


# ============================================
# ➕ ADICIONAR SALDO
# ============================================
@router.callback_query(F.data.startswith("adm_user:add_balance:"))
async def cb_user_add_balance(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    user_id = int(callback.data.split(":")[2])
    user = await session.get(User, user_id)
    if user is None:
        await callback.answer("❌ Usuário não encontrado.", show_alert=True)
        return

    await state.update_data(user_id=user_id, action="add")
    await callback.message.answer(
        f"➕ <b>ADICIONAR SALDO</b>\n\n"
        f"Usuário: <b>{user.first_name or user.telegram_id}</b>\n"
        f"Saldo atual: <b>R$ {_format_brl(user.balance)}</b>\n\n"
        f"Envie o valor a adicionar (ex: <code>10.00</code>):",
        reply_markup=_cancel_keyboard(f"adm_user:view:{user_id}"),
    )
    await state.set_state(AdminStates.editing_user_balance)
    await callback.answer()


# ============================================
# ➖ REMOVER SALDO
# ============================================
@router.callback_query(F.data.startswith("adm_user:remove_balance:"))
async def cb_user_remove_balance(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    user_id = int(callback.data.split(":")[2])
    user = await session.get(User, user_id)
    if user is None:
        await callback.answer("❌ Usuário não encontrado.", show_alert=True)
        return

    await state.update_data(user_id=user_id, action="remove")
    await callback.message.answer(
        f"➖ <b>REMOVER SALDO</b>\n\n"
        f"Usuário: <b>{user.first_name or user.telegram_id}</b>\n"
        f"Saldo atual: <b>R$ {_format_brl(user.balance)}</b>\n\n"
        f"Envie o valor a remover (ex: <code>5.00</code>):",
        reply_markup=_cancel_keyboard(f"adm_user:view:{user_id}"),
    )
    await state.set_state(AdminStates.editing_user_balance)
    await callback.answer()


# ============================================
# 💰 SALVAR ALTERAÇÃO DE SALDO
# ============================================
@router.message(AdminStates.editing_user_balance)
async def msg_save_balance(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    data = await state.get_data()
    user_id = data.get("user_id")
    action = data.get("action", "add")

    user = await session.get(User, user_id)
    if user is None:
        await message.answer("❌ Usuário não encontrado.")
        await state.clear()
        return

    raw = (message.text or "").strip().replace(",", ".")
    try:
        value = Decimal(raw)
        if value <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer("❌ Valor inválido. Ex: <code>10.00</code>")
        return

    value = value.quantize(Decimal("0.01"))
    old_balance = user.balance or Decimal("0.00")

    if action == "add":
        user.balance = old_balance + value
        action_label = "adicionou"
    else:
        user.balance = max(Decimal("0.00"), old_balance - value)
        action_label = "removeu"

    session.add(user)

    await _log_audit(
        session,
        message.from_user.id,
        f"user_balance_{action}",
        target_type="user",
        target_id=str(user.telegram_id),
        old_value={"balance": str(old_balance)},
        new_value={"balance": str(user.balance)},
    )

    await message.answer(
        f"✅ Admin {action_label} <b>R$ {value:.2f}</b>\n\n"
        f"👤 {user.first_name or user.telegram_id}\n"
        f"💰 Novo saldo: <b>R$ {_format_brl(user.balance)}</b>"
    )

    # Notifica o usuário
    try:
        if action == "add":
            notif = (
                f"🎉 <b>Saldo adicionado!</b>\n\n"
                f"💰 +R$ {value:.2f}\n"
                f"💸 Novo saldo: <b>R$ {_format_brl(user.balance)}</b>"
            )
        else:
            notif = (
                f"⚠️ <b>Saldo ajustado</b>\n\n"
                f"📉 -R$ {value:.2f}\n"
                f"💸 Novo saldo: <b>R$ {_format_brl(user.balance)}</b>"
            )
        await message.bot.send_message(
            chat_id=user.telegram_id,
            text=notif,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"⚠️ Não foi possível notificar usuário: {e}")

    await state.clear()


# ============================================
# 🛒 VER COMPRAS DO USUÁRIO
# ============================================
@router.callback_query(F.data.startswith("adm_user:orders:"))
async def cb_user_orders(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    user_id = int(callback.data.split(":")[2])
    user = await session.get(User, user_id)
    if user is None:
        await callback.answer("❌ Usuário não encontrado.", show_alert=True)
        return

    stmt = (
        select(Order)
        .where(Order.user_id == user.id)
        .order_by(Order.created_at.desc())
        .limit(20)
    )
    result = await session.execute(stmt)
    orders = list(result.scalars().all())

    if not orders:
        text = (
            f"🛒 <b>Compras de {user.first_name or user.telegram_id}</b>\n\n"
            "Nenhuma compra registrada."
        )
    else:
        lines = [
            f"🛒 <b>Compras de {user.first_name or user.telegram_id}</b>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "",
        ]
        for o in orders[:10]:
            date = o.created_at.strftime("%d/%m/%Y") if o.created_at else "?"
            lines.append(
                f"• <code>{o.order_code[:12]}...</code> — "
                f"{o.product_name} — R$ {_format_brl(o.total_price)} — {date}"
            )
        if len(orders) > 10:
            lines.append(f"\n<i>+{len(orders) - 10} compras mais antigas</i>")
        text = "\n".join(lines)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Voltar", callback_data=f"adm_user:view:{user.id}")]
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 💳 VER TRANSAÇÕES DO USUÁRIO
# ============================================
@router.callback_query(F.data.startswith("adm_user:transactions:"))
async def cb_user_transactions(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    user_id = int(callback.data.split(":")[2])
    user = await session.get(User, user_id)
    if user is None:
        await callback.answer("❌ Usuário não encontrado.", show_alert=True)
        return

    from core.models import Payment, PaymentStatus

    stmt = (
        select(Payment)
        .where(Payment.user_id == user.id)
        .order_by(Payment.created_at.desc())
        .limit(20)
    )
    result = await session.execute(stmt)
    payments = list(result.scalars().all())

    if not payments:
        text = (
            f"💳 <b>Transações de {user.first_name or user.telegram_id}</b>\n\n"
            "Nenhuma transação registrada."
        )
    else:
        lines = [
            f"💳 <b>Transações de {user.first_name or user.telegram_id}</b>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "",
        ]
        for p in payments[:10]:
            date = p.created_at.strftime("%d/%m %H:%M") if p.created_at else "?"
            status_emoji = {
                PaymentStatus.APPROVED: "✅",
                PaymentStatus.PENDING: "⏳",
                PaymentStatus.EXPIRED: "⌛",
                PaymentStatus.REJECTED: "❌",
            }.get(p.status, "❓")
            lines.append(
                f"{status_emoji} R$ {_format_brl(p.amount)} — "
                f"{p.status.value} — {date}"
            )
        text = "\n".join(lines)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Voltar", callback_data=f"adm_user:view:{user.id}")]
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 🔴 BLOQUEAR USUÁRIO
# ============================================
@router.callback_query(F.data.startswith("adm_user:block:"))
async def cb_user_block(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    user_id = int(callback.data.split(":")[2])
    user = await session.get(User, user_id)
    if user is None:
        await callback.answer("❌ Usuário não encontrado.", show_alert=True)
        return

    await state.update_data(user_id=user_id)
    await callback.message.answer(
        f"🔴 <b>BLOQUEAR USUÁRIO</b>\n\n"
        f"Usuário: <b>{user.first_name or user.telegram_id}</b>\n\n"
        f"Envie o <b>motivo do bloqueio</b>\n"
        f"(ou envie <code>-</code> pra sem motivo):",
        reply_markup=_cancel_keyboard(f"adm_user:view:{user_id}"),
    )
    await state.set_state(AdminStates.blocking_user_reason)
    await callback.answer()


@router.message(AdminStates.blocking_user_reason)
async def msg_user_block_reason(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    data = await state.get_data()
    user_id = data.get("user_id")
    user = await session.get(User, user_id)
    if user is None:
        await message.answer("❌ Usuário não encontrado.")
        await state.clear()
        return

    reason = (message.text or "").strip()
    if reason == "-":
        reason = ""

    await state.update_data(reason=reason)
    await message.answer(
        "⏰ <b>Duração do bloqueio</b>\n\nEscolha:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="10 minutos", callback_data="adm_user:block_dur:600")],
                [InlineKeyboardButton(text="1 hora", callback_data="adm_user:block_dur:3600")],
                [InlineKeyboardButton(text="24 horas", callback_data="adm_user:block_dur:86400")],
                [InlineKeyboardButton(text="7 dias", callback_data="adm_user:block_dur:604800")],
                [InlineKeyboardButton(text="Permanente", callback_data="adm_user:block_dur:0")],
                [InlineKeyboardButton(text="❌ Cancelar", callback_data=f"adm_user:view:{user_id}")],
            ]
        ),
    )
    await state.set_state(AdminStates.blocking_user_duration)


@router.callback_query(F.data.startswith("adm_user:block_dur:"))
async def cb_user_block_duration(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    duration = int(callback.data.split(":")[2])
    data = await state.get_data()
    user_id = data.get("user_id")
    reason = data.get("reason", "")

    user = await session.get(User, user_id)
    if user is None:
        await callback.answer("❌ Usuário não encontrado.", show_alert=True)
        await state.clear()
        return

    from datetime import datetime, timedelta, timezone

    expires_at = None
    if duration > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=duration)

    # Verifica se já está bloqueado
    stmt = select(BlockedUser).where(
        BlockedUser.user_telegram_id == user.telegram_id
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()

    if existing:
        existing.reason = reason
        existing.expires_at = expires_at
        existing.blocked_by = callback.from_user.id
        session.add(existing)
    else:
        blocked = BlockedUser(
            user_telegram_id=user.telegram_id,
            reason=reason,
            blocked_by=callback.from_user.id,
            expires_at=expires_at,
        )
        session.add(blocked)

    user.status = UserStatus.BLOCKED
    session.add(user)

    await _log_audit(
        session,
        callback.from_user.id,
        "block_user",
        target_type="user",
        target_id=str(user.telegram_id),
        new_value={"reason": reason, "duration_seconds": duration},
    )

    duration_txt = "Permanente" if duration == 0 else f"{duration}s"
    await callback.answer(f"🔴 Bloqueado por {duration_txt}", show_alert=True)

    # Notifica o usuário
    try:
        await callback.bot.send_message(
            chat_id=user.telegram_id,
            text=(
                f"🚫 <b>Você foi bloqueado</b>\n\n"
                f"Motivo: {reason or 'Não informado'}\n"
                f"Duração: <b>{duration_txt}</b>"
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass

    await state.clear()

    callback.data = f"adm_user:view:{user_id}"
    await cb_user_view(callback, session)


# ============================================
# 🟢 DESBLOQUEAR
# ============================================
@router.callback_query(F.data.startswith("adm_user:unblock:"))
async def cb_user_unblock(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    user_id = int(callback.data.split(":")[2])
    user = await session.get(User, user_id)
    if user is None:
        await callback.answer("❌ Usuário não encontrado.", show_alert=True)
        return

    # Remove da tabela BlockedUser
    stmt = select(BlockedUser).where(
        BlockedUser.user_telegram_id == user.telegram_id
    )
    blocked = (await session.execute(stmt)).scalar_one_or_none()
    if blocked:
        await session.delete(blocked)

    user.status = UserStatus.ACTIVE
    session.add(user)

    await _log_audit(
        session,
        callback.from_user.id,
        "unblock_user",
        target_type="user",
        target_id=str(user.telegram_id),
    )

    await callback.answer("🟢 Usuário desbloqueado!", show_alert=True)

    # Notifica
    try:
        await callback.bot.send_message(
            chat_id=user.telegram_id,
            text="🟢 <b>Você foi desbloqueado!</b>\n\nVolte a usar o bot normalmente.",
            parse_mode="HTML",
        )
    except Exception:
        pass

    callback.data = f"adm_user:view:{user_id}"
    await cb_user_view(callback, session)


# ============================================
# 📩 ENVIAR MENSAGEM AO USUÁRIO
# ============================================
@router.callback_query(F.data.startswith("adm_user:send_msg:"))
async def cb_user_send_msg(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    user_id = int(callback.data.split(":")[2])
    user = await session.get(User, user_id)
    if user is None:
        await callback.answer("❌ Usuário não encontrado.", show_alert=True)
        return

    await state.update_data(user_id=user_id)
    await callback.message.answer(
        f"📩 <b>ENVIAR MENSAGEM</b>\n\n"
        f"Para: <b>{user.first_name or user.telegram_id}</b>\n\n"
        f"Envie a mensagem que deseja enviar:",
        reply_markup=_cancel_keyboard(f"adm_user:view:{user_id}"),
    )
    await state.set_state(AdminStates.sending_broadcast_user)
    await callback.answer()


@router.message(AdminStates.sending_broadcast_user)
async def msg_user_send_msg(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    data = await state.get_data()
    user_id = data.get("user_id")
    user = await session.get(User, user_id)
    if user is None:
        await message.answer("❌ Usuário não encontrado.")
        await state.clear()
        return

    text = message.text or message.caption or ""
    if not text.strip():
        await message.answer("❌ Texto vazio.")
        return

    try:
        await message.bot.send_message(
            chat_id=user.telegram_id,
            text=text,
            parse_mode="HTML",
        )
        await message.answer("✅ Mensagem enviada!")
    except Exception as e:
        await message.answer(f"❌ Erro ao enviar: <code>{str(e)[:150]}</code>")

    await state.clear()


# ============================================
# 🚫 LISTA DE BLOQUEADOS
# ============================================
@router.callback_query(F.data == "adm_user:blocked_list")
async def cb_user_blocked_list(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    stmt = select(BlockedUser).order_by(BlockedUser.blocked_at.desc()).limit(30)
    result = await session.execute(stmt)
    blocked_list = list(result.scalars().all())

    if not blocked_list:
        text = (
            "🚫 <b>USUÁRIOS BLOQUEADOS</b>\n\n"
            "Nenhum usuário bloqueado no momento."
        )
    else:
        lines = [
            "🚫 <b>USUÁRIOS BLOQUEADOS</b>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "",
        ]
        for b in blocked_list:
            date = b.blocked_at.strftime("%d/%m %H:%M") if b.blocked_at else "?"
            exp = "Permanente" if not b.expires_at else b.expires_at.strftime("%d/%m %H:%M")
            lines.append(
                f"• <code>{b.user_telegram_id}</code> — "
                f"{b.reason or 'sem motivo'} — até {exp}"
            )
        text = "\n".join(lines)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_cfg:usuarios")]
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 🎁 BÔNUS DE REGISTRO
# ============================================
@router.callback_query(F.data == "adm_user:register_bonus")
async def cb_user_register_bonus(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    current = await config_service.get_str(session, "register_bonus", "0.00")

    text = (
        "🎁 <b>BÔNUS DE REGISTRO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Bônus atual: <b>R$ {current}</b>\n\n"
        "Este é o valor que cada novo usuário recebe\n"
        "ao se registrar no bot.\n\n"
        "Para não dar nenhum bônus, envie <code>0</code>.\n\n"
        "Envie o novo valor:"
    )

    await callback.message.answer(text, reply_markup=_cancel_keyboard())
    await state.set_state(AdminStates.editing_user_data)
    await callback.answer()


@router.message(AdminStates.editing_user_data)
async def msg_user_register_bonus(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    raw = (message.text or "").strip().replace(",", ".")
    try:
        val = Decimal(raw)
        if val < 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer("❌ Valor inválido. Ex: <code>5.00</code>")
        return

    old = await config_service.get_str(session, "register_bonus", "0.00")
    await config_service.set_config(session, "register_bonus", f"{val:.2f}")

    await _log_audit(
        session,
        message.from_user.id,
        "edit_register_bonus",
        old_value={"register_bonus": old},
        new_value={"register_bonus": f"{val:.2f}"},
    )

    await message.answer(f"✅ Bônus de registro: <b>R$ {val:.2f}</b>")
    await state.clear()


# ============================================
# 📢 TRANSMITIR A TODOS
# ============================================
@router.callback_query(F.data == "adm_user:broadcast")
async def cb_user_broadcast(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    total = await session.scalar(
        select(func.count(User.id)).where(
            User.status == UserStatus.ACTIVE,
            User.is_blocked_bot.is_(False),
        )
    ) or 0

    text = (
        "📢 <b>TRANSMITIR A TODOS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Usuários ativos: <b>{total}</b>\n\n"
        "Envie a mensagem que deseja transmitir.\n"
        "Pode ser <b>texto</b>, <b>foto com legenda</b> ou "
        "<b>vídeo com legenda</b>."
    )

    await callback.message.answer(text, reply_markup=_cancel_keyboard())
    await state.set_state(AdminStates.waiting_broadcast_text)
    await callback.answer()


@router.message(AdminStates.waiting_broadcast_text)
async def msg_user_broadcast(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    raw_text = message.text or message.caption or ""
    if not raw_text.strip() and not (message.photo or message.video):
        await message.answer("❌ Mensagem vazia.")
        return

    # Confirma
    stmt = select(func.count(User.id)).where(
        User.status == UserStatus.ACTIVE,
        User.is_blocked_bot.is_(False),
    )
    total = await session.scalar(stmt) or 0

    await state.update_data(
        broadcast_text=raw_text,
        broadcast_photo=message.photo[-1].file_id if message.photo else None,
        broadcast_video=message.video.file_id if message.video else None,
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ SIM, ENVIAR", callback_data="adm_user:broadcast_send")],
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_cfg:usuarios")],
        ]
    )

    await message.answer(
        f"📢 <b>Confirmar envio?</b>\n\n"
        f"Vai enviar para <b>{total}</b> usuário(s).",
        reply_markup=keyboard,
    )


@router.callback_query(F.data == "adm_user:broadcast_send")
async def cb_user_broadcast_send(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    data = await state.get_data()
    text = data.get("broadcast_text", "")
    photo = data.get("broadcast_photo")
    video = data.get("broadcast_video")

    await callback.answer("📢 Enviando...", show_alert=False)

    stmt = select(User).where(
        User.status == UserStatus.ACTIVE,
        User.is_blocked_bot.is_(False),
    )
    result = await session.execute(stmt)
    users = list(result.scalars().all())

    import asyncio

    sent = 0
    failed = 0

    for u in users:
        try:
            if photo:
                await callback.bot.send_photo(
                    chat_id=u.telegram_id,
                    photo=photo,
                    caption=text or None,
                    parse_mode="HTML",
                )
            elif video:
                await callback.bot.send_video(
                    chat_id=u.telegram_id,
                    video=video,
                    caption=text or None,
                    parse_mode="HTML",
                )
            else:
                await callback.bot.send_message(
                    chat_id=u.telegram_id,
                    text=text,
                    parse_mode="HTML",
                )
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    await callback.message.answer(
        f"📢 <b>Transmissão concluída!</b>\n\n"
        f"✅ Enviadas: <b>{sent}</b>\n"
        f"❌ Falhas: <b>{failed}</b>"
    )

    await state.clear()

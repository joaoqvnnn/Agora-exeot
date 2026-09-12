# ============================================
# 💸 ADMIN WITHDRAWALS — Larizinha Store
# ============================================
# Gerenciamento REAL de saques de afiliados.
# Todos os botões funcionam de verdade.
#
# Cobre:
#   - LISTAR saques (pendentes, pagos, recusados)
#   - VER detalhes
#   - APROVAR (marca como pago + notifica)
#   - RECUSAR (estorna saldo + motivo)
# ============================================

from datetime import datetime, timezone
from decimal import Decimal

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.states import AdminStates
from core.models import (
    Admin,
    AuditLog,
    User,
    Withdrawal,
    WithdrawalMethod,
    WithdrawalStatus,
)


router = Router(name="admin_withdrawals")


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


def _format_brl(v) -> str:
    if v is None:
        return "0,00"
    return f"{float(v):.2f}".replace(".", ",")


def _status_emoji(status: WithdrawalStatus) -> str:
    return {
        WithdrawalStatus.PENDING: "⏳",
        WithdrawalStatus.PROCESSING: "🔄",
        WithdrawalStatus.PAID: "✅",
        WithdrawalStatus.REJECTED: "❌",
        WithdrawalStatus.REFUNDED: "↩️",
        WithdrawalStatus.CANCELLED: "🚫",
    }.get(status, "❓")


# ============================================
# 📋 LISTA DE SAQUES
# ============================================
@router.callback_query(F.data == "adm_wd:list")
async def cb_withdrawals_list(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await _show_withdrawals(callback, session, filter_type="pending", page=0)


@router.callback_query(F.data.startswith("adm_wd:list:"))
async def cb_withdrawals_list_filter(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    parts = callback.data.split(":")
    filter_type = parts[2] if len(parts) > 2 else "pending"
    page = int(parts[3]) if len(parts) > 3 else 0

    await _show_withdrawals(callback, session, filter_type, page)


async def _show_withdrawals(
    callback: CallbackQuery,
    session: AsyncSession,
    filter_type: str = "pending",
    page: int = 0,
) -> None:
    PER_PAGE = 10

    status_filter = {
        "pending": [WithdrawalStatus.PENDING],
        "processing": [WithdrawalStatus.PROCESSING],
        "paid": [WithdrawalStatus.PAID],
        "rejected": [WithdrawalStatus.REJECTED],
        "all": [
            WithdrawalStatus.PENDING,
            WithdrawalStatus.PROCESSING,
            WithdrawalStatus.PAID,
            WithdrawalStatus.REJECTED,
            WithdrawalStatus.REFUNDED,
            WithdrawalStatus.CANCELLED,
        ],
    }.get(filter_type, [WithdrawalStatus.PENDING])

    base = select(Withdrawal).where(Withdrawal.status.in_(status_filter))

    total = await session.scalar(
        select(func.count()).select_from(base.subquery())
    ) or 0

    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    stmt = (
        base.order_by(Withdrawal.created_at.desc())
        .offset(page * PER_PAGE)
        .limit(PER_PAGE)
    )
    result = await session.execute(stmt)
    withdrawals = list(result.scalars().all())

    filter_labels = {
        "pending": "⏳ Pendentes",
        "processing": "🔄 Processando",
        "paid": "✅ Pagos",
        "rejected": "❌ Recusados",
        "all": "📋 Todos",
    }

    header = (
        "💸 <b>SAQUES</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Filtro: <b>{filter_labels.get(filter_type, filter_type)}</b>\n"
        f"Total: <b>{total}</b>\n\n"
    )

    rows: list[list[InlineKeyboardButton]] = []

    if not withdrawals:
        body = "Nenhum saque neste filtro."
    else:
        lines = []
        for w in withdrawals:
            date = w.created_at.strftime("%d/%m %H:%M") if w.created_at else "?"
            icon = _status_emoji(w.status)
            lines.append(
                f"{icon} <code>{w.user_telegram_id}</code> — "
                f"R$ {_format_brl(w.amount)} — {w.method.value} — {date}"
            )
            rows.append([
                InlineKeyboardButton(
                    text=f"{icon} R$ {_format_brl(w.amount)} — {w.user_telegram_id}",
                    callback_data=f"adm_wd:view:{w.id}",
                )
            ])
        body = "\n".join(lines)

    # Navegação
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                text="⬅️",
                callback_data=f"adm_wd:list:{filter_type}:{page - 1}",
            ))
        nav.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="adm:noop",
        ))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(
                text="➡️",
                callback_data=f"adm_wd:list:{filter_type}:{page + 1}",
            ))
        rows.append(nav)

    # Filtros
    rows.append([
        InlineKeyboardButton(text="⏳ Pendentes", callback_data="adm_wd:list:pending:0"),
        InlineKeyboardButton(text="✅ Pagos", callback_data="adm_wd:list:paid:0"),
    ])
    rows.append([
        InlineKeyboardButton(text="❌ Recusados", callback_data="adm_wd:list:rejected:0"),
        InlineKeyboardButton(text="📋 Todos", callback_data="adm_wd:list:all:0"),
    ])
    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_cfg:afiliados")
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    text = header + body

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 👁️ VER DETALHE DO SAQUE
# ============================================
@router.callback_query(F.data.startswith("adm_wd:view:"))
async def cb_withdrawal_view(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    wd_id = int(callback.data.split(":")[2])
    wd = await session.get(Withdrawal, wd_id)
    if wd is None:
        await callback.answer("❌ Saque não encontrado.", show_alert=True)
        return

    user = await session.get(User, wd.user_id)

    date = wd.created_at.strftime("%d/%m/%Y %H:%M") if wd.created_at else "?"
    processed = (
        wd.processed_at.strftime("%d/%m/%Y %H:%M")
        if wd.processed_at else "—"
    )

    icon = _status_emoji(wd.status)

    pix_info = "—"
    if wd.method == WithdrawalMethod.PIX:
        pix_info = (
            f"💠 Chave Pix: <code>{wd.pix_key or '—'}</code>\n"
            f"🏷 Tipo: <b>{wd.pix_key_type or '—'}</b>"
        )

    bank_info = "—"
    if wd.method == WithdrawalMethod.BANK and wd.bank_data:
        bd = wd.bank_data
        bank_info = (
            f"🏦 Banco: <b>{bd.get('bank_name', '—')}</b>\n"
            f"🏷 Agência: <code>{bd.get('agency', '—')}</code>\n"
            f"💳 Conta: <code>{bd.get('account', '—')}</code>\n"
            f"👤 Titular: <b>{bd.get('holder_name', '—')}</b>"
        )

    user_name = user.first_name if user else "?"
    username = f"@{user.username}" if user and user.username else "—"

    text = (
        f"{icon} <b>SAQUE #{wd.id}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Usuário: <b>{user_name}</b>\n"
        f"📛 Username: {username}\n"
        f"🆔 Telegram: <code>{wd.user_telegram_id}</code>\n\n"
        f"💰 Valor: <b>R$ {_format_brl(wd.amount)}</b>\n"
        f"📊 Status: <b>{wd.status.value}</b>\n"
        f"💼 Método: <b>{wd.method.value.upper()}</b>\n\n"
        f"📅 Criado: {date}\n"
        f"⏰ Processado: {processed}\n\n"
    )

    if wd.method == WithdrawalMethod.PIX:
        text += f"{pix_info}\n\n"
    else:
        text += f"{bank_info}\n\n"

    if wd.rejection_reason:
        text += f"❌ Motivo da recusa: {wd.rejection_reason}\n\n"

    if wd.external_transaction_id:
        text += f"🆔 TX: <code>{wd.external_transaction_id}</code>\n\n"

    # Botões de ação
    rows: list[list[InlineKeyboardButton]] = []

    if wd.status in (WithdrawalStatus.PENDING, WithdrawalStatus.PROCESSING):
        rows.append([
            InlineKeyboardButton(
                text="✅ Aprovar e Pagar",
                callback_data=f"adm_wd:approve:{wd.id}",
            )
        ])
        rows.append([
            InlineKeyboardButton(
                text="❌ Recusar e Estornar",
                callback_data=f"adm_wd:reject:{wd.id}",
            )
        ])

    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_wd:list:pending:0")
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# ✅ APROVAR SAQUE
# ============================================
@router.callback_query(F.data.startswith("adm_wd:approve:"))
async def cb_withdrawal_approve(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    wd_id = int(callback.data.split(":")[2])
    wd = await session.get(Withdrawal, wd_id)
    if wd is None:
        await callback.answer("❌ Saque não encontrado.", show_alert=True)
        return

    if wd.status not in (WithdrawalStatus.PENDING, WithdrawalStatus.PROCESSING):
        await callback.answer(
            f"⚠️ Saque já está como {wd.status.value}.",
            show_alert=True,
        )
        return

    # Marca como pago
    wd.status = WithdrawalStatus.PAID
    wd.processed_at = datetime.now(timezone.utc)
    wd.approved_by = callback.from_user.id
    session.add(wd)

    await _log_audit(
        session,
        callback.from_user.id,
        "approve_withdrawal",
        target_type="withdrawal",
        target_id=str(wd.id),
        old_value={"status": "pending"},
        new_value={"status": "paid", "amount": str(wd.amount)},
    )

    await callback.answer("✅ Saque aprovado!", show_alert=True)

    # Notifica o usuário
    try:
        notif = (
            f"✅ <b>Saque aprovado!</b>\n\n"
            f"💰 Valor: <b>R$ {_format_brl(wd.amount)}</b>\n"
            f"💼 Método: <b>{wd.method.value.upper()}</b>\n\n"
        )
        if wd.method == WithdrawalMethod.PIX:
            notif += f"💠 Chave: <code>{wd.pix_key}</code>\n\n"
        elif wd.method == WithdrawalMethod.BANK and wd.bank_data:
            bd = wd.bank_data
            notif += (
                f"🏦 Banco: <b>{bd.get('bank_name', '—')}</b>\n"
                f"💳 Conta: <code>{bd.get('account', '—')}</code>\n\n"
            )
        notif += "O valor já foi enviado. Confira sua conta!"

        await callback.bot.send_message(
            chat_id=wd.user_telegram_id,
            text=notif,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"⚠️ Não foi possível notificar {wd.user_telegram_id}: {e}")

    callback.data = f"adm_wd:view:{wd_id}"
    await cb_withdrawal_view(callback, session)


# ============================================
# ❌ RECUSAR SAQUE
# ============================================
@router.callback_query(F.data.startswith("adm_wd:reject:"))
async def cb_withdrawal_reject(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    wd_id = int(callback.data.split(":")[2])
    wd = await session.get(Withdrawal, wd_id)
    if wd is None:
        await callback.answer("❌ Saque não encontrado.", show_alert=True)
        return

    if wd.status not in (WithdrawalStatus.PENDING, WithdrawalStatus.PROCESSING):
        await callback.answer(
            f"⚠️ Saque já está como {wd.status.value}.",
            show_alert=True,
        )
        return

    await state.update_data(withdrawal_id=wd_id)
    await callback.message.answer(
        f"❌ <b>RECUSAR SAQUE #{wd_id}</b>\n\n"
        f"💰 Valor: <b>R$ {_format_brl(wd.amount)}</b>\n"
        f"👤 Usuário: <code>{wd.user_telegram_id}</code>\n\n"
        "Envie o <b>motivo da recusa</b>\n"
        "(ou envie <code>-</code> pra sem motivo):",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Cancelar", callback_data=f"adm_wd:view:{wd_id}")]
            ]
        ),
    )
    await state.set_state(AdminStates.rejection_reason)
    await callback.answer()


@router.message(AdminStates.rejection_reason)
async def msg_withdrawal_reject(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    data = await state.get_data()
    wd_id = data.get("withdrawal_id")
    wd = await session.get(Withdrawal, wd_id)

    if wd is None:
        await message.answer("❌ Saque não encontrado.")
        await state.clear()
        return

    reason = (message.text or "").strip()
    if reason == "-":
        reason = ""

    # Recusa e estorna
    wd.status = WithdrawalStatus.REFUNDED
    wd.processed_at = datetime.now(timezone.utc)
    wd.rejection_reason = reason
    wd.approved_by = message.from_user.id
    session.add(wd)

    # Estorna saldo pro afiliado
    user = await session.get(User, wd.user_id)
    if user is not None:
        user.affiliate_balance = (
            user.affiliate_balance or Decimal("0.00")
        ) + wd.amount
        session.add(user)

    await _log_audit(
        session,
        message.from_user.id,
        "reject_withdrawal",
        target_type="withdrawal",
        target_id=str(wd.id),
        new_value={"status": "refunded", "reason": reason},
    )

    await message.answer(
        f"✅ Saque #{wd_id} recusado e saldo estornado.\n\n"
        f"💰 Valor devolvido: <b>R$ {_format_brl(wd.amount)}</b>"
    )

    # Notifica o usuário
    try:
        await message.bot.send_message(
            chat_id=wd.user_telegram_id,
            text=(
                f"❌ <b>Saque recusado</b>\n\n"
                f"💰 Valor: <b>R$ {_format_brl(wd.amount)}</b>\n"
                f"📄 Motivo: {reason or 'Não informado'}\n\n"
                f"O valor foi devolvido ao seu saldo de afiliado."
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"⚠️ Não foi possível notificar {wd.user_telegram_id}: {e}")

    await state.clear()


# ============================================
# 🔄 MARCAR COMO PROCESSANDO
# ============================================
@router.callback_query(F.data.startswith("adm_wd:processing:"))
async def cb_withdrawal_processing(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    wd_id = int(callback.data.split(":")[2])
    wd = await session.get(Withdrawal, wd_id)
    if wd is None:
        await callback.answer("❌ Saque não encontrado.", show_alert=True)
        return

    wd.status = WithdrawalStatus.PROCESSING
    session.add(wd)

    await _log_audit(
        session,
        callback.from_user.id,
        "withdrawal_processing",
        target_type="withdrawal",
        target_id=str(wd.id),
    )

    await callback.answer("🔄 Marcado como processando.", show_alert=True)

    callback.data = f"adm_wd:view:{wd_id}"
    await cb_withdrawal_view(callback, session)

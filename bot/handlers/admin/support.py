# ============================================
# 🎧 ADMIN SUPPORT — Larizinha Store
# ============================================
# Configuração REAL de atendimento (IA + humano).
# Todos os botões funcionam de verdade.
#
# Cobre:
#   - LIGAR/DESLIGAR IA
#   - LINK do suporte humano
#   - MENSAGEM pronta
#   - TICKETS abertos (listar, ver, responder, fechar)
#   - HANDOFF (humano assume)
# ============================================

from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.states import AdminStates
from core.models import (
    Admin,
    AuditLog,
    Ticket,
    TicketStatus,
    User,
)
from core.services import config as config_service


router = Router(name="admin_support")


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


def _cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_sup:menu")]
        ]
    )


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_sup:menu")
async def cb_support_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    ai_enabled = await config_service.get_bool(session, "ai_enabled", True)
    support_link = await config_service.get_str(session, "support_link", "")
    open_tickets = await session.scalar(
        select(func.count(Ticket.id)).where(
            Ticket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS])
        )
    ) or 0

    ai_status = "🟢 ATIVA" if ai_enabled else "🔴 DESATIVADA"
    link_status = "🟢 Configurado" if support_link else "⚪ Não configurado"

    text = (
        "🎧 <b>CONFIGURAÇÃO DE ATENDIMENTO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🤖 IA: <b>{ai_status}</b>\n"
        f"🔗 Link de suporte: <b>{link_status}</b>\n"
        f"🎫 Tickets abertos: <b>{open_tickets}</b>\n\n"
        "Escolha uma opção:"
    )

    toggle_text = "🔴 DESATIVAR IA" if ai_enabled else "🟢 ATIVAR IA"
    toggle_cb = "adm_sup:ai_off" if ai_enabled else "adm_sup:ai_on"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle_text, callback_data=toggle_cb)],
            [InlineKeyboardButton(text="🔗 Mudar Link de Suporte", callback_data="adm_sup:set_link")],
            [InlineKeyboardButton(text="🎫 Ver Tickets Abertos", callback_data="adm_sup:tickets")],
            [InlineKeyboardButton(text="📝 Mensagem Inicial do Atendimento", callback_data="adm_msg:view:support_welcome")],
            [InlineKeyboardButton(text="🧠 Instruções da IA", callback_data="adm_sup:ai_prompt")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:config")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 🤖 IA ON/OFF
# ============================================
@router.callback_query(F.data == "adm_sup:ai_on")
async def cb_support_ai_on(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await config_service.set_config(session, "ai_enabled", "true")
    await _log_audit(session, callback.from_user.id, "ai_on")
    await callback.answer("🟢 IA ativada", show_alert=True)
    await cb_support_menu(callback, session)


@router.callback_query(F.data == "adm_sup:ai_off")
async def cb_support_ai_off(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await config_service.set_config(session, "ai_enabled", "false")
    await _log_audit(session, callback.from_user.id, "ai_off")
    await callback.answer("🔴 IA desativada", show_alert=True)
    await cb_support_menu(callback, session)


# ============================================
# 🔗 MUDAR LINK DE SUPORTE
# ============================================
@router.callback_query(F.data == "adm_sup:set_link")
async def cb_support_set_link(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    current = await config_service.get_str(session, "support_link", "Não definido")

    await callback.message.answer(
        "🔗 <b>MUDAR LINK DE SUPORTE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Atual:</b>\n<code>{current}</code>\n\n"
        "Envie o novo link.\n\n"
        "Exemplos:\n"
        "• <code>https://wa.me/5511999999999</code>\n"
        "• <code>https://t.me/seu_suporte</code>",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_support_link)
    await callback.answer()


# ============================================
# 🎫 TICKETS
# ============================================
@router.callback_query(F.data == "adm_sup:tickets")
async def cb_support_tickets(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    stmt = (
        select(Ticket)
        .where(Ticket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS]))
        .order_by(Ticket.opened_at.desc())
        .limit(20)
    )
    result = await session.execute(stmt)
    tickets = list(result.scalars().all())

    if not tickets:
        text = (
            "🎫 <b>TICKETS ABERTOS</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "✅ Nenhum ticket aberto no momento."
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_sup:menu")]
            ]
        )
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except Exception:
            await callback.message.answer(text, reply_markup=keyboard)
        await callback.answer()
        return

    lines = [
        "🎫 <b>TICKETS ABERTOS</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    rows: list[list[InlineKeyboardButton]] = []

    for t in tickets:
        date = t.opened_at.strftime("%d/%m %H:%M") if t.opened_at else "?"
        status_emoji = {
            TicketStatus.OPEN: "🟢",
            TicketStatus.IN_PROGRESS: "🔵",
            TicketStatus.WAITING_USER: "⏸",
        }.get(t.status, "❓")

        lines.append(
            f"{status_emoji} <code>#{t.id}</code> — "
            f"👤 {t.user_telegram_id} — {date}"
        )
        if t.subject:
            lines.append(f"   📝 {t.subject[:60]}")

        rows.append([
            InlineKeyboardButton(
                text=f"{status_emoji} #{t.id} — {t.user_telegram_id}",
                callback_data=f"adm_sup:view_ticket:{t.id}",
            )
        ])

    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_sup:menu")
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
# 👁️ VER TICKET
# ============================================
@router.callback_query(F.data.startswith("adm_sup:view_ticket:"))
async def cb_support_view_ticket(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    ticket_id = int(callback.data.split(":")[2])
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        await callback.answer("❌ Ticket não encontrado.", show_alert=True)
        return

    user = await session.scalar(
        select(User).where(User.telegram_id == ticket.user_telegram_id)
    )

    user_name = user.first_name if user else "?"
    username = f"@{user.username}" if user and user.username else "—"
    date = ticket.opened_at.strftime("%d/%m/%Y %H:%M") if ticket.opened_at else "?"

    # Últimas mensagens
    messages = ticket.messages or []
    last_msgs = messages[-10:] if len(messages) > 10 else messages

    lines = [
        f"🎫 <b>TICKET #{ticket.id}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"👤 Usuário: <b>{user_name}</b>",
        f"📛 Username: {username}",
        f"🆔 ID: <code>{ticket.user_telegram_id}</code>",
        f"📅 Aberto em: {date}",
        f"📊 Status: <b>{ticket.status.value}</b>",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "<b>Últimas mensagens:</b>",
        "",
    ]

    if not last_msgs:
        lines.append("<i>Sem mensagens ainda.</i>")
    else:
        for msg in last_msgs:
            role = msg.get("role", "user")
            text = msg.get("text", "")[:200]
            prefix = "👤" if role == "user" else "🤖"
            lines.append(f"{prefix} {text}")

    rows: list[list[InlineKeyboardButton]] = []

    if ticket.status != TicketStatus.CLOSED:
        rows.append([
            InlineKeyboardButton(
                text="💬 Responder",
                callback_data=f"adm_sup:reply:{ticket.id}",
            )
        ])
        rows.append([
            InlineKeyboardButton(
                text="🙋 Assumir (humano)",
                callback_data=f"adm_sup:take:{ticket.id}",
            )
        ])
        rows.append([
            InlineKeyboardButton(
                text="🔒 Fechar ticket",
                callback_data=f"adm_sup:close:{ticket.id}",
            )
        ])

    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_sup:tickets")
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
# 💬 RESPONDER TICKET
# ============================================
@router.callback_query(F.data.startswith("adm_sup:reply:"))
async def cb_support_reply(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    ticket_id = int(callback.data.split(":")[2])
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        await callback.answer("❌ Ticket não encontrado.", show_alert=True)
        return

    await state.update_data(ticket_id=ticket_id)
    await callback.message.answer(
        f"💬 <b>RESPONDER TICKET #{ticket_id}</b>\n\n"
        f"Envie a mensagem que deseja enviar ao usuário:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="❌ Cancelar",
                    callback_data=f"adm_sup:view_ticket:{ticket_id}",
                )]
            ]
        ),
    )
    await state.set_state(AdminStates.waiting_message)
    await callback.answer()


@router.message(AdminStates.waiting_message)
async def msg_support_reply(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        await message.answer("❌ Ticket não encontrado.")
        await state.clear()
        return

    reply_text = message.text or message.caption or ""
    if not reply_text.strip():
        await message.answer("❌ Texto vazio.")
        return

    # Adiciona na lista de mensagens
    messages = list(ticket.messages or [])
    messages.append({
        "role": "admin",
        "text": reply_text,
        "admin_id": message.from_user.id,
        "at": datetime.now(timezone.utc).isoformat(),
    })
    ticket.messages = messages
    ticket.status = TicketStatus.WAITING_USER
    session.add(ticket)

    # Envia ao usuário
    try:
        await message.bot.send_message(
            chat_id=ticket.user_telegram_id,
            text=(
                f"💬 <b>Atendimento:</b>\n\n"
                f"{reply_text}"
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"⚠️ Não foi possível enviar pro usuário: {e}")

    await message.answer(
        f"✅ Mensagem enviada ao ticket #{ticket_id}.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="🔙 Ver ticket",
                    callback_data=f"adm_sup:view_ticket:{ticket_id}",
                )]
            ]
        ),
    )
    await state.clear()


# ============================================
# 🙋 ASSUMIR COMO HUMANO (handoff)
# ============================================
@router.callback_query(F.data.startswith("adm_sup:take:"))
async def cb_support_take(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    ticket_id = int(callback.data.split(":")[2])
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        await callback.answer("❌ Ticket não encontrado.", show_alert=True)
        return

    ticket.status = TicketStatus.IN_PROGRESS
    ticket.assigned_admin_id = callback.from_user.id
    session.add(ticket)

    await _log_audit(
        session,
        callback.from_user.id,
        "support_takeover",
        new_value={"ticket_id": ticket_id},
    )

    # Avisa o usuário
    try:
        await callback.bot.send_message(
            chat_id=ticket.user_telegram_id,
            text=(
                "🙋 <b>Um atendente humano assumiu seu atendimento.</b>\n\n"
                "Pode enviar sua mensagem normalmente."
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass

    await callback.answer("✅ Você assumiu este ticket!", show_alert=True)

    callback.data = f"adm_sup:view_ticket:{ticket_id}"
    await cb_support_view_ticket(callback, session)


# ============================================
# 🔒 FECHAR TICKET
# ============================================
@router.callback_query(F.data.startswith("adm_sup:close:"))
async def cb_support_close(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    ticket_id = int(callback.data.split(":")[2])
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        await callback.answer("❌ Ticket não encontrado.", show_alert=True)
        return

    ticket.status = TicketStatus.CLOSED
    ticket.closed_at = datetime.now(timezone.utc)
    session.add(ticket)

    await _log_audit(
        session,
        callback.from_user.id,
        "support_close",
        new_value={"ticket_id": ticket_id},
    )

    # Avisa o usuário
    try:
        await callback.bot.send_message(
            chat_id=ticket.user_telegram_id,
            text=(
                "✅ <b>Seu atendimento foi encerrado.</b>\n\n"
                "Se precisar de ajuda novamente, use /atendimento."
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass

    await callback.answer("🔒 Ticket fechado.", show_alert=True)

    callback.data = "adm_sup:tickets"
    await cb_support_tickets(callback, session)


# ============================================
# 🧠 INSTRUÇÕES DA IA
# ============================================
@router.callback_query(F.data == "adm_sup:ai_prompt")
async def cb_support_ai_prompt(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    current = await config_service.get_str(
        session,
        "ai_system_prompt",
        "Você é a assistente virtual da Larizinha Store. Atenda com educação e clareza. "
        "Responda dúvidas sobre produtos, pagamento, entrega e garantia. "
        "Se o cliente pedir humano, diga que vai chamar um atendente.",
    )

    await callback.message.answer(
        "🧠 <b>INSTRUÇÕES DA IA</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Atual:</b>\n<pre>{current[:700]}</pre>\n\n"
        "Envie as novas instruções (personalidade da IA).",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_support_message)
    await callback.answer()


@router.message(AdminStates.editing_support_message)
async def msg_support_ai_prompt(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    new_prompt = message.text or message.caption or ""
    if not new_prompt.strip():
        await message.answer("❌ Texto vazio.")
        return

    old = await config_service.get_str(session, "ai_system_prompt", "")
    await config_service.set_config(session, "ai_system_prompt", new_prompt)

    await _log_audit(
        session,
        message.from_user.id,
        "edit_ai_prompt",
        old_value={"prompt_preview": old[:80]},
        new_value={"prompt_preview": new_prompt[:80]},
    )

    await message.answer("✅ Instruções da IA atualizadas!")
    await state.clear()

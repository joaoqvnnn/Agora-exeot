# ============================================
# 🎧 ATENDIMENTO (CLIENTE) — Larizinha Store
# ============================================
# Atendimento com IA + handoff para humano.
# Cria ticket, envia mensagem pro suporte configurado,
# IA responde automaticamente até o humano assumir.
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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.states import SupportStates
from core.models import Ticket, TicketStatus, User
from core.services import ai as ai_service
from core.services import config as config_service


router = Router(name="atendimento")


# ============================================
# 🧰 AUXILIARES
# ============================================
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
            logger.warning(f"⚠️ Falha ao editar/enviar: {e}")


async def _get_active_ticket(
    session: AsyncSession,
    user_telegram_id: int,
) -> Ticket | None:
    """Retorna ticket em aberto do usuário, se existir."""
    stmt = (
        select(Ticket)
        .where(
            Ticket.user_telegram_id == user_telegram_id,
            Ticket.status.in_([
                TicketStatus.OPEN,
                TicketStatus.IN_PROGRESS,
                TicketStatus.WAITING_USER,
            ]),
        )
        .order_by(Ticket.opened_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _get_or_create_ticket(
    session: AsyncSession,
    user: User,
) -> Ticket:
    """Retorna ticket ativo ou cria novo."""
    existing = await _get_active_ticket(session, user.telegram_id)
    if existing is not None:
        return existing

    ticket = Ticket(
        user_telegram_id=user.telegram_id,
        subject="Atendimento via bot",
        status=TicketStatus.OPEN,
        messages=[],
    )
    session.add(ticket)
    await session.flush()
    return ticket


async def _append_to_ticket(
    session: AsyncSession,
    ticket: Ticket,
    role: str,
    text: str,
    extra: dict | None = None,
) -> None:
    """Adiciona mensagem ao histórico do ticket."""
    messages = list(ticket.messages or [])
    entry = {
        "role": role,
        "text": text,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        entry.update(extra)
    messages.append(entry)
    ticket.messages = messages
    session.add(ticket)


# ============================================
# 🎧 BOTÃO "ATENDIMENTO" DO /start
# ============================================
@router.callback_query(F.data == "menu:atendimento")
async def cb_support_menu(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    """Menu de atendimento."""
    ai_enabled = await config_service.get_bool(session, "ai_enabled", True)
    support_link = await config_service.get_str(session, "support_link", "")

    text = (
        f"🎧 <b>Atendimento</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Escolha como deseja ser atendido:\n\n"
    )

    if ai_enabled:
        text += (
            f"🤖 <b>Assistente virtual</b> — respostas rápidas sobre "
            f"produtos, pagamento e entrega\n\n"
        )

    text += (
        f"👤 <b>Atendente humano</b> — para casos específicos\n\n"
    )

    if support_link:
        text += f"🔗 <b>Suporte direto:</b>\n<code>{support_link}</code>"

    rows: list[list[InlineKeyboardButton]] = []

    if ai_enabled:
        rows.append([
            InlineKeyboardButton(
                text="🤖 Conversar com a IA",
                callback_data="sup:ai_start",
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="👤 Falar com atendente",
            callback_data="sup:humano",
        )
    ])

    if support_link and support_link.startswith(("http", "tg://")):
        rows.append([
            InlineKeyboardButton(
                text="🔗 Abrir suporte externo",
                url=support_link,
            )
        ])

    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="menu:voltar")
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()

    user.last_menu = "atendimento"
    session.add(user)


# ============================================
# 🤖 INICIAR ATENDIMENTO COM IA
# ============================================
@router.callback_query(F.data == "sup:ai_start")
async def cb_ai_start(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """Inicia conversa com a IA."""
    ai_enabled = await config_service.get_bool(session, "ai_enabled", True)

    if not ai_enabled:
        await callback.answer(
            "⚠️ A IA está temporariamente indisponível.",
            show_alert=True,
        )
        return

    ticket = await _get_or_create_ticket(session, user)

    text = (
        f"🤖 <b>Assistente Virtual</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Olá, {user.first_name or 'cliente'}! 👋\n\n"
        f"Estou aqui para te ajudar com dúvidas sobre:\n"
        f"• Produtos e preços\n"
        f"• Pagamento e entrega\n"
        f"• Garantia e suporte\n\n"
        f"💡 Digite sua pergunta ou escreva <b>humano</b> "
        f"para falar com um atendente.\n\n"
        f"<i>Digite /cancelar para sair.</i>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👤 Falar com humano", callback_data="sup:humano")],
            [InlineKeyboardButton(text="❌ Encerrar", callback_data="sup:close")],
        ]
    )

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()

    await state.set_state(SupportStates.in_chat)
    await state.update_data(ticket_id=ticket.id)


# ============================================
# 💬 RECEBER MENSAGEM DO CLIENTE (IA responde)
# ============================================
@router.message(SupportStates.in_chat)
async def msg_ai_chat(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """Cliente envia mensagem → IA responde."""
    raw = (message.text or "").strip()

    if not raw:
        return

    if raw.startswith("/cancelar") or raw.startswith("/start"):
        await state.clear()
        await message.answer("✅ Atendimento encerrado. Use /start para voltar ao menu.")
        return

    data = await state.get_data()
    ticket_id = data.get("ticket_id")

    ticket = None
    if ticket_id:
        ticket = await session.get(Ticket, ticket_id)

    if ticket is None:
        ticket = await _get_or_create_ticket(session, user)
        await state.update_data(ticket_id=ticket.id)

    # Se humano assumiu, encaminha mensagem pro humano
    if ticket.status == TicketStatus.IN_PROGRESS and ticket.assigned_admin_id:
        await _append_to_ticket(session, ticket, "user", raw)

        # Notifica o admin
        try:
            await message.bot.send_message(
                chat_id=ticket.assigned_admin_id,
                text=(
                    f"💬 <b>Nova mensagem do cliente</b>\n\n"
                    f"👤 {user.first_name or 'Cliente'}\n"
                    f"🆔 <code>{user.telegram_id}</code>\n"
                    f"🎫 Ticket #{ticket.id}\n\n"
                    f"<b>Mensagem:</b>\n{raw}"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"⚠️ Falha ao notificar admin: {e}")

        await message.answer("✅ Mensagem enviada para o atendente.")
        return

    # IA responde
    await _append_to_ticket(session, ticket, "user", raw)

    await message.bot.send_chat_action(
        chat_id=message.chat.id, action="typing"
    )

    # Chama IA
    history = []
    for msg in (ticket.messages or [])[-10:]:
        role = msg.get("role", "user")
        if role in ("user", "assistant"):
            history.append({
                "role": role,
                "content": msg.get("text", ""),
            })

    response = await ai_service.get_response(
        session=session,
        user_message=raw,
        user_id=user.telegram_id,
        user_name=user.first_name or "Cliente",
        balance=f"{user.balance or 0:.2f}".replace(".", ","),
        history=history,
    )

    await _append_to_ticket(session, ticket, "assistant", response)

    # Detecta se IA quer chamar humano
    if "atendente humano" in response.lower() or "chamar um atendente" in response.lower():
        ticket.status = TicketStatus.OPEN
        session.add(ticket)

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="👤 Falar com humano agora", callback_data="sup:humano")],
                [InlineKeyboardButton(text="❌ Encerrar", callback_data="sup:close")],
            ]
        )
        await message.answer(response, reply_markup=keyboard)
    else:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="👤 Falar com humano", callback_data="sup:humano")],
                [InlineKeyboardButton(text="❌ Encerrar", callback_data="sup:close")],
            ]
        )
        await message.answer(response, reply_markup=keyboard)


# ============================================
# 👤 FALAR COM HUMANO (handoff)
# ============================================
@router.callback_query(F.data == "sup:humano")
async def cb_human_handoff(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """Cliente quer atendente humano."""
    ticket = await _get_or_create_ticket(session, user)

    # Atualiza ticket
    ticket.status = TicketStatus.OPEN
    await _append_to_ticket(
        session, ticket, "user",
        "Cliente solicitou atendimento humano.",
    )

    # Busca o dono pra notificar
    from core.models import Admin

    stmt = select(Admin).where(
        Admin.is_active.is_(True),
        Admin.is_owner.is_(True),
    )
    result = await session.execute(stmt)
    owners = list(result.scalars().all())

    # Notifica todos os donos
    notification_text = (
        f"🚨 <b>Cliente pediu atendimento humano</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 {user.first_name or 'Cliente'}\n"
        f"📛 @{user.username}" if user.username else ""
    )
    notification_text = (
        f"🚨 <b>Cliente pediu atendimento humano</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>{user.first_name or 'Cliente'}</b>\n"
        f"📛 {('@' + user.username) if user.username else '—'}\n"
        f"🆔 <code>{user.telegram_id}</code>\n"
        f"💰 Saldo: R$ {float(user.balance or 0):.2f}\n\n"
        f"🎫 Ticket: <code>#{ticket.id}</code>"
    )

    for owner in owners:
        try:
            await callback.bot.send_message(
                chat_id=owner.telegram_id,
                text=notification_text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(
                            text="🙋 Assumir atendimento",
                            callback_data=f"adm_sup:take:{ticket.id}",
                        )],
                        [InlineKeyboardButton(
                            text="👁 Ver ticket",
                            callback_data=f"adm_sup:view_ticket:{ticket.id}",
                        )],
                    ]
                ),
            )
        except Exception as e:
            logger.warning(f"⚠️ Falha ao notificar dono {owner.telegram_id}: {e}")

    # Mensagem pro cliente
    support_link = await config_service.get_str(session, "support_link", "")

    text = (
        f"🙋 <b>Atendimento humano solicitado</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎫 Seu ticket: <code>#{ticket.id}</code>\n\n"
        f"Um atendente vai responder assim que possível.\n\n"
        f"💡 <b>Enquanto aguarda, você pode:</b>\n"
        f"• Enviar mais detalhes sobre sua dúvida\n"
        f"• Continuar navegando pelo bot\n\n"
    )

    if support_link:
        text += f"🔗 Se preferir, acesse:\n<code>{support_link}</code>"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Encerrar atendimento", callback_data="sup:close")],
            [InlineKeyboardButton(text="🔙 Voltar ao menu", callback_data="menu:voltar")],
        ]
    )

    await _edit_or_send(callback, text, keyboard)
    await callback.answer("🙋 Atendente solicitado!", show_alert=True)

    # Muda o estado pro chat
    await state.set_state(SupportStates.in_chat)
    await state.update_data(ticket_id=ticket.id)


# ============================================
# ❌ ENCERRAR ATENDIMENTO
# ============================================
@router.callback_query(F.data == "sup:close")
async def cb_close_support(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """Encerra o atendimento atual."""
    data = await state.get_data()
    ticket_id = data.get("ticket_id")

    if ticket_id:
        ticket = await session.get(Ticket, ticket_id)
        if ticket and ticket.status != TicketStatus.CLOSED:
            ticket.status = TicketStatus.CLOSED
            ticket.closed_at = datetime.now(timezone.utc)
            session.add(ticket)

            # Avisa o admin responsável
            if ticket.assigned_admin_id:
                try:
                    await callback.bot.send_message(
                        chat_id=ticket.assigned_admin_id,
                        text=(
                            f"✅ <b>Ticket #{ticket.id} encerrado pelo cliente.</b>"
                        ),
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

    await state.clear()

    from bot.keyboards.main_menu import build_main_menu
    from core.config import settings

    text = "✅ <b>Atendimento encerrado.</b>\n\nUse o menu abaixo para continuar."
    keyboard = await build_main_menu(session, webapp_url=settings.webapp_url)

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()


# ============================================
# 📞 MENU DE ATENDIMENTO (via botão do /start)
# ============================================
@router.callback_query(F.data == "menu:sobre")
async def cb_about(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    """Botão "Sobre o Bot"."""
    from core.services.messages import render_message

    text = await render_message(
        session,
        key="sobre",
        variables={
            "USER_ID": user.telegram_id,
            "USERNAME": user.username or user.first_name or "Usuário",
            "BALANCE": f"{float(user.balance or 0):.2f}".replace(".", ","),
        },
    )

    from bot.keyboards.main_menu import build_main_menu
    from core.config import settings

    keyboard = await build_main_menu(session, webapp_url=settings.webapp_url)

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()

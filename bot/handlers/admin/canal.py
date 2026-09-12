# ============================================
# 📢 ADMIN CANAL — Larizinha Store
# ============================================
# Configuração REAL do canal obrigatório.
# Todos os botões funcionam de verdade.
#
# Cobre:
#   - LIGAR/DESLIGAR canal obrigatório
#   - DEFINIR ID do canal
#   - DEFINIR link do canal
#   - EDITAR mensagem de exigência
#   - EDITAR texto do botão
#   - TESTAR verificação
# ============================================

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

from bot.states.states import AdminStates
from core.models import Admin, AuditLog
from core.services import config as config_service


router = Router(name="admin_canal")


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
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_canal:menu")]
        ]
    )


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_canal:menu")
async def cb_canal_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    enabled = await config_service.get_bool(session, "required_channel_enabled", False)
    channel_id = await config_service.get_str(session, "required_channel_id", "")
    channel_link = await config_service.get_str(session, "required_channel_link", "")

    status = "🟢 LIGADO" if enabled else "🔴 DESLIGADO"

    text = (
        "📢 <b>CANAL OBRIGATÓRIO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚙️ Status: <b>{status}</b>\n"
        f"🆔 ID do canal: <code>{channel_id or '—'}</code>\n"
        f"🔗 Link: <code>{channel_link or '—'}</code>\n\n"
        "Quando ligado, o usuário precisa entrar no canal "
        "para usar o bot.\n"
        "A verificação é <b>real</b> (o bot consulta se o usuário "
        "é membro).\n\n"
        "Use os botões abaixo para configurar:"
    )

    toggle_text = "🔴 DESLIGAR" if enabled else "🟢 LIGAR"
    toggle_cb = "adm_canal:off" if enabled else "adm_canal:on"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle_text, callback_data=toggle_cb)],
            [InlineKeyboardButton(text="🆔 Definir ID do Canal", callback_data="adm_canal:set_id")],
            [InlineKeyboardButton(text="🔗 Definir Link do Canal", callback_data="adm_canal:set_link")],
            [InlineKeyboardButton(text="📝 Editar Mensagem", callback_data="adm_canal:set_message")],
            [InlineKeyboardButton(text="🔘 Editar Texto do Botão", callback_data="adm_canal:set_button")],
            [InlineKeyboardButton(text="🧪 Testar Verificação", callback_data="adm_canal:test")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:config")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 🟢 / 🔴 TOGGLE
# ============================================
@router.callback_query(F.data == "adm_canal:on")
async def cb_canal_on(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    channel_id = await config_service.get_str(session, "required_channel_id", "")
    if not channel_id:
        await callback.answer(
            "⚠️ Configure primeiro o ID do canal!",
            show_alert=True,
        )
        return

    await config_service.set_config(session, "required_channel_enabled", "true")
    await _log_audit(session, callback.from_user.id, "canal_required_on")
    await callback.answer("🟢 Canal obrigatório ativado!", show_alert=True)
    await cb_canal_menu(callback, session)


@router.callback_query(F.data == "adm_canal:off")
async def cb_canal_off(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await config_service.set_config(session, "required_channel_enabled", "false")
    await _log_audit(session, callback.from_user.id, "canal_required_off")
    await callback.answer("🔴 Canal obrigatório desativado!", show_alert=True)
    await cb_canal_menu(callback, session)


# ============================================
# 🆔 DEFINIR ID DO CANAL
# ============================================
@router.callback_query(F.data == "adm_canal:set_id")
async def cb_canal_set_id(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    current = await config_service.get_str(session, "required_channel_id", "Não definido")

    await callback.message.answer(
        "🆔 <b>DEFINIR ID DO CANAL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Atual:</b> <code>{current}</code>\n\n"
        "Envie o <b>ID do canal</b> (deve começar com -100).\n\n"
        "Exemplo: <code>-1001234567890</code>\n\n"
        "💡 Pra descobrir:\n"
        "1. Adicione o bot como admin do canal\n"
        "2. Encaminhe uma mensagem do canal para @userinfobot\n"
        "3. Ele mostra o ID (formato -100...)",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_required_channel)
    await callback.answer()


@router.message(AdminStates.editing_required_channel)
async def msg_canal_save_id(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    raw = (message.text or "").strip()

    try:
        channel_id = int(raw)
        if not raw.startswith("-100"):
            await message.answer(
                "❌ ID de canal deve começar com <code>-100</code>.\n\n"
                "Se for grupo, começa com <code>-</code>."
            )
            return
    except ValueError:
        await message.answer("❌ ID inválido. Deve ser um número.")
        return

    # Testa se o bot consegue acessar
    try:
        chat = await message.bot.get_chat(chat_id=channel_id)
        chat_title = chat.title or "Sem título"
    except Exception as e:
        await message.answer(
            f"❌ Não consegui acessar esse canal.\n\n"
            f"<b>Erro:</b> <code>{str(e)[:200]}</code>\n\n"
            f"Verifique se o bot é <b>administrador</b> do canal."
        )
        return

    old = await config_service.get_str(session, "required_channel_id", "")
    await config_service.set_config(session, "required_channel_id", str(channel_id))

    await _log_audit(
        session,
        message.from_user.id,
        "edit_canal_id",
        old_value={"id": old},
        new_value={"id": str(channel_id)},
    )

    await message.answer(
        f"✅ <b>ID definido!</b>\n\n"
        f"📢 Canal: <b>{chat_title}</b>\n"
        f"🆔 ID: <code>{channel_id}</code>"
    )
    await state.clear()


# ============================================
# 🔗 DEFINIR LINK DO CANAL
# ============================================
@router.callback_query(F.data == "adm_canal:set_link")
async def cb_canal_set_link(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    current = await config_service.get_str(session, "required_channel_link", "Não definido")

    await callback.message.answer(
        "🔗 <b>DEFINIR LINK DO CANAL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Atual:</b>\n<code>{current}</code>\n\n"
        "Envie o link do canal.\n\n"
        "Exemplo: <code>https://t.me/seucanal</code>",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_required_channel_message)
    await callback.answer()


@router.message(AdminStates.editing_required_channel_message)
async def msg_canal_save_link(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    raw = (message.text or "").strip()

    if not raw.startswith(("https://t.me/", "http://t.me/", "tg://")):
        await message.answer(
            "❌ Link inválido. Use <code>https://t.me/seucanal</code>"
        )
        return

    old = await config_service.get_str(session, "required_channel_link", "")
    await config_service.set_config(session, "required_channel_link", raw)

    await _log_audit(
        session,
        message.from_user.id,
        "edit_canal_link",
        old_value={"link": old},
        new_value={"link": raw},
    )

    await message.answer(f"✅ Link definido: <code>{raw}</code>")
    await state.clear()


# ============================================
# 📝 EDITAR MENSAGEM
# ============================================
@router.callback_query(F.data == "adm_canal:set_message")
async def cb_canal_set_message(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "📝 <b>EDITAR MENSAGEM DO CANAL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "A mensagem é editável no <b>Editor de Mensagens</b>.\n\n"
        "Chave: <code>canal_obrigatorio</code>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="✏️ Editar agora",
                    callback_data="adm_msg:view:canal_obrigatorio:0",
                )],
                [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_canal:menu")],
            ]
        ),
    )
    await callback.answer()


# ============================================
# 🔘 EDITAR TEXTO DO BOTÃO
# ============================================
@router.callback_query(F.data == "adm_canal:set_button")
async def cb_canal_set_button(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "🔘 <b>EDITAR TEXTO DO BOTÃO</b>\n\n"
        "O texto do botão é editável no <b>Editor de Mensagens</b>.\n\n"
        "Chave: <code>canal_botao</code>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="✏️ Editar agora",
                    callback_data="adm_msg:view:canal_botao:0",
                )],
                [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_canal:menu")],
            ]
        ),
    )
    await callback.answer()


# ============================================
# 🧪 TESTAR VERIFICAÇÃO
# ============================================
@router.callback_query(F.data == "adm_canal:test")
async def cb_canal_test(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.answer("🧪 Testando...", show_alert=False)

    channel_id_raw = await config_service.get_str(session, "required_channel_id", "")
    if not channel_id_raw:
        await callback.message.answer(
            "❌ Nenhum canal configurado.\n\n"
            "Defina o ID do canal primeiro.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🆔 Definir ID", callback_data="adm_canal:set_id")],
                    [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_canal:menu")],
                ]
            ),
        )
        return

    try:
        channel_id = int(channel_id_raw)
    except ValueError:
        await callback.message.answer("❌ ID do canal inválido.")
        return

    # Testa acesso
    try:
        chat = await callback.bot.get_chat(chat_id=channel_id)
    except Exception as e:
        await callback.message.answer(
            f"❌ <b>Erro ao acessar o canal</b>\n\n"
            f"<code>{str(e)[:200]}</code>\n\n"
            f"Verifique se o bot é admin.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_canal:menu")]
                ]
            ),
        )
        return

    # Testa se o admin é membro
    try:
        member = await callback.bot.get_chat_member(
            chat_id=channel_id,
            user_id=callback.from_user.id,
        )
        status = member.status
        is_member = status in ("creator", "administrator", "member", "restricted")
    except Exception as e:
        await callback.message.answer(
            f"⚠️ Não consegui verificar se você é membro.\n\n"
            f"<code>{str(e)[:200]}</code>"
        )
        return

    member_emoji = "✅" if is_member else "❌"

    text = (
        "🧪 <b>TESTE DE VERIFICAÇÃO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ <b>Canal acessível:</b>\n"
        f"📢 {chat.title}\n"
        f"🆔 <code>{channel_id}</code>\n\n"
        f"{member_emoji} <b>Você é membro?</b> <b>{'Sim' if is_member else 'Não'}</b>\n\n"
        f"🔍 Status: <code>{status}</code>\n\n"
        "💡 Se o bot não enxerga membros corretamente, "
        "verifique se ele é <b>administrador</b> no canal."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Testar de novo", callback_data="adm_canal:test")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_canal:menu")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

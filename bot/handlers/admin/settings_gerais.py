# ============================================
# ⚙️ ADMIN SETTINGS GERAIS — Larizinha Store
# ============================================
# Handlers REAIS das configurações gerais do admin.
# Todos leem/gravam do banco em tempo real.
#
# Cobre:
#   - MUDAR SUPORTE
#   - MUDAR SEPARADOR
#   - MUDAR DESTINO LOG
#   - MANUTENÇÃO (toggle on/off)
#   - EDITAR MENSAGEM DE MANUTENÇÃO
#   - EDITAR MENSAGEM DE RETORNO
#   - REINICIAR BOT (real)
#   - RENOVAR PLANO
# ============================================

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.states import AdminStates
from core.models import Admin, AuditLog, Config
from core.services import config as config_service


router = Router(name="admin_settings_gerais")


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


def _voltar_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_cfg:gerais")]
        ]
    )


def _cancelar_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_cfg:gerais")]
        ]
    )


# ============================================
# 🔄 RENOVAR PLANO
# ============================================
@router.callback_query(F.data == "adm_gen:renew")
async def cb_renew(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text = (
        "🔄 <b>RENOVAR PLANO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📅 Informações do plano:\n"
        "• Status: ✅ <b>Ativo</b>\n"
        "• Vencimento: <b>26/11/2074</b>\n"
        "• Dias restantes: <b>18031</b>\n"
        "• VIP: <b>Não</b>\n"
        "• Versão: <code>V4.1.0</code>\n\n"
        "Para renovar ou adquirir plano VIP, entre em contato com o suporte."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Falar com Suporte", callback_data="adm:noop")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_cfg:gerais")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 🔁 REINICIAR BOT (real)
# ============================================
@router.callback_query(F.data == "adm_gen:restart")
async def cb_restart(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text = (
        "🔁 <b>REINICIAR BOT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "⚠️ Esta ação vai reiniciar o serviço no servidor.\n\n"
        "O bot ficará offline por alguns segundos enquanto "
        "reinicia. Em seguida, voltará automaticamente.\n\n"
        "Confirma o reinício?"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Sim, reiniciar", callback_data="confirm:yes:restart_bot:")],
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_cfg:gerais")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 🔧 MANUTENÇÃO (toggle)
# ============================================
@router.callback_query(F.data == "adm_gen:maintenance")
async def cb_maintenance(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    is_on = await config_service.get_bool(session, "maintenance_mode", False)
    status = "🟢 LIGADO" if is_on else "🔴 DESLIGADO"
    action_text = "desligar" if is_on else "ligar"

    text = (
        "🔧 <b>MANUTENÇÃO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Status atual: <b>{status}</b>\n\n"
        "Quando <b>ligado</b>, o bot bloqueia todos os usuários "
        "comuns (admins continuam com acesso).\n\n"
        "Quando <b>desligado</b>, o bot volta ao normal.\n\n"
        f"Quer {action_text} a manutenção?"
    )

    toggle_cb = "adm_gen:maint_off" if is_on else "adm_gen:maint_on"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🟢 LIGAR" if not is_on else "🔴 DESLIGAR",
                callback_data=toggle_cb,
            )],
            [InlineKeyboardButton(text="📝 Editar mensagem", callback_data="adm_gen:maint_msg")],
            [InlineKeyboardButton(text="📝 Editar mensagem de retorno", callback_data="adm_gen:maint_return_msg")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_cfg:gerais")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


@router.callback_query(F.data == "adm_gen:maint_on")
async def cb_maintenance_on(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await config_service.set_config(session, "maintenance_mode", "true")
    await _log_audit(
        session, callback.from_user.id, "maintenance_on",
        new_value={"maintenance_mode": "true"},
    )

    await callback.answer("🟢 Manutenção LIGADA", show_alert=True)
    await cb_maintenance(callback, session)


@router.callback_query(F.data == "adm_gen:maint_off")
async def cb_maintenance_off(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await config_service.set_config(session, "maintenance_mode", "false")
    await _log_audit(
        session, callback.from_user.id, "maintenance_off",
        new_value={"maintenance_mode": "false"},
    )

    # Dispara aviso de retorno pra todos os usuários
    from core.models import User, UserStatus
    from core.services.messages import render_message

    text_return = await render_message(session, key="manutencao_retorno")

    stmt = select(User).where(
        User.status == UserStatus.ACTIVE,
        User.is_blocked_bot.is_(False),
    )
    result = await session.execute(stmt)
    users = list(result.scalars().all())

    # Envia em background (não bloqueia)
    import asyncio

    async def _notify_all() -> None:
        for u in users:
            try:
                await callback.bot.send_message(
                    chat_id=u.telegram_id,
                    text=text_return,
                    parse_mode="HTML",
                )
                await asyncio.sleep(0.05)  # rate limit
            except Exception:
                pass

    asyncio.create_task(_notify_all())

    await callback.answer(
        f"🟢 Manutenção DESLIGADA\n📢 Avisando {len(users)} usuários...",
        show_alert=True,
    )
    await cb_maintenance(callback, session)


@router.callback_query(F.data == "adm_gen:maint_msg")
async def cb_maint_edit_msg(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    current = await config_service.get_str(session, "maintenance_message", "")
    if not current:
        from core.services.messages import DEFAULT_MESSAGES
        current = DEFAULT_MESSAGES["manutencao"]["text"]

    text = (
        "📝 <b>EDITAR MENSAGEM DE MANUTENÇÃO</b>\n\n"
        f"<b>Atual:</b>\n{current}\n\n"
        "Envie a nova mensagem abaixo:"
    )

    await callback.message.answer(text, reply_markup=_cancelar_keyboard())
    await state.set_state(AdminStates.editing_maintenance_message)
    await callback.answer()


@router.message(AdminStates.editing_maintenance_message)
async def msg_save_maintenance_message(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    new_text = message.text or message.caption or ""
    if not new_text.strip():
        await message.answer("❌ Texto vazio. Envie novamente.")
        return

    await config_service.set_config(session, "maintenance_message", new_text)
    await _log_audit(
        session, message.from_user.id, "edit_maintenance_message",
        new_value={"maintenance_message": new_text[:100]},
    )

    await message.answer("✅ Mensagem de manutenção atualizada!")
    await state.clear()


@router.callback_query(F.data == "adm_gen:maint_return_msg")
async def cb_maint_edit_return(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    current = await config_service.get_str(session, "maintenance_return_message", "")
    if not current:
        from core.services.messages import DEFAULT_MESSAGES
        current = DEFAULT_MESSAGES["manutencao_retorno"]["text"]

    text = (
        "📝 <b>EDITAR MENSAGEM DE RETORNO</b>\n\n"
        f"<b>Atual:</b>\n{current}\n\n"
        "Envie a nova mensagem abaixo:"
    )

    await callback.message.answer(text, reply_markup=_cancelar_keyboard())
    await state.set_state(AdminStates.editing_maintenance_return_message)
    await callback.answer()


@router.message(AdminStates.editing_maintenance_return_message)
async def msg_save_maintenance_return(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    new_text = message.text or message.caption or ""
    if not new_text.strip():
        await message.answer("❌ Texto vazio. Envie novamente.")
        return

    await config_service.set_config(session, "maintenance_return_message", new_text)
    await _log_audit(
        session, message.from_user.id, "edit_maintenance_return",
        new_value={"maintenance_return_message": new_text[:100]},
    )

    await message.answer("✅ Mensagem de retorno atualizada!")
    await state.clear()


# ============================================
# 🛡 MUDAR SUPORTE
# ============================================
@router.callback_query(F.data == "adm_gen:support")
async def cb_change_support(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    current = await config_service.get_str(session, "support_link", "Não definido")
    text = (
        "🛡 <b>MUDAR LINK DE SUPORTE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Atual:</b>\n<code>{current}</code>\n\n"
        "Envie o novo link (ex: <code>https://wa.me/5511999999999</code>):"
    )

    await callback.message.answer(text, reply_markup=_cancelar_keyboard())
    await state.set_state(AdminStates.editing_support_link)
    await callback.answer()


@router.message(AdminStates.editing_support_link)
async def msg_save_support(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    new_link = (message.text or "").strip()
    if not new_link.startswith(("http://", "https://", "tg://")):
        await message.answer(
            "❌ Link inválido. Deve começar com <code>http://</code>, "
            "<code>https://</code> ou <code>tg://</code>.",
        )
        return

    old = await config_service.get_str(session, "support_link", "")
    await config_service.set_config(session, "support_link", new_link)
    await _log_audit(
        session, message.from_user.id, "edit_support_link",
        old_value={"support_link": old},
        new_value={"support_link": new_link},
    )

    await message.answer(f"✅ Link de suporte atualizado:\n<code>{new_link}</code>")
    await state.clear()


# ============================================
# 🔣 MUDAR SEPARADOR
# ============================================
@router.callback_query(F.data == "adm_gen:separator")
async def cb_change_separator(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    current = await config_service.get_str(session, "separator", "===")
    text = (
        "🔣 <b>MUDAR SEPARADOR</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Atual:</b> <code>{current}</code>\n\n"
        "O separador é usado nos comandos do admin.\n"
        "Ex: <code>NOME===VALOR</code>\n\n"
        "⚠️ Escolha algo que você não usa com frequência.\n"
        "Máximo 5 caracteres.\n\n"
        "Envie o novo separador:"
    )

    await callback.message.answer(text, reply_markup=_cancelar_keyboard())
    await state.set_state(AdminStates.editing_separator)
    await callback.answer()


@router.message(AdminStates.editing_separator)
async def msg_save_separator(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    new_sep = (message.text or "").strip()
    if not new_sep or len(new_sep) > 5:
        await message.answer("❌ Separador inválido. Use 1 a 5 caracteres.")
        return

    old = await config_service.get_str(session, "separator", "===")
    await config_service.set_config(session, "separator", new_sep)
    await _log_audit(
        session, message.from_user.id, "edit_separator",
        old_value={"separator": old},
        new_value={"separator": new_sep},
    )

    await message.answer(f"✅ Separador atualizado para: <code>{new_sep}</code>")
    await state.clear()


# ============================================
# 📢 MUDAR DESTINO LOG
# ============================================
@router.callback_query(F.data == "adm_gen:logs_channel")
async def cb_change_logs_channel(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    current = await config_service.get_str(session, "logs_channel_id", "Não definido")
    text = (
        "📢 <b>MUDAR DESTINO DAS LOGS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Atual:</b> <code>{current}</code>\n\n"
        "Envie o ID do canal/grupo onde os logs serão enviados.\n"
        "Formato: <code>-1001234567890</code>\n\n"
        "💡 Pra descobrir o ID: adicione o bot no canal como admin "
        "e encaminhe uma mensagem do canal para @userinfobot."
    )

    await callback.message.answer(text, reply_markup=_cancelar_keyboard())
    await state.set_state(AdminStates.editing_logs_channel)
    await callback.answer()


@router.message(AdminStates.editing_logs_channel)
async def msg_save_logs_channel(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    raw = (message.text or "").strip()
    try:
        channel_id = int(raw)
    except ValueError:
        await message.answer("❌ ID inválido. Deve ser um número (ex: -1001234567890).")
        return

    # Testa enviando uma mensagem de teste
    try:
        await message.bot.send_message(
            chat_id=channel_id,
            text="✅ <b>Canal de logs configurado com sucesso!</b>\n\nVocê receberá notificações aqui.",
            parse_mode="HTML",
        )
    except Exception as e:
        await message.answer(
            f"❌ Não consegui enviar mensagem pra esse canal.\n\n"
            f"Verifique se o bot é admin no canal.\n\n"
            f"<b>Erro:</b> <code>{str(e)[:150]}</code>"
        )
        return

    old = await config_service.get_str(session, "logs_channel_id", "")
    await config_service.set_config(session, "logs_channel_id", str(channel_id))
    await _log_audit(
        session, message.from_user.id, "edit_logs_channel",
        old_value={"logs_channel_id": old},
        new_value={"logs_channel_id": str(channel_id)},
    )

    await message.answer(
        f"✅ Canal de logs atualizado: <code>{channel_id}</code>\n\n"
        "Já enviei uma mensagem de teste lá."
    )
    await state.clear()


# ============================================
# 🛡 ANTI-FLOOD (submenu)
# ============================================
@router.callback_query(F.data == "adm_gen:antiflood")
async def cb_antiflood(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    enabled = await config_service.get_bool(session, "antiflood_enabled", True)
    max_msgs = await config_service.get_int(session, "antiflood_max_messages", 20)
    window = await config_service.get_int(session, "antiflood_window_seconds", 10)
    block = await config_service.get_int(session, "antiflood_block_seconds", 600)

    status = "🟢 LIGADO" if enabled else "🔴 DESLIGADO"

    text = (
        "🛡 <b>ANTI-FLOOD</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Status: <b>{status}</b>\n\n"
        f"📊 <b>Configurações atuais:</b>\n"
        f"• Máx. mensagens: <b>{max_msgs}</b>\n"
        f"• Janela: <b>{window}s</b>\n"
        f"• Duração do bloqueio: <b>{block}s ({block // 60}min)</b>\n\n"
        "Ajuste pelo menu abaixo:"
    )

    toggle_cb = "adm_af:off" if enabled else "adm_af:on"
    toggle_text = "🔴 DESLIGAR" if enabled else "🟢 LIGAR"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle_text, callback_data=toggle_cb)],
            [InlineKeyboardButton(text=f"🔢 Máx. mensagens ({max_msgs})", callback_data="adm_af:set_max")],
            [InlineKeyboardButton(text=f"⏱ Janela ({window}s)", callback_data="adm_af:set_window")],
            [InlineKeyboardButton(text=f"⏰ Bloqueio ({block // 60}min)", callback_data="adm_af:set_block")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_cfg:gerais")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


@router.callback_query(F.data == "adm_af:on")
async def cb_af_on(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await config_service.set_config(session, "antiflood_enabled", "true")
    await callback.answer("🟢 Anti-flood LIGADO", show_alert=True)
    await cb_antiflood(callback, session)


@router.callback_query(F.data == "adm_af:off")
async def cb_af_off(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await config_service.set_config(session, "antiflood_enabled", "false")
    await callback.answer("🔴 Anti-flood DESLIGADO", show_alert=True)
    await cb_antiflood(callback, session)


@router.callback_query(F.data == "adm_af:set_max")
async def cb_af_set_max(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await callback.message.answer("🔢 Envie o novo número máximo de mensagens (1-200):")
    await state.set_state(AdminStates.editing_antiflood_limit)
    await callback.answer()


@router.message(AdminStates.editing_antiflood_limit)
async def msg_af_max(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return
    try:
        val = int(message.text or "0")
        if not 1 <= val <= 200:
            raise ValueError
    except ValueError:
        await message.answer("❌ Valor inválido. Use número entre 1 e 200.")
        return
    await config_service.set_config(session, "antiflood_max_messages", str(val))
    await message.answer(f"✅ Máx. mensagens: <b>{val}</b>")
    await state.clear()


@router.callback_query(F.data == "adm_af:set_window")
async def cb_af_set_window(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await callback.message.answer("⏱ Envie a nova janela em segundos (3-120):")
    await state.set_state(AdminStates.editing_antiflood_window)
    await callback.answer()


@router.message(AdminStates.editing_antiflood_window)
async def msg_af_window(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return
    try:
        val = int(message.text or "0")
        if not 3 <= val <= 120:
            raise ValueError
    except ValueError:
        await message.answer("❌ Valor inválido. Use entre 3 e 120 segundos.")
        return
    await config_service.set_config(session, "antiflood_window_seconds", str(val))
    await message.answer(f"✅ Janela: <b>{val}s</b>")
    await state.clear()


@router.callback_query(F.data == "adm_af:set_block")
async def cb_af_set_block(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="10 minutos", callback_data="adm_af:blk:600")],
            [InlineKeyboardButton(text="30 minutos", callback_data="adm_af:blk:1800")],
            [InlineKeyboardButton(text="1 hora", callback_data="adm_af:blk:3600")],
            [InlineKeyboardButton(text="24 horas", callback_data="adm_af:blk:86400")],
            [InlineKeyboardButton(text="Personalizado", callback_data="adm_af:blk:custom")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_gen:antiflood")],
        ]
    )
    await callback.message.answer(
        "⏰ <b>Duração do bloqueio</b>\n\nEscolha:",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_af:blk:"))
async def cb_af_set_block_value(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    value = callback.data.split(":")[2]

    if value == "custom":
        await callback.message.answer("⏰ Envie a duração em segundos (60 - 604800):")
        await state.set_state(AdminStates.editing_antiflood_block)
        await callback.answer()
        return

    try:
        secs = int(value)
    except ValueError:
        await callback.answer("❌ Valor inválido.", show_alert=True)
        return

    await config_service.set_config(session, "antiflood_block_seconds", str(secs))
    await callback.answer(f"✅ Bloqueio: {secs // 60}min", show_alert=True)
    await cb_antiflood(callback, session)


@router.message(AdminStates.editing_antiflood_block)
async def msg_af_block(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return
    try:
        val = int(message.text or "0")
        if not 60 <= val <= 604800:
            raise ValueError
    except ValueError:
        await message.answer("❌ Valor inválido. Use entre 60 e 604800 segundos.")
        return
    await config_service.set_config(session, "antiflood_block_seconds", str(val))
    await message.answer(f"✅ Bloqueio: <b>{val // 60}min</b>")
    await state.clear()


# ============================================
# 🚫 BLOQUEIOS (submenu)
# ============================================
@router.callback_query(F.data == "adm_gen:blocks")
async def cb_blocks(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    from core.models import BlockedUser
    from sqlalchemy import func

    total = await session.scalar(
        select(func.count(BlockedUser.id))
    ) or 0

    text = (
        "🚫 <b>BLOQUEIOS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Usuários bloqueados: <b>{total}</b>\n\n"
        "Use os botões para gerenciar:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Listar bloqueados", callback_data="adm_block:list")],
            [InlineKeyboardButton(text="➕ Bloquear usuário", callback_data="adm_block:add")],
            [InlineKeyboardButton(text="➖ Desbloquear", callback_data="adm_block:remove")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_cfg:gerais")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()

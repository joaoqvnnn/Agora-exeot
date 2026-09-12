# ============================================
# 📱 ADMIN TELEGRAM — Larizinha Store
# ============================================
# Configuração central do Telegram (bot principal).
# Todos os botões funcionam de verdade.
#
# Cobre:
#   - Info do bot (username, ID, nome)
#   - Token (mascarado + trocar)
#   - Webhook (verificar, setar, remover)
#   - Canal obrigatório (atalho)
#   - Canal de logs (atalho)
#   - Anti-flood (atalho)
#   - Comandos (atalho)
#   - Suporte (atalho)
# ============================================

import httpx
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
from core.config import settings
from core.models import Admin, AuditLog
from core.services import config as config_service


router = Router(name="admin_telegram")


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
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_tg:menu")]
        ]
    )


def _mask(v: str | None, show: int = 8) -> str:
    if not v:
        return "—"
    if len(v) <= show * 2:
        return "•" * 8
    return f"{v[:show]}...{v[-4:]}"


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_tg:menu")
async def cb_tg_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    # Info do bot
    bot_info = None
    try:
        me = await callback.bot.get_me()
        bot_info = {
            "id": me.id,
            "username": me.username,
            "first_name": me.first_name,
            "can_join_groups": me.can_join_groups,
            "can_read_messages": me.can_read_all_group_messages,
            "supports_inline": me.supports_inline_queries,
        }
    except Exception:
        pass

    # Webhook
    webhook_info = None
    try:
        wh = await callback.bot.get_webhook_info()
        webhook_info = {
            "url": wh.url,
            "has_custom_certificate": wh.has_custom_certificate,
            "pending_updates": wh.pending_update_count,
            "last_error": wh.last_error_message,
            "last_error_date": wh.last_error_date,
            "max_connections": wh.max_connections,
        }
    except Exception:
        pass

    channel_required = await config_service.get_bool(session, "required_channel_enabled", False)
    logs_channel = await config_service.get_str(session, "logs_channel_id", "")
    antiflood = await config_service.get_bool(session, "antiflood_enabled", True)
    support_link = await config_service.get_str(session, "support_link", "—")

    bot_line = "—"
    if bot_info:
        bot_line = f"@{bot_info['username']} (ID: {bot_info['id']})"

    webhook_line = "❌ Não configurado"
    if webhook_info and webhook_info["url"]:
        webhook_line = f"✅ {webhook_info['url'][:50]}"
    elif webhook_info:
        webhook_line = "⚠️ Modo polling"

    text = (
        "📱 <b>CONFIGURAÇÃO TELEGRAM</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🤖 Bot: <code>{bot_line}</code>\n"
        f"🔑 Token: <code>{_mask(settings.telegram_bot_token)}</code>\n"
        f"🌐 Webhook: {webhook_line}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📊 <b>Status rápido:</b>\n\n"
        f"📢 Canal obrigatório: {'🟢' if channel_required else '🔴'}\n"
        f"📋 Canal de logs: <code>{logs_channel or '—'}</code>\n"
        f"🛡 Anti-flood: {'🟢' if antiflood else '🔴'}\n"
        f"🎧 Suporte: <code>{support_link[:40]}</code>\n\n"
        "Escolha uma opção:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="ℹ️ Info Completa do Bot", callback_data="adm_tg:info")],
            [InlineKeyboardButton(text="🌐 Gerenciar Webhook", callback_data="adm_tg:webhook")],
            [InlineKeyboardButton(text="🧩 Sincronizar Comandos", callback_data="adm_cmd:sync")],
            [InlineKeyboardButton(text="📢 Canal Obrigatório", callback_data="adm_canal:menu")],
            [InlineKeyboardButton(text="📋 Canal de Logs", callback_data="adm_gen:logs_channel")],
            [InlineKeyboardButton(text="🎧 Link de Suporte", callback_data="adm_gen:support")],
            [InlineKeyboardButton(text="🛡 Anti-flood", callback_data="adm_gen:antiflood")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:config")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard, disable_web_page_preview=True)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard, disable_web_page_preview=True)

    await callback.answer()


# ============================================
# ℹ️ INFO COMPLETA DO BOT
# ============================================
@router.callback_query(F.data == "adm_tg:info")
async def cb_tg_info(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.answer("ℹ️ Carregando...", show_alert=False)

    try:
        me = await callback.bot.get_me()
    except Exception as e:
        await callback.message.answer(f"❌ Erro ao consultar bot: <code>{str(e)[:150]}</code>")
        return

    text = (
        "ℹ️ <b>INFO DO BOT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🤖 Nome: <b>{me.first_name}</b>\n"
        f"📛 Username: <b>@{me.username}</b>\n"
        f"🆔 ID: <code>{me.id}</code>\n\n"
        f"👥 Pode entrar em grupos: {'✅' if me.can_join_groups else '❌'}\n"
        f"📩 Lê todas as mensagens em grupos: {'✅' if me.can_read_all_group_messages else '❌'}\n"
        f"🔍 Suporta inline queries: {'✅' if me.supports_inline_queries else '❌'}\n\n"
        "🔑 <b>Token atual:</b>\n"
        f"<code>{_mask(settings.telegram_bot_token, 15)}</code>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Atualizar", callback_data="adm_tg:info")],
            [InlineKeyboardButton(text="🌐 Webhook", callback_data="adm_tg:webhook")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_tg:menu")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)


# ============================================
# 🌐 WEBHOOK
# ============================================
@router.callback_query(F.data == "adm_tg:webhook")
async def cb_tg_webhook(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.answer("🌐 Consultando...", show_alert=False)

    try:
        wh = await callback.bot.get_webhook_info()
    except Exception as e:
        await callback.message.answer(f"❌ Erro: <code>{str(e)[:150]}</code>")
        return

    status = "✅ Configurado" if wh.url else "❌ Não configurado"

    text = (
        "🌐 <b>WEBHOOK</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 Status: <b>{status}</b>\n\n"
        f"🔗 URL: <code>{wh.url or '—'}</code>\n"
        f"📩 Updates pendentes: <b>{wh.pending_update_count}</b>\n"
        f"🔌 Max conexões: <b>{wh.max_connections}</b>\n"
    )

    if wh.last_error_message:
        text += (
            f"\n⚠️ <b>Último erro:</b>\n"
            f"<code>{wh.last_error_message[:200]}</code>"
        )

    rows: list[list[InlineKeyboardButton]] = []

    if not wh.url:
        # Não tem webhook — oferece configurar
        rows.append([
            InlineKeyboardButton(
                text="✅ Configurar Webhook",
                callback_data="adm_tg:set_webhook",
            )
        ])
    else:
        rows.append([
            InlineKeyboardButton(
                text="❌ Remover Webhook",
                callback_data="adm_tg:delete_webhook",
            )
        ])
        rows.append([
            InlineKeyboardButton(
                text="🔄 Reset Webhook",
                callback_data="adm_tg:reset_webhook",
            )
        ])

    rows.append([
        InlineKeyboardButton(text="🔄 Atualizar", callback_data="adm_tg:webhook")
    ])
    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_tg:menu")
    ])

    try:
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )


@router.callback_query(F.data == "adm_tg:set_webhook")
async def cb_tg_set_webhook(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    current = settings.telegram_webhook_full_url

    await callback.message.answer(
        "🌐 <b>CONFIGURAR WEBHOOK</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 Sugerido (do .env):\n<code>{current}</code>\n\n"
        "Envie a URL pública do webhook (precisa ser HTTPS).\n\n"
        "Ou envie <code>auto</code> para usar a URL sugerida.",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(tg_field="webhook_url")
    await callback.answer()


@router.message(AdminStates.editing_config_value)
async def msg_tg_set_webhook(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    data = await state.get_data()
    field = data.get("tg_field")

    if field != "webhook_url":
        return

    raw = (message.text or "").strip()

    if raw.lower() == "auto":
        url = settings.telegram_webhook_full_url
    else:
        if not raw.startswith("https://"):
            await message.answer("❌ URL deve começar com <code>https://</code>")
            return
        url = raw

    secret = settings.telegram_webhook_secret or None

    try:
        result = await message.bot.set_webhook(
            url=url,
            secret_token=secret,
            drop_pending_updates=False,
            max_connections=40,
        )

        if result:
            await _log_audit(
                session,
                message.from_user.id,
                "set_webhook",
                new_value={"url": url},
            )
            await message.answer(
                f"✅ <b>Webhook configurado!</b>\n\n"
                f"🔗 URL: <code>{url}</code>"
            )
        else:
            await message.answer("⚠️ Telegram respondeu False. Verifique a URL.")

    except Exception as e:
        logger.exception(f"❌ Erro ao configurar webhook: {e}")
        await message.answer(f"❌ Erro: <code>{str(e)[:200]}</code>")

    await state.clear()


@router.callback_query(F.data == "adm_tg:delete_webhook")
async def cb_tg_delete_webhook(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    try:
        result = await callback.bot.delete_webhook(drop_pending_updates=False)

        if result:
            await _log_audit(
                session,
                callback.from_user.id,
                "delete_webhook",
            )
            await callback.answer("✅ Webhook removido!", show_alert=True)
        else:
            await callback.answer("⚠️ Telegram respondeu False.", show_alert=True)

    except Exception as e:
        await callback.answer(f"❌ Erro: {str(e)[:100]}", show_alert=True)

    callback.data = "adm_tg:webhook"
    await cb_tg_webhook(callback, session)


@router.callback_query(F.data == "adm_tg:reset_webhook")
async def cb_tg_reset_webhook(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    try:
        # Remove
        await callback.bot.delete_webhook(drop_pending_updates=True)
        # Reconfigura
        url = settings.telegram_webhook_full_url
        await callback.bot.set_webhook(
            url=url,
            secret_token=settings.telegram_webhook_secret or None,
            drop_pending_updates=True,
            max_connections=40,
        )

        await _log_audit(
            session,
            callback.from_user.id,
            "reset_webhook",
            new_value={"url": url},
        )

        await callback.answer("✅ Webhook resetado!", show_alert=True)

    except Exception as e:
        await callback.answer(f"❌ Erro: {str(e)[:100]}", show_alert=True)

    callback.data = "adm_tg:webhook"
    await cb_tg_webhook(callback, session)

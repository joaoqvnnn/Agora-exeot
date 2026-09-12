# ============================================
# 📲 ADMIN WHATSAPP — Larizinha Store
# ============================================
# Configuração REAL da integração WhatsApp
# (API não oficial — Baileys/WPPConnect/Evolution).
# Todos os botões funcionam de verdade.
# ============================================

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.states import AdminStates
from core.config import settings
from core.models import Admin, AuditLog
from core.services import config as config_service
from core.services import whatsapp as wa_service


router = Router(name="admin_whatsapp")


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
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_wa:menu")]
        ]
    )


def _mask(v: str | None, show: int = 6) -> str:
    if not v:
        return "—"
    if len(v) <= show * 2:
        return "•" * 8
    return f"{v[:show]}...{v[-4:]}"


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_wa:menu")
async def cb_wa_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    api_url = await config_service.get_str(session, "whatsapp_api_url", settings.whatsapp_api_url or "")
    api_key = await config_service.get_str(session, "whatsapp_api_key", settings.whatsapp_api_key or "")
    phone = await config_service.get_str(session, "whatsapp_phone_number", settings.whatsapp_phone_number or "")
    auto_deliver = await config_service.get_bool(session, "wa_auto_deliver", True)
    auto_ai = await config_service.get_bool(session, "wa_auto_ai", False)

    configured = "🟢 Configurado" if (api_url and api_key) else "🔴 Não configurado"

    deliver_status = "🟢 Ativo" if auto_deliver else "🔴 Desligado"
    ai_status = "🟢 Ativo" if auto_ai else "🔴 Desligado"

    text = (
        "📲 <b>CONFIGURAÇÃO WHATSAPP</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Status: <b>{configured}</b>\n\n"
        f"🌐 API URL: <code>{(api_url or '—')[:50]}</code>\n"
        f"🔑 API Key: <code>{_mask(api_key)}</code>\n"
        f"📱 Número: <code>{phone or '—'}</code>\n\n"
        "⚙️ <b>Automações:</b>\n"
        f"📦 Entrega automática de produtos: <b>{deliver_status}</b>\n"
        f"🤖 IA responde dúvidas: <b>{ai_status}</b>\n\n"
        "Use os botões para configurar:"
    )

    del_toggle = "🔴 Desligar" if auto_deliver else "🟢 Ligar"
    ai_toggle = "🔴 Desligar" if auto_ai else "🟢 Ligar"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Mudar API URL", callback_data="adm_wa:set_url")],
            [InlineKeyboardButton(text="🔑 Mudar API Key", callback_data="adm_wa:set_key")],
            [InlineKeyboardButton(text="📱 Mudar Número", callback_data="adm_wa:set_phone")],
            [InlineKeyboardButton(
                text=f"📦 Entrega automática — {del_toggle}",
                callback_data="adm_wa:toggle_deliver",
            )],
            [InlineKeyboardButton(
                text=f"🤖 IA — {ai_toggle}",
                callback_data="adm_wa:toggle_ai",
            )],
            [InlineKeyboardButton(text="🧪 Testar Conexão", callback_data="adm_wa:test")],
            [InlineKeyboardButton(text="📤 Enviar Mensagem de Teste", callback_data="adm_wa:send_test")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:config")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 🌐 MUDAR API URL
# ============================================
@router.callback_query(F.data == "adm_wa:set_url")
async def cb_wa_set_url(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "🌐 <b>MUDAR API URL</b>\n\n"
        "Envie a URL da sua API de WhatsApp.\n\n"
        "Exemplos:\n"
        "• <code>https://api.seudominio.com</code>\n"
        "• <code>https://evolution.seudominio.com</code>",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(wa_field="whatsapp_api_url")
    await callback.answer()


# ============================================
# 🔑 MUDAR API KEY
# ============================================
@router.callback_query(F.data == "adm_wa:set_key")
async def cb_wa_set_key(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "🔑 <b>MUDAR API KEY</b>\n\n"
        "Envie a chave/token da sua API de WhatsApp.",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(wa_field="whatsapp_api_key")
    await callback.answer()


# ============================================
# 📱 MUDAR NÚMERO
# ============================================
@router.callback_query(F.data == "adm_wa:set_phone")
async def cb_wa_set_phone(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "📱 <b>MUDAR NÚMERO DE ENVIO</b>\n\n"
        "Envie o número no formato internacional:\n"
        "<code>5511999999999</code>",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(wa_field="whatsapp_phone_number")
    await callback.answer()


# ============================================
# 💾 SALVAR VALOR
# ============================================
@router.message(AdminStates.editing_config_value)
async def msg_wa_save(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    data = await state.get_data()
    field = data.get("wa_field")

    if not field:
        await state.clear()
        return

    raw = (message.text or "").strip()
    if not raw:
        await message.answer("❌ Valor vazio.")
        return

    # Validações
    if field == "whatsapp_api_url" and not raw.startswith(("http://", "https://")):
        await message.answer("❌ URL inválida. Deve começar com http:// ou https://")
        return

    if field == "whatsapp_phone_number":
        digits = "".join(c for c in raw if c.isdigit())
        if len(digits) < 10:
            await message.answer("❌ Número inválido.")
            return

    old = await config_service.get_str(session, field, "")
    await config_service.set_config(session, field, raw)

    # Atualiza settings em runtime
    try:
        if field == "whatsapp_api_url":
            settings.whatsapp_api_url = raw
        elif field == "whatsapp_api_key":
            settings.whatsapp_api_key = raw
        elif field == "whatsapp_phone_number":
            settings.whatsapp_phone_number = raw
    except Exception:
        pass

    await _log_audit(
        session,
        message.from_user.id,
        f"edit_whatsapp_{field}",
        old_value={field: _mask(old)},
        new_value={field: _mask(raw)},
    )

    label = field.replace("whatsapp_", "").upper()
    await message.answer(f"✅ <b>{label}</b> atualizado!")
    await state.clear()


# ============================================
# 📦 TOGGLE ENTREGA AUTOMÁTICA
# ============================================
@router.callback_query(F.data == "adm_wa:toggle_deliver")
async def cb_wa_toggle_deliver(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    current = await config_service.get_bool(session, "wa_auto_deliver", True)
    new = not current
    await config_service.set_config(session, "wa_auto_deliver", "true" if new else "false")

    await _log_audit(
        session,
        callback.from_user.id,
        "toggle_wa_auto_deliver",
        new_value={"enabled": new},
    )

    status = "🟢 LIGADO" if new else "🔴 DESLIGADO"
    await callback.answer(f"Entrega automática: {status}", show_alert=True)

    callback.data = "adm_wa:menu"
    await cb_wa_menu(callback, session)


# ============================================
# 🤖 TOGGLE IA
# ============================================
@router.callback_query(F.data == "adm_wa:toggle_ai")
async def cb_wa_toggle_ai(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    current = await config_service.get_bool(session, "wa_auto_ai", False)
    new = not current
    await config_service.set_config(session, "wa_auto_ai", "true" if new else "false")

    await _log_audit(
        session,
        callback.from_user.id,
        "toggle_wa_ai",
        new_value={"enabled": new},
    )

    status = "🟢 LIGADA" if new else "🔴 DESLIGADA"
    await callback.answer(f"IA no WhatsApp: {status}", show_alert=True)

    callback.data = "adm_wa:menu"
    await cb_wa_menu(callback, session)


# ============================================
# 🧪 TESTAR CONEXÃO
# ============================================
@router.callback_query(F.data == "adm_wa:test")
async def cb_wa_test(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.answer("🧪 Testando...", show_alert=False)

    # Carrega config do banco
    for field, attr in [
        ("whatsapp_api_url", "whatsapp_api_url"),
        ("whatsapp_api_key", "whatsapp_api_key"),
        ("whatsapp_phone_number", "whatsapp_phone_number"),
    ]:
        val = await config_service.get_str(session, field, "")
        if val:
            setattr(settings, attr, val)

    result = await wa_service.test_connection()

    if result.get("ok"):
        text = (
            "🧪 <b>TESTE WHATSAPP</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "✅ <b>Conexão OK!</b>\n\n"
            f"📊 Estado: <code>{result.get('state')}</code>"
        )
    else:
        text = (
            "🧪 <b>TESTE WHATSAPP</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "❌ <b>Falha na conexão</b>\n\n"
            f"<b>Erro:</b> <code>{result.get('error')}</code>"
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Testar novamente", callback_data="adm_wa:test")],
            [InlineKeyboardButton(text="📤 Enviar teste", callback_data="adm_wa:send_test")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_wa:menu")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)


# ============================================
# 📤 ENVIAR MENSAGEM DE TESTE
# ============================================
@router.callback_query(F.data == "adm_wa:send_test")
async def cb_wa_send_test(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "📤 <b>ENVIAR MENSAGEM DE TESTE</b>\n\n"
        "Envie o número de WhatsApp que vai receber a mensagem:\n\n"
        "Formato: <code>5511999999999</code>",
        reply_markup=_cancel_keyboard(),
    )
    await state.update_data(wa_test=True)
    await state.set_state(AdminStates.editing_config_value)
    await callback.answer()


# ============================================
# HANDLER ESPECIAL PARA TESTE
# ============================================
# O handler abaixo já cobre o teste, mas vamos
# adicionar um específico para clareza
from aiogram import F as _F
from aiogram.types import Message as _Message


@router.message(AdminStates.editing_config_value, _F.text.regexp(r"^\d{10,15}$"))
async def msg_wa_send_test_number(
    message: _Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    data = await state.get_data()
    if not data.get("wa_test"):
        # Não é teste — deixa pro handler genérico
        return

    phone = (message.text or "").strip()

    # Carrega configs
    for field, attr in [
        ("whatsapp_api_url", "whatsapp_api_url"),
        ("whatsapp_api_key", "whatsapp_api_key"),
    ]:
        val = await config_service.get_str(session, field, "")
        if val:
            setattr(settings, attr, val)

    await message.answer("📤 Enviando mensagem de teste...")

    result = await wa_service.send_message(
        phone=phone,
        message=(
            "🧪 *Teste de conexão — Larizinha Store*\n\n"
            "Se você recebeu esta mensagem, sua integração de WhatsApp "
            "está funcionando corretamente! ✅"
        ),
    )

    if result.get("success"):
        await message.answer(
            f"✅ <b>Mensagem enviada!</b>\n\n"
            f"📱 Para: <code>{phone}</code>\n\n"
            "Verifique o WhatsApp."
        )
    else:
        await message.answer(
            f"❌ <b>Falha ao enviar</b>\n\n"
            f"<code>{result.get('error')}</code>"
        )

    await state.clear()

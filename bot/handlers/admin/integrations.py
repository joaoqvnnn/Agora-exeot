# ============================================
# 🔌 ADMIN INTEGRATIONS — Larizinha Store
# ============================================
# Painel de integrações externas com teste REAL.
# Todos os botões funcionam de verdade.
#
# Cobre:
#   - Telegram (bot + canal)
#   - Mercado Pago (Pix)
#   - WhatsApp (API não oficial)
#   - E-mail (SMTP)
#   - IA (OpenAI)
#   - Mini App (URL)
#   - Webhooks
# ============================================

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.models import Admin, AuditLog
from core.services import config as config_service


router = Router(name="admin_integrations")


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
    new_value: dict | None = None,
) -> None:
    log = AuditLog(
        admin_telegram_id=admin_id,
        action=action,
        new_value=new_value,
    )
    session.add(log)


def _status_emoji(ok: bool | None) -> str:
    if ok is True:
        return "🟢"
    if ok is False:
        return "🔴"
    return "⚪"


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm:integrations")
async def cb_integrations_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    # Verifica status de cada integração
    mp_token = await config_service.get_str(session, "mercadopago_access_token", "")
    if not mp_token:
        mp_token = settings.mercadopago_access_token or ""

    wa_url = settings.whatsapp_api_url or ""
    wa_key = settings.whatsapp_api_key or ""

    smtp_user = settings.smtp_user or ""

    openai_key = settings.openai_api_key or ""

    text = (
        "🔌 <b>INTEGRAÇÕES</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Status das integrações externas:\n\n"
        f"{_status_emoji(bool(settings.telegram_bot_token))} "
        f"<b>Telegram</b> — Bot principal\n"
        f"{_status_emoji(bool(mp_token))} "
        f"<b>Mercado Pago</b> — Pagamentos Pix\n"
        f"{_status_emoji(bool(wa_url and wa_key))} "
        f"<b>WhatsApp</b> — API externa\n"
        f"{_status_emoji(bool(smtp_user))} "
        f"<b>E-mail SMTP</b> — Envios\n"
        f"{_status_emoji(bool(openai_key))} "
        f"<b>OpenAI</b> — Atendimento IA\n\n"
        "Toque em uma integração para testar:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Telegram", callback_data="adm_int:test:telegram")],
            [InlineKeyboardButton(text="💳 Mercado Pago", callback_data="adm_int:test:mercadopago")],
            [InlineKeyboardButton(text="📲 WhatsApp", callback_data="adm_int:test:whatsapp")],
            [InlineKeyboardButton(text="📧 E-mail SMTP", callback_data="adm_int:test:email")],
            [InlineKeyboardButton(text="🤖 OpenAI (IA)", callback_data="adm_int:test:openai")],
            [InlineKeyboardButton(text="🌐 Mini App", callback_data="adm_int:test:webapp")],
            [InlineKeyboardButton(text="🔄 Testar TUDO", callback_data="adm_int:test_all")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:dashboard")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 🧪 TESTAR INTEGRAÇÃO INDIVIDUAL
# ============================================
@router.callback_query(F.data.startswith("adm_int:test:"))
async def cb_integration_test(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    integration = callback.data.split(":")[2]

    await callback.answer("🧪 Testando...", show_alert=False)

    result_text = await _run_test(session, integration)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🔄 Testar novamente",
                callback_data=f"adm_int:test:{integration}",
            )],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:integrations")],
        ]
    )

    try:
        await callback.message.edit_text(result_text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(result_text, reply_markup=keyboard)


async def _run_test(session: AsyncSession, integration: str) -> str:
    """Executa o teste apropriado e retorna o texto de resultado."""
    header = f"🧪 <b>TESTE — {integration.upper()}</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"

    try:
        if integration == "telegram":
            if not settings.telegram_bot_token:
                return header + "❌ Bot token não configurado."

            token = settings.telegram_bot_token
            masked = f"{token[:10]}...{token[-6:]}"

            bot_info = None
            try:
                me = await _get_telegram_me(token)
                bot_info = me
            except Exception as e:
                return header + f"❌ Erro: <code>{str(e)[:200]}</code>"

            if bot_info:
                return header + (
                    "✅ <b>Conexão OK!</b>\n\n"
                    f"🤖 Bot: <b>@{bot_info.get('username')}</b>\n"
                    f"🆔 ID: <code>{bot_info.get('id')}</code>\n"
                    f"📛 Nome: {bot_info.get('first_name')}\n"
                    f"🔑 Token: <code>{masked}</code>"
                )

        elif integration == "mercadopago":
            from core.services import pix as pix_service

            token_db = await config_service.get_str(
                session, "mercadopago_access_token", ""
            )
            if token_db:
                settings.mercadopago_access_token = token_db

            result = await pix_service.test_connection()

            if result.get("ok"):
                return header + (
                    "✅ <b>Conexão OK!</b>\n\n"
                    f"👤 User ID: <code>{result.get('user_id')}</code>\n"
                    f"📛 Nickname: <code>{result.get('nickname')}</code>\n"
                    f"📧 E-mail: <code>{result.get('email')}</code>"
                )
            return header + f"❌ <code>{result.get('error')}</code>"

        elif integration == "whatsapp":
            from core.services import whatsapp as wa

            result = await wa.test_connection()
            if result.get("ok"):
                return header + (
                    "✅ <b>WhatsApp conectado!</b>\n\n"
                    f"📊 Estado: <code>{result.get('state')}</code>"
                )
            return header + f"❌ <code>{result.get('error')}</code>"

        elif integration == "email":
            from core.services import email as email_service

            result = await email_service.test_connection()
            if result.get("ok"):
                return header + (
                    "✅ <b>SMTP conectado!</b>\n\n"
                    f"🖥 Host: <code>{result.get('host')}</code>\n"
                    f"📧 From: <code>{settings.smtp_from_email or settings.smtp_user}</code>"
                )
            return header + f"❌ <code>{result.get('error')}</code>"

        elif integration == "openai":
            from core.services import ai as ai_service

            result = await ai_service.test_connection()
            if result.get("ok"):
                return header + (
                    "✅ <b>OpenAI conectada!</b>\n\n"
                    f"🧠 Modelo: <code>{result.get('model')}</code>\n"
                    f"💬 Resposta teste: <code>{result.get('reply')}</code>"
                )
            return header + f"❌ <code>{result.get('error')}</code>"

        elif integration == "webapp":
            webapp_url = await config_service.get_str(
                session, "webapp_url", settings.webapp_url
            )
            if not webapp_url or "seu-servico" in webapp_url:
                return header + (
                    "⚠️ <b>URL do Mini App não configurada</b>\n\n"
                    "Configure em <b>Configurações Gerais</b>."
                )
            return header + (
                "✅ <b>URL configurada:</b>\n\n"
                f"<code>{webapp_url}</code>"
            )

        else:
            return header + "❌ Integração desconhecida."

    except Exception as e:
        return header + f"❌ <b>Erro inesperado:</b>\n<code>{str(e)[:300]}</code>"


async def _get_telegram_me(token: str) -> dict:
    """Chama getMe da API do Telegram."""
    import httpx

    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"https://api.telegram.org/bot{token}/getMe")
        data = r.json()
        if not data.get("ok"):
            raise Exception(data.get("description", "getMe falhou"))
        return data["result"]


# ============================================
# 🧪 TESTAR TUDO
# ============================================
@router.callback_query(F.data == "adm_int:test_all")
async def cb_integration_test_all(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.answer("🧪 Testando todas...", show_alert=False)

    lines = [
        "🧪 <b>TESTE DE TODAS AS INTEGRAÇÕES</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    integrations = [
        ("telegram", "📱 Telegram"),
        ("mercadopago", "💳 Mercado Pago"),
        ("whatsapp", "📲 WhatsApp"),
        ("email", "📧 E-mail"),
        ("openai", "🤖 OpenAI"),
    ]

    ok_count = 0

    for key, label in integrations:
        try:
            result_text = await _run_test(session, key)
            if "✅" in result_text:
                lines.append(f"🟢 {label} — <b>OK</b>")
                ok_count += 1
            elif "⚠️" in result_text:
                lines.append(f"🟡 {label} — <b>Aviso</b>")
            else:
                lines.append(f"🔴 {label} — <b>Falha</b>")
        except Exception as e:
            lines.append(f"🔴 {label} — <code>{str(e)[:60]}</code>")

    lines.append("")
    lines.append(f"📊 <b>{ok_count}/{len(integrations)}</b> integrações OK")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Testar novamente", callback_data="adm_int:test_all")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:integrations")],
        ]
    )

    try:
        await callback.message.edit_text("\n".join(lines), reply_markup=keyboard)
    except Exception:
        await callback.message.answer("\n".join(lines), reply_markup=keyboard)

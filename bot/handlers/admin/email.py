# ============================================
# 📧 ADMIN EMAIL — Larizinha Store
# ============================================
# Configuração REAL do servidor SMTP.
# Todos os botões funcionam de verdade.
#
# Cobre:
#   - Definir host/porta
#   - Definir usuário/senha
#   - Definir remetente
#   - Testar conexão
#   - Enviar e-mail de teste
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
from core.services import email as email_service


router = Router(name="admin_email")


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
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_email:menu")]
        ]
    )


def _mask(v: str | None, show: int = 4) -> str:
    if not v:
        return "—"
    if len(v) <= show * 2:
        return "•" * 8
    return f"{v[:show]}...{v[-2:]}"


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_email:menu")
async def cb_email_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    host = await config_service.get_str(session, "smtp_host", settings.smtp_host)
    port = await config_service.get_str(session, "smtp_port", str(settings.smtp_port))
    user = await config_service.get_str(session, "smtp_user", settings.smtp_user or "")
    from_name = await config_service.get_str(
        session, "smtp_from_name", settings.smtp_from_name
    )
    from_email = await config_service.get_str(
        session, "smtp_from_email", settings.smtp_from_email or ""
    )
    password = await config_service.get_str(
        session, "smtp_password", settings.smtp_password or ""
    )

    configured = "🟢 Configurado" if (host and user and password) else "🔴 Não configurado"

    text = (
        "📧 <b>CONFIGURAÇÃO DE E-MAIL (SMTP)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Status: <b>{configured}</b>\n\n"
        f"🖥 Host: <code>{host or '—'}</code>\n"
        f"🔌 Porta: <code>{port}</code>\n"
        f"👤 Usuário: <code>{user or '—'}</code>\n"
        f"🔑 Senha: <code>{_mask(password)}</code>\n"
        f"📛 Nome remetente: <b>{from_name or '—'}</b>\n"
        f"📧 E-mail remetente: <code>{from_email or '—'}</code>\n\n"
        "Use os botões para configurar:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🖥 Mudar Host", callback_data="adm_email:set_host")],
            [InlineKeyboardButton(text="🔌 Mudar Porta", callback_data="adm_email:set_port")],
            [InlineKeyboardButton(text="👤 Mudar Usuário", callback_data="adm_email:set_user")],
            [InlineKeyboardButton(text="🔑 Mudar Senha", callback_data="adm_email:set_pass")],
            [InlineKeyboardButton(text="📛 Mudar Nome Remetente", callback_data="adm_email:set_name")],
            [InlineKeyboardButton(text="📧 Mudar E-mail Remetente", callback_data="adm_email:set_from")],
            [InlineKeyboardButton(text="🧪 Testar Conexão", callback_data="adm_email:test")],
            [InlineKeyboardButton(text="📤 Enviar E-mail de Teste", callback_data="adm_email:send_test")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:config")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 🖥 MUDAR HOST
# ============================================
@router.callback_query(F.data == "adm_email:set_host")
async def cb_email_set_host(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "🖥 <b>MUDAR HOST SMTP</b>\n\n"
        "Exemplos:\n"
        "• <code>smtp.gmail.com</code>\n"
        "• <code>smtp.zoho.com</code>\n"
        "• <code>smtp.sendgrid.net</code>\n"
        "• <code>smtp-mail.outlook.com</code>\n\n"
        "Envie o host:",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(email_field="smtp_host")
    await callback.answer()


# ============================================
# 🔌 MUDAR PORTA
# ============================================
@router.callback_query(F.data == "adm_email:set_port")
async def cb_email_set_port(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "🔌 <b>MUDAR PORTA SMTP</b>\n\n"
        "Portas comuns:\n"
        "• <code>587</code> (TLS - recomendado)\n"
        "• <code>465</code> (SSL)\n"
        "• <code>25</code> (sem criptografia)\n\n"
        "Envie a porta:",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(email_field="smtp_port")
    await callback.answer()


# ============================================
# 👤 MUDAR USUÁRIO
# ============================================
@router.callback_query(F.data == "adm_email:set_user")
async def cb_email_set_user(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "👤 <b>MUDAR USUÁRIO SMTP</b>\n\n"
        "Geralmente é o e-mail completo:\n"
        "<code>seuemail@gmail.com</code>",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(email_field="smtp_user")
    await callback.answer()


# ============================================
# 🔑 MUDAR SENHA
# ============================================
@router.callback_query(F.data == "adm_email:set_pass")
async def cb_email_set_pass(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "🔑 <b>MUDAR SENHA SMTP</b>\n\n"
        "⚠️ No Gmail, use uma <b>senha de app</b> (não a senha normal).\n\n"
        "Gere em: https://myaccount.google.com/apppasswords\n\n"
        "Envie a senha:",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(email_field="smtp_password")
    await callback.answer()


# ============================================
# 📛 MUDAR NOME REMETENTE
# ============================================
@router.callback_query(F.data == "adm_email:set_name")
async def cb_email_set_name(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "📛 <b>MUDAR NOME DO REMETENTE</b>\n\n"
        "Exemplo: <code>Larizinha Store</code>",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(email_field="smtp_from_name")
    await callback.answer()


# ============================================
# 📧 MUDAR E-MAIL REMETENTE
# ============================================
@router.callback_query(F.data == "adm_email:set_from")
async def cb_email_set_from(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "📧 <b>MUDAR E-MAIL DO REMETENTE</b>\n\n"
        "Este é o e-mail que aparece como remetente.\n\n"
        "Exemplo: <code>contato@sualoja.com</code>",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(email_field="smtp_from_email")
    await callback.answer()


# ============================================
# 💾 SALVAR VALOR
# ============================================
@router.message(AdminStates.editing_config_value)
async def msg_email_save(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    data = await state.get_data()
    field = data.get("email_field")

    if not field:
        await state.clear()
        return

    raw = (message.text or "").strip()
    if not raw:
        await message.answer("❌ Valor vazio.")
        return

    # Validações específicas
    if field == "smtp_port":
        try:
            port = int(raw)
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            await message.answer("❌ Porta inválida (1-65535).")
            return

    if field == "smtp_from_email" and "@" not in raw:
        await message.answer("❌ E-mail inválido.")
        return

    old = await config_service.get_str(session, field, "")
    await config_service.set_config(session, field, raw)

    # Atualiza settings em runtime
    try:
        if field == "smtp_host":
            settings.smtp_host = raw
        elif field == "smtp_port":
            settings.smtp_port = int(raw)
        elif field == "smtp_user":
            settings.smtp_user = raw
        elif field == "smtp_password":
            settings.smtp_password = raw
        elif field == "smtp_from_name":
            settings.smtp_from_name = raw
        elif field == "smtp_from_email":
            settings.smtp_from_email = raw
    except Exception:
        pass

    await _log_audit(
        session,
        message.from_user.id,
        f"edit_email_{field}",
        old_value={field: _mask(old)},
        new_value={field: _mask(raw)},
    )

    label = field.replace("smtp_", "").upper()
    await message.answer(f"✅ <b>{label}</b> atualizado com sucesso!")

    # Reexibe o menu
    await state.clear()


# ============================================
# 🧪 TESTAR CONEXÃO
# ============================================
@router.callback_query(F.data == "adm_email:test")
async def cb_email_test(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.answer("🧪 Testando...", show_alert=False)

    # Carrega config do banco
    for field, attr in [
        ("smtp_host", "smtp_host"),
        ("smtp_port", "smtp_port"),
        ("smtp_user", "smtp_user"),
        ("smtp_password", "smtp_password"),
        ("smtp_from_email", "smtp_from_email"),
        ("smtp_from_name", "smtp_from_name"),
    ]:
        val = await config_service.get_str(session, field, "")
        if val:
            try:
                if field == "smtp_port":
                    setattr(settings, attr, int(val))
                else:
                    setattr(settings, attr, val)
            except Exception:
                pass

    result = await email_service.test_connection()

    if result.get("ok"):
        text = (
            "🧪 <b>TESTE SMTP</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "✅ <b>Conexão OK!</b>\n\n"
            f"🖥 Host: <code>{result.get('host')}</code>\n"
            f"👤 User: <code>{settings.smtp_user}</code>\n"
            f"📧 From: <code>{settings.smtp_from_email or settings.smtp_user}</code>"
        )
    else:
        text = (
            "🧪 <b>TESTE SMTP</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "❌ <b>Falha na conexão</b>\n\n"
            f"<b>Erro:</b> <code>{result.get('error')}</code>\n\n"
            "Verifique host, porta, usuário e senha."
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Testar novamente", callback_data="adm_email:test")],
            [InlineKeyboardButton(text="📤 Enviar teste", callback_data="adm_email:send_test")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_email:menu")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)


# ============================================
# 📤 ENVIAR E-MAIL DE TESTE
# ============================================
@router.callback_query(F.data == "adm_email:send_test")
async def cb_email_send_test(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.answer("📤 Enviando...", show_alert=False)

    # Carrega configs
    for field, attr in [
        ("smtp_host", "smtp_host"),
        ("smtp_port", "smtp_port"),
        ("smtp_user", "smtp_user"),
        ("smtp_password", "smtp_password"),
        ("smtp_from_email", "smtp_from_email"),
    ]:
        val = await config_service.get_str(session, field, "")
        if val:
            try:
                if field == "smtp_port":
                    setattr(settings, attr, int(val))
                else:
                    setattr(settings, attr, val)
            except Exception:
                pass

    # Precisa do e-mail do admin pra enviar
    admin_email = await config_service.get_str(session, "admin_test_email", "")
    if not admin_email:
        # Usa o próprio SMTP user
        admin_email = settings.smtp_user or ""

    if not admin_email:
        await callback.message.answer(
            "❌ Nenhum e-mail de destino configurado.\n\n"
            "Configure <code>admin_test_email</code> ou preencha o SMTP user.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_email:menu")]
                ]
            ),
        )
        return

    html = (
        "<h2>🧪 Teste de e-mail — Larizinha Store</h2>"
        "<p>Se você recebeu este e-mail, o SMTP está funcionando corretamente!</p>"
        "<p>Data: " + __import__("datetime").datetime.now().strftime("%d/%m/%Y %H:%M:%S") + "</p>"
    )

    result = await email_service.send_email(
        to_email=admin_email,
        subject="🧪 Teste de E-mail — Larizinha Store",
        html_body=html,
        text_body="Teste de e-mail da Larizinha Store. Se você recebeu, o SMTP está OK.",
    )

    if result.get("success"):
        text = (
            "📤 <b>E-mail de teste enviado!</b>\n\n"
            f"📧 Para: <code>{admin_email}</code>\n\n"
            "Verifique sua caixa de entrada (e a pasta de spam)."
        )
    else:
        text = (
            "❌ <b>Falha ao enviar</b>\n\n"
            f"<code>{result.get('error')}</code>"
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Enviar novamente", callback_data="adm_email:send_test")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_email:menu")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

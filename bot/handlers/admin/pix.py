# ============================================
# 💳 ADMIN PIX — Larizinha Store
# ============================================
# Configuração REAL do Mercado Pago pelo painel.
# Todos os botões funcionam de verdade.
# ============================================

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.states import AdminStates
from core.models import Admin, AuditLog
from core.services import config as config_service
from core.services import pix as pix_service


router = Router(name="admin_pix")


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


def _mask_token(token: str) -> str:
    if not token or len(token) < 12:
        return token or "Não configurado"
    return f"{token[:10]}...{token[-6:]}"


def _cancelar_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_cfg:pix")]
        ]
    )


# ============================================
# 💳 MENU PIX
# ============================================
@router.callback_query(F.data == "adm_cfg:pix")
async def cb_pix_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    token = await config_service.get_str(session, "mercadopago_access_token", "")
    if not token:
        from core.config import settings
        token = settings.mercadopago_access_token or ""

    pix_min = await config_service.get_str(session, "pix_min", "4.00")
    pix_max = await config_service.get_str(session, "pix_max", "500.00")
    expiration = await config_service.get_str(session, "pix_expiration_minutes", "10")
    bonus = await config_service.get_str(session, "pix_bonus_percent", "0")
    bonus_min = await config_service.get_str(session, "pix_bonus_min", "0")
    pix_auto = await config_service.get_bool(session, "pix_auto", True)

    mode = "🟢 PIX AUTOMÁTICO" if pix_auto else "🔴 PIX MANUAL"

    text = (
        "💳 <b>CONFIGURAÇÕES DE PIX</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔑 TOKEN MERCADO PAGO:\n<code>{_mask_token(token)}</code>\n\n"
        f"💵 DEPÓSITO MÍNIMO: <b>R$ {pix_min}</b>\n"
        f"💵 DEPÓSITO MÁXIMO: <b>R$ {pix_max}</b>\n"
        f"⏱ TEMPO DE EXPIRAÇÃO: <b>{expiration} minutos</b>\n"
        f"🎁 BÔNUS DE DEPÓSITO: <b>{bonus}%</b>\n"
        f"🎁 MÍNIMO PARA BÔNUS: <b>R$ {bonus_min}</b>\n"
        f"⚙️ MODO: <b>{mode}</b>\n\n"
        "Use os botões abaixo para configurar:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔑 Mudar Token", callback_data="adm_pix:token")],
            [InlineKeyboardButton(text="💰 Mudar Depósito Mínimo", callback_data="adm_pix:min")],
            [InlineKeyboardButton(text="💰 Mudar Depósito Máximo", callback_data="adm_pix:max")],
            [InlineKeyboardButton(text="⏱ Mudar Tempo de Expiração", callback_data="adm_pix:expiration")],
            [InlineKeyboardButton(text="🎁 Mudar Bônus", callback_data="adm_pix:bonus")],
            [InlineKeyboardButton(text="🎁 Mudar Mínimo para Bônus", callback_data="adm_pix:bonus_min")],
            [
                InlineKeyboardButton(text="🟢 PIX AUTOMÁTICO", callback_data="adm_pix:auto_on"),
                InlineKeyboardButton(text="🔴 PIX MANUAL", callback_data="adm_pix:auto_off"),
            ],
            [InlineKeyboardButton(text="🧪 Testar Conexão MP", callback_data="adm_pix:test")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:config")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 🔑 MUDAR TOKEN
# ============================================
@router.callback_query(F.data == "adm_pix:token")
async def cb_change_token(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text = (
        "🔑 <b>MUDAR TOKEN MERCADO PAGO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Envie o novo Access Token do Mercado Pago.\n"
        "Formato: <code>APP_USR-...</code>\n\n"
        "💡 Obtenha em:\n"
        "https://www.mercadopago.com.br/developers/panel"
    )
    await callback.message.answer(text, reply_markup=_cancelar_keyboard())
    await state.set_state(AdminStates.editing_mp_token)
    await callback.answer()


@router.message(AdminStates.editing_mp_token)
async def msg_save_token(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    token = (message.text or "").strip()
    if not token.startswith("APP_USR-") and not token.startswith("TEST-"):
        await message.answer(
            "❌ Token inválido. Deve começar com <code>APP_USR-</code> ou <code>TEST-</code>."
        )
        return

    old = await config_service.get_str(session, "mercadopago_access_token", "")
    await config_service.set_config(session, "mercadopago_access_token", token)
    await _log_audit(
        session, message.from_user.id, "edit_mp_token",
        old_value={"token": _mask_token(old)},
        new_value={"token": _mask_token(token)},
    )

    await message.answer("✅ Token do Mercado Pago atualizado com sucesso!")
    await state.clear()


# ============================================
# 💰 MUDAR MÍNIMO
# ============================================
@router.callback_query(F.data == "adm_pix:min")
async def cb_change_min(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await callback.message.answer(
        "💰 Envie o novo <b>depósito mínimo</b> em reais.\nExemplo: <code>4.00</code>",
        reply_markup=_cancelar_keyboard(),
    )
    await state.set_state(AdminStates.editing_pix_min)
    await callback.answer()


@router.message(AdminStates.editing_pix_min)
async def msg_save_min(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return
    raw = (message.text or "").replace(",", ".").strip()
    try:
        val = float(raw)
        if val <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Valor inválido. Ex: <code>4.00</code>")
        return

    old = await config_service.get_str(session, "pix_min", "4.00")
    await config_service.set_config(session, "pix_min", f"{val:.2f}")
    await _log_audit(
        session, message.from_user.id, "edit_pix_min",
        old_value={"pix_min": old},
        new_value={"pix_min": f"{val:.2f}"},
    )
    await message.answer(f"✅ Depósito mínimo: <b>R$ {val:.2f}</b>")
    await state.clear()


# ============================================
# 💰 MUDAR MÁXIMO
# ============================================
@router.callback_query(F.data == "adm_pix:max")
async def cb_change_max(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await callback.message.answer(
        "💰 Envie o novo <b>depósito máximo</b> em reais.\nExemplo: <code>500.00</code>",
        reply_markup=_cancelar_keyboard(),
    )
    await state.set_state(AdminStates.editing_pix_max)
    await callback.answer()


@router.message(AdminStates.editing_pix_max)
async def msg_save_max(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return
    raw = (message.text or "").replace(",", ".").strip()
    try:
        val = float(raw)
        if val <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Valor inválido. Ex: <code>500.00</code>")
        return

    old = await config_service.get_str(session, "pix_max", "500.00")
    await config_service.set_config(session, "pix_max", f"{val:.2f}")
    await _log_audit(
        session, message.from_user.id, "edit_pix_max",
        old_value={"pix_max": old},
        new_value={"pix_max": f"{val:.2f}"},
    )
    await message.answer(f"✅ Depósito máximo: <b>R$ {val:.2f}</b>")
    await state.clear()


# ============================================
# ⏱ MUDAR EXPIRAÇÃO
# ============================================
@router.callback_query(F.data == "adm_pix:expiration")
async def cb_change_expiration(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await callback.message.answer(
        "⏱ Envie o novo <b>tempo de expiração</b> do Pix em minutos (1-60).",
        reply_markup=_cancelar_keyboard(),
    )
    await state.set_state(AdminStates.editing_pix_expiration)
    await callback.answer()


@router.message(AdminStates.editing_pix_expiration)
async def msg_save_expiration(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return
    try:
        val = int((message.text or "").strip())
        if not 1 <= val <= 60:
            raise ValueError
    except ValueError:
        await message.answer("❌ Valor inválido. Use número entre 1 e 60.")
        return

    old = await config_service.get_str(session, "pix_expiration_minutes", "10")
    await config_service.set_config(session, "pix_expiration_minutes", str(val))
    await _log_audit(
        session, message.from_user.id, "edit_pix_expiration",
        old_value={"expiration": old},
        new_value={"expiration": str(val)},
    )
    await message.answer(f"✅ Expiração: <b>{val} minutos</b>")
    await state.clear()


# ============================================
# 🎁 MUDAR BÔNUS
# ============================================
@router.callback_query(F.data == "adm_pix:bonus")
async def cb_change_bonus(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await callback.message.answer(
        "🎁 Envie o novo <b>percentual de bônus</b> (0-100).\nExemplo: <code>10</code>",
        reply_markup=_cancelar_keyboard(),
    )
    await state.set_state(AdminStates.editing_pix_bonus)
    await callback.answer()


@router.message(AdminStates.editing_pix_bonus)
async def msg_save_bonus(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return
    raw = (message.text or "").replace(",", ".").strip()
    try:
        val = float(raw)
        if not 0 <= val <= 100:
            raise ValueError
    except ValueError:
        await message.answer("❌ Valor inválido. Use 0 a 100.")
        return

    old = await config_service.get_str(session, "pix_bonus_percent", "0")
    await config_service.set_config(session, "pix_bonus_percent", f"{val:.2f}")
    await _log_audit(
        session, message.from_user.id, "edit_pix_bonus",
        old_value={"bonus": old},
        new_value={"bonus": f"{val:.2f}"},
    )
    await message.answer(f"✅ Bônus: <b>{val:.2f}%</b>")
    await state.clear()


# ============================================
# 🎁 MUDAR MÍNIMO PARA BÔNUS
# ============================================
@router.callback_query(F.data == "adm_pix:bonus_min")
async def cb_change_bonus_min(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await callback.message.answer(
        "🎁 Envie o <b>valor mínimo</b> para ganhar bônus.\nExemplo: <code>10.00</code>",
        reply_markup=_cancelar_keyboard(),
    )
    await state.set_state(AdminStates.editing_pix_bonus_min)
    await callback.answer()


@router.message(AdminStates.editing_pix_bonus_min)
async def msg_save_bonus_min(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return
    raw = (message.text or "").replace(",", ".").strip()
    try:
        val = float(raw)
        if val < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Valor inválido. Ex: <code>10.00</code>")
        return

    old = await config_service.get_str(session, "pix_bonus_min", "0")
    await config_service.set_config(session, "pix_bonus_min", f"{val:.2f}")
    await _log_audit(
        session, message.from_user.id, "edit_pix_bonus_min",
        old_value={"bonus_min": old},
        new_value={"bonus_min": f"{val:.2f}"},
    )
    await message.answer(f"✅ Mínimo para bônus: <b>R$ {val:.2f}</b>")
    await state.clear()


# ============================================
# ⚙️ MODO PIX
# ============================================
@router.callback_query(F.data == "adm_pix:auto_on")
async def cb_pix_auto_on(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await config_service.set_config(session, "pix_auto", "true")
    await callback.answer("🟢 Pix AUTOMÁTICO ativado", show_alert=True)
    await cb_pix_menu(callback, session)


@router.callback_query(F.data == "adm_pix:auto_off")
async def cb_pix_auto_off(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await config_service.set_config(session, "pix_auto", "false")
    await callback.answer("🔴 Pix MANUAL ativado", show_alert=True)
    await cb_pix_menu(callback, session)


# ============================================
# 🧪 TESTAR CONEXÃO MP
# ============================================
@router.callback_query(F.data == "adm_pix:test")
async def cb_test_mp(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.answer("🧪 Testando...", show_alert=False)

    # Pega token do banco ou do env
    token_db = await config_service.get_str(session, "mercadopago_access_token", "")
    from core.config import settings

    if token_db:
        settings.mercadopago_access_token = token_db

    result = await pix_service.test_connection()

    if result.get("ok"):
        text = (
            "🧪 <b>TESTE MERCADO PAGO</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "✅ <b>Conexão OK!</b>\n\n"
            f"👤 User ID: <code>{result.get('user_id')}</code>\n"
            f"📛 Nickname: <code>{result.get('nickname')}</code>\n"
            f"📧 E-mail: <code>{result.get('email')}</code>"
        )
    else:
        text = (
            "🧪 <b>TESTE MERCADO PAGO</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "❌ <b>Falha na conexão</b>\n\n"
            f"<b>Erro:</b> <code>{result.get('error')}</code>\n\n"
            "Verifique se o token está correto."
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_cfg:pix")]
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

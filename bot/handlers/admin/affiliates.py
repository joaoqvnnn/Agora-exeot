# ============================================
# 🤝 ADMIN AFFILIATES — Larizinha Store
# ============================================
# Configuração REAL do sistema de afiliados.
# Todos os botões funcionam de verdade.
# ============================================

from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.states import AdminStates
from core.models import (
    Admin,
    AffiliateCommission,
    AuditLog,
    User,
    Withdrawal,
    WithdrawalStatus,
)
from core.services import config as config_service


router = Router(name="admin_affiliates")


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


def _cancel_keyboard(back_data: str = "adm_cfg:afiliados") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancelar", callback_data=back_data)]
        ]
    )


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_cfg:afiliados")
async def cb_affiliates_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    enabled = await config_service.get_bool(session, "affiliate_enabled", True)
    commission = await config_service.get_str(session, "affiliate_commission", "20.0")
    points_per = await config_service.get_str(session, "affiliate_points_per_recharge", "1")
    min_points = await config_service.get_str(session, "affiliate_min_points", "500")
    multiplier = await config_service.get_str(session, "affiliate_multiplier", "0.01")
    min_withdrawal = await config_service.get_str(session, "affiliate_min_withdrawal", "20.00")

    status = "🟢 ATIVO" if enabled else "🔴 DESATIVADO"

    text = (
        "🤝 <b>CONFIGURAR AFILIADOS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚙️ Sistema: <b>{status}</b>\n"
        f"🧲 Comissão: <b>{commission}%</b>\n"
        f"📊 Pontos por recarga: <b>{points_per}</b>\n"
        f"🎯 Mínimo de pontos: <b>{min_points}</b>\n"
        f"✖️ Multiplicador: <b>{multiplier}</b>\n"
        f"💸 Saque mínimo: <b>R$ {min_withdrawal}</b>\n\n"
        "Use os botões abaixo para configurar:"
    )

    toggle_text = "🔴 DESATIVAR" if enabled else "🟢 ATIVAR"
    toggle_cb = "adm_aff:off" if enabled else "adm_aff:on"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle_text, callback_data=toggle_cb)],
            [InlineKeyboardButton(text=f"🧲 Comissão ({commission}%)", callback_data="adm_aff:set_commission")],
            [InlineKeyboardButton(text=f"📊 Pontos por Recarga ({points_per})", callback_data="adm_aff:set_points")],
            [InlineKeyboardButton(text=f"🎯 Mínimo p/ Converter ({min_points})", callback_data="adm_aff:set_min_points")],
            [InlineKeyboardButton(text=f"✖️ Multiplicador ({multiplier})", callback_data="adm_aff:set_multiplier")],
            [InlineKeyboardButton(text=f"💸 Saque Mínimo (R$ {min_withdrawal})", callback_data="adm_aff:set_min_withdrawal")],
            [InlineKeyboardButton(text="💸 Saques Pendentes", callback_data="adm_wd:list")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:config")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 🟢 / 🔴 TOGGLE SISTEMA
# ============================================
@router.callback_query(F.data == "adm_aff:on")
async def cb_aff_on(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await config_service.set_config(session, "affiliate_enabled", "true")
    await _log_audit(session, callback.from_user.id, "affiliate_on")
    await callback.answer("🟢 Sistema ativado", show_alert=True)
    await cb_affiliates_menu(callback, session)


@router.callback_query(F.data == "adm_aff:off")
async def cb_aff_off(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await config_service.set_config(session, "affiliate_enabled", "false")
    await _log_audit(session, callback.from_user.id, "affiliate_off")
    await callback.answer("🔴 Sistema desativado", show_alert=True)
    await cb_affiliates_menu(callback, session)


# ============================================
# 🧲 COMISSÃO
# ============================================
@router.callback_query(F.data == "adm_aff:set_commission")
async def cb_aff_set_commission(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await callback.message.answer(
        "🧲 Envie o <b>percentual de comissão</b> (0 a 100).\n"
        "Exemplo: <code>20</code>",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_affiliate_commission)
    await callback.answer()


@router.message(AdminStates.editing_affiliate_commission)
async def msg_aff_commission(
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

    old = await config_service.get_str(session, "affiliate_commission", "20.0")
    await config_service.set_config(session, "affiliate_commission", f"{val:.2f}")
    await _log_audit(
        session, message.from_user.id, "edit_affiliate_commission",
        old_value={"commission": old},
        new_value={"commission": f"{val:.2f}"},
    )
    await message.answer(f"✅ Comissão: <b>{val:.2f}%</b>")
    await state.clear()


# ============================================
# 📊 PONTOS POR RECARGA
# ============================================
@router.callback_query(F.data == "adm_aff:set_points")
async def cb_aff_set_points(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await callback.message.answer(
        "📊 Envie a quantidade de <b>pontos por recarga</b>.\n"
        "Exemplo: <code>1</code>",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_affiliate_points_per_recharge)
    await callback.answer()


@router.message(AdminStates.editing_affiliate_points_per_recharge)
async def msg_aff_points(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return
    try:
        val = int((message.text or "").strip())
        if val < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Número inválido.")
        return

    old = await config_service.get_str(session, "affiliate_points_per_recharge", "1")
    await config_service.set_config(session, "affiliate_points_per_recharge", str(val))
    await _log_audit(
        session, message.from_user.id, "edit_affiliate_points",
        old_value={"points": old},
        new_value={"points": str(val)},
    )
    await message.answer(f"✅ Pontos por recarga: <b>{val}</b>")
    await state.clear()


# ============================================
# 🎯 MÍNIMO DE PONTOS
# ============================================
@router.callback_query(F.data == "adm_aff:set_min_points")
async def cb_aff_set_min_points(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await callback.message.answer(
        "🎯 Envie o <b>mínimo de pontos</b> para converter em saldo.\n"
        "Exemplo: <code>500</code>",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_affiliate_min_points)
    await callback.answer()


@router.message(AdminStates.editing_affiliate_min_points)
async def msg_aff_min_points(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return
    try:
        val = int((message.text or "").strip())
        if val < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Número inválido.")
        return

    old = await config_service.get_str(session, "affiliate_min_points", "500")
    await config_service.set_config(session, "affiliate_min_points", str(val))
    await _log_audit(
        session, message.from_user.id, "edit_affiliate_min_points",
        old_value={"min_points": old},
        new_value={"min_points": str(val)},
    )
    await message.answer(f"✅ Mínimo de pontos: <b>{val}</b>")
    await state.clear()


# ============================================
# ✖️ MULTIPLICADOR
# ============================================
@router.callback_query(F.data == "adm_aff:set_multiplier")
async def cb_aff_set_multiplier(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await callback.message.answer(
        "✖️ Envie o <b>multiplicador</b> de pontos para saldo.\n\n"
        "Exemplos:\n"
        "• <code>0.01</code> → 500 pontos = R$ 5,00\n"
        "• <code>0.50</code> → 20 pontos = R$ 10,00",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_affiliate_multiplier)
    await callback.answer()


@router.message(AdminStates.editing_affiliate_multiplier)
async def msg_aff_multiplier(
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
        await message.answer("❌ Valor inválido. Ex: <code>0.01</code>")
        return

    old = await config_service.get_str(session, "affiliate_multiplier", "0.01")
    await config_service.set_config(session, "affiliate_multiplier", f"{val}")
    await _log_audit(
        session, message.from_user.id, "edit_affiliate_multiplier",
        old_value={"multiplier": old},
        new_value={"multiplier": f"{val}"},
    )
    await message.answer(f"✅ Multiplicador: <b>{val}</b>")
    await state.clear()


# ============================================
# 💸 SAQUE MÍNIMO
# ============================================
@router.callback_query(F.data == "adm_aff:set_min_withdrawal")
async def cb_aff_set_min_withdrawal(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await callback.message.answer(
        "💸 Envie o <b>saque mínimo</b> em reais.\nExemplo: <code>20.00</code>",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_affiliate_min_withdrawal)
    await callback.answer()


@router.message(AdminStates.editing_affiliate_min_withdrawal)
async def msg_aff_min_withdrawal(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return
    raw = (message.text or "").replace(",", ".").strip()
    try:
        val = Decimal(raw)
        if val < 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer("❌ Valor inválido. Ex: <code>20.00</code>")
        return

    val = val.quantize(Decimal("0.01"))
    old = await config_service.get_str(session, "affiliate_min_withdrawal", "20.00")
    await config_service.set_config(session, "affiliate_min_withdrawal", f"{val:.2f}")
    await _log_audit(
        session, message.from_user.id, "edit_affiliate_min_withdrawal",
        old_value={"min_withdrawal": old},
        new_value={"min_withdrawal": f"{val:.2f}"},
    )
    await message.answer(f"✅ Saque mínimo: <b>R$ {val:.2f}</b>")
    await state.clear()

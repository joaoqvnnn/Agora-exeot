# ============================================
# 🔔 ADMIN NOTIFICATIONS — Larizinha Store
# ============================================
# Configuração REAL das notificações automáticas.
# Todos os botões funcionam de verdade.
#
# Cobre os eventos:
#   - Compra realizada
#   - Pix criado
#   - Pix pago
#   - Pix expirado
#   - Estoque baixo
#   - Estoque reabastecido
#   - Saque solicitado
#   - Saque aprovado
#   - Saque recusado
#   - Gift Card resgatado
#   - Nova comissão de afiliado
#   - Manutenção
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
from core.models import Admin, AuditLog
from core.services import config as config_service


router = Router(name="admin_notifications")


# ============================================
# 📚 EVENTOS DISPONÍVEIS
# ============================================
EVENTS: dict[str, dict] = {
    "notif_purchase": {
        "label": "🛒 Compra realizada",
        "description": "Quando um cliente compra",
        "default": "true",
    },
    "notif_pix_created": {
        "label": "💳 Pix criado",
        "description": "Quando um Pix é gerado",
        "default": "false",
    },
    "notif_pix_paid": {
        "label": "✅ Pix pago",
        "description": "Quando um Pix é confirmado",
        "default": "true",
    },
    "notif_pix_expired": {
        "label": "⌛ Pix expirado",
        "description": "Quando um Pix vence",
        "default": "false",
    },
    "notif_stock_low": {
        "label": "📉 Estoque baixo",
        "description": "Quando o estoque cai abaixo do limite",
        "default": "true",
    },
    "notif_stock_restocked": {
        "label": "📈 Estoque reabastecido",
        "description": "Quando adiciona logins",
        "default": "true",
    },
    "notif_withdrawal_request": {
        "label": "💸 Saque solicitado",
        "description": "Quando alguém pede saque",
        "default": "true",
    },
    "notif_withdrawal_approved": {
        "label": "✅ Saque aprovado",
        "description": "Quando o saque é pago",
        "default": "true",
    },
    "notif_withdrawal_rejected": {
        "label": "❌ Saque recusado",
        "description": "Quando o saque é recusado",
        "default": "true",
    },
    "notif_gift_redeemed": {
        "label": "🎁 Gift Card resgatado",
        "description": "Quando resgata um gift",
        "default": "true",
    },
    "notif_affiliate_commission": {
        "label": "🤝 Comissão gerada",
        "description": "Quando um afiliado recebe comissão",
        "default": "false",
    },
    "notif_maintenance": {
        "label": "🔧 Manutenção",
        "description": "Quando o bot entra/sai de manutenção",
        "default": "true",
    },
}


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
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_notif:menu")]
        ]
    )


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_notif:menu")
async def cb_notif_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    # Conta eventos ativos
    active_count = 0
    for key in EVENTS.keys():
        enabled = await config_service.get_bool(
            session, key, EVENTS[key]["default"] == "true"
        )
        if enabled:
            active_count += 1

    total = len(EVENTS)

    # Canal de destino
    logs_channel = await config_service.get_str(session, "logs_channel_id", "")

    text = (
        "🔔 <b>NOTIFICAÇÕES AUTOMÁTICAS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 Eventos ativos: <b>{active_count}/{total}</b>\n"
        f"📢 Canal de logs: <code>{logs_channel or 'Não definido'}</code>\n\n"
        "As notificações são enviadas para o <b>canal de logs</b> "
        "configurado em <i>Configurações Gerais</i>.\n\n"
        "Toque em um evento para ligar/desligar:"
    )

    rows: list[list[InlineKeyboardButton]] = []

    for key, info in EVENTS.items():
        enabled = await config_service.get_bool(
            session, key, info["default"] == "true"
        )
        icon = "🟢" if enabled else "🔴"
        rows.append([
            InlineKeyboardButton(
                text=f"{icon} {info['label']}",
                callback_data=f"adm_notif:toggle:{key}",
            )
        ])

    rows.append([
        InlineKeyboardButton(text="⚙️ Canal de Destino", callback_data="adm_notif:set_channel")
    ])
    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:config")
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 🟢 / 🔴 TOGGLE EVENTO
# ============================================
@router.callback_query(F.data.startswith("adm_notif:toggle:"))
async def cb_notif_toggle(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    try:
        key = callback.data.split(":", 2)[2]
    except IndexError:
        await callback.answer("❌ Valor inválido.", show_alert=True)
        return

    if key not in EVENTS:
        await callback.answer("❌ Evento desconhecido.", show_alert=True)
        return

    info = EVENTS[key]
    current = await config_service.get_bool(
        session, key, info["default"] == "true"
    )
    new = not current

    await config_service.set_config(session, key, "true" if new else "false")

    await _log_audit(
        session,
        callback.from_user.id,
        "toggle_notification",
        old_value={key: current},
        new_value={key: new},
    )

    status = "🟢 LIGADO" if new else "🔴 DESLIGADO"
    await callback.answer(f"{info['label']}: {status}", show_alert=True)

    callback.data = "adm_notif:menu"
    await cb_notif_menu(callback, session)


# ============================================
# ⚙️ CANAL DE DESTINO
# ============================================
@router.callback_query(F.data == "adm_notif:set_channel")
async def cb_notif_set_channel(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    current = await config_service.get_str(session, "logs_channel_id", "Não definido")

    await callback.message.answer(
        "📢 <b>CANAL DE DESTINO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Atual:</b> <code>{current}</code>\n\n"
        "Envie o ID do canal/grupo que vai receber as notificações.\n\n"
        "Formato: <code>-1001234567890</code>\n\n"
        "💡 Pra descobrir o ID:\n"
        "1. Adicione o bot como admin do canal\n"
        "2. Encaminhe uma mensagem do canal para @userinfobot",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(notif_field="logs_channel_id")
    await callback.answer()


@router.message(AdminStates.editing_config_value)
async def msg_notif_save_channel(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    data = await state.get_data()
    field = data.get("notif_field")

    if field != "logs_channel_id":
        return

    raw = (message.text or "").strip()

    try:
        channel_id = int(raw)
    except ValueError:
        await message.answer("❌ ID inválido. Deve ser um número.")
        return

    # Testa enviar uma mensagem de teste
    try:
        await message.bot.send_message(
            chat_id=channel_id,
            text=(
                "✅ <b>Canal de notificações configurado!</b>\n\n"
                "Você vai receber aqui as notificações automáticas "
                "do sistema."
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        await message.answer(
            f"❌ Não consegui enviar mensagem pra esse canal.\n\n"
            f"<b>Erro:</b> <code>{str(e)[:200]}</code>\n\n"
            f"Verifique se o bot é <b>admin</b> no canal."
        )
        return

    old = await config_service.get_str(session, "logs_channel_id", "")
    await config_service.set_config(session, "logs_channel_id", str(channel_id))

    await _log_audit(
        session,
        message.from_user.id,
        "edit_notif_channel",
        old_value={"logs_channel_id": old},
        new_value={"logs_channel_id": str(channel_id)},
    )

    await message.answer(
        f"✅ Canal de notificações definido: <code>{channel_id}</code>"
    )
    await state.clear()


# ============================================
# 🧪 TESTAR NOTIFICAÇÕES
# ============================================
@router.callback_query(F.data == "adm_notif:test")
async def cb_notif_test(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    channel_id_raw = await config_service.get_str(session, "logs_channel_id", "")
    if not channel_id_raw:
        await callback.answer("❌ Canal não configurado.", show_alert=True)
        return

    try:
        channel_id = int(channel_id_raw)
    except ValueError:
        await callback.answer("❌ ID do canal inválido.", show_alert=True)
        return

    await callback.answer("🧪 Enviando teste...", show_alert=False)

    # Envia notificação de exemplo
    try:
        await callback.bot.send_message(
            chat_id=channel_id,
            text=(
                "🧪 <b>TESTE DE NOTIFICAÇÃO</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Se você está vendo esta mensagem, as notificações "
                "automáticas estão funcionando! ✅\n\n"
                "🕐 Enviado pelo admin para teste."
            ),
            parse_mode="HTML",
        )
        await callback.answer("✅ Notificação de teste enviada!", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ Erro: {str(e)[:100]}", show_alert=True)


# ============================================
# 🔔 FUNÇÕES UTILITÁRIAS (usadas por outros módulos)
# ============================================
async def send_notification(
    bot,
    session: AsyncSession,
    event_key: str,
    text: str,
    reply_markup=None,
    media_url: str | None = None,
    media_type: str = "text",
) -> bool:
    """
    Envia uma notificação para o canal de logs,
    respeitando se o evento está ativo.
    """
    info = EVENTS.get(event_key)
    if info is None:
        return False

    enabled = await config_service.get_bool(
        session, event_key, info["default"] == "true"
    )
    if not enabled:
        return False

    channel_id_raw = await config_service.get_str(session, "logs_channel_id", "")
    if not channel_id_raw:
        return False

    try:
        channel_id = int(channel_id_raw)
    except ValueError:
        return False

    try:
        if media_type == "photo" and media_url:
            await bot.send_photo(
                chat_id=channel_id,
                photo=media_url,
                caption=text,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
        elif media_type == "video" and media_url:
            await bot.send_video(
                chat_id=channel_id,
                video=media_url,
                caption=text,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
        else:
            await bot.send_message(
                chat_id=channel_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        return True
    except Exception as e:
        from loguru import logger

        logger.warning(f"⚠️ Falha ao enviar notificação '{event_key}': {e}")
        return False


# ============================================
# 📤 NOTIFICAÇÃO: NOVA COMPRA
# ============================================
async def notify_purchase(
    bot,
    session: AsyncSession,
    order_code: str,
    user_id: int,
    product_name: str,
    amount: float,
    quantity: int = 1,
) -> bool:
    """Envia notificação de nova compra."""
    user_masked = f"{str(user_id)[:3]}***{str(user_id)[-2:]}" if len(str(user_id)) > 5 else str(user_id)
    valor = f"{amount:.2f}".replace(".", ",")

    text = (
        f"💎 <b>NOVO ACESSO LIBERADO</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Usuário: <code>{user_masked}</code>\n"
        f"📦 Plano: <b>{product_name}</b>\n"
        f"🔢 Quantidade: <b>{quantity}</b>\n"
        f"💵 Valor: <b>R$ {valor}</b>\n"
        f"🔑 TX: <code>{order_code[:12]}...</code>\n\n"
        f"🚀 Acesso liberado automaticamente"
    )

    from datetime import datetime, timezone

    text += f"\n🕐 Data: {datetime.now(timezone.utc).strftime('%d/%m/%Y, %H:%M')}"

    return await send_notification(bot, session, "notif_purchase", text)


# ============================================
# 📤 NOTIFICAÇÃO: PIX PAGO
# ============================================
async def notify_pix_paid(
    bot,
    session: AsyncSession,
    user_id: int,
    amount: float,
    bonus: float = 0.0,
) -> bool:
    """Envia notificação de Pix pago."""
    user_masked = f"{str(user_id)[:3]}***{str(user_id)[-2:]}" if len(str(user_id)) > 5 else str(user_id)
    valor = f"{amount:.2f}".replace(".", ",")
    bonus_txt = f"R$ {bonus:.2f}".replace(".", ",") if bonus > 0 else "—"

    text = (
        f"✅ <b>PIX CONFIRMADO</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Usuário: <code>{user_masked}</code>\n"
        f"💵 Valor: <b>R$ {valor}</b>\n"
        f"🎁 Bônus: <b>{bonus_txt}</b>\n\n"
        f"💰 Saldo creditado automaticamente."
    )

    return await send_notification(bot, session, "notif_pix_paid", text)


# ============================================
# 📤 NOTIFICAÇÃO: SAQUE SOLICITADO
# ============================================
async def notify_withdrawal_request(
    bot,
    session: AsyncSession,
    user_id: int,
    amount: float,
    method: str,
) -> bool:
    """Envia notificação de saque solicitado."""
    user_masked = f"{str(user_id)[:3]}***{str(user_id)[-2:]}" if len(str(user_id)) > 5 else str(user_id)
    valor = f"{amount:.2f}".replace(".", ",")

    text = (
        f"💸 <b>NOVO SAQUE SOLICITADO</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Usuário: <code>{user_masked}</code>\n"
        f"💰 Valor: <b>R$ {valor}</b>\n"
        f"💼 Método: <b>{method.upper()}</b>\n\n"
        f"⏳ Aguardando aprovação."
    )

    return await send_notification(bot, session, "notif_withdrawal_request", text)


# ============================================
# 📤 NOTIFICAÇÃO: ESTOQUE BAIXO
# ============================================
async def notify_stock_low(
    bot,
    session: AsyncSession,
    product_name: str,
    remaining: int,
    threshold: int,
) -> bool:
    """Envia notificação de estoque baixo."""
    text = (
        f"📉 <b>ESTOQUE BAIXO</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 Produto: <b>{product_name}</b>\n"
        f"🔢 Restam: <b>{remaining}</b> unidade(s)\n"
        f"⚠️ Limite: <b>{threshold}</b>\n\n"
        f"💡 Considere reabastecer!"
    )

    return await send_notification(bot, session, "notif_stock_low", text)


# ============================================
# 📤 NOTIFICAÇÃO: ESTOQUE REABASTECIDO
# ============================================
async def notify_stock_restocked(
    bot,
    session: AsyncSession,
    product_name: str,
    quantity_added: int,
    total: int,
) -> bool:
    """Envia notificação de estoque reabastecido."""
    text = (
        f"📈 <b>ESTOQUE REABASTECIDO</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 Produto: <b>{product_name}</b>\n"
        f"➕ Adicionado: <b>{quantity_added}</b> unidade(s)\n"
        f"📊 Total em estoque: <b>{total}</b>\n\n"
        f"✅ Pronto para venda!"
    )

    return await send_notification(bot, session, "notif_stock_restocked", text)


# ============================================
# 📤 NOTIFICAÇÃO: GIFT CARD RESGATADO
# ============================================
async def notify_gift_redeemed(
    bot,
    session: AsyncSession,
    user_id: int,
    value: float,
    code: str,
) -> bool:
    """Envia notificação de gift card resgatado."""
    user_masked = f"{str(user_id)[:3]}***{str(user_id)[-2:]}" if len(str(user_id)) > 5 else str(user_id)
    valor = f"{value:.2f}".replace(".", ",")

    text = (
        f"🎁 <b>GIFT CARD RESGATADO</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Usuário: <code>{user_masked}</code>\n"
        f"🎫 Código: <code>{code}</code>\n"
        f"💵 Valor: <b>R$ {valor}</b>\n\n"
        f"✅ Saldo creditado automaticamente."
    )

    return await send_notification(bot, session, "notif_gift_redeemed", text)

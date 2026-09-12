# ============================================
# 📧 DELIVERY EMAIL — Larizinha Store
# ============================================
# Fluxo COMPLETO de entrega por e-mail.
#
# Passo a passo:
#   1. Cliente compra produto
#   2. Escolhe "Receber por E-mail"
#   3. Digita o e-mail
#   4. Sistema valida formato
#   5. Sistema envia código de 6 dígitos
#   6. Cliente digita o código
#   7. Sistema valida (persistente + limite de tentativas)
#   8. Sistema envia OUTRO e-mail com LINK DE ACESSO
#   9. Cliente clica no link → website
#   10. Cliente digita a senha cadastrada
#   11. Produto é liberado (login/senha/código)
#
# O Telegram NUNCA recebe os dados do produto —
# eles ficam apenas no website protegido por senha.
#
# ✨ ATUALIZADO:
#   - Usa `email_verification` (persistente no banco)
#   - Códigos sobrevivem a restart
#   - Cooldown de 60s entre reenvios
#   - Auditoria de cada ação
# ============================================

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

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

from bot.states.states import PurchaseStates
from core.models import (
    Order,
    OrderStatus,
    StockItem,
    StockStatus,
    User,
    VerificationCodeType,
)
from core.services import config as config_service
from core.services import email as email_service
from core.services import email_verification
from core.services import stock as stock_service


router = Router(name="delivery_email")


# ============================================
# ⚙️ CONFIGURAÇÕES
# ============================================
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.IGNORECASE)


# ============================================
# 🧰 AUXILIARES
# ============================================
def _mask_email(email: str) -> str:
    """Mascara o e-mail: joao@gmail.com → j***o@g***l.com"""
    try:
        local, domain = email.split("@", 1)
        if len(local) <= 2:
            local_m = local[0] + "*"
        else:
            local_m = local[0] + "*" * (len(local) - 2) + local[-1]

        dom_parts = domain.split(".")
        dom_name = dom_parts[0]
        if len(dom_name) <= 2:
            dom_m = dom_name[0] + "*"
        else:
            dom_m = dom_name[0] + "*" * (len(dom_name) - 2) + dom_name[-1]

        return f"{local_m}@{dom_m}.{'.'.join(dom_parts[1:])}"
    except Exception:
        return email


async def _edit_or_send(callback: CallbackQuery, text: str, keyboard=None) -> None:
    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
    except Exception:
        try:
            await callback.message.answer(
                text,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
        except Exception as e:
            logger.warning(f"⚠️ Falha ao exibir: {e}")


def _cancel_keyboard(back_data: str = "buy:cancel:0:0") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancelar", callback_data=back_data)]
        ]
    )


def _cancel_and_resend_keyboard(
    back_data: str = "buy:cancel:0:0",
) -> InlineKeyboardMarkup:
    """Botões de cancelar + reenviar código."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🔄 Reenviar Código",
                callback_data="buy:resend_email_code",
            )],
            [InlineKeyboardButton(
                text="✏️ Trocar E-mail",
                callback_data="buy:change_email",
            )],
            [InlineKeyboardButton(
                text="❌ Cancelar",
                callback_data=back_data,
            )],
        ]
    )


# ============================================
# 📧 INICIAR FLUXO DE ENTREGA POR E-MAIL
# ============================================
@router.callback_query(F.data.startswith("buy:delivery_email:"))
async def cb_start_email_delivery(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """
    Cliente escolheu "Receber por E-mail".
    Pede o e-mail.
    """
    parts = callback.data.split(":")
    try:
        order_id = int(parts[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Pedido inválido.", show_alert=True)
        return

    # Busca o pedido
    order = await session.get(Order, order_id)
    if order is None or order.user_id != user.id:
        await callback.answer("❌ Pedido não encontrado.", show_alert=True)
        return

    # Salva no state
    await state.update_data(
        delivery_order_id=order_id,
        delivery_email=None,
        delivery_attempts=0,
    )

    text = (
        f"📧 <b>Digite seu e-mail para receber o produto</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 Produto: <b>{order.product_name}</b>\n"
        f"💰 Valor: <b>R$ {float(order.total_price):.2f}</b>\n\n"
        f"O produto será enviado para a caixa de entrada do e-mail.\n\n"
        f"📮 <b>Envie seu e-mail agora:</b>\n"
        f"Exemplo: <code>seuemail@gmail.com</code>"
    )

    await _edit_or_send(callback, text, _cancel_keyboard())
    await callback.answer()

    await state.set_state(PurchaseStates.waiting_email)


# ============================================
# 📩 RECEBER E VALIDAR E-MAIL
# ============================================
@router.message(PurchaseStates.waiting_email)
async def msg_receive_email(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    raw = (message.text or "").strip().lower()

    # /cancelar
    if raw.startswith("/cancelar") or raw.startswith("/start"):
        await state.clear()
        await message.answer("❌ Envio por e-mail cancelado.")
        return

    if not raw:
        await message.answer("❌ Envie um e-mail válido.")
        return

    # Valida formato
    if not EMAIL_REGEX.match(raw):
        await message.answer(
            "❌ <b>E-mail inválido.</b>\n\n"
            "Digite um endereço de e-mail válido.\n"
            "Exemplo: <code>seuemail@gmail.com</code>"
        )
        return

    # Pega dados do state
    data = await state.get_data()
    order_id = data.get("delivery_order_id")

    if not order_id:
        await message.answer("❌ Sessão expirada. Use /start.")
        await state.clear()
        return

    # Salva o e-mail
    await state.update_data(delivery_email=raw)

    # Envia código (persistente no banco)
    result = await email_verification.send_product_delivery_code(
        session=session,
        email=raw,
        order_id=order_id,
        telegram_id=user.telegram_id,
    )

    if not result.get("success"):
        error = result.get("error", "Erro desconhecido")
        cooldown = result.get("cooldown_seconds")

        if cooldown:
            await message.answer(
                f"⏰ <b>Aguarde {cooldown}s</b> antes de solicitar outro código."
            )
        else:
            await message.answer(
                f"❌ <b>Erro ao enviar o e-mail.</b>\n\n"
                f"<code>{error}</code>\n\n"
                f"Tente novamente ou use outro e-mail."
            )
        return

    expiration = result.get("expiration_minutes", 15)

    await message.answer(
        f"📩 <b>Enviamos um código para seu e-mail.</b>\n\n"
        f"📧 E-mail: <b>{_mask_email(raw)}</b>\n\n"
        f"Digite o <b>código de 6 dígitos</b> que você recebeu:\n\n"
        f"<i>O código expira em {expiration} minutos.</i>",
        reply_markup=_cancel_and_resend_keyboard(),
    )

    await state.set_state(PurchaseStates.waiting_email_code)


# ============================================
# 🔢 VALIDAR CÓDIGO
# ============================================
@router.message(PurchaseStates.waiting_email_code)
async def msg_validate_code(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    raw = (message.text or "").strip()

    # /cancelar
    if raw.startswith("/cancelar") or raw.startswith("/start"):
        await state.clear()
        await message.answer("❌ Envio por e-mail cancelado.")
        return

    # Extrai só dígitos
    code_typed = "".join(c for c in raw if c.isdigit())

    if len(code_typed) != 6:
        await message.answer(
            "❌ <b>Código inválido.</b>\n"
            "Envie os 6 dígitos recebidos no e-mail."
        )
        return

    data = await state.get_data()
    email = data.get("delivery_email")
    order_id = data.get("delivery_order_id")

    if not email or not order_id:
        await message.answer("❌ Sessão expirada. Use /start.")
        await state.clear()
        return

    # Valida (persistente no banco)
    result = await email_verification.verify_product_delivery(
        session=session,
        email=email,
        code=code_typed,
    )

    if not result.get("success"):
        error = result.get("error", "Código incorreto")
        attempts = result.get("attempts_remaining")
        locked = result.get("locked")
        expired = result.get("expired")

        if locked:
            await message.answer(
                f"🚫 {error}\n\n"
                f"Envie /start pra começar de novo."
            )
            await state.clear()
            return

        if expired:
            await message.answer(
                f"⏰ {error}\n\n"
                f"Envie /start pra começar de novo."
            )
            await state.clear()
            return

        extra = ""
        if attempts is not None:
            extra = f"\n\nTentativas restantes: <b>{attempts}</b>"

        await message.answer(f"❌ {error}{extra}")
        return

    # ✓ Código correto → entrega por e-mail
    await _deliver_by_email(
        message=message,
        state=state,
        session=session,
        user=user,
        order_id=order_id,
        email=email,
    )


# ============================================
# 📤 ENTREGAR POR E-MAIL (envia link de acesso)
# ============================================
async def _deliver_by_email(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    order_id: int,
    email: str,
) -> None:
    """
    Código validado. Agora:
      1. Atualiza método de entrega do pedido
      2. Gera token de ativação
      3. Envia e-mail com LINK DE ACESSO
      4. Confirma no Telegram (sem mostrar dados)
    """
    order = await session.get(Order, order_id)
    if order is None:
        await message.answer("❌ Pedido não encontrado.")
        await state.clear()
        return

    # Atualiza método de entrega
    order.delivery_method = "email"
    order.delivery_target = email
    session.add(order)

    # Busca os itens
    stmt = select(StockItem).where(StockItem.order_id == order_id)
    result = await session.execute(stmt)
    items = list(result.scalars().all())

    if not items:
        await message.answer("❌ Nenhum item encontrado para este pedido.")
        await state.clear()
        return

    # Salva o e-mail no usuário (se ainda não tiver)
    if not user.email:
        user.email = email
        user.email_verified = True
        session.add(user)

    await session.commit()

    # Envia o e-mail com LINK DE ACESSO
    send_result = await email_service.send_product_email(
        session=session,
        to_email=email,
        user=user,
        order=order,
        items=items,
    )

    if not send_result.get("success"):
        await message.answer(
            f"❌ <b>Erro ao enviar o e-mail.</b>\n\n"
            f"<code>{send_result.get('error', 'Erro')}</code>\n\n"
            f"Tente novamente mais tarde."
        )
        await state.clear()
        return

    # Sucesso!
    await message.answer(
        f"✅ <b>Produto enviado para o seu e-mail!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📧 E-mail: <b>{_mask_email(email)}</b>\n\n"
        f"📩 <b>Abra seu e-mail agora.</b>\n\n"
        f"No e-mail, você encontrará um botão "
        f"<b>🔓 ACESSAR PRODUTO</b>.\n\n"
        f"💡 Ao clicar, você será levado para a página de ativação "
        f"onde precisará digitar sua <b>senha de saque</b> para liberar "
        f"o produto.\n\n"
        f"⚠️ <b>Por segurança, os dados do produto não são enviados "
        f"no Telegram.</b>"
    )

    # Notifica canal de logs
    try:
        from bot.handlers.admin.notifications import notify_purchase
        await notify_purchase(
            bot=message.bot,
            session=session,
            order_code=order.order_code,
            user_id=user.telegram_id,
            product_name=order.product_name,
            amount=float(order.total_price),
            quantity=order.quantity,
        )
    except Exception as e:
        logger.debug(f"⚠️ Falha ao notificar: {e}")

    # Marca como entregue
    try:
        await stock_service.mark_as_delivered(session, [i.id for i in items])
        await session.commit()
    except Exception:
        pass

    await state.clear()


# ============================================
# 🔄 REENVIAR CÓDIGO
# ============================================
@router.callback_query(F.data == "buy:resend_email_code")
async def cb_resend_code(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    email = data.get("delivery_email")
    order_id = data.get("delivery_order_id")

    if not email or not order_id:
        await callback.answer("❌ Sessão expirada.", show_alert=True)
        return

    # Reenvia (com cooldown)
    result = await email_verification.send_product_delivery_code(
        session=session,
        email=email,
        order_id=order_id,
        telegram_id=user.telegram_id,
    )

    if not result.get("success"):
        error = result.get("error", "Erro")
        cooldown = result.get("cooldown_seconds")

        if cooldown:
            await callback.answer(
                f"⏰ Aguarde {cooldown}s", show_alert=True
            )
        else:
            await callback.answer(f"❌ {error}", show_alert=True)
        return

    await callback.answer("📩 Novo código enviado!", show_alert=True)


# ============================================
# ✏️ TROCAR E-MAIL
# ============================================
@router.callback_query(F.data == "buy:change_email")
async def cb_change_email(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """Cliente quer digitar outro e-mail."""
    data = await state.get_data()
    order_id = data.get("delivery_order_id")

    await state.update_data(
        delivery_email=None,
        delivery_attempts=0,
    )

    text = (
        f"📧 <b>Digite o novo e-mail</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Envie um e-mail válido.\n"
        f"Exemplo: <code>seuemail@gmail.com</code>"
    )

    await _edit_or_send(callback, text, _cancel_keyboard())
    await callback.answer()

    await state.set_state(PurchaseStates.waiting_email)


# ============================================
# 📱 ESCOLHA DO MÉTODO DE ENTREGA
# ============================================
@router.callback_query(F.data.startswith("buy:choose_delivery:"))
async def cb_choose_delivery(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    """
    Cliente escolhe entre Telegram, WhatsApp ou E-mail.
    """
    parts = callback.data.split(":")
    try:
        order_id = int(parts[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Pedido inválido.", show_alert=True)
        return

    order = await session.get(Order, order_id)
    if order is None or order.user_id != user.id:
        await callback.answer("❌ Pedido não encontrado.", show_alert=True)
        return

    text = (
        f"📬 <b>Como deseja receber o produto?</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 Produto: <b>{order.product_name}</b>\n"
        f"🎫 Pedido: <code>{order.order_code[:12]}...</code>\n\n"
        f"Escolha o método de entrega:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🤖 Telegram (aqui mesmo)",
                callback_data=f"buy:delivery_telegram:{order_id}",
            )],
            [InlineKeyboardButton(
                text="📧 E-mail (com link de ativação)",
                callback_data=f"buy:delivery_email:{order_id}",
            )],
            [InlineKeyboardButton(
                text="📱 WhatsApp",
                callback_data=f"buy:delivery_whatsapp:{order_id}",
            )],
            [InlineKeyboardButton(
                text="❌ Cancelar",
                callback_data=f"buy:cancel:{order_id}:0",
            )],
        ]
    )

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()


# ============================================
# 📱 ENTREGA POR TELEGRAM (imediata)
# ============================================
@router.callback_query(F.data.startswith("buy:delivery_telegram:"))
async def cb_delivery_telegram(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    """Entrega imediata no Telegram."""
    parts = callback.data.split(":")
    try:
        order_id = int(parts[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Pedido inválido.", show_alert=True)
        return

    order = await session.get(Order, order_id)
    if order is None or order.user_id != user.id:
        await callback.answer("❌ Pedido não encontrado.", show_alert=True)
        return

    order.delivery_method = "telegram"
    order.delivery_target = str(user.telegram_id)
    session.add(order)
    await session.commit()

    await callback.answer("📤 Entregando no Telegram...", show_alert=False)

    try:
        from core.services import delivery as delivery_service
        await delivery_service.deliver_order(
            session=session,
            bot=callback.bot,
            order_id=order_id,
        )
    except Exception as e:
        logger.exception(f"❌ Erro na entrega: {e}")
        await callback.message.answer(
            "❌ Erro ao entregar. Tente novamente em instantes."
        )


# ============================================
# 📲 ENTREGA POR WHATSAPP
# ============================================
@router.callback_query(F.data.startswith("buy:delivery_whatsapp:"))
async def cb_delivery_whatsapp(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """Entrega via WhatsApp (verifica se tem número cadastrado)."""
    parts = callback.data.split(":")
    try:
        order_id = int(parts[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Pedido inválido.", show_alert=True)
        return

    order = await session.get(Order, order_id)
    if order is None or order.user_id != user.id:
        await callback.answer("❌ Pedido não encontrado.", show_alert=True)
        return

    # Verifica se tem WhatsApp
    if not user.whatsapp:
        text = (
            f"📱 <b>Você ainda não cadastrou seu WhatsApp.</b>\n\n"
            f"Digite seu número agora para receber o produto:"
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="❌ Cancelar",
                    callback_data=f"buy:cancel:{order_id}:0",
                )]
            ]
        )
        await _edit_or_send(callback, text, keyboard)
        await callback.answer()

        await state.update_data(
            delivery_order_id=order_id,
            delivery_method="whatsapp",
        )
        await state.set_state(PurchaseStates.waiting_whatsapp)
        return

    # Já tem WhatsApp → confirma envio
    text = (
        f"📱 <b>Enviar para seu WhatsApp?</b>\n\n"
        f"📞 Número: <code>{user.whatsapp}</code>\n\n"
        f"📦 Produto: <b>{order.product_name}</b>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="✅ Enviar agora",
                callback_data=f"buy:confirm_whatsapp:{order_id}",
            )],
            [InlineKeyboardButton(
                text="✏️ Trocar número",
                callback_data=f"buy:change_whatsapp:{order_id}",
            )],
            [InlineKeyboardButton(
                text="❌ Cancelar",
                callback_data=f"buy:cancel:{order_id}:0",
            )],
        ]
    )

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()


# ============================================
# 📱 RECEBER WHATSAPP (se não tiver cadastrado)
# ============================================
@router.message(PurchaseStates.waiting_whatsapp)
async def msg_receive_whatsapp(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    raw = (message.text or "").strip()

    if raw.startswith("/cancelar") or raw.startswith("/start"):
        await state.clear()
        await message.answer("❌ Envio por WhatsApp cancelado.")
        return

    digits = "".join(c for c in raw if c.isdigit())

    if len(digits) < 10 or len(digits) > 13:
        await message.answer(
            "❌ <b>Número inválido.</b>\n\n"
            "Use DDD + Número.\n"
            "Exemplo: <code>11999998888</code>"
        )
        return

    # Salva no user
    user.whatsapp = digits
    session.add(user)
    await session.commit()

    data = await state.get_data()
    order_id = data.get("delivery_order_id")

    if not order_id:
        await state.clear()
        await message.answer("❌ Sessão expirada.")
        return

    await state.clear()

    # Confirma envio
    text = (
        f"✅ <b>WhatsApp salvo!</b>\n\n"
        f"📞 <code>{digits}</code>\n\n"
        f"Deseja receber o produto agora?"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="📤 Enviar agora",
                callback_data=f"buy:confirm_whatsapp:{order_id}",
            )],
            [InlineKeyboardButton(
                text="🔙 Menu",
                callback_data="menu:voltar",
            )],
        ]
    )

    await message.answer(text, reply_markup=keyboard)


# ============================================
# ✅ CONFIRMAR ENVIO WHATSAPP
# ============================================
@router.callback_query(F.data.startswith("buy:confirm_whatsapp:"))
async def cb_confirm_whatsapp(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    parts = callback.data.split(":")
    try:
        order_id = int(parts[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Pedido inválido.", show_alert=True)
        return

    order = await session.get(Order, order_id)
    if order is None or order.user_id != user.id:
        await callback.answer("❌ Pedido não encontrado.", show_alert=True)
        return

    if not user.whatsapp:
        await callback.answer("❌ Cadastre um WhatsApp primeiro.", show_alert=True)
        return

    order.delivery_method = "whatsapp"
    order.delivery_target = user.whatsapp
    session.add(order)
    await session.commit()

    await callback.answer("📤 Enviando para WhatsApp...", show_alert=False)

    # Usa o wa_delivery service
    try:
        from core.services import wa_delivery

        result = await wa_delivery.deliver_order_via_whatsapp(
            session=session,
            order_id=order_id,
        )

        if result.get("success"):
            await callback.message.answer(
                f"✅ <b>Produto enviado para seu WhatsApp!</b>\n\n"
                f"📞 <code>{user.whatsapp}</code>\n\n"
                f"📱 Abra o WhatsApp e confira."
            )
        else:
            await callback.message.answer(
                f"❌ <b>Erro ao enviar.</b>\n\n"
                f"{result.get('error', 'Erro desconhecido')}"
            )
    except Exception as e:
        logger.exception(f"❌ Erro WhatsApp: {e}")
        await callback.message.answer("❌ Erro ao enviar. Tente novamente.")


# ============================================
# ✏️ TROCAR WHATSAPP
# ============================================
@router.callback_query(F.data.startswith("buy:change_whatsapp:"))
async def cb_change_whatsapp(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    parts = callback.data.split(":")
    try:
        order_id = int(parts[2])
    except (ValueError, IndexError):
        order_id = 0

    await state.update_data(
        delivery_order_id=order_id,
        delivery_method="whatsapp",
    )

    await callback.message.answer(
        "📱 <b>Envie seu novo número de WhatsApp</b>\n\n"
        "Formato: DDD + Número (apenas números)\n"
        "Exemplo: <code>11999998888</code>"
    )
    await callback.answer()

    await state.set_state(PurchaseStates.waiting_whatsapp)


# ============================================
# 🔘 NOOP
# ============================================
@router.callback_query(F.data == "buy:delivery_noop")
async def cb_delivery_noop(callback: CallbackQuery) -> None:
    await callback.answer()

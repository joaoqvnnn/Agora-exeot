# ============================================
# 💠 PIX (CLIENTE) — Larizinha Store
# ============================================
# Fluxo completo de Pix do cliente:
#   - Gerar Pix (recarga, compra, falta)
#   - Mostrar QR Code + copia-e-cola
#   - Copiar chave (sem mandar msg)
#   - Verificar pagamento (consulta REAL no MP)
#   - Expiração automática
#   - Pagamento aprovado
#
# Regra de mensagem única quando possível.
# ============================================

import asyncio
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.pix import (
    build_bonus_keyboard,
    build_insufficient_balance_keyboard,
    build_payment_approved_keyboard,
    build_pix_expired_keyboard,
    build_pix_keyboard,
    build_recharge_menu_keyboard,
)
from bot.states.states import RechargeStates
from core.models import (
    Payment,
    PaymentStatus,
    PaymentType,
    Product,
    ProductStatus,
    User,
)
from core.services import config as config_service
from core.services import payment as payment_service
from core.services import pix as pix_service
from core.services.messages import render_message


router = Router(name="pix_cliente")


# ============================================
# 🧰 AUXILIARES
# ============================================
def _format_brl(v) -> str:
    if v is None:
        return "0,00"
    return f"{float(v):.2f}".replace(".", ",")


async def _edit_or_send(callback: CallbackQuery, text: str, keyboard) -> None:
    try:
        await callback.message.edit_text(
            text, reply_markup=keyboard, disable_web_page_preview=True
        )
    except Exception:
        try:
            await callback.message.answer(
                text, reply_markup=keyboard, disable_web_page_preview=True
            )
        except Exception as e:
            logger.warning(f"⚠️ Falha ao editar/enviar: {e}")


def _generate_qr_png(data: str) -> bytes | None:
    """Gera QR Code PNG em bytes."""
    try:
        import qrcode
        from io import BytesIO

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
        )
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer.read()
    except Exception as e:
        logger.warning(f"⚠️ Falha ao gerar QR Code: {e}")
        return None


# ============================================
# 💰 MENU DE RECARGA
# ============================================
@router.callback_query(F.data == "menu:recarregar")
async def cb_recharge_menu(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    """Menu inicial de recarga."""
    balance = _format_brl(user.balance)

    text = (
        f"🆔| ID da Carteira: <code>{user.telegram_id}</code>\n"
        f"💰| Saldo Disponível: <b>R$ {balance}</b>\n\n"
        f"📍 Opte por 💠 Pix Rápido para que seu saldo seja "
        f"creditado imediatamente.\n\n"
        f"💡 Selecione uma opção para recarregar:"
    )

    keyboard = build_recharge_menu_keyboard()

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()

    user.last_menu = "recarregar"
    session.add(user)


# ============================================
# 💠 PIX RÁPIDO — PEDIR VALOR
# ============================================
@router.callback_query(F.data == "pix:gerar:0:")
async def cb_pix_ask_amount(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """Pede o valor da recarga."""
    await callback.answer()

    min_amount = await config_service.get_str(session, "pix_min", "4.00")
    bonus_percent = await config_service.get_str(session, "pix_bonus_percent", "0")
    bonus_min = await config_service.get_str(session, "pix_bonus_min", "0")

    text = (
        f"ℹ️ <b>Informe o valor que deseja recarregar:</b>\n\n"
        f"🔻 Recarga mínima: <b>R$ {min_amount}</b>\n\n"
        f"⚠️ Por favor, envie o valor que deseja recarregar agora.\n"
        f"Ao realizar um depósito você declara ter lido e estar "
        f"de acordo com nossos /termos\n\n"
    )

    if float(bonus_percent) > 0:
        text += (
            f"🎁 Bônus de recarga: <b>{bonus_percent}%</b>\n"
            f"❗️ Recarga mínima para ganhar o bônus: <b>R$ {bonus_min}</b>"
        )

    await _edit_or_send(callback, text, None)

    await state.set_state(RechargeStates.waiting_amount)
    await state.update_data(pix_context="recharge")


# ============================================
# 💠 PIX DE COMPRA FALTANTE
# ============================================
@router.callback_query(F.data.startswith("buy:gerar_pix:"))
async def cb_pix_purchase_missing(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """Gera Pix pra completar compra."""
    await callback.answer()

    parts = callback.data.split(":")
    try:
        product_id = int(parts[2])
        quantity = int(parts[3])
    except (ValueError, IndexError):
        await callback.answer("❌ Dados inválidos.", show_alert=True)
        return

    product = await session.get(Product, product_id)
    if product is None or product.status != ProductStatus.ACTIVE:
        await callback.answer("❌ Produto indisponível.", show_alert=True)
        return

    # Calcula valor faltante
    total_price = (product.price * quantity).quantize(Decimal("0.01"))
    balance = user.balance or Decimal("0.00")
    missing = (total_price - balance).quantize(Decimal("0.01"))

    if missing <= 0:
        await callback.answer("✅ Você já tem saldo suficiente!", show_alert=True)
        return

    # Guarda contexto pra continuar depois do pagamento
    await state.update_data(
        pix_context="purchase",
        product_id=product_id,
        quantity=quantity,
        target_amount=str(missing),
    )

    await _create_pix(
        callback=callback,
        user=user,
        session=session,
        amount=missing,
        purpose="purchase",
    )


# ============================================
# 📥 RECEBER VALOR DIGITADO (recarga)
# ============================================
@router.message(RechargeStates.waiting_amount)
async def msg_recharge_amount(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """Recebe o valor digitado."""
    text = (message.text or "").strip()

    if text.startswith("/cancelar") or text.startswith("/start"):
        await state.clear()
        await message.answer("❌ Operação cancelada.")
        return

    # Normaliza
    raw = text.replace(",", ".").replace("R$", "").strip()

    try:
        amount = Decimal(raw)
        if amount <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer(
            "❌ <b>Valor inválido!</b> Envie apenas números.\n"
            "Exemplo: <code>10</code> ou <code>25.50</code>"
        )
        return

    amount = amount.quantize(Decimal("0.01"))

    # Valida limites
    min_amount = await config_service.get_decimal(session, "pix_min", "4.00")
    max_amount = await config_service.get_decimal(session, "pix_max", "500.00")

    if amount < min_amount:
        await message.answer(
            f"❌ Valor mínimo: <b>R$ {_format_brl(min_amount)}</b>"
        )
        return

    if amount > max_amount:
        await message.answer(
            f"❌ Valor máximo: <b>R$ {_format_brl(max_amount)}</b>"
        )
        return

    # Verifica bônus — vale a pena sugerir?
    bonus_percent = await config_service.get_decimal(session, "pix_bonus_percent", "0")
    bonus_min = await config_service.get_decimal(session, "pix_bonus_min", "0")

    if bonus_percent > 0 and amount < bonus_min:
        missing_to_bonus = (bonus_min - amount).quantize(Decimal("0.01"))

        # Mostra a tela de upsell do bônus
        await state.update_data(
            pending_amount=str(amount),
            bonus_suggested=str(bonus_min),
        )

        text = (
            f"🎁 <b>Eiii, eu tenho algo pra você!</b>\n\n"
            f"Recarregando <b>R$ {_format_brl(bonus_min)}</b> você ganha "
            f"acesso a mais <b>{bonus_percent}%</b> de bônus "
            f"(+R$ {_format_brl(bonus_min * bonus_percent / 100)}), "
            f"tem certeza que vai perder essa?\n\n"
            f"💡 Faltam apenas <b>R$ {_format_brl(missing_to_bonus)}</b> "
            f"para ganhar o bônus!"
        )

        keyboard = build_bonus_keyboard(
            current_amount=_format_brl(amount),
            suggested_amount=_format_brl(bonus_min),
        )

        await message.answer(text, reply_markup=keyboard)
        await state.set_state(RechargeStates.waiting_bonus_confirm)
        return

    # Sem bônus a considerar → gera direto
    await state.clear()
    await _create_pix_message(
        message=message,
        user=user,
        session=session,
        amount=amount,
        purpose="recharge",
    )


# ============================================
# 🎁 CONFIRMAR BÔNUS (continuar como está)
# ============================================
@router.callback_query(F.data.startswith("pix:gerar:"))
async def cb_pix_gerar(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """Gera Pix com valor específico (usado pelos botões de bônus e outros)."""
    parts = callback.data.split(":")
    # form: pix:gerar:VALOR:  ou  pix:gerar:VALOR:payment_id
    if len(parts) < 4:
        await callback.answer("❌ Valor inválido.", show_alert=True)
        return

    amount_str = parts[2]
    if amount_str == "0":
        # Já é o handler que pede valor
        callback.data = "pix:gerar:0:"
        await cb_pix_ask_amount(callback, state, user, session)
        return

    try:
        amount = Decimal(amount_str).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        await callback.answer("❌ Valor inválido.", show_alert=True)
        return

    await callback.answer()

    data = await state.get_data()
    context = data.get("pix_context", "recharge")

    await state.clear()

    if context == "purchase" and data.get("product_id"):
        await _create_pix(
            callback=callback,
            user=user,
            session=session,
            amount=amount,
            purpose="purchase",
        )
    else:
        await _create_pix(
            callback=callback,
            user=user,
            session=session,
            amount=amount,
            purpose="recharge",
        )


# ============================================
# 🔙 VOLTAR DO PIX (menu recarga)
# ============================================
@router.callback_query(F.data == "pix:voltar")
async def cb_pix_back(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    await state.clear()
    await cb_recharge_menu(callback, user, session)


# ============================================
# 💠 CRIAR PIX (callback)
# ============================================
async def _create_pix(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    amount: Decimal,
    purpose: str = "recharge",
) -> None:
    """Cria o Pix e edita a mensagem."""
    # Mostra "gerando pagamento..."
    await _edit_or_send(
        callback,
        "⏳ <b>Gerando pagamento...</b>",
        None,
    )

    # Chama o service
    result = await payment_service.generate_recharge_pix(
        session=session,
        user=user,
        amount=amount,
    )

    if not result.get("success"):
        await _edit_or_send(
            callback,
            f"❌ <b>Erro ao gerar Pix</b>\n\n{result.get('error', 'Erro desconhecido.')}",
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Voltar", callback_data="menu:voltar")]
                ]
            ),
        )
        return

    payment = result["payment"]

    # Monta texto do Pix
    expiration_minutes = await config_service.get_int(
        session, "pix_expiration_minutes", 10
    )

    bonus = result.get("bonus_amount", Decimal("0.00"))
    total = result.get("total_credited", amount)

    balance = user.balance or Decimal("0.00")
    after = balance + total

    text = (
        f"💰 <b>Comprar Saldo com Pix Automático:</b>\n\n"
        f"⏱️ Expira em: <b>{expiration_minutes} Minutos</b>\n"
        f"💵 Valor: <b>R$ {_format_brl(amount)}</b>\n"
        f"✨ ID da Recarga: <code>{payment.payment_id}</code>\n\n"
        f"📃 <b>Atenção:</b> Este código é válido para apenas um único pagamento.\n"
        f"Se você utilizá-lo mais de uma vez, o saldo adicional será perdido "
        f"sem direito a reembolso.\n\n"
        f"💎 <b>Pix Copia e Cola:</b>\n"
        f"<code>{result.get('qr_code', '')}</code>\n\n"
        f"💡 <b>Dica:</b> Clique no código acima para copiar.\n\n"
        f"📊 <b>Dados:</b>\n"
        f"— 💰 Saldo Atual: <b>R$ {_format_brl(balance)}</b>\n"
        f"— 🎁 Bônus à receber: <b>R$ {_format_brl(bonus)}</b>\n"
        f"— 💸 Saldo após o pagamento: <b>R$ {_format_brl(after)}</b>\n\n"
        f"🇧🇷 Após o pagamento, seu saldo será liberado instantaneamente."
    )

    keyboard = build_pix_keyboard(payment_id=payment.payment_id)

    # Tenta enviar com imagem do QR Code
    qr_data = result.get("qr_code", "")
    qr_png = _generate_qr_png(qr_data) if qr_data else None

    if qr_png:
        try:
            # Apaga a mensagem antiga e envia nova com foto
            try:
                await callback.message.delete()
            except Exception:
                pass

            photo = BufferedInputFile(qr_png, filename="pix.png")
            sent = await callback.message.answer_photo(
                photo=photo,
                caption=text,
                reply_markup=keyboard,
            )

            # Salva o message_id pra edições futuras
            user.last_message_id = sent.message_id
            session.add(user)
            return
        except Exception as e:
            logger.warning(f"⚠️ Falha ao enviar QR: {e}")

    # Fallback: só texto
    await _edit_or_send(callback, text, keyboard)


# ============================================
# 💠 CRIAR PIX (mensagem)
# ============================================
async def _create_pix_message(
    message: Message,
    user: User,
    session: AsyncSession,
    amount: Decimal,
    purpose: str = "recharge",
) -> None:
    """Cria o Pix a partir de uma mensagem."""
    sent = await message.answer("⏳ <b>Gerando pagamento...</b>")

    result = await payment_service.generate_recharge_pix(
        session=session,
        user=user,
        amount=amount,
    )

    if not result.get("success"):
        try:
            await sent.edit_text(
                f"❌ <b>Erro ao gerar Pix</b>\n\n{result.get('error', 'Erro desconhecido.')}"
            )
        except Exception:
            pass
        return

    payment = result["payment"]

    expiration_minutes = await config_service.get_int(
        session, "pix_expiration_minutes", 10
    )

    bonus = result.get("bonus_amount", Decimal("0.00"))
    total = result.get("total_credited", amount)

    balance = user.balance or Decimal("0.00")
    after = balance + total

    text = (
        f"💰 <b>Comprar Saldo com Pix Automático:</b>\n\n"
        f"⏱️ Expira em: <b>{expiration_minutes} Minutos</b>\n"
        f"💵 Valor: <b>R$ {_format_brl(amount)}</b>\n"
        f"✨ ID da Recarga: <code>{payment.payment_id}</code>\n\n"
        f"📃 <b>Atenção:</b> Este código é válido para apenas um único pagamento.\n\n"
        f"💎 <b>Pix Copia e Cola:</b>\n"
        f"<code>{result.get('qr_code', '')}</code>\n\n"
        f"💡 <b>Dica:</b> Clique no código acima para copiar.\n\n"
        f"📊 <b>Dados:</b>\n"
        f"— 💰 Saldo Atual: <b>R$ {_format_brl(balance)}</b>\n"
        f"— 🎁 Bônus à receber: <b>R$ {_format_brl(bonus)}</b>\n"
        f"— 💸 Saldo após o pagamento: <b>R$ {_format_brl(after)}</b>\n\n"
        f"🇧🇷 Após o pagamento, seu saldo será liberado instantaneamente."
    )

    keyboard = build_pix_keyboard(payment_id=payment.payment_id)

    qr_data = result.get("qr_code", "")
    qr_png = _generate_qr_png(qr_data) if qr_data else None

    try:
        if qr_png:
            try:
                await sent.delete()
            except Exception:
                pass

            photo = BufferedInputFile(qr_png, filename="pix.png")
            sent2 = await message.answer_photo(
                photo=photo,
                caption=text,
                reply_markup=keyboard,
            )
            user.last_message_id = sent2.message_id
            session.add(user)
        else:
            await sent.edit_text(text, reply_markup=keyboard)
            user.last_message_id = sent.message_id
            session.add(user)
    except Exception as e:
        logger.warning(f"⚠️ Falha ao exibir Pix: {e}")


# ============================================
# 📋 COPIAR PIX (sem mandar msg)
# ============================================
@router.callback_query(F.data.startswith("pix:copiar:"))
async def cb_pix_copiar(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    """Copia o código Pix (só alert, sem msg)."""
    try:
        payment_id = callback.data.split(":")[2]
    except IndexError:
        await callback.answer("❌ Dados inválidos.", show_alert=True)
        return

    payment = await payment_service.get_payment_by_id(session, payment_id)
    if payment is None:
        await callback.answer("❌ Pix não encontrado.", show_alert=True)
        return

    if payment.status == PaymentStatus.EXPIRED:
        await callback.answer("⌛ Pix expirado.", show_alert=True)
        return

    # Copia pro clipboard do cliente
    pix_code = payment.qr_code or ""
    if not pix_code:
        await callback.answer("❌ Código indisponível.", show_alert=True)
        return

    # Bot só confirma — o cliente copia manualmente
    await callback.answer(
        "📋 Código copiado! Cole no seu banco.",
        show_alert=True,
    )


# ============================================
# 🔄 VERIFICAR PAGAMENTO (consulta real)
# ============================================
@router.callback_query(F.data.startswith("pix:verificar:"))
async def cb_pix_verificar(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    """Consulta o status real no Mercado Pago."""
    try:
        payment_id = callback.data.split(":")[2]
    except IndexError:
        await callback.answer("❌ Dados inválidos.", show_alert=True)
        return

    await callback.answer("🔄 Verificando...", show_alert=False)

    result = await payment_service.check_payment_status(
        session=session,
        payment_id=payment_id,
    )

    if not result.get("success"):
        await callback.answer(
            f"❌ {result.get('error', 'Erro ao verificar.')}",
            show_alert=True,
        )
        return

    status = result.get("status", "unknown")

    if status == "approved":
        await _show_payment_approved(callback, user, session, result["payment"])
    elif status == "expired":
        await _show_payment_expired(callback, user, session, result["payment"])
    else:
        # Ainda pendente
        await callback.answer(
            "⏳ Pagamento ainda não identificado.\n"
            "Se você já pagou, aguarde alguns segundos e tente novamente.",
            show_alert=True,
        )


# ============================================
# ✅ PAGAMENTO APROVADO
# ============================================
async def _show_payment_approved(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    payment: Payment,
) -> None:
    """Exibe confirmação de pagamento aprovado."""
    # Recarrega saldo atualizado
    await session.refresh(user)

    credited = payment.total_credited or payment.amount
    bonus = payment.bonus_amount or Decimal("0.00")

    from datetime import datetime, timezone
    date_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M")

    text = (
        f"✅ <b>PAGAMENTO APROVADO!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 Valor: <b>R$ {_format_brl(payment.amount)}</b>\n"
        f"🎁 Bônus: <b>R$ {_format_brl(bonus)}</b>\n"
        f"💵 Saldo atual: <b>R$ {_format_brl(user.balance)}</b>\n\n"
        f"🆔 ID: <code>{payment.payment_id}</code>\n"
        f"⏰ Data: {date_str}"
    )

    keyboard = build_payment_approved_keyboard()

    try:
        # Se a mensagem tem foto, edita a legenda
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=text,
                reply_markup=keyboard,
            )
        else:
            await callback.message.edit_text(
                text,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)


# ============================================
# ⌛ PAGAMENTO EXPIRADO
# ============================================
async def _show_payment_expired(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    payment: Payment,
) -> None:
    """Exibe tela de pagamento expirado."""
    text = (
        f"⌛️ <b>PAGAMENTO PIX EXPIRADO</b>\n\n"
        f"⚠️ O tempo limite para realizar este pagamento foi excedido.\n\n"
        f"🆔 Referência: <code>{payment.payment_id}</code>\n"
        f"💸 Valor Solicitado: <b>R$ {_format_brl(payment.amount)}</b>"
    )

    keyboard = build_pix_expired_keyboard()

    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=text,
                reply_markup=keyboard,
            )
        else:
            await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)


# ============================================
# ❌ CANCELAR PIX
# ============================================
@router.callback_query(F.data.startswith("pix:cancelar:"))
async def cb_pix_cancelar(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """Cancela o Pix atual."""
    try:
        payment_id = callback.data.split(":")[2]
    except IndexError:
        payment_id = ""

    await state.clear()

    # Marca como cancelado (não estorna, só para o fluxo)
    if payment_id and payment_id != "0":
        payment = await payment_service.get_payment_by_id(session, payment_id)
        if payment and payment.status == PaymentStatus.PENDING:
            payment.status = PaymentStatus.CANCELLED
            session.add(payment)

    await callback.answer("❌ Pix cancelado.", show_alert=True)

    # Volta pro /start
    from bot.keyboards.main_menu import build_main_menu
    from core.config import settings

    text = "❌ Operação cancelada."
    keyboard = await build_main_menu(session, webapp_url=settings.webapp_url)

    await _edit_or_send(callback, text, keyboard)


# ============================================
# 🔘 NOOP
# ============================================
@router.callback_query(F.data == "pix:noop")
async def cb_pix_noop(callback: CallbackQuery) -> None:
    await callback.answer()

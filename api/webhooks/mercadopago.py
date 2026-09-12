# ============================================
# 💳 WEBHOOK MERCADO PAGO — Larizinha Store
# ============================================
# Recebe notificações de pagamento do Mercado Pago.
# Confirma pagamentos REAIS e credita saldo.
#
# ⚠️ IMPORTANTE:
#   Este arquivo usa APIRouter (FastAPI), NÃO o
#   Router do aiogram. Não confundir!
# ============================================

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from loguru import logger
from sqlalchemy import select

from core.database import AsyncSessionLocal
from core.models import Payment, PaymentStatus, User
from core.services import payment as payment_service
from core.services import pix as pix_service


# ⚠️ APIRouter (FastAPI) — NÃO usar aiogram.Router aqui
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ============================================
# 💳 ENDPOINT PRINCIPAL
# ============================================
@router.post("/mercadopago")
async def mercadopago_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_signature: str | None = Header(None, alias="x-signature"),
    x_request_id: str | None = Header(None, alias="x-request-id"),
):
    """Recebe webhook do Mercado Pago."""
    try:
        try:
            body: dict[str, Any] = await request.json()
        except Exception:
            body = {}

        payment_id = None

        if isinstance(body, dict):
            data = body.get("data", {})
            if isinstance(data, dict):
                payment_id = data.get("id")
            if not payment_id:
                payment_id = body.get("id")

        if not payment_id:
            payment_id = request.query_params.get("data.id")
            if not payment_id:
                payment_id = request.query_params.get("id")

        if not payment_id:
            logger.warning("⚠️ Webhook MP sem ID de pagamento")
            return {"ok": True, "ignored": "sem id"}

        payment_id = str(payment_id)
        logger.info(f"💳 Webhook MP recebido: {payment_id}")

        if x_signature:
            valid = await pix_service.verify_webhook_signature(
                x_signature=x_signature,
                x_request_id=x_request_id or "",
                data_id=payment_id,
            )
            if not valid:
                logger.warning(f"🚫 Assinatura inválida: {payment_id}")
                raise HTTPException(status_code=401, detail="invalid signature")

        background_tasks.add_task(_process_mp_payment, payment_id)
        return {"ok": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"❌ Erro no webhook MP: {e}")
        return {"ok": True, "error": str(e)[:100]}


# ============================================
# 🔄 PROCESSAR PAGAMENTO
# ============================================
async def _process_mp_payment(mp_payment_id: str) -> None:
    async with AsyncSessionLocal() as session:
        try:
            mp_result = await pix_service.get_payment_status(mp_payment_id)

            if not mp_result.get("success"):
                logger.warning(f"⚠️ Falha MP {mp_payment_id}: {mp_result.get('error')}")
                return

            mp_status = mp_result.get("status", "unknown")
            mp_detail = mp_result.get("status_detail", "")

            logger.info(f"💳 MP {mp_payment_id} → status={mp_status}")

            stmt = select(Payment).where(Payment.external_id == mp_payment_id)
            result = await session.execute(stmt)
            payment = result.scalar_one_or_none()

            if payment is None:
                logger.warning(f"⚠️ Pagamento {mp_payment_id} não encontrado")
                return

            if payment.status == PaymentStatus.APPROVED:
                logger.info(f"ℹ️ Pagamento {payment.payment_id} já aprovado")
                return

            if pix_service.is_payment_approved(mp_status):
                result = await payment_service.confirm_payment(
                    session=session,
                    payment_id=payment.payment_id,
                    external_id=mp_payment_id,
                    raw_webhook=mp_result.get("raw"),
                )

                if result.get("success"):
                    await session.commit()
                    logger.success(f"✅ Pagamento confirmado: {payment.payment_id}")
                    await _notify_payment_approved(session, payment)
                    if result.get("user"):
                        await _handle_post_approval(session, result["user"], payment)
                else:
                    logger.error(f"❌ Erro: {result.get('error')}")
                    await session.rollback()

            elif pix_service.is_payment_expired(mp_status, mp_detail):
                if payment.status == PaymentStatus.PENDING:
                    payment.status = PaymentStatus.EXPIRED
                    session.add(payment)
                    await session.commit()
                    logger.info(f"⌛ Expirando: {payment.payment_id}")
                    await _notify_payment_expired(session, payment)

            elif mp_status in ("rejected", "cancelled"):
                if payment.status == PaymentStatus.PENDING:
                    payment.status = PaymentStatus.REJECTED
                    payment.webhook_data = mp_result.get("raw")
                    session.add(payment)
                    await session.commit()
                    logger.info(f"❌ Rejeitado: {payment.payment_id}")

            else:
                logger.debug(f"ℹ️ {payment.payment_id} ainda pendente")

        except Exception as e:
            logger.exception(f"❌ Erro: {e}")
            await session.rollback()


# ============================================
# 📢 NOTIFICAÇÕES
# ============================================
async def _notify_payment_approved(session, payment: Payment) -> None:
    try:
        from bot.handlers.admin.notifications import notify_pix_paid
        from bot.loader import bot

        await notify_pix_paid(
            bot=bot,
            session=session,
            user_id=payment.user_telegram_id,
            amount=float(payment.amount),
            bonus=float(payment.bonus_amount or Decimal("0.00")),
        )
    except Exception as e:
        logger.debug(f"⚠️ Falha ao notificar: {e}")


async def _notify_payment_expired(session, payment: Payment) -> None:
    try:
        from bot.loader import bot

        text = (
            f"⌛️ <b>PAGAMENTO PIX EXPIRADO</b>\n\n"
            f"⚠️ O tempo limite foi excedido.\n\n"
            f"🆔 Referência: <code>{payment.payment_id}</code>\n"
            f"💸 Valor: <b>R$ {float(payment.amount):.2f}</b>\n\n"
            f"💡 Use /menu para gerar um novo Pix."
        )

        await bot.send_message(
            chat_id=payment.user_telegram_id,
            text=text,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.debug(f"⚠️ Falha ao notificar: {e}")


# ============================================
# 📦 PÓS-APROVAÇÃO
# ============================================
async def _handle_post_approval(session, user: User, payment: Payment) -> None:
    from core.models import PaymentType

    try:
        from bot.loader import bot

        if payment.type == PaymentType.RECHARGE:
            credited = payment.total_credited or payment.amount
            bonus = payment.bonus_amount or Decimal("0.00")

            text = (
                f"✅ <b>PAGAMENTO APROVADO!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"💰 Valor: <b>R$ {float(payment.amount):.2f}</b>\n"
            )
            if bonus > 0:
                text += f"🎁 Bônus: <b>R$ {float(bonus):.2f}</b>\n"

            text += (
                f"💵 Saldo atual: <b>R$ {float(user.balance):.2f}</b>\n\n"
                f"🆔 ID: <code>{payment.payment_id}</code>"
            )

            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=text,
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.warning(f"⚠️ Falha ao notificar: {e}")

        elif payment.type == PaymentType.PURCHASE and payment.order_id:
            from core.services import delivery as delivery_service

            result = await delivery_service.deliver_order(
                session=session,
                bot=bot,
                order_id=payment.order_id,
            )

            if not result.get("success"):
                logger.error(f"❌ Falha ao entregar: {result.get('error')}")

        await session.commit()

    except Exception as e:
        logger.exception(f"❌ Erro pós-aprovação: {e}")
        await session.rollback()


# ============================================
# 🧪 TESTES
# ============================================
@router.get("/mercadopago/test")
async def mercadopago_test():
    return {
        "ok": True,
        "message": "Webhook MP ativo",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/mercadopago/check/{payment_id}")
async def check_payment_manually(
    payment_id: str,
    background_tasks: BackgroundTasks,
):
    background_tasks.add_task(_process_mp_payment, payment_id)
    return {"ok": True, "message": f"Verificação agendada para {payment_id}"}

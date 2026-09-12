# ============================================
# 💰 PAYMENT SERVICE — Larizinha Store
# ============================================
# Regras de negócio do pagamento Pix.
# Cria registro no banco, confirma, credita saldo,
# expira pagamentos vencidos, registra bônus,
# gera comissão de afiliado e entrega pedidos.
# ============================================

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import (
    AffiliateCommission,
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
    PaymentType,
    User,
)
from core.services import config as config_service
from core.services import pix as pix_service


# ============================================
# 🆕 CRIAÇÃO DE REGISTRO
# ============================================
async def create_payment_record(
    session: AsyncSession,
    user: User,
    amount: Decimal,
    payment_type: PaymentType,
    expiration_minutes: int = 10,
    order_id: Optional[int] = None,
) -> Payment:
    """Cria um registro de pagamento pendente no banco."""
    payment = Payment(
        payment_id=uuid.uuid4().hex,
        user_id=user.id,
        user_telegram_id=user.telegram_id,
        type=payment_type,
        amount=amount,
        status=PaymentStatus.PENDING,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=expiration_minutes),
        order_id=order_id,
    )
    session.add(payment)
    await session.flush()
    logger.info(
        f"💰 Pagamento criado: {payment.payment_id} | "
        f"user={user.telegram_id} | R$ {amount} | tipo={payment_type.value}"
    )
    return payment


# ============================================
# 💠 GERAR PIX COMPLETO (recarga)
# ============================================
async def generate_recharge_pix(
    session: AsyncSession,
    user: User,
    amount: Decimal,
) -> dict[str, Any]:
    """
    Gera um Pix completo de recarga:
      1. Valida limites (min/max)
      2. Calcula bônus
      3. Cria registro no banco
      4. Chama Mercado Pago
      5. Atualiza registro com dados do Pix
    Retorna dict com sucesso, dados do Pix e do banco.
    """
    # 1. Valida limites
    min_amount = await config_service.get_decimal(session, "pix_min", "4.00")
    max_amount = await config_service.get_decimal(session, "pix_max", "500.00")

    if amount < min_amount:
        return {"success": False, "error": f"Valor mínimo: R$ {min_amount}"}
    if amount > max_amount:
        return {"success": False, "error": f"Valor máximo: R$ {max_amount}"}

    # 2. Bônus
    bonus_percent = await config_service.get_decimal(session, "pix_bonus_percent", "0")
    bonus_min = await config_service.get_decimal(session, "pix_bonus_min", "0")

    bonus_amount = Decimal("0.00")
    if bonus_percent > 0 and amount >= bonus_min:
        bonus_amount = (amount * bonus_percent / Decimal("100")).quantize(
            Decimal("0.01")
        )

    total_credited = amount + bonus_amount

    # 3. Expiração
    expiration_minutes = await config_service.get_int(session, "pix_expiration_minutes", 10)

    # 4. Cria registro
    payment = await create_payment_record(
        session=session,
        user=user,
        amount=amount,
        payment_type=PaymentType.RECHARGE,
        expiration_minutes=expiration_minutes,
    )
    payment.bonus_amount = bonus_amount
    payment.total_credited = total_credited
    session.add(payment)
    await session.flush()

    # 5. Chama Mercado Pago
    external_ref = pix_service.generate_external_reference(user.telegram_id)
    result = await pix_service.create_pix_payment(
        amount=amount,
        description=f"Recarga {settings_name()} - R$ {amount}",
        payer_email=user.email or f"user{user.telegram_id}@telegram.local",
        external_reference=external_ref,
        expiration_minutes=expiration_minutes,
        payer_first_name=user.first_name or "Cliente",
        payer_last_name=user.last_name or "Telegram",
    )

    if not result.get("success"):
        payment.status = PaymentStatus.REJECTED
        session.add(payment)
        return {
            "success": False,
            "error": result.get("error", "Erro ao gerar Pix."),
        }

    # 6. Atualiza registro com dados do MP
    payment.external_id = result["payment_id"]
    payment.qr_code = result.get("qr_code", "")
    payment.qr_code_image_url = result.get("ticket_url", "")
    payment.webhook_data = result.get("raw", {})
    session.add(payment)
    await session.flush()

    return {
        "success": True,
        "payment": payment,
        "qr_code": result.get("qr_code", ""),
        "qr_code_base64": result.get("qr_code_base64", ""),
        "ticket_url": result.get("ticket_url", ""),
        "expires_at": payment.expires_at,
        "bonus_amount": bonus_amount,
        "total_credited": total_credited,
    }


# ============================================
# ✅ CONFIRMAR PAGAMENTO
# ============================================
async def confirm_payment(
    session: AsyncSession,
    payment_id: str,
    external_id: Optional[str] = None,
    raw_webhook: Optional[dict] = None,
) -> dict[str, Any]:
    """
    Confirma um pagamento (chamado pelo webhook).
    Credita o saldo, gera comissão, atualiza status.
    Retorna dict com resultado.
    """
    # Busca pagamento pelo ID interno ou externo
    payment = await _find_payment(session, payment_id, external_id)
    if payment is None:
        return {"success": False, "error": "Pagamento não encontrado."}

    # Já foi aprovado? Idempotência
    if payment.status == PaymentStatus.APPROVED:
        logger.info(f"ℹ️ Pagamento {payment.payment_id} já estava aprovado.")
        return {"success": True, "already_approved": True, "payment": payment}

    # Carrega usuário
    user = await session.get(User, payment.user_id)
    if user is None:
        return {"success": False, "error": "Usuário não encontrado."}

    # Marca como aprovado
    payment.status = PaymentStatus.APPROVED
    payment.paid_at = datetime.now(timezone.utc)
    if raw_webhook:
        payment.webhook_data = raw_webhook
    session.add(payment)

    # Credita saldo (valor + bônus)
    credited = payment.total_credited or payment.amount
    user.balance = (user.balance or Decimal("0.00")) + credited
    user.total_recharged = (user.total_recharged or Decimal("0.00")) + payment.amount
    session.add(user)

    logger.info(
        f"✅ Pagamento aprovado: {payment.payment_id} | "
        f"+R$ {credited} pra user {user.telegram_id} | "
        f"novo saldo: R$ {user.balance}"
    )

    # Comissão de afiliado
    if user.referred_by:
        await _create_affiliate_commission(session, user, payment)

    # Se for compra, finaliza pedido
    if payment.type == PaymentType.PURCHASE and payment.order_id:
        await _finalize_order(session, payment.order_id)

    return {
        "success": True,
        "payment": payment,
        "user": user,
        "credited": credited,
    }


# ============================================
# ❌ EXPIRAR PAGAMENTO
# ============================================
async def expire_payment(
    session: AsyncSession,
    payment_id: str,
) -> bool:
    """Marca um pagamento como expirado."""
    stmt = select(Payment).where(Payment.payment_id == payment_id)
    result = await session.execute(stmt)
    payment = result.scalar_one_or_none()

    if payment is None or payment.status != PaymentStatus.PENDING:
        return False

    payment.status = PaymentStatus.EXPIRED
    session.add(payment)
    logger.info(f"⌛ Pagamento expirado: {payment.payment_id}")
    return True


async def expire_overdue_payments(session: AsyncSession) -> list[Payment]:
    """Marca como expirado todos os pagamentos vencidos. Roda no cron."""
    now = datetime.now(timezone.utc)
    stmt = select(Payment).where(
        Payment.status == PaymentStatus.PENDING,
        Payment.expires_at < now,
    )
    result = await session.execute(stmt)
    payments = list(result.scalars().all())

    for p in payments:
        p.status = PaymentStatus.EXPIRED
        session.add(p)

    if payments:
        logger.info(f"⌛ {len(payments)} pagamentos expirados")
    return payments


# ============================================
# 🔍 CONSULTA
# ============================================
async def get_payment_by_id(
    session: AsyncSession,
    payment_id: str,
) -> Optional[Payment]:
    stmt = select(Payment).where(Payment.payment_id == payment_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_pending_by_user(
    session: AsyncSession,
    user_telegram_id: int,
) -> list[Payment]:
    stmt = select(Payment).where(
        Payment.user_telegram_id == user_telegram_id,
        Payment.status == PaymentStatus.PENDING,
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def check_payment_status(
    session: AsyncSession,
    payment_id: str,
) -> dict[str, Any]:
    """
    Consulta o status atual: banco + Mercado Pago.
    Se o MP disser aprovado e o banco ainda estiver pendente,
    confirma automaticamente.
    """
    payment = await get_payment_by_id(session, payment_id)
    if payment is None:
        return {"success": False, "error": "Pagamento não encontrado."}

    # Se já aprovado no banco, retorna
    if payment.status == PaymentStatus.APPROVED:
        return {"success": True, "status": "approved", "payment": payment}

    # Se expirou no banco
    now = datetime.now(timezone.utc)
    if payment.status == PaymentStatus.PENDING and payment.expires_at < now:
        await expire_payment(session, payment_id)
        return {"success": True, "status": "expired", "payment": payment}

    # Consulta MP se tiver external_id
    if not payment.external_id:
        return {"success": True, "status": payment.status.value, "payment": payment}

    mp_result = await pix_service.get_payment_status(payment.external_id)
    if not mp_result.get("success"):
        return {
            "success": True,
            "status": payment.status.value,
            "payment": payment,
            "warning": mp_result.get("error"),
        }

    mp_status = mp_result.get("status", "unknown")

    if pix_service.is_payment_approved(mp_status):
        result = await confirm_payment(
            session=session,
            payment_id=payment.payment_id,
            external_id=payment.external_id,
            raw_webhook=mp_result.get("raw"),
        )
        if result.get("success"):
            return {"success": True, "status": "approved", "payment": payment}

    if pix_service.is_payment_expired(mp_status, mp_result.get("status_detail", "")):
        await expire_payment(session, payment_id)
        return {"success": True, "status": "expired", "payment": payment}

    return {"success": True, "status": payment.status.value, "payment": payment}


# ============================================
# 🧰 AUXILIARES
# ============================================
async def _find_payment(
    session: AsyncSession,
    payment_id: str,
    external_id: Optional[str] = None,
) -> Optional[Payment]:
    """Procura pagamento por ID interno ou externo."""
    stmt = select(Payment).where(Payment.payment_id == payment_id)
    result = await session.execute(stmt)
    payment = result.scalar_one_or_none()
    if payment is not None:
        return payment

    if external_id:
        stmt = select(Payment).where(Payment.external_id == external_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    return None


async def _create_affiliate_commission(
    session: AsyncSession,
    user: User,
    payment: Payment,
) -> Optional[AffiliateCommission]:
    """Cria comissão pro afiliado que indicou o usuário."""
    from core.services import config as cfg

    commission_percent = await cfg.get_decimal(session, "affiliate_commission", "20.0")
    if commission_percent <= 0:
        return None

    commission_value = (payment.amount * commission_percent / Decimal("100")).quantize(
        Decimal("0.01")
    )

    commission = AffiliateCommission(
        affiliate_telegram_id=user.referred_by,
        referred_telegram_id=user.telegram_id,
        payment_id=payment.id,
        base_amount=payment.amount,
        percentage=commission_percent,
        commission=commission_value,
    )
    session.add(commission)

    # Credita no saldo de afiliado
    stmt = select(User).where(User.telegram_id == user.referred_by)
    result = await session.execute(stmt)
    affiliate_user = result.scalar_one_or_none()
    if affiliate_user is not None:
        affiliate_user.affiliate_balance = (
            affiliate_user.affiliate_balance or Decimal("0.00")
        ) + commission_value
        session.add(affiliate_user)

    await session.flush()
    logger.info(
        f"🤝 Comissão criada: R$ {commission_value} pro afiliado "
        f"{user.referred_by} (indicou {user.telegram_id})"
    )
    return commission


async def _finalize_order(
    session: AsyncSession,
    order_id: int,
) -> None:
    """Marca pedido como pago."""
    order = await session.get(Order, order_id)
    if order is None:
        return
    order.status = OrderStatus.PAID
    session.add(order)
    logger.info(f"🛒 Pedido {order_id} marcado como PAGO")


def settings_name() -> str:
    """Nome do bot pras descrições de pagamento."""
    from core.config import settings

    return "Larizinha Store"

# ============================================
# 💸 WITHDRAWAL SERVICE — Larizinha Store
# ============================================
# Processamento REAL de saques de afiliados.
# Suporta DOIS modos:
#   1. MANUAL  → admin aprova, sistema marca como pago
#   2. AUTOMÁTICO → sistema envia o Pix via Mercado Pago
#
# Pix via Mercado Pago API:
#   POST /v1/payments com payment_method_id="pix"
#   e payer com chave Pix → transferência direta
#
# Se falhar, ESTORNA o saldo do afiliado.
# ============================================

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import httpx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.models import (
    User,
    Withdrawal,
    WithdrawalMethod,
    WithdrawalStatus,
)


MP_API_BASE = "https://api.mercadopago.com"
TIMEOUT = 30.0


# ============================================
# 📋 CRIAR SOLICITAÇÃO
# ============================================
async def create_withdrawal_request(
    session: AsyncSession,
    user: User,
    amount: Decimal,
    method: WithdrawalMethod,
    pix_key: Optional[str] = None,
    pix_key_type: Optional[str] = None,
    bank_data: Optional[dict] = None,
) -> Withdrawal:
    """Registra uma solicitação de saque pendente."""
    wd = Withdrawal(
        user_id=user.id,
        user_telegram_id=user.telegram_id,
        amount=amount,
        method=method,
        status=WithdrawalStatus.PENDING,
        pix_key=pix_key,
        pix_key_type=pix_key_type,
        bank_data=bank_data,
    )
    session.add(wd)
    await session.flush()
    logger.info(
        f"💸 Saque solicitado: #{wd.id} | user={user.telegram_id} | "
        f"R$ {amount} | método={method.value}"
    )
    return wd


# ============================================
# 💠 ENVIAR PIX REAL (Mercado Pago)
# ============================================
async def send_pix_transfer(
    pix_key: str,
    pix_key_type: str,
    amount: Decimal,
    description: str = "Saque de afiliado",
    external_reference: Optional[str] = None,
) -> dict[str, Any]:
    """
    Envia Pix real via Mercado Pago (API de transferências).

    IMPORTANTE:
      - Requer conta Mercado Pago com saldo disponível
      - Requer permissão de transferência (API /v1/transfers)
      - Se falhar, retorna {success: False} e estorna

    Retorna dict:
      - success: bool
      - transfer_id: str
      - status: str
      - error: str
    """
    if not settings.mercadopago_access_token:
        return {"success": False, "error": "Token MP não configurado."}

    idempotency_key = str(uuid.uuid4())
    if external_reference is None:
        external_reference = f"withdraw_{idempotency_key[:8]}"

    # Normaliza chave Pix conforme tipo
    key_normalized = _normalize_pix_key(pix_key, pix_key_type)

    payload = {
        "amount": float(amount),
        "currency_id": "BRL",
        "description": description,
        "external_reference": external_reference,
        "payment_method_id": "pix",
        "pix": {
            "key": key_normalized,
            "type": pix_key_type.upper() if pix_key_type else "CPF",
        },
    }

    headers = {
        "Authorization": f"Bearer {settings.mercadopago_access_token}",
        "Content-Type": "application/json",
        "X-Idempotency-Key": idempotency_key,
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{MP_API_BASE}/v1/transfers",
                json=payload,
                headers=headers,
            )

        if response.status_code not in (200, 201):
            logger.error(
                f"❌ Erro MP transferência ({response.status_code}): "
                f"{response.text[:300]}"
            )
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text[:150]}",
            }

        data = response.json()

        transfer_id = str(data.get("id", ""))
        status = data.get("status", "unknown")

        logger.info(
            f"💠 Pix enviado: transfer_id={transfer_id} | "
            f"R$ {amount} | status={status}"
        )

        return {
            "success": True,
            "transfer_id": transfer_id,
            "status": status,
            "raw": data,
        }

    except httpx.TimeoutException:
        return {"success": False, "error": "Timeout na comunicação com MP."}
    except httpx.RequestError as e:
        logger.error(f"❌ Erro de rede na transferência: {e}")
        return {"success": False, "error": f"Erro de rede: {e}"}
    except Exception as e:
        logger.exception(f"❌ Erro inesperado na transferência: {e}")
        return {"success": False, "error": str(e)}


# ============================================
# ✅ PROCESSAR SAQUE (AUTOMÁTICO)
# ============================================
async def process_withdrawal_auto(
    session: AsyncSession,
    withdrawal_id: int,
) -> dict[str, Any]:
    """
    Processa saque automaticamente via Pix MP.
    Se falhar, estorna o saldo do afiliado.
    """
    wd = await session.get(Withdrawal, withdrawal_id)
    if wd is None:
        return {"success": False, "error": "Saque não encontrado."}

    if wd.status not in (WithdrawalStatus.PENDING, WithdrawalStatus.PROCESSING):
        return {
            "success": False,
            "error": f"Saque já está como {wd.status.value}.",
        }

    if wd.method != WithdrawalMethod.PIX:
        return {"success": False, "error": "Saque automático só por Pix."}

    if not wd.pix_key:
        return {"success": False, "error": "Chave Pix não cadastrada."}

    # Marca como processando
    wd.status = WithdrawalStatus.PROCESSING
    session.add(wd)
    await session.flush()

    # Envia Pix
    result = await send_pix_transfer(
        pix_key=wd.pix_key,
        pix_key_type=wd.pix_key_type or "CPF",
        amount=wd.amount,
        description=f"Saque #{wd.id} - Larizinha Store",
        external_reference=f"wd_{wd.id}",
    )

    if not result.get("success"):
        # ESTORNA
        await _refund_withdrawal(session, wd, reason=result.get("error", "Erro no Pix"))
        return {
            "success": False,
            "error": result.get("error"),
            "refunded": True,
        }

    # Sucesso
    wd.status = WithdrawalStatus.PAID
    wd.processed_at = datetime.now(timezone.utc)
    wd.external_transaction_id = result.get("transfer_id")
    session.add(wd)

    logger.info(f"✅ Saque #{wd.id} pago automaticamente via Pix.")
    return {
        "success": True,
        "transfer_id": result.get("transfer_id"),
        "withdrawal": wd,
    }


# ============================================
# 🏦 TRANSFERÊNCIA BANCÁRIA (manual do admin)
# ============================================
async def process_withdrawal_bank_manual(
    session: AsyncSession,
    withdrawal_id: int,
    admin_id: int,
    external_tx_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Marca saque bancário como pago (admin fez transferência
    manualmente pelo banco).
    """
    wd = await session.get(Withdrawal, withdrawal_id)
    if wd is None:
        return {"success": False, "error": "Saque não encontrado."}

    if wd.status not in (WithdrawalStatus.PENDING, WithdrawalStatus.PROCESSING):
        return {
            "success": False,
            "error": f"Saque já está como {wd.status.value}.",
        }

    wd.status = WithdrawalStatus.PAID
    wd.processed_at = datetime.now(timezone.utc)
    wd.approved_by = admin_id
    if external_tx_id:
        wd.external_transaction_id = external_tx_id
    session.add(wd)

    logger.info(f"✅ Saque bancário #{wd.id} marcado como pago por admin {admin_id}")
    return {"success": True, "withdrawal": wd}


# ============================================
# ❌ RECUSAR / ESTORNAR
# ============================================
async def reject_withdrawal(
    session: AsyncSession,
    withdrawal_id: int,
    admin_id: int,
    reason: str = "",
) -> dict[str, Any]:
    """Recusa um saque e estorna o saldo."""
    wd = await session.get(Withdrawal, withdrawal_id)
    if wd is None:
        return {"success": False, "error": "Saque não encontrado."}

    if wd.status in (WithdrawalStatus.PAID, WithdrawalStatus.REFUNDED):
        return {"success": False, "error": "Saque já foi processado."}

    await _refund_withdrawal(session, wd, reason=reason, admin_id=admin_id)
    return {"success": True, "withdrawal": wd}


async def _refund_withdrawal(
    session: AsyncSession,
    wd: Withdrawal,
    reason: str = "",
    admin_id: Optional[int] = None,
) -> None:
    """Devolve o saldo ao afiliado e marca como estornado."""
    user = await session.get(User, wd.user_id)
    if user is not None:
        user.affiliate_balance = (
            user.affiliate_balance or Decimal("0.00")
        ) + wd.amount
        session.add(user)
        logger.info(
            f"↩️ Estornado R$ {wd.amount} pro afiliado {user.telegram_id} "
            f"(saque #{wd.id})"
        )

    wd.status = WithdrawalStatus.REFUNDED
    wd.processed_at = datetime.now(timezone.utc)
    wd.rejection_reason = reason
    if admin_id:
        wd.approved_by = admin_id
    session.add(wd)


# ============================================
# 🔍 DADOS DO SAQUE
# ============================================
async def get_user_withdrawals(
    session: AsyncSession,
    user_id: int,
    limit: int = 20,
) -> list[Withdrawal]:
    stmt = (
        select(Withdrawal)
        .where(Withdrawal.user_id == user_id)
        .order_by(Withdrawal.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_pending_withdrawals(
    session: AsyncSession,
) -> list[Withdrawal]:
    stmt = (
        select(Withdrawal)
        .where(Withdrawal.status == WithdrawalStatus.PENDING)
        .order_by(Withdrawal.created_at.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ============================================
# 🧰 HELPERS
# ============================================
def _normalize_pix_key(key: str, key_type: Optional[str]) -> str:
    """Normaliza a chave Pix conforme o tipo."""
    key = key.strip()
    if not key_type:
        return key

    kt = key_type.lower()
    if kt in ("cpf", "cnpj"):
        return "".join(c for c in key if c.isdigit())
    if kt == "phone":
        digits = "".join(c for c in key if c.isdigit())
        if not digits.startswith("+") and not digits.startswith("55"):
            digits = "55" + digits
        return f"+{digits}"
    if kt == "email":
        return key.lower()
    return key


def is_valid_pix_key(key: str, key_type: str) -> bool:
    """Valida formato básico de chave Pix."""
    import re

    kt = key_type.lower()
    if kt == "cpf":
        digits = "".join(c for c in key if c.isdigit())
        return len(digits) == 11
    if kt == "cnpj":
        digits = "".join(c for c in key if c.isdigit())
        return len(digits) == 14
    if kt == "email":
        return bool(re.match(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", key.lower()))
    if kt == "phone":
        digits = "".join(c for c in key if c.isdigit())
        return 10 <= len(digits) <= 13
    if kt == "random":
        return len(key) >= 32
    return len(key) > 0


def get_pix_type_label(key_type: str) -> str:
    """Retorna o rótulo amigável do tipo de chave."""
    labels = {
        "cpf": "CPF",
        "cnpj": "CNPJ",
        "email": "E-mail",
        "phone": "Telefone",
        "random": "Chave Aleatória",
    }
    return labels.get(key_type.lower(), key_type.upper())

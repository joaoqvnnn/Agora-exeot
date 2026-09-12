# ============================================
# 💳 PIX SERVICE — Larizinha Store
# ============================================
# Integração REAL com o Mercado Pago (Pix).
# Usa httpx async direto na API v1 (mais confiável
# que o SDK oficial síncrono).
#
# Fluxo:
#   1. create_pix_payment() → cria cobrança Pix
#   2. Retorna ID, QR Code (imagem base64), copia e cola
#   3. Webhook confirma → payment_service credita saldo
#   4. get_payment_status() consulta sob demanda
# ============================================

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

import httpx
from loguru import logger

from core.config import settings


# ============================================
# 🌐 CONFIGURAÇÃO DA API
# ============================================
MP_API_BASE = "https://api.mercadopago.com"
TIMEOUT = 30.0


# ============================================
# 📤 CRIAÇÃO DE PAGAMENTO PIX
# ============================================
async def create_pix_payment(
    amount: Decimal,
    description: str,
    payer_email: str,
    external_reference: str,
    expiration_minutes: int = 10,
    notification_url: Optional[str] = None,
    payer_first_name: str = "Cliente",
    payer_last_name: str = "Telegram",
) -> dict[str, Any]:
    """
    Cria uma cobrança Pix no Mercado Pago.

    Retorna dict com:
      - success: bool
      - payment_id: str
      - status: str
      - qr_code: str (copia e cola)
      - qr_code_base64: str (imagem do QR em base64)
      - expires_at: datetime
      - raw: dict (resposta bruta)
      - error: str (se falhou)
    """
    if not settings.mercadopago_access_token:
        return {"success": False, "error": "Token do Mercado Pago não configurado."}

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=expiration_minutes)
    idempotency_key = str(uuid.uuid4())

    payload = {
        "transaction_amount": float(amount),
        "description": description,
        "payment_method_id": "pix",
        "external_reference": external_reference,
        "date_of_expiration": expires_at.strftime("%Y-%m-%dT%H:%M:%S.000-03:00"),
        "notification_url": notification_url or settings.mercadopago_webhook_url,
        "payer": {
            "email": payer_email,
            "first_name": payer_first_name,
            "last_name": payer_last_name,
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
                f"{MP_API_BASE}/v1/payments",
                json=payload,
                headers=headers,
            )

        if response.status_code not in (200, 201):
            logger.error(
                f"❌ Erro Mercado Pago ({response.status_code}): {response.text}"
            )
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text[:200]}",
            }

        data = response.json()

        # Extrai QR Code e copia-e-cola
        point_of_interaction = data.get("point_of_interaction", {})
        transaction_data = point_of_interaction.get("transaction_data", {})
        qr_code = transaction_data.get("qr_code", "")
        qr_code_base64 = transaction_data.get("qr_code_base64", "")
        ticket_url = transaction_data.get("ticket_url", "")

        payment_id = str(data.get("id"))
        status = data.get("status", "pending")

        logger.info(
            f"💠 Pix criado: id={payment_id} | valor=R$ {amount} | "
            f"status={status} | expira={expires_at.isoformat()}"
        )

        return {
            "success": True,
            "payment_id": payment_id,
            "status": status,
            "qr_code": qr_code,
            "qr_code_base64": qr_code_base64,
            "ticket_url": ticket_url,
            "expires_at": expires_at,
            "raw": data,
        }

    except httpx.TimeoutException:
        logger.error("❌ Timeout ao criar Pix no Mercado Pago")
        return {"success": False, "error": "Timeout na comunicação com Mercado Pago."}
    except httpx.RequestError as e:
        logger.error(f"❌ Erro de rede ao criar Pix: {e}")
        return {"success": False, "error": f"Erro de rede: {e}"}
    except Exception as e:
        logger.exception(f"❌ Erro inesperado ao criar Pix: {e}")
        return {"success": False, "error": f"Erro inesperado: {e}"}


# ============================================
# 🔍 CONSULTA DE PAGAMENTO
# ============================================
async def get_payment_status(payment_id: str) -> dict[str, Any]:
    """
    Consulta o status atual de um pagamento no Mercado Pago.

    Retorna dict com:
      - success: bool
      - status: str (pending, approved, rejected, cancelled, refunded)
      - status_detail: str
      - amount: float
      - raw: dict
    """
    if not settings.mercadopago_access_token:
        return {"success": False, "error": "Token não configurado."}

    headers = {
        "Authorization": f"Bearer {settings.mercadopago_access_token}",
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"{MP_API_BASE}/v1/payments/{payment_id}",
                headers=headers,
            )

        if response.status_code != 200:
            logger.warning(
                f"⚠️ Consulta Pix {payment_id} retornou {response.status_code}"
            )
            return {
                "success": False,
                "error": f"HTTP {response.status_code}",
            }

        data = response.json()

        return {
            "success": True,
            "status": data.get("status", "unknown"),
            "status_detail": data.get("status_detail", ""),
            "amount": data.get("transaction_amount", 0.0),
            "external_reference": data.get("external_reference", ""),
            "date_approved": data.get("date_approved"),
            "raw": data,
        }

    except httpx.TimeoutException:
        return {"success": False, "error": "Timeout"}
    except Exception as e:
        logger.exception(f"❌ Erro ao consultar Pix {payment_id}: {e}")
        return {"success": False, "error": str(e)}


# ============================================
# 🚫 CANCELAMENTO
# ============================================
async def cancel_payment(payment_id: str) -> bool:
    """Cancela um pagamento pendente."""
    if not settings.mercadopago_access_token:
        return False

    headers = {
        "Authorization": f"Bearer {settings.mercadopago_access_token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.put(
                f"{MP_API_BASE}/v1/payments/{payment_id}",
                json={"status": "cancelled"},
                headers=headers,
            )
        if response.status_code == 200:
            logger.info(f"🚫 Pix {payment_id} cancelado")
            return True
        logger.warning(f"⚠️ Não foi possível cancelar Pix {payment_id}")
        return False
    except Exception as e:
        logger.exception(f"❌ Erro ao cancelar Pix: {e}")
        return False


# ============================================
# 🔐 VERIFICAÇÃO DE WEBHOOK
# ============================================
async def verify_webhook_signature(
    x_signature: str,
    x_request_id: str,
    data_id: str,
) -> bool:
    """
    Verifica a assinatura do webhook do Mercado Pago.

    Se o secret não estiver configurado, retorna True (não bloqueia).
    Em produção, CONFIGURE o secret pra bloquear fraude.
    """
    secret = settings.mercadopago_webhook_secret
    if not secret:
        logger.warning("⚠️ MERCADOPAGO_WEBHOOK_SECRET não configurado.")
        return True

    try:
        # Formato do Mercado Pago:
        # ts=...,v1=...
        parts = dict(
            item.split("=", 1)
            for item in x_signature.split(",")
            if "=" in item
        )
        ts = parts.get("ts", "")
        v1 = parts.get("v1", "")
        if not ts or not v1:
            return False

        # String assinada
        manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts};"

        import hashlib
        import hmac

        expected = hmac.new(
            secret.encode("utf-8"),
            manifest.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, v1)

    except Exception as e:
        logger.exception(f"❌ Erro ao verificar assinatura do webhook: {e}")
        return False


# ============================================
# 📊 HELPERS
# ============================================
def generate_external_reference(user_telegram_id: int) -> str:
    """Gera uma referência externa única pro Mercado Pago."""
    ts = int(datetime.now(timezone.utc).timestamp())
    short_uuid = uuid.uuid4().hex[:8]
    return f"user_{user_telegram_id}_{ts}_{short_uuid}"


def extract_user_from_reference(ref: str) -> Optional[int]:
    """Extrai o telegram_id de uma external_reference."""
    try:
        parts = ref.split("_")
        if len(parts) >= 2 and parts[0] == "user":
            return int(parts[1])
    except (IndexError, ValueError):
        pass
    return None


def is_payment_approved(status: str) -> bool:
    """Verifica se o status do MP indica pagamento aprovado."""
    return status in ("approved", "accredited")


def is_payment_expired(status: str, status_detail: str = "") -> bool:
    """Verifica se o pagamento expirou."""
    return status == "cancelled" or status_detail in (
        "expired",
        "timeout",
    )


# ============================================
# 🧪 TESTE DE CONEXÃO (painel admin)
# ============================================
async def test_connection() -> dict[str, Any]:
    """Testa se o token do Mercado Pago está funcionando."""
    if not settings.mercadopago_access_token:
        return {"ok": False, "error": "Token não configurado."}

    headers = {
        "Authorization": f"Bearer {settings.mercadopago_access_token}",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{MP_API_BASE}/users/me",
                headers=headers,
            )
        if response.status_code == 200:
            data = response.json()
            return {
                "ok": True,
                "user_id": data.get("id"),
                "nickname": data.get("nickname"),
                "email": data.get("email"),
            }
        return {"ok": False, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

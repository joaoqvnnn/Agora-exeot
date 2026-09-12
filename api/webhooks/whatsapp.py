# ============================================
# 📱 WEBHOOK WHATSAPP — Larizinha Store
# ============================================
# Recebe eventos do serviço Baileys (Node.js).
#
# Eventos:
#   - "connected"  → WhatsApp conectado (QR escaneado)
#   - "message"    → Nova mensagem recebida
#
# Fluxo de mensagem:
#   1. Baileys detecta mensagem
#   2. Envia POST pra cá
#   3. Validamos o secret
#   4. Buscamos/criamos usuário pelo número
#   5. Encaminhamos pra IA responder
#   6. IA processa e envia resposta via wa_client
#   7. Registramos tudo no banco (auditoria + logs)
# ============================================

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import select

from core.config import settings
from core.database import AsyncSessionLocal
from core.models import User, UserStatus


router = APIRouter(prefix="/webhooks", tags=["webhooks-whatsapp"])


# ============================================
# 📦 SCHEMAS
# ============================================
class WhatsAppEvent(BaseModel):
    """Formato do payload enviado pelo Baileys."""

    event: str = Field(..., description="connected, message, etc")
    from_: Optional[str] = Field(None, alias="from")
    messageId: Optional[str] = None
    timestamp: Optional[int] = None
    text: Optional[str] = None
    pushName: Optional[str] = None
    messageType: Optional[str] = "text"

    # Para evento "connected"
    phone: Optional[str] = None

    class Config:
        populate_by_name = True
        extra = "allow"


# ============================================
# 📥 ENDPOINT PRINCIPAL
# ============================================
@router.post("/whatsapp")
async def whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_webhook_secret: Optional[str] = Header(None, alias="X-Webhook-Secret"),
):
    """
    Recebe eventos do serviço Baileys.

    O Baileys envia:
      - Header X-Webhook-Secret pra autenticação
      - Body com o evento
    """
    # ─── Valida secret ───
    expected_secret = settings.whatsapp_api_key or ""

    if expected_secret and x_webhook_secret != expected_secret:
        logger.warning(
            f"🚫 Webhook WhatsApp com secret inválido: "
            f"{x_webhook_secret[:10] if x_webhook_secret else 'ausente'}..."
        )
        raise HTTPException(status_code=401, detail="Secret inválido")

    # ─── Parse do body ───
    try:
        body: dict[str, Any] = await request.json()
    except Exception as e:
        logger.warning(f"⚠️ Webhook WhatsApp sem JSON válido: {e}")
        return {"ok": True, "ignored": "json inválido"}

    event_type = body.get("event", "unknown")

    logger.debug(f"📱 Webhook WhatsApp recebido: {event_type}")

    # ─── Roteia por tipo de evento ───
    if event_type == "connected":
        background_tasks.add_task(_handle_connected, body)

    elif event_type == "message":
        # Só processa se tiver texto
        text = body.get("text", "").strip()
        sender = body.get("from")

        if not text or not sender:
            return {"ok": True, "ignored": "sem texto ou remetente"}

        background_tasks.add_task(_handle_message, body)

    else:
        logger.debug(f"ℹ️ Evento não tratado: {event_type}")

    return {"ok": True}


# ============================================
# 🟢 HANDLER: CONECTADO
# ============================================
async def _handle_connected(body: dict[str, Any]) -> None:
    """
    Quando o Baileys conecta (QR escaneado),
    avisa o admin no Telegram.
    """
    phone = body.get("phone", "?")
    push_name = body.get("pushName", "?")

    logger.success(
        f"✅ WhatsApp conectado: {push_name} ({phone})"
    )

    # Notifica admins via Telegram
    try:
        from bot.loader import bot
        from core.models import Admin

        async with AsyncSessionLocal() as session:
            stmt = select(Admin).where(Admin.is_active.is_(True))
            result = await session.execute(stmt)
            admins = list(result.scalars().all())

            now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M:%S")

            text = (
                f"📱 <b>WHATSAPP CONECTADO</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📞 Número: <code>{phone}</code>\n"
                f"👤 Nome: <b>{push_name}</b>\n"
                f"⏰ Conectado em: {now}\n\n"
                f"✅ O serviço de WhatsApp está online e pronto pra receber mensagens."
            )

            for adm in admins:
                try:
                    await bot.send_message(
                        chat_id=adm.telegram_id,
                        text=text,
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

    except Exception as e:
        logger.debug(f"⚠️ Falha ao notificar admins: {e}")


# ============================================
# 💬 HANDLER: MENSAGEM RECEBIDA
# ============================================
async def _handle_message(body: dict[str, Any]) -> None:
    """
    Processa uma mensagem recebida pelo WhatsApp.

    Fluxo:
      1. Extrai o número do remetente
      2. Busca/cria usuário pelo número
      3. Verifica se o usuário está bloqueado
      4. Verifica se o WhatsApp está ativo (setting)
      5. Chama IA pra responder
      6. Envia resposta de volta via Baileys
    """
    from core.services import wa_handler

    sender_raw = body.get("from", "")
    text = body.get("text", "").strip()
    push_name = body.get("pushName", "")

    # Extrai número limpo do JID (5511999999999@s.whatsapp.net)
    phone = sender_raw.split("@")[0] if "@" in sender_raw else sender_raw

    if not phone or not text:
        return

    logger.info(f"💬 WhatsApp de {phone}: {text[:80]}")

    try:
        await wa_handler.process_incoming_message(
            phone=phone,
            text=text,
            push_name=push_name,
            message_id=body.get("messageId"),
        )
    except Exception as e:
        logger.exception(f"❌ Erro ao processar mensagem WhatsApp: {e}")


# ============================================
# 🏥 HEALTHCHECK
# ============================================
@router.get("/whatsapp/health")
async def whatsapp_webhook_health():
    """Healthcheck do webhook de WhatsApp."""
    from core.services import wa_client

    status = await wa_client.get_status()

    return {
        "ok": True,
        "service": "whatsapp-webhook",
        "configured": bool(settings.whatsapp_api_url),
        "remote_connected": status.get("connected", False),
        "remote_phone": status.get("phone_number"),
        "remote_name": status.get("push_name"),
    }


# ============================================
# 🧪 TESTE MANUAL (debug)
# ============================================
@router.post("/whatsapp/test")
async def whatsapp_webhook_test(
    phone: str,
    message: str,
    x_webhook_secret: Optional[str] = Header(None, alias="X-Webhook-Secret"),
):
    """
    Endpoint pra testar o fluxo sem precisar mandar
    mensagem real pelo WhatsApp.

    Exemplo:
      POST /webhooks/whatsapp/test?phone=5511999999999&message=Oi
    """
    # Valida secret
    expected_secret = settings.whatsapp_api_key or ""
    if expected_secret and x_webhook_secret != expected_secret:
        raise HTTPException(status_code=401, detail="Secret inválido")

    # Processa como se fosse uma mensagem real
    try:
        from core.services import wa_handler

        await wa_handler.process_incoming_message(
            phone=phone,
            text=message,
            push_name="Teste",
            message_id="test_" + datetime.now().strftime("%Y%m%d%H%M%S"),
        )

        return {
            "ok": True,
            "message": "Mensagem de teste processada",
            "phone": phone,
        }

    except Exception as e:
        logger.exception(f"❌ Erro no teste: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# 🔍 CONSULTAR CONEXÃO (painel admin)
# ============================================
@router.get("/whatsapp/status")
async def whatsapp_status():
    """
    Retorna o status detalhado do serviço WhatsApp.
    Usado pelo painel admin.
    """
    from core.services import wa_client

    status = await wa_client.get_status()

    return {
        "ok": status.get("ok", False),
        "configured": bool(settings.whatsapp_api_url),
        "connected": status.get("connected", False),
        "connecting": status.get("connecting", False),
        "phone_number": status.get("phone_number"),
        "push_name": status.get("push_name"),
        "has_qr": status.get("has_qr", False),
        "qr_url": wa_client.get_qr_url() if status.get("has_qr") else None,
        "stats": status.get("stats", {}),
        "last_disconnect": status.get("last_disconnect"),
        "error": status.get("error"),
    }


# ============================================
# 📸 PEGAR QR CODE (JSON)
# ============================================
@router.get("/whatsapp/qr")
async def whatsapp_qr():
    """
    Retorna o QR Code atual em JSON.
    Útil pro painel admin mostrar o QR.
    """
    from core.services import wa_client

    base = wa_client._base_url()
    if not base:
        raise HTTPException(
            status_code=503,
            detail="Serviço WhatsApp não configurado",
        )

    import httpx

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{base}/qr?format=json",
                headers=wa_client._headers(),
            )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=response.text[:200],
            )

        return response.json()

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# 🚪 DESCONECTAR (painel admin)
# ============================================
@router.post("/whatsapp/disconnect")
async def whatsapp_disconnect(
    x_webhook_secret: Optional[str] = Header(None, alias="X-Webhook-Secret"),
):
    """
    Desconecta o WhatsApp (logout).
    Requer escanear QR de novo.
    """
    expected_secret = settings.whatsapp_api_key or ""
    if expected_secret and x_webhook_secret != expected_secret:
        raise HTTPException(status_code=401, detail="Secret inválido")

    from core.services import wa_client

    result = await wa_client.logout()

    if result.get("success"):
        return {"ok": True, "message": "WhatsApp desconectado"}
    else:
        raise HTTPException(
            status_code=500,
            detail=result.get("error", "Erro ao desconectar"),
        )


# ============================================
# 🔄 REINICIAR (painel admin)
# ============================================
@router.post("/whatsapp/restart")
async def whatsapp_restart(
    x_webhook_secret: Optional[str] = Header(None, alias="X-Webhook-Secret"),
):
    """Reinicia a conexão (mantém credenciais)."""
    expected_secret = settings.whatsapp_api_key or ""
    if expected_secret and x_webhook_secret != expected_secret:
        raise HTTPException(status_code=401, detail="Secret inválido")

    from core.services import wa_client

    result = await wa_client.restart()

    if result.get("success"):
        return {"ok": True, "message": "Reiniciando conexão"}
    else:
        raise HTTPException(
            status_code=500,
            detail=result.get("error", "Erro ao reiniciar"),
        )


# ============================================
# 📸 NOVO QR (painel admin)
# ============================================
@router.post("/whatsapp/new-qr")
async def whatsapp_new_qr(
    x_webhook_secret: Optional[str] = Header(None, alias="X-Webhook-Secret"),
):
    """
    Força geração de novo QR Code.
    Limpa credenciais antigas.
    """
    expected_secret = settings.whatsapp_api_key or ""
    if expected_secret and x_webhook_secret != expected_secret:
        raise HTTPException(status_code=401, detail="Secret inválido")

    from core.services import wa_client

    result = await wa_client.request_new_qr()

    if result.get("success"):
        return {
            "ok": True,
            "message": "Novo QR sendo gerado",
            "qr_url": wa_client.get_qr_url(),
        }
    else:
        raise HTTPException(
            status_code=500,
            detail=result.get("error", "Erro ao gerar QR"),
        )

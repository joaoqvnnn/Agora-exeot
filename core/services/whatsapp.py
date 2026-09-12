# ============================================
# 📱 WHATSAPP SERVICE — Larizinha Store
# ============================================
# Integração com API de WhatsApp NÃO OFICIAL
# (Baileys, WPPConnect, Evolution API, etc).
#
# Usa HTTP simples — funciona com qualquer API que
# aceite POST /send ou similar. Configurável via .env:
#   WHATSAPP_API_URL
#   WHATSAPP_API_KEY
#   WHATSAPP_PHONE_NUMBER
#
# Fluxos:
#   - Envio de mensagem (texto)
#   - Envio de imagem
#   - Envio de documento (PDF)
#   - Verificação de número ativo
#   - Webhook de recebimento (IA responde)
# ============================================

import re
from typing import Any, Optional

import httpx
from loguru import logger

from core.config import settings


TIMEOUT = 30.0


# ============================================
# 🧼 NORMALIZAÇÃO DE NÚMERO
# ============================================
def normalize_phone(phone: str) -> str:
    """
    Normaliza número pra formato internacional.
    Remove tudo que não é dígito, adiciona 55 se faltar.
    """
    digits = re.sub(r"\D", "", phone)
    if not digits.startswith("55") and len(digits) <= 11:
        digits = "55" + digits
    return digits


def is_valid_phone(phone: str) -> bool:
    """Valida se é um número brasileiro plausível."""
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("55"):
        digits = digits[2:]
    return 10 <= len(digits) <= 11


# ============================================
# 📤 ENVIO DE MENSAGEM
# ============================================
async def send_message(
    phone: str,
    message: str,
    media_url: Optional[str] = None,
    media_type: Optional[str] = None,
) -> dict[str, Any]:
    """
    Envia mensagem de texto (ou mídia) pelo WhatsApp.
    Retorna dict com sucesso e erro.
    """
    if not settings.whatsapp_api_url or not settings.whatsapp_api_key:
        logger.warning("⚠️ WhatsApp API não configurada.")
        return {"success": False, "error": "WhatsApp não configurado."}

    phone = normalize_phone(phone)
    if not is_valid_phone(phone):
        return {"success": False, "error": "Número inválido."}

    payload: dict[str, Any] = {
        "number": phone,
        "phone": phone,
        "to": phone,
        "message": message,
        "text": message,
    }

    if media_url:
        payload["media"] = media_url
        payload["mediaUrl"] = media_url
        payload["media_url"] = media_url
        payload["type"] = media_type or "image"
        payload["mediatype"] = media_type or "image"

    headers = {
        "apikey": settings.whatsapp_api_key,
        "Authorization": f"Bearer {settings.whatsapp_api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{settings.whatsapp_api_url.rstrip('/')}/message/sendText",
                json=payload,
                headers=headers,
            )

        if response.status_code in (200, 201):
            logger.info(f"📱 WhatsApp enviado para {phone}")
            return {"success": True, "raw": _safe_json(response)}
        else:
            logger.warning(
                f"⚠️ WhatsApp API respondeu {response.status_code}: "
                f"{response.text[:200]}"
            )
            return {
                "success": False,
                "error": f"HTTP {response.status_code}",
                "raw": _safe_json(response),
            }
    except httpx.TimeoutException:
        return {"success": False, "error": "Timeout na API do WhatsApp."}
    except Exception as e:
        logger.exception(f"❌ Erro ao enviar WhatsApp: {e}")
        return {"success": False, "error": str(e)}


# ============================================
# 📎 ENVIO DE MÍDIA
# ============================================
async def send_image(
    phone: str,
    image_url: str,
    caption: str = "",
) -> dict[str, Any]:
    """Envia imagem com legenda."""
    return await send_message(
        phone=phone,
        message=caption,
        media_url=image_url,
        media_type="image",
    )


async def send_document(
    phone: str,
    document_url: str,
    caption: str = "",
    filename: str = "documento.pdf",
) -> dict[str, Any]:
    """Envia documento (PDF)."""
    if not settings.whatsapp_api_url or not settings.whatsapp_api_key:
        return {"success": False, "error": "WhatsApp não configurado."}

    phone = normalize_phone(phone)
    payload = {
        "number": phone,
        "media": document_url,
        "mediaUrl": document_url,
        "mediatype": "document",
        "fileName": filename,
        "caption": caption,
    }
    headers = {
        "apikey": settings.whatsapp_api_key,
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{settings.whatsapp_api_url.rstrip('/')}/message/sendMedia",
                json=payload,
                headers=headers,
            )
        if response.status_code in (200, 201):
            return {"success": True, "raw": _safe_json(response)}
        return {"success": False, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================
# 🔍 VERIFICAÇÃO DE NÚMERO
# ============================================
async def check_number(phone: str) -> dict[str, Any]:
    """Verifica se o número existe no WhatsApp."""
    if not settings.whatsapp_api_url or not settings.whatsapp_api_key:
        return {"success": False, "error": "WhatsApp não configurado."}

    phone = normalize_phone(phone)
    headers = {
        "apikey": settings.whatsapp_api_key,
        "Content-Type": "application/json",
    }
    payload = {"number": phone}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{settings.whatsapp_api_url.rstrip('/')}/chat/whatsappNumbers",
                json=payload,
                headers=headers,
            )
        if response.status_code == 200:
            data = response.json()
            exists = False
            if isinstance(data, list) and data:
                exists = bool(data[0].get("exists"))
            elif isinstance(data, dict):
                exists = bool(data.get("exists"))
            return {"success": True, "exists": exists, "raw": data}
        return {"success": False, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================
# 🔐 ENVIO DE CÓDIGO DE VERIFICAÇÃO
# ============================================
async def send_verification_code(
    phone: str,
    code: str,
    bot_name: str = "Larizinha Store",
) -> dict[str, Any]:
    """Envia código de verificação pelo WhatsApp."""
    message = (
        f"🔐 *{bot_name}*\n\n"
        f"Seu código de verificação é:\n\n"
        f"*{code}*\n\n"
        f"Válido por 15 minutos.\n"
        f"⚠️ Não compartilhe com ninguém."
    )
    return await send_message(phone, message)


# ============================================
# 📦 ENTREGA DE PRODUTO
# ============================================
async def send_product_delivery(
    phone: str,
    product_name: str,
    order_code: str,
    items: list[dict[str, str]],
    expiration_date: str = "N/A",
    bot_name: str = "Larizinha Store",
) -> dict[str, Any]:
    """
    Envia dados do produto pro WhatsApp do cliente.
    `items` = lista de dicts com email, password, code, note.
    """
    lines = [
        f"🎉 *COMPRA REALIZADA*",
        f"",
        f"⚜️ Serviço: *{product_name}*",
        f"🎫 ID: `{order_code}`",
        f"📆 Vencimento: {expiration_date}",
        f"",
    ]

    for idx, item in enumerate(items, start=1):
        lines.append(f"🔐 *Login {idx}/{len(items)}*")
        lines.append(f"📧 Email: `{item.get('email', 'N/A')}`")
        lines.append(f"🔑 Senha: `{item.get('password', 'N/A')}`")
        if item.get("code"):
            lines.append(f"🔗 Código: {item['code']}")
        if item.get("note"):
            lines.append(f"📃 Nota: {item['note']}")
        lines.append("")

    lines.append("💡 Guarde esses dados.")
    lines.append(f"📞 Suporte: responda esta mensagem")

    message = "\n".join(lines)
    return await send_message(phone, message)


# ============================================
# 🤖 IA — RESPOSTA AUTOMÁTICA
# ============================================
async def send_ai_reply(
    phone: str,
    user_message: str,
) -> dict[str, Any]:
    """
    Envia mensagem do usuário pra IA e responde
    pelo WhatsApp.
    """
    from core.services import ai as ai_service

    reply = await ai_service.get_whatsapp_response(user_message)

    if not reply:
        reply = (
            "🤖 Não consegui entender. Tente novamente ou "
            "digite *humano* para falar com um atendente."
        )

    return await send_message(phone, reply)


# ============================================
# 🔗 INTEGRAÇÃO COM O BOT (deep link)
# ============================================
def build_bot_link(bot_username: str = "larizinhastorebot") -> str:
    """Gera link pro bot do Telegram."""
    return f"https://t.me/{bot_username}"


# ============================================
# 🧪 TESTE DE CONEXÃO
# ============================================
async def test_connection() -> dict[str, Any]:
    """Testa se a API do WhatsApp está respondendo."""
    if not settings.whatsapp_api_url or not settings.whatsapp_api_key:
        return {"ok": False, "error": "WhatsApp não configurado."}

    headers = {"apikey": settings.whatsapp_api_key}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.whatsapp_api_url.rstrip('/')}/instance/connectionState",
                headers=headers,
            )
        if response.status_code == 200:
            data = _safe_json(response)
            return {"ok": True, "state": data}
        return {"ok": False, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ============================================
# 🧰 HELPERS
# ============================================
def _safe_json(response: httpx.Response) -> Any:
    """Tenta parsear JSON com segurança."""
    try:
        return response.json()
    except Exception:
        return {"text": response.text[:500]}

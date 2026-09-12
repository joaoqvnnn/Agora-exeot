# ============================================
# 📡 WA CLIENT — Larizinha Store
# ============================================
# Cliente HTTP Python que conversa com o serviço
# Baileys (Node.js) que roda no Render.
#
# Responsabilidades:
#   - Enviar mensagens de texto
#   - Enviar mídia (imagem, vídeo, PDF)
#   - Verificar se número existe no WhatsApp
#   - Consultar status da conexão
#   - Forçar logout / novo QR
#
# URL do serviço vem de settings.whatsapp_api_url
# ⚠️ Isso NÃO é a API oficial — é o serviço Baileys.
# ============================================

import re
from typing import Any, Optional

import httpx
from loguru import logger

from core.config import settings


# ============================================
# ⚙️ CONFIGURAÇÕES
# ============================================
TIMEOUT_DEFAULT = 30.0
TIMEOUT_SHORT = 10.0


# ============================================
# 🧰 HELPERS
# ============================================
def _base_url() -> Optional[str]:
    """Retorna a URL base do serviço Baileys."""
    url = settings.whatsapp_api_url
    if not url:
        return None
    return url.rstrip("/")


def _headers() -> dict[str, str]:
    """Headers padrão para requests."""
    headers = {
        "Content-Type": "application/json",
    }
    if settings.whatsapp_api_key:
        headers["X-Api-Key"] = settings.whatsapp_api_key
    return headers


def normalize_phone(phone: str) -> str:
    """
    Normaliza número pro formato esperado pelo Baileys.
    Remove tudo que não é dígito e adiciona 55 se faltar.
    """
    digits = re.sub(r"\D", "", str(phone))

    # Remove 0 inicial
    if digits.startswith("0"):
        digits = digits[1:]

    # Adiciona 55 se faltar
    if not digits.startswith("55") and len(digits) <= 11:
        digits = "55" + digits

    return digits


def is_valid_phone(phone: str) -> bool:
    """Valida se é um número brasileiro plausível."""
    digits = re.sub(r"\D", "", str(phone))
    if digits.startswith("55"):
        digits = digits[2:]
    return 10 <= len(digits) <= 11


def format_phone_display(phone: str) -> str:
    """Formata número pra exibição: 55 44 99999-9999."""
    digits = normalize_phone(phone)
    if len(digits) == 13:
        return f"+{digits[:2]} ({digits[2:4]}) {digits[4:9]}-{digits[9:]}"
    return f"+{digits}"


# ============================================
# 🏥 STATUS DO SERVIÇO
# ============================================
async def get_status() -> dict[str, Any]:
    """
    Consulta o status do serviço Baileys.
    Retorna:
      - connected: bool
      - phoneNumber: str
      - pushName: str
      - hasQr: bool
      - stats: {messagesSent, messagesReceived}
    """
    base = _base_url()
    if not base:
        return {"ok": False, "error": "whatsapp_api_url não configurada"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SHORT) as client:
            response = await client.get(
                f"{base}/status",
                headers=_headers(),
            )

        if response.status_code != 200:
            return {
                "ok": False,
                "error": f"HTTP {response.status_code}",
                "raw": response.text[:300],
            }

        data = response.json()
        return {
            "ok": True,
            "connected": data.get("connected", False),
            "connecting": data.get("connecting", False),
            "phone_number": data.get("phoneNumber"),
            "push_name": data.get("pushName"),
            "has_qr": data.get("hasQr", False),
            "last_disconnect": data.get("lastDisconnect"),
            "stats": data.get("stats", {}),
            "qr_generated_at": data.get("qrGeneratedAt"),
        }

    except httpx.TimeoutException:
        return {"ok": False, "error": "Timeout ao consultar status"}
    except Exception as e:
        logger.exception(f"❌ Erro ao consultar status do WhatsApp: {e}")
        return {"ok": False, "error": str(e)}


async def is_connected() -> bool:
    """Verifica rapidamente se o WhatsApp está conectado."""
    result = await get_status()
    return result.get("ok", False) and result.get("connected", False)


# ============================================
# 📤 ENVIAR MENSAGEM DE TEXTO
# ============================================
async def send_message(
    phone: str,
    message: str,
) -> dict[str, Any]:
    """
    Envia mensagem de texto.

    Retorna:
      - success: bool
      - error: str (se falhou)
      - raw: dict (resposta bruta)
    """
    base = _base_url()
    if not base:
        return {
            "success": False,
            "error": "Serviço WhatsApp não configurado (whatsapp_api_url vazio)",
        }

    if not phone or not message:
        return {"success": False, "error": "Telefone e mensagem são obrigatórios"}

    phone_normalized = normalize_phone(phone)

    if not is_valid_phone(phone_normalized):
        return {"success": False, "error": f"Número inválido: {phone}"}

    payload = {
        "phone": phone_normalized,
        "message": message,
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_DEFAULT) as client:
            response = await client.post(
                f"{base}/send",
                json=payload,
                headers=_headers(),
            )

        if response.status_code == 200:
            logger.info(f"📱 WhatsApp enviado para {phone_normalized}")
            return {"success": True, "raw": _safe_json(response)}

        if response.status_code == 503:
            logger.warning("⚠️ WhatsApp não conectado — mensagem não enviada")
            return {
                "success": False,
                "error": "WhatsApp não conectado",
                "raw": _safe_json(response),
            }

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
        return {"success": False, "error": "Timeout ao enviar"}
    except httpx.RequestError as e:
        return {"success": False, "error": f"Erro de rede: {e}"}
    except Exception as e:
        logger.exception(f"❌ Erro ao enviar WhatsApp: {e}")
        return {"success": False, "error": str(e)}


# ============================================
# 🖼️ ENVIAR IMAGEM
# ============================================
async def send_image(
    phone: str,
    image_url: str,
    caption: str = "",
) -> dict[str, Any]:
    """Envia uma imagem com legenda."""
    return await send_media(
        phone=phone,
        media_url=image_url,
        media_type="image",
        caption=caption,
    )


# ============================================
# 🎥 ENVIAR VÍDEO
# ============================================
async def send_video(
    phone: str,
    video_url: str,
    caption: str = "",
) -> dict[str, Any]:
    """Envia um vídeo com legenda."""
    return await send_media(
        phone=phone,
        media_url=video_url,
        media_type="video",
        caption=caption,
    )


# ============================================
# 📄 ENVIAR DOCUMENTO (PDF)
# ============================================
async def send_document(
    phone: str,
    document_url: str,
    caption: str = "",
) -> dict[str, Any]:
    """Envia documento (PDF)."""
    return await send_media(
        phone=phone,
        media_url=document_url,
        media_type="document",
        caption=caption,
    )


# ============================================
# 📎 ENVIAR MÍDIA (GENÉRICO)
# ============================================
async def send_media(
    phone: str,
    media_url: str,
    media_type: str = "image",
    caption: str = "",
) -> dict[str, Any]:
    """
    Envia mídia genérica.

    media_type: image, video, document
    """
    base = _base_url()
    if not base:
        return {"success": False, "error": "Serviço WhatsApp não configurado"}

    if not phone or not media_url:
        return {"success": False, "error": "Telefone e URL são obrigatórios"}

    phone_normalized = normalize_phone(phone)

    if not is_valid_phone(phone_normalized):
        return {"success": False, "error": f"Número inválido: {phone}"}

    payload = {
        "phone": phone_normalized,
        "mediaUrl": media_url,
        "mediaType": media_type,
        "caption": caption or "",
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_DEFAULT) as client:
            response = await client.post(
                f"{base}/send-media",
                json=payload,
                headers=_headers(),
            )

        if response.status_code == 200:
            logger.info(f"📱 WhatsApp mídia enviada para {phone_normalized}")
            return {"success": True, "raw": _safe_json(response)}

        return {
            "success": False,
            "error": f"HTTP {response.status_code}",
            "raw": _safe_json(response),
        }

    except Exception as e:
        logger.exception(f"❌ Erro ao enviar mídia: {e}")
        return {"success": False, "error": str(e)}


# ============================================
# 🔍 VERIFICAR SE NÚMERO EXISTE
# ============================================
async def check_number_exists(phone: str) -> dict[str, Any]:
    """
    Verifica se um número existe no WhatsApp.

    Retorna:
      - success: bool
      - exists: bool
      - jid: str
    """
    base = _base_url()
    if not base:
        return {"success": False, "error": "Serviço WhatsApp não configurado"}

    phone_normalized = normalize_phone(phone)

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SHORT) as client:
            response = await client.post(
                f"{base}/check-number",
                json={"phone": phone_normalized},
                headers=_headers(),
            )

        if response.status_code == 200:
            data = response.json()
            return {
                "success": True,
                "exists": data.get("exists", False),
                "jid": data.get("jid"),
            }

        return {
            "success": False,
            "error": f"HTTP {response.status_code}",
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================
# 🚪 LOGOUT
# ============================================
async def logout() -> dict[str, Any]:
    """Desconecta o WhatsApp (requer escanear QR de novo)."""
    base = _base_url()
    if not base:
        return {"success": False, "error": "Serviço WhatsApp não configurado"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_DEFAULT) as client:
            response = await client.post(
                f"{base}/logout",
                headers=_headers(),
            )

        if response.status_code == 200:
            logger.warning("🚪 WhatsApp desconectado (logout)")
            return {"success": True}

        return {"success": False, "error": f"HTTP {response.status_code}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================
# 🔄 REINICIAR CONEXÃO
# ============================================
async def restart() -> dict[str, Any]:
    """Reinicia a conexão (mantém credenciais)."""
    base = _base_url()
    if not base:
        return {"success": False, "error": "Serviço WhatsApp não configurado"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_DEFAULT) as client:
            response = await client.post(
                f"{base}/restart",
                headers=_headers(),
            )

        if response.status_code == 200:
            logger.info("🔄 WhatsApp reconectando...")
            return {"success": True}

        return {"success": False, "error": f"HTTP {response.status_code}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================
# 📸 GERAR NOVO QR (limpa credenciais)
# ============================================
async def request_new_qr() -> dict[str, Any]:
    """Força geração de novo QR Code (limpa auth)."""
    base = _base_url()
    if not base:
        return {"success": False, "error": "Serviço WhatsApp não configurado"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_DEFAULT) as client:
            response = await client.post(
                f"{base}/new-qr",
                headers=_headers(),
            )

        if response.status_code == 200:
            logger.info("📸 Novo QR solicitado")
            return {"success": True}

        return {"success": False, "error": f"HTTP {response.status_code}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================
# 🔗 URL DO QR CODE (pra abrir no navegador)
# ============================================
def get_qr_url() -> Optional[str]:
    """
    Retorna URL pública da página do QR Code.
    Abra no navegador pra escanear.
    """
    base = _base_url()
    if not base:
        return None
    return f"{base}/qr"


def get_qr_json_url() -> Optional[str]:
    """Retorna URL da API JSON do QR."""
    base = _base_url()
    if not base:
        return None
    return f"{base}/qr?format=json"


# ============================================
# 📨 ENTREGA DE PRODUTO (mensagem formatada)
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

    items = lista de dicts: [{"email": "...", "password": "...", "code": "...", "note": "..."}]
    """
    lines = [
        f"🎉 *COMPRA REALIZADA*",
        f"",
        f"⚜️ Serviço: *{product_name}*",
        f"🎫 ID: `{order_code[:16]}`",
        f"📆 Vencimento: {expiration_date}",
        f"",
    ]

    for idx, item in enumerate(items, start=1):
        total = len(items)
        lines.append(f"🔐 *Login {idx}/{total}*")
        if item.get("email"):
            lines.append(f"📧 Email: `{item['email']}`")
        if item.get("password"):
            lines.append(f"🔑 Senha: `{item['password']}`")
        if item.get("code"):
            lines.append(f"🔗 Código: {item['code']}")
        if item.get("note"):
            lines.append(f"📃 Nota: {item['note']}")
        lines.append("")

    lines.append("💡 _Guarde esses dados em local seguro._")
    lines.append(f"📞 Suporte: {bot_name}")

    message = "\n".join(lines)

    return await send_message(phone, message)


# ============================================
# 🤖 RESPOSTA AUTOMÁTICA COM IA
# ============================================
async def send_ai_reply(
    phone: str,
    user_message: str,
    ai_response: str,
) -> dict[str, Any]:
    """
    Envia resposta da IA pro cliente.
    """
    if not ai_response:
        ai_response = (
            "🤖 Não consegui entender. Tente novamente ou "
            "digite *humano* para falar com um atendente."
        )

    return await send_message(phone, ai_response)


# ============================================
# 🧪 TESTE DE CONEXÃO
# ============================================
async def test_connection() -> dict[str, Any]:
    """
    Testa a conexão com o serviço Baileys.
    Retorna info pra painel admin.
    """
    base = _base_url()
    if not base:
        return {"ok": False, "error": "whatsapp_api_url não configurada"}

    if not settings.whatsapp_api_key:
        return {"ok": False, "error": "whatsapp_api_key não configurada"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SHORT) as client:
            # Testa o /status
            response = await client.get(
                f"{base}/status",
                headers=_headers(),
            )

        if response.status_code != 200:
            return {
                "ok": False,
                "error": f"HTTP {response.status_code}",
                "raw": response.text[:200],
            }

        data = response.json()

        return {
            "ok": True,
            "connected": data.get("connected", False),
            "phone_number": data.get("phoneNumber"),
            "push_name": data.get("pushName"),
            "has_qr": data.get("hasQr", False),
            "stats": data.get("stats", {}),
        }

    except httpx.TimeoutException:
        return {"ok": False, "error": "Timeout na conexão"}
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

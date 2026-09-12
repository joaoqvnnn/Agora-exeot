# ============================================
# 🤖 AI SERVICE — Larizinha Store
# ============================================
# Integração com OpenAI para atendimento automático
# no Telegram e WhatsApp.
#
# A IA:
#   - Responde dúvidas sobre produtos
#   - Consulta estoque e preços em tempo real
#   - Envia PDF de produtos quando solicitado
#   - Detecta quando o usuário quer falar com humano
#   - Pausa quando humano assume (handoff)
# ============================================

import io
from typing import Any, Optional

from loguru import logger
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.models import Product, ProductStatus, StockItem, StockStatus


# ============================================
# 🔌 CLIENTE OPENAI
# ============================================
def _get_client() -> Optional[AsyncOpenAI]:
    if not settings.openai_api_key:
        return None
    return AsyncOpenAI(api_key=settings.openai_api_key)


# ============================================
# 🧠 PROMPT DO SISTEMA
# ============================================
SYSTEM_PROMPT = """Você é a assistente virtual da {bot_name}, uma loja de streamings e contas premium.

Seu papel:
- Atender clientes com educação, clareza e objetividade
- Tirar dúvidas sobre produtos, pagamento, entrega e garantia
- NUNCA invente informações — se não souber, diga que vai chamar um atendente
- NUNCA prometa prazos ou valores que não estão no catálogo
- Quando o cliente pedir algo que você não pode resolver, diga:
  "Vou chamar um atendente humano para te ajudar. Um momento! 🙋"

Regras importantes:
- Pagamento é via Pix, entrega automática após confirmação
- Garantia varia por produto (consulte no catálogo)
- Não compartilhe dados de outros clientes
- Se o cliente pedir lista de produtos, use a ferramenta de catálogo
- Se pedir PDF, use a ferramenta de gerar PDF

Seja breve. Respostas longas cansam no chat. Prefira 2-4 parágrafos curtos.

Contexto do cliente:
- Telegram ID: {user_id}
- Nome: {user_name}
- Saldo: R$ {balance}
"""


# ============================================
# 💬 RESPOSTA PRINCIPAL (Telegram)
# ============================================
async def get_response(
    session: AsyncSession,
    user_message: str,
    user_id: int = 0,
    user_name: str = "Cliente",
    balance: str = "0,00",
    history: Optional[list[dict[str, str]]] = None,
) -> str:
    """
    Gera resposta da IA pra uma mensagem do usuário.
    `history` = lista de {"role": "user"/"assistant", "content": "..."}
    """
    client = _get_client()
    if client is None:
        return "🤖 Atendimento automático indisponível no momento."

    # Detecta intenção de humano
    if _wants_human(user_message):
        return "Vou chamar um atendente humano para te ajudar. Um momento! 🙋"

    # Detecta intenção de catálogo
    if _wants_catalog(user_message):
        catalog_text = await _build_catalog_text(session)
        return catalog_text

    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT.format(
                bot_name="Larizinha Store",
                user_id=user_id,
                user_name=user_name,
                balance=balance,
            ),
        }
    ]

    if history:
        messages.extend(history[-10:])  # últimas 10 mensagens

    messages.append({"role": "user", "content": user_message})

    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            max_tokens=settings.openai_max_tokens,
            temperature=settings.openai_temperature,
        )
        reply = response.choices[0].message.content or ""
        return reply.strip()
    except Exception as e:
        logger.exception(f"❌ Erro na OpenAI: {e}")
        return "🤖 Estou com dificuldades técnicas. Tente novamente em instantes."


# ============================================
# 📱 RESPOSTA PARA WHATSAPP
# ============================================
async def get_whatsapp_response(user_message: str) -> str:
    """Versão simplificada (sem banco) para WhatsApp."""
    client = _get_client()
    if client is None:
        return ""

    if _wants_human(user_message):
        return "Vou chamar um atendente humano. Um momento! 🙋"

    messages = [
        {
            "role": "system",
            "content": (
                "Você é a assistente da Larizinha Store no WhatsApp. "
                "Atenda com educação e clareza. Se não souber, diga que vai "
                "chamar um humano. Responda em português. Seja breve."
            ),
        },
        {"role": "user", "content": user_message},
    ]

    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            max_tokens=300,
            temperature=0.7,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as e:
        logger.exception(f"❌ Erro OpenAI WhatsApp: {e}")
        return ""


# ============================================
# 📋 CATÁLOGO EM TEXTO
# ============================================
async def _build_catalog_text(session: AsyncSession) -> str:
    """Monta uma lista de produtos com preço e estoque."""
    stmt = (
        select(Product)
        .where(Product.status == ProductStatus.ACTIVE)
        .order_by(Product.position, Product.name)
    )
    result = await session.execute(stmt)
    products = list(result.scalars().all())

    if not products:
        return "📦 Não temos produtos disponíveis no momento."

    lines = ["📦 *Nosso catálogo:*", ""]
    for p in products:
        stock = await session.scalar(
            select(StockItem.id).where(
                StockItem.product_id == p.id,
                StockItem.status == StockStatus.AVAILABLE,
            ).limit(1)
        )
        emoji = p.emoji or "🎬"
        price = f"{p.price:.2f}".replace(".", ",")
        status_icon = "🟢" if stock else "🔴"
        lines.append(f"{status_icon} {emoji} *{p.name}* — R$ {price}")

    lines.append("")
    lines.append("💡 Pra comprar, use o bot: @larizinhastorebot")
    return "\n".join(lines)


# ============================================
# 🔍 DETECÇÃO DE INTENÇÃO
# ============================================
def _wants_human(message: str) -> bool:
    """Detecta se o usuário quer atendimento humano."""
    keywords = [
        "humano", "atendente", "pessoa", "responsável", "responsavel",
        "falar com alguém", "falar com alguem", "suporte humano",
        "atendimento humano", "chama alguém", "chama alguem",
    ]
    lower = message.lower()
    return any(k in lower for k in keywords)


def _wants_catalog(message: str) -> bool:
    """Detecta se o usuário quer ver o catálogo."""
    keywords = [
        "catálogo", "catalogo", "produtos", "o que vocês vendem",
        "o que voces vendem", "lista", "serviços", "servicos",
        "quais produtos", "ver tudo",
    ]
    lower = message.lower()
    return any(k in lower for k in keywords)


def _wants_pdf(message: str) -> bool:
    """Detecta se o usuário quer receber PDF."""
    keywords = ["pdf", "arquivo", "documento", "receber por pdf"]
    return any(k in message.lower() for k in keywords)


# ============================================
# 📄 GERAÇÃO DE PDF DE PRODUTO
# ============================================
async def generate_product_pdf(
    session: AsyncSession,
    product_id: int,
) -> Optional[bytes]:
    """
    Gera um PDF simples com os dados de um produto.
    Retorna bytes do PDF ou None em caso de erro.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError:
        logger.warning("⚠️ reportlab não instalado. PDF indisponível.")
        return None

    product = await session.get(Product, product_id)
    if product is None:
        return None

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, height - 60, f"{product.name}")

    c.setFont("Helvetica", 12)
    y = height - 100

    price_str = f"R$ {product.price:.2f}".replace(".", ",")
    c.drawString(50, y, f"Preco: {price_str}")
    y -= 20

    stock_count = await session.scalar(
        select(StockItem.id).where(
            StockItem.product_id == product.id,
            StockItem.status == StockStatus.AVAILABLE,
        )
    )
    c.drawString(50, y, f"Estoque: {'Disponivel' if stock_count else 'Esgotado'}")
    y -= 20

    c.drawString(50, y, f"Garantia: {product.warranty_days} dias")
    y -= 40

    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "Descricao:")
    y -= 20

    c.setFont("Helvetica", 11)
    description = product.description or "Sem descrição."
    for line in _wrap_text(description, 80):
        c.drawString(50, y, line)
        y -= 15
        if y < 60:
            c.showPage()
            y = height - 60

    c.setFont("Helvetica-Oblique", 9)
    c.drawString(50, 40, "Larizinha Store - Entrega automatica 24h")

    c.save()
    buffer.seek(0)
    return buffer.read()


def _wrap_text(text: str, max_chars: int) -> list[str]:
    """Quebra texto em linhas de N caracteres."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 <= max_chars:
            current = f"{current} {word}".strip()
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


# ============================================
# 🧪 TESTE DE CONEXÃO
# ============================================
async def test_connection() -> dict[str, Any]:
    """Testa se a chave da OpenAI está funcionando."""
    client = _get_client()
    if client is None:
        return {"ok": False, "error": "OPENAI_API_KEY não configurada."}

    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
        )
        return {
            "ok": True,
            "model": settings.openai_model,
            "reply": response.choices[0].message.content,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

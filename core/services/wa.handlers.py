# ============================================
# 🧠 WA HANDLER — Larizinha Store
# ============================================
# Cérebro do processamento de mensagens do WhatsApp.
#
# Fluxo:
#   1. Recebe mensagem (de api/webhooks/whatsapp.py)
#   2. Normaliza o número
#   3. Busca/cria usuário pelo WhatsApp
#   4. Verifica se está bloqueado/banido
#   5. Verifica se o serviço está ativo (admin)
#   6. Detecta intenções (humano, catálogo, PDF, etc)
#   7. Chama IA pra responder
#   8. Envia a resposta via wa_client
#   9. Registra tudo em log
#
# Funcionalidades:
#   - Responde dúvidas gerais
#   - Consulta catálogo em tempo real
#   - Envia PDF de produtos quando solicitado
#   - Detecta pedido de humano → cria ticket
#   - Handoff: IA para de responder quando humano assume
#   - Anti-flood leve
#   - Anti-spam de mensagens repetidas
# ============================================

import asyncio
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import AsyncSessionLocal
from core.models import (
    Product,
    ProductStatus,
    StockItem,
    StockStatus,
    Ticket,
    TicketStatus,
    User,
    UserStatus,
)
from core.services import config as config_service
from core.services import wa_client


# ============================================
# ⚙️ CONFIGURAÇÕES
# ============================================
# Cache de anti-spam: {phone: {"last_msg": str, "count": int, "first_at": datetime}}
_spam_cache: dict[str, dict] = {}

SPAM_WINDOW_SECONDS = 60     # janela de 1 min
SPAM_MAX_REPEATS = 5         # máximo de mensagens idênticas
SPAM_BLOCK_MINUTES = 10      # bloqueio temporário


# ============================================
# 🎯 ENTRYPOINT PRINCIPAL
# ============================================
async def process_incoming_message(
    phone: str,
    text: str,
    push_name: str = "",
    message_id: Optional[str] = None,
) -> None:
    """
    Ponto de entrada — recebe mensagem do webhook e processa.
    Roda em background, não bloqueia o webhook.
    """
    # Normaliza número
    phone = _normalize_phone(phone)

    if not phone or not text:
        return

    logger.info(f"💬 WhatsApp [{phone}] {push_name}: {text[:80]}")

    try:
        async with AsyncSessionLocal() as session:
            # 1. Verifica se está ativo
            enabled = await config_service.get_bool(
                session, "wa_auto_reply_enabled", True
            )
            if not enabled:
                logger.debug("🔕 WhatsApp auto-reply desativado")
                return

            # 2. Anti-spam
            if _is_spam(phone, text):
                logger.warning(f"🚫 Spam detectado de {phone}")
                return

            # 3. Busca/cria usuário
            user = await _get_or_create_user(session, phone, push_name)

            if user is None:
                logger.warning(f"⚠️ Não foi possível criar usuário pra {phone}")
                return

            # 4. Verifica bloqueio
            if user.status == UserStatus.BLOCKED:
                logger.info(f"🚫 Usuário {phone} está bloqueado — ignorando")
                return

            if user.status == UserStatus.BANNED:
                logger.info(f"⛔ Usuário {phone} está banido — ignorando")
                return

            # 5. Verifica se há ticket com humano ativo
            has_human = await _has_active_human_ticket(session, phone)

            if has_human:
                # Humano assumiu — apenas registra no ticket, não responde
                await _append_to_active_ticket(session, phone, text, "user")
                logger.debug(f"🙋 Humano ativo no ticket — mensagem registrada")
                return

            # 6. IA responde
            await _respond_with_ai(
                session=session,
                user=user,
                phone=phone,
                text=text,
                push_name=push_name,
            )

    except Exception as e:
        logger.exception(f"❌ Erro ao processar mensagem WhatsApp: {e}")


# ============================================
# 🧰 NORMALIZAÇÃO DE NÚMERO
# ============================================
def _normalize_phone(phone: str) -> str:
    """Remove tudo que não é dígito."""
    if not phone:
        return ""
    return re.sub(r"\D", "", str(phone))


# ============================================
# 🚫 ANTI-SPAM
# ============================================
def _is_spam(phone: str, text: str) -> bool:
    """
    Detecta spam: mesma mensagem repetida N vezes em X segundos.
    """
    now = datetime.now(timezone.utc)
    text_key = text.strip().lower()[:100]

    entry = _spam_cache.get(phone)

    if entry is None:
        _spam_cache[phone] = {
            "last_msg": text_key,
            "count": 1,
            "first_at": now,
            "blocked_until": None,
        }
        return False

    # Bloqueado?
    blocked_until = entry.get("blocked_until")
    if blocked_until and blocked_until > now:
        return True
    if blocked_until and blocked_until <= now:
        _spam_cache.pop(phone, None)
        return False

    # Mesma mensagem repetida?
    first_at = entry.get("first_at")
    if first_at and (now - first_at).total_seconds() > SPAM_WINDOW_SECONDS:
        # Janela expirou — reseta
        _spam_cache[phone] = {
            "last_msg": text_key,
            "count": 1,
            "first_at": now,
            "blocked_until": None,
        }
        return False

    # Mesma mensagem
    if entry.get("last_msg") == text_key:
        entry["count"] += 1
        if entry["count"] > SPAM_MAX_REPEATS:
            entry["blocked_until"] = now + timedelta(minutes=SPAM_BLOCK_MINUTES)
            logger.warning(
                f"🚫 Anti-spam: {phone} bloqueado por {SPAM_BLOCK_MINUTES}min"
            )
            return True
    else:
        # Mensagem diferente — reseta
        entry["last_msg"] = text_key
        entry["count"] = 1
        entry["first_at"] = now

    return False


# ============================================
# 👤 BUSCAR / CRIAR USUÁRIO
# ============================================
async def _get_or_create_user(
    session: AsyncSession,
    phone: str,
    push_name: str = "",
) -> Optional[User]:
    """
    Busca usuário pelo número de WhatsApp.
    Se não existir, cria um "usuário do WhatsApp" (não vinculado ao Telegram).
    """
    # Busca por WhatsApp
    stmt = select(User).where(User.whatsapp == phone)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is not None:
        # Atualiza última interação
        user.last_seen_at = datetime.now(timezone.utc)
        session.add(user)
        await session.flush()
        return user

    # Não existe — cria usuário "WhatsApp-only"
    # Telegram_id negativo fictício pra não colidir (evita conflito)
    # Ou usa um ID derivado do telefone
    fake_telegram_id = -int(phone[-10:]) if len(phone) >= 10 else -999999999

    # Evita colisão
    existing_by_id = await session.scalar(
        select(User).where(User.telegram_id == fake_telegram_id)
    )

    if existing_by_id:
        # Já existe com esse ID fake — vincula o WhatsApp
        if not existing_by_id.whatsapp:
            existing_by_id.whatsapp = phone
            session.add(existing_by_id)
            await session.flush()
        return existing_by_id

    new_user = User(
        telegram_id=fake_telegram_id,
        whatsapp=phone,
        first_name=push_name or f"WhatsApp {phone[-4:]}",
        status=UserStatus.ACTIVE,
        last_seen_at=datetime.now(timezone.utc),
    )
    session.add(new_user)
    await session.flush()

    logger.info(f"🆕 Novo usuário WhatsApp: {phone} ({push_name})")

    return new_user


# ============================================
# 🎫 TICKET HUMANO ATIVO?
# ============================================
async def _has_active_human_ticket(
    session: AsyncSession,
    phone: str,
) -> bool:
    """
    Verifica se há um ticket com humano atribuído.
    Se sim, IA NÃO deve responder.
    """
    stmt = select(Ticket).where(
        Ticket.user_telegram_id == int(phone[-10:]) if len(phone) >= 10 else Ticket.id == -1,
        Ticket.status == TicketStatus.IN_PROGRESS,
        Ticket.assigned_admin_id.is_not(None),
    )
    result = await session.execute(stmt)
    ticket = result.scalar_one_or_none()
    return ticket is not None


async def _append_to_active_ticket(
    session: AsyncSession,
    phone: str,
    text: str,
    role: str,
) -> None:
    """Adiciona mensagem ao ticket ativo (sem IA responder)."""
    # Busca ticket ativo
    stmt = (
        select(Ticket)
        .where(
            Ticket.status == TicketStatus.IN_PROGRESS,
            Ticket.assigned_admin_id.is_not(None),
        )
        .order_by(Ticket.opened_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    ticket = result.scalar_one_or_none()

    if ticket is None:
        return

    messages = list(ticket.messages or [])
    messages.append({
        "role": role,
        "text": text,
        "at": datetime.now(timezone.utc).isoformat(),
        "channel": "whatsapp",
    })
    ticket.messages = messages
    session.add(ticket)
    await session.flush()

    # Notifica o admin responsável via Telegram
    if ticket.assigned_admin_id:
        try:
            from bot.loader import bot

            await bot.send_message(
                chat_id=ticket.assigned_admin_id,
                text=(
                    f"💬 <b>Nova mensagem no WhatsApp</b>\n\n"
                    f"🎫 Ticket #{ticket.id}\n"
                    f"📞 <code>{phone}</code>\n\n"
                    f"<b>Mensagem:</b>\n{text}"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.debug(f"⚠️ Falha ao notificar admin: {e}")


# ============================================
# 🤖 RESPONDER COM IA
# ============================================
async def _respond_with_ai(
    session: AsyncSession,
    user: User,
    phone: str,
    text: str,
    push_name: str,
) -> None:
    """
    Chama a IA, gera resposta e envia via WhatsApp.
    """
    from core.services import ai as ai_service

    # Verifica se IA está ligada
    ai_enabled = await config_service.get_bool(session, "ai_enabled", True)

    if not ai_enabled:
        logger.debug("🤖 IA desligada — ignorando")
        return

    # Detecta intenções antes de chamar IA
    intent = _detect_intent(text)

    # ─── 1. Pediu humano ───
    if intent == "human":
        await _handle_human_request(session, user, phone, push_name)
        return

    # ─── 2. Pediu catálogo ───
    if intent == "catalog":
        await _handle_catalog_request(session, phone)
        return

    # ─── 3. Pediu PDF ───
    if intent == "pdf":
        await _handle_pdf_request(session, phone, text)
        return

    # ─── 4. Saudação ───
    if intent == "greeting":
        await _handle_greeting(session, phone, push_name)
        return

    # ─── 5. IA normal ───
    await _handle_ai_response(session, user, phone, text, push_name)


# ============================================
# 🎯 DETECTAR INTENÇÃO
# ============================================
def _detect_intent(text: str) -> str:
    """
    Detecta a intenção da mensagem.

    Retorna:
      - "human": quer falar com humano
      - "catalog": quer ver produtos
      - "pdf": quer PDF
      - "greeting": saudação
      - "normal": nenhum dos acima
    """
    lower = text.lower().strip()

    # Humano
    human_keywords = [
        "humano", "atendente", "pessoa", "responsável", "responsavel",
        "falar com alguém", "falar com alguem", "suporte humano",
        "chama alguém", "chama alguem", "suporte real", "atendimento humano",
        "quero falar com alguém", "quero falar com alguem",
    ]
    if any(k in lower for k in human_keywords):
        return "human"

    # Catálogo
    catalog_keywords = [
        "catálogo", "catalogo", "produtos", "o que vocês vendem",
        "o que voces vendem", "lista", "serviços", "servicos",
        "quais produtos", "ver tudo", "menu",
    ]
    if any(k in lower for k in catalog_keywords):
        return "catalog"

    # PDF
    pdf_keywords = ["pdf", "arquivo", "documento", "receber por pdf", "manda pdf"]
    if any(k in lower for k in pdf_keywords):
        return "pdf"

    # Saudação
    greeting_keywords = [
        "oi", "olá", "ola", "bom dia", "boa tarde", "boa noite",
        "hey", "e aí", "e ai", "tudo bem", "opa",
    ]
    # Só considera saudação se for mensagem curta
    if len(lower) <= 20 and any(lower.startswith(k) or lower == k for k in greeting_keywords):
        return "greeting"

    return "normal"


# ============================================
# 👋 SAUDAÇÃO
# ============================================
async def _handle_greeting(
    session: AsyncSession,
    phone: str,
    push_name: str,
) -> None:
    """Responde com saudação amigável."""
    bot_name = await config_service.get_str(session, "bot_name", "Larizinha Store")

    name = push_name or "cliente"

    message = (
        f"Olá, {name}! 👋\n\n"
        f"Bem-vindo(a) à *{bot_name}*!\n\n"
        f"Sou a assistente virtual e posso te ajudar com:\n\n"
        f"• 🛍 Ver produtos e preços\n"
        f"• 💰 Formas de pagamento\n"
        f"• 📦 Entrega e garantia\n"
        f"• 🎧 Dúvidas em geral\n\n"
        f"Digite *catálogo* pra ver nossos produtos ou "
        f"*humano* pra falar com um atendente."
    )

    await wa_client.send_message(phone, message)


# ============================================
# 📦 CATÁLOGO
# ============================================
async def _handle_catalog_request(
    session: AsyncSession,
    phone: str,
) -> None:
    """Envia o catálogo em texto."""
    bot_name = await config_service.get_str(session, "bot_name", "Larizinha Store")

    # Busca produtos ativos
    stmt = (
        select(Product)
        .where(Product.status == ProductStatus.ACTIVE)
        .order_by(Product.position, Product.name)
    )
    result = await session.execute(stmt)
    products = list(result.scalars().all())

    if not products:
        await wa_client.send_message(
            phone,
            "📦 Estamos atualizando nosso catálogo. Tente novamente em instantes.",
        )
        return

    lines = [
        f"📦 *Catálogo {bot_name}*",
        f"━━━━━━━━━━━━━━━━━━━━━━",
        f"",
    ]

    for p in products:
        # Conta estoque
        stock = await session.scalar(
            select(func.count(StockItem.id)).where(
                StockItem.product_id == p.id,
                StockItem.status == StockStatus.AVAILABLE,
            )
        ) or 0

        emoji = p.emoji or "🎬"
        price = f"{p.price:.2f}".replace(".", ",")
        status = "🟢" if stock > 0 else "🔴"

        lines.append(f"{status} {emoji} *{p.name}*")
        lines.append(f"   💵 R$ {price}")

    lines.append("")
    lines.append("💡 _Pra comprar, acesse o bot do Telegram:_")
    lines.append("👉 https://t.me/seu_bot")

    message = "\n".join(lines)

    # WhatsApp tem limite de 4096
    if len(message) > 3500:
        message = message[:3500] + "\n\n... _(truncado)_"

    await wa_client.send_message(phone, message)


# ============================================
# 📄 PDF DE PRODUTO
# ============================================
async def _handle_pdf_request(
    session: AsyncSession,
    phone: str,
    text: str,
) -> None:
    """
    Gera PDF de um produto específico e envia.
    """
    from core.services import ai as ai_service

    # Tenta extrair nome do produto da mensagem
    text_lower = text.lower()
    product = None

    # Busca todos produtos e verifica se algum é mencionado
    stmt = select(Product).where(Product.status == ProductStatus.ACTIVE)
    result = await session.execute(stmt)
    products = list(result.scalars().all())

    for p in products:
        if p.name.lower() in text_lower:
            product = p
            break

    if product is None:
        # Não identificou — pergunta qual
        await wa_client.send_message(
            phone,
            "📄 Qual produto você deseja receber em PDF?\n\n"
            "Digite o nome exato do produto.",
        )
        return

    # Gera PDF
    try:
        pdf_bytes = await ai_service.generate_product_pdf(session, product.id)

        if pdf_bytes is None:
            await wa_client.send_message(
                phone,
                "❌ Não foi possível gerar o PDF agora. Tente novamente.",
            )
            return

        # Envia o PDF
        # (precisa upload prévio numa URL pública)
        # Simplificação: envia como mensagem com info
        price = f"{product.price:.2f}".replace(".", ",")

        message = (
            f"📄 *{product.name}*\n\n"
            f"💵 Valor: R$ {price}\n"
            f"🛡 Garantia: {product.warranty_days} dias\n"
            f"⏳ Duração: {product.duration_days} dias\n\n"
            f"📝 {product.description or 'Sem descrição.'}\n\n"
            f"Para comprar, acesse o bot: https://t.me/seu_bot"
        )

        await wa_client.send_message(phone, message)

    except Exception as e:
        logger.exception(f"❌ Erro ao gerar/enviar PDF: {e}")
        await wa_client.send_message(
            phone,
            "❌ Erro ao gerar PDF. Tente novamente em instantes.",
        )


# ============================================
# 🙋 PEDIR HUMANO
# ============================================
async def _handle_human_request(
    session: AsyncSession,
    user: User,
    phone: str,
    push_name: str,
) -> None:
    """
    Cliente pediu atendimento humano.
    Cria ticket e notifica admins.
    """
    # Busca ticket ativo
    stmt = (
        select(Ticket)
        .where(
            Ticket.user_telegram_id == user.telegram_id,
            Ticket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS]),
        )
        .order_by(Ticket.opened_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    ticket = result.scalar_one_or_none()

    if ticket is None:
        # Cria novo
        ticket = Ticket(
            user_telegram_id=user.telegram_id,
            subject="Atendimento humano (WhatsApp)",
            status=TicketStatus.OPEN,
            messages=[{
                "role": "user",
                "text": "Cliente solicitou atendimento humano pelo WhatsApp.",
                "at": datetime.now(timezone.utc).isoformat(),
                "channel": "whatsapp",
            }],
        )
        session.add(ticket)
        await session.flush()

    # Notifica admins no Telegram
    await _notify_admins_human_request(session, ticket, user, phone, push_name)

    # Responde pro cliente
    await wa_client.send_message(
        phone,
        "🙋 *Atendimento humano solicitado!*\n\n"
        "Um atendente vai responder em breve.\n\n"
        "💡 Enquanto isso, você pode continuar enviando mensagens que "
        "serão encaminhadas para o atendente.",
    )


async def _notify_admins_human_request(
    session: AsyncSession,
    ticket: Ticket,
    user: User,
    phone: str,
    push_name: str,
) -> None:
    """Notifica todos os admins sobre pedido de humano."""
    from bot.loader import bot
    from core.models import Admin

    stmt = select(Admin).where(Admin.is_active.is_(True))
    result = await session.execute(stmt)
    admins = list(result.scalars().all())

    text = (
        f"🚨 <b>Cliente pediu atendimento humano</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📱 <b>Canal:</b> WhatsApp\n"
        f"👤 <b>Nome:</b> {push_name or 'Cliente'}\n"
        f"📞 <b>Número:</b> <code>{phone}</code>\n\n"
        f"🎫 Ticket: <code>#{ticket.id}</code>\n\n"
        f"💡 Responda pelo painel admin ou pelo WhatsApp."
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


# ============================================
# 🤖 RESPOSTA NORMAL COM IA
# ============================================
async def _handle_ai_response(
    session: AsyncSession,
    user: User,
    phone: str,
    text: str,
    push_name: str,
) -> None:
    """
    Chama a IA e envia a resposta.
    """
    from core.services import ai as ai_service

    # Monta contexto
    bot_name = await config_service.get_str(session, "bot_name", "Larizinha Store")

    # Info de produtos (contexto)
    catalog_context = await _build_catalog_context(session)

    # Chama IA
    try:
        response = await _call_ai(
            session=session,
            user=user,
            text=text,
            push_name=push_name,
            bot_name=bot_name,
            catalog_context=catalog_context,
        )
    except Exception as e:
        logger.exception(f"❌ Erro na IA: {e}")
        response = "🤖 Estou com dificuldades técnicas. Tente novamente em instantes."

    if not response:
        response = "🤖 Não entendi. Pode reformular sua pergunta?"

    # Detecta se IA sugeriu humano
    if "atendente humano" in response.lower() or "chamar um atendente" in response.lower():
        # Cria ticket automaticamente
        await _handle_human_request(session, user, phone, push_name)
        return

    # Envia a resposta
    await wa_client.send_message(phone, response)

    logger.info(f"🤖 IA respondeu para {phone}")


# ============================================
# 🧠 CHAMAR IA
# ============================================
async def _call_ai(
    session: AsyncSession,
    user: User,
    text: str,
    push_name: str,
    bot_name: str,
    catalog_context: str,
) -> str:
    """
    Chama a OpenAI com contexto do negócio.
    """
    from core.config import settings
    from openai import AsyncOpenAI

    if not settings.openai_api_key:
        return "🤖 Atendimento automático indisponível no momento."

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # System prompt
    system_prompt = (
        f"Você é a assistente virtual da *{bot_name}*, uma loja de streamings "
        f"e contas premium no WhatsApp.\n\n"
        f"Seu papel:\n"
        f"- Atender clientes com educação, clareza e objetividade\n"
        f"- Tirar dúvidas sobre produtos, pagamento, entrega e garantia\n"
        f"- NUNCA invente informações — se não souber, diga que vai chamar "
        f"um atendente\n"
        f"- Quando o cliente pedir algo que você não pode resolver, diga: "
        f"\"Vou chamar um atendente humano para te ajudar. Um momento!\"\n"
        f"- Se o cliente pedir atendimento humano, responda: "
        f"\"Entendi! Já estou solicitando um atendente humano.\"\n\n"
        f"Regras importantes:\n"
        f"- Pagamento é via Pix, entrega automática\n"
        f"- Não compartilhe dados de outros clientes\n"
        f"- Seja breve: 2-4 parágrafos curtos no máximo\n"
        f"- Use formatação do WhatsApp: *negrito*, _itálico_, `código`\n"
        f"- NUNCA use markdown do Telegram (HTML, <b>, etc)\n\n"
        f"Contexto do catálogo atual (NUNCA invente produtos que não estão aqui):\n"
        f"{catalog_context}\n"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text},
    ]

    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=messages,
        max_tokens=500,
        temperature=0.7,
    )

    reply = response.choices[0].message.content or ""
    return reply.strip()


# ============================================
# 📋 CONTEXTO DO CATÁLOGO
# ============================================
async def _build_catalog_context(session: AsyncSession) -> str:
    """
    Monta string com o catálogo atual pra IA usar como contexto.
    Evita alucinação.
    """
    stmt = (
        select(Product)
        .where(Product.status == ProductStatus.ACTIVE)
        .order_by(Product.position, Product.name)
        .limit(30)
    )
    result = await session.execute(stmt)
    products = list(result.scalars().all())

    if not products:
        return "(Nenhum produto cadastrado no momento)"

    lines = []
    for p in products:
        stock = await session.scalar(
            select(func.count(StockItem.id)).where(
                StockItem.product_id == p.id,
                StockItem.status == StockStatus.AVAILABLE,
            )
        ) or 0

        price = f"{p.price:.2f}".replace(".", ",")
        status = "disponível" if stock > 0 else "esgotado"

        lines.append(f"- {p.name}: R$ {price} ({status})")

    return "\n".join(lines)


# ============================================
# 🧪 TESTE DE FLUXO
# ============================================
async def test_handler() -> None:
    """Testa o handler com uma mensagem fake."""
    await process_incoming_message(
        phone="5511999999999",
        text="Olá, quais produtos vocês têm?",
        push_name="Cliente Teste",
    )


# ============================================
# 🧹 LIMPAR CACHE DE SPAM (job)
# ============================================
async def clean_spam_cache() -> int:
    """
    Remove entradas antigas do cache de spam.
    Chamado pelo job de limpeza diário.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=1)

    to_remove = []
    for phone, entry in _spam_cache.items():
        first_at = entry.get("first_at")
        blocked_until = entry.get("blocked_until")

        # Expira se não foi bloqueado e passou 1 hora
        if first_at and first_at < cutoff:
            if not blocked_until or blocked_until < now:
                to_remove.append(phone)

    for phone in to_remove:
        _spam_cache.pop(phone, None)

    if to_remove:
        logger.info(f"🧹 {len(to_remove)} entradas de spam limpas")

    return len(to_remove)

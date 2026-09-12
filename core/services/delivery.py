# ============================================
# 📦 DELIVERY SERVICE — Larizinha Store
# ============================================
# Entrega dos produtos comprados ao cliente.
# Suporta 3 canais: Telegram, WhatsApp e E-mail.
# Cada canal tem seu fluxo próprio de confirmação.
# ============================================

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from aiogram import Bot
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Order, OrderStatus, Product, StockItem, User


# ============================================
# 📤 ENTREGA PRINCIPAL
# ============================================
async def deliver_order(
    session: AsyncSession,
    bot: Bot,
    order_id: int,
) -> dict[str, Any]:
    """
    Entrega um pedido pelo canal escolhido.
    Retorna dict com sucesso e detalhes.
    """
    order = await session.get(Order, order_id)
    if order is None:
        return {"success": False, "error": "Pedido não encontrado."}

    if order.status == OrderStatus.DELIVERED:
        return {"success": True, "already_delivered": True}

    # Carrega itens do estoque vinculados
    stmt = select(StockItem).where(StockItem.order_id == order_id)
    result = await session.execute(stmt)
    items = list(result.scalars().all())

    if not items:
        logger.error(f"❌ Pedido {order_id} sem itens de estoque.")
        return {"success": False, "error": "Sem itens vinculados ao pedido."}

    user = await session.get(User, order.user_id)
    if user is None:
        return {"success": False, "error": "Usuário não encontrado."}

    method = (order.delivery_method or "telegram").lower()

    if method == "telegram":
        result = await _deliver_telegram(bot, user, order, items)
    elif method == "whatsapp":
        result = await _deliver_whatsapp(session, user, order, items)
    elif method == "email":
        result = await _deliver_email(session, user, order, items)
    else:
        result = {"success": False, "error": f"Canal inválido: {method}"}

    if result.get("success"):
        order.status = OrderStatus.DELIVERED
        order.delivered_at = datetime.now(timezone.utc)
        session.add(order)

        # Marca itens como entregues
        for item in items:
            from core.models import StockStatus
            item.status = StockStatus.DELIVERED
            session.add(item)

        logger.info(
            f"📦 Pedido {order.order_code} entregue via {method} "
            f"pra {user.telegram_id}"
        )

    return result


# ============================================
# 📱 TELEGRAM
# ============================================
async def _deliver_telegram(
    bot: Bot,
    user: User,
    order: Order,
    items: list[StockItem],
) -> dict[str, Any]:
    """Entrega os dados do produto direto no Telegram."""
    text = _build_delivery_text(order, items)

    try:
        await bot.send_message(
            chat_id=user.telegram_id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return {"success": True, "channel": "telegram"}
    except Exception as e:
        logger.exception(f"❌ Erro ao entregar por Telegram: {e}")
        return {"success": False, "error": str(e)}


# ============================================
# 📱 WHATSAPP
# ============================================
async def _deliver_whatsapp(
    session: AsyncSession,
    user: User,
    order: Order,
    items: list[StockItem],
) -> dict[str, Any]:
    """Entrega os dados do produto pelo WhatsApp."""
    if not user.whatsapp:
        return {"success": False, "error": "Usuário sem WhatsApp cadastrado."}

    from core.services import whatsapp as wa_service

    text = _build_delivery_text(order, items, for_whatsapp=True)

    result = await wa_service.send_message(
        phone=user.whatsapp,
        message=text,
    )
    return result


# ============================================
# 📧 E-MAIL
# ============================================
async def _deliver_email(
    session: AsyncSession,
    user: User,
    order: Order,
    items: list[StockItem],
) -> dict[str, Any]:
    """
    Envia o produto por e-mail.
    O Telegram NÃO recebe o link de ativação —
    ele fica no e-mail, com link para o website.
    """
    if not user.email:
        return {"success": False, "error": "Usuário sem e-mail cadastrado."}

    from core.services import email as email_service

    result = await email_service.send_product_email(
        session=session,
        to_email=user.email,
        user=user,
        order=order,
        items=items,
    )
    return result


# ============================================
# 🧾 MONTAGEM DA MENSAGEM (Telegram/WhatsApp)
# ============================================
def _build_delivery_text(
    order: Order,
    items: list[StockItem],
    for_whatsapp: bool = False,
) -> str:
    """Monta a mensagem de entrega com os dados dos logins."""
    date_str = (
        order.created_at.strftime("%d/%m/%Y") if order.created_at else "N/A"
    )
    exp_str = (
        order.expires_at.strftime("%d/%m/%Y") if order.expires_at else "N/A"
    )
    valor = f"{order.total_price:.2f}".replace(".", ",")

    header = (
        f"🎉 <b>COMPRA REALIZADA</b>\n\n"
        f"⏰ Data da compra: {date_str}\n"
        f"📆 Vencimento: {exp_str}\n"
        f"💰 Valor: <b>R$ {valor}</b>\n"
        f"🎫 ID da compra: <code>{order.order_code}</code>\n"
        f"⚜️ Serviço: <b>{order.product_name}</b>\n"
        f"📦 Quantidade: <b>{order.quantity}</b>"
    )

    # Limpa tags se for WhatsApp
    if for_whatsapp:
        header = header.replace("<b>", "*").replace("</b>", "*")
        header = header.replace("<code>", "`").replace("</code>", "`")

    blocks = [header]

    for idx, item in enumerate(items, start=1):
        email = item.email or "N/A"
        password = item.password or "N/A"
        code = item.code or ""
        note = item.note or ""

        block_lines = [
            f"\n🔐 <b>Login {idx}/{len(items)}</b>",
            f"📧 Email: <code>{email}</code>",
            f"🔑 Senha: <code>{password}</code>",
        ]
        if code:
            block_lines.append(f"🔗 Código/Link: <code>{code}</code>")
        if note:
            block_lines.append(f"📃 Nota: {note}")

        block = "\n".join(block_lines)

        if for_whatsapp:
            block = block.replace("<b>", "*").replace("</b>", "*")
            block = block.replace("<code>", "`").replace("</code>", "`")

        blocks.append(block)

    footer = "\n\n💡 Guarde esses dados. Em caso de dúvidas, use /atendimento."
    if for_whatsapp:
        footer = "\n\n💡 Guarde esses dados. Em caso de dúvidas, responda esta mensagem."

    return "\n".join(blocks) + footer


# ============================================
# 🔔 NOTIFICAÇÃO DE VENDA (canal de logs)
# ============================================
async def notify_sale_to_logs_channel(
    bot: Bot,
    session: AsyncSession,
    order: Order,
    user: User,
) -> None:
    """Envia notificação de venda pro canal de logs."""
    from core.services import config as config_service

    channel_id_raw = await config_service.get_str(session, "logs_channel_id", "")
    if not channel_id_raw:
        return

    try:
        channel_id = int(channel_id_raw)
    except (TypeError, ValueError):
        return

    user_masked = _mask_telegram_id(user.telegram_id)
    valor = f"{order.total_price:.2f}".replace(".", ",")
    date_str = datetime.now(timezone.utc).strftime("%d/%m/%Y, %H:%M")

    text = (
        f"💎 <b>NOVO ACESSO LIBERADO</b>\n\n"
        f"👤 Usuário: <code>{user_masked}</code>\n"
        f"📦 Plano: <b>{order.product_name}</b>\n"
        f"💵 Status: ✅ <b>Pago e ativo</b>\n"
        f"🔑 TX: <code>{order.order_code[:12]}...</code>\n"
        f"🕐 Data: {date_str}\n\n"
        f"🚀 Acesso liberado automaticamente"
    )

    try:
        await bot.send_message(
            chat_id=channel_id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.warning(f"⚠️ Não foi possível notificar canal de logs: {e}")


# ============================================
# 🧰 HELPERS
# ============================================
def _mask_telegram_id(telegram_id: int) -> str:
    """Mascara um Telegram ID: 776***48."""
    s = str(telegram_id)
    if len(s) <= 5:
        return s
    return f"{s[:3]}***{s[-2:]}"


def format_brl(value: Decimal | float) -> str:
    """Formata valor em reais."""
    return f"R$ {float(value):.2f}".replace(".", ",")

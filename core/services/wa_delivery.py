# ============================================
# 📦 WA DELIVERY — Larizinha Store
# ============================================
# Entrega de produtos via WhatsApp.
#
# Fluxo:
#   1. Cliente compra (Telegram / WebApp)
#   2. Escolhe "Receber por WhatsApp"
#   3. Sistema envia mensagem formatada pro WhatsApp
#   4. Inclui botão/link "🔐 ATIVAR PRODUTO"
#   5. Cliente clica → abre WhatsApp Flow ou website
#   6. Cliente digita a senha cadastrada
#   7. Produto liberado
#
# IMPORTANTE:
#   - Formatação WhatsApp: *negrito*, _itálico_, `código`
#   - NÃO enviar link de ativação do Telegram
#   - A ativação é separada por segurança
# ============================================

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.models import (
    Order,
    OrderStatus,
    StockItem,
    StockStatus,
    User,
)
from core.services import config as config_service
from core.services import wa_client


# ============================================
# 🧰 HELPERS
# ============================================
def _format_brl(v) -> str:
    if v is None:
        return "0,00"
    return f"{float(v):.2f}".replace(".", ",")


def _format_date(dt: datetime | None) -> str:
    if dt is None:
        return "N/A"
    return dt.strftime("%d/%m/%Y")


def _mask_email(email: Optional[str]) -> str:
    """Mascara e-mail parcialmente."""
    if not email:
        return "N/A"
    try:
        local, domain = email.split("@", 1)
        if len(local) <= 2:
            local_m = local[0] + "*"
        else:
            local_m = local[0] + "*" * (len(local) - 2) + local[-1]
        return f"{local_m}@{domain}"
    except Exception:
        return email


# ============================================
# 📤 ENTREGA PRINCIPAL
# ============================================
async def deliver_order_via_whatsapp(
    session: AsyncSession,
    order_id: int,
) -> dict[str, Any]:
    """
    Entrega um pedido via WhatsApp.

    Retorna:
      - success: bool
      - error: str (se falhou)
      - message_id: str
    """
    # Busca o pedido
    order = await session.get(Order, order_id)
    if order is None:
        return {"success": False, "error": "Pedido não encontrado"}

    if order.status == OrderStatus.DELIVERED:
        return {
            "success": True,
            "already_delivered": True,
            "message": "Pedido já foi entregue",
        }

    # Busca o usuário
    user = await session.get(User, order.user_id)
    if user is None:
        return {"success": False, "error": "Usuário não encontrado"}

    # Verifica se tem WhatsApp cadastrado
    phone = user.whatsapp
    if not phone:
        return {
            "success": False,
            "error": "Usuário não tem WhatsApp cadastrado",
        }

    # Verifica se o WhatsApp está ativo
    enabled = await config_service.get_bool(session, "wa_auto_deliver", True)
    if not enabled:
        return {
            "success": False,
            "error": "Entrega automática via WhatsApp desativada",
        }

    # Verifica se o serviço está conectado
    wa_status = await wa_client.get_status()
    if not wa_status.get("connected"):
        return {
            "success": False,
            "error": "WhatsApp não conectado",
        }

    # Busca os itens do pedido
    items_stmt = select(StockItem).where(StockItem.order_id == order_id)
    items_result = await session.execute(items_stmt)
    items = list(items_result.scalars().all())

    if not items:
        return {
            "success": False,
            "error": "Nenhum item encontrado no pedido",
        }

    # Monta a mensagem
    message = await _build_delivery_message(
        session=session,
        user=user,
        order=order,
        items=items,
    )

    # Envia
    result = await wa_client.send_message(phone=phone, message=message)

    if not result.get("success"):
        logger.error(
            f"❌ Falha ao enviar pedido {order.order_code} via WhatsApp: "
            f"{result.get('error')}"
        )
        return {
            "success": False,
            "error": result.get("error", "Erro desconhecido"),
        }

    # Atualiza pedido
    order.delivery_method = "whatsapp"
    order.delivery_target = phone
    order.status = OrderStatus.DELIVERED
    order.delivered_at = datetime.now(timezone.utc)
    session.add(order)

    # Marca itens como entregues
    for item in items:
        if item.status != StockStatus.DELIVERED:
            item.status = StockStatus.DELIVERED
            session.add(item)

    await session.flush()

    logger.info(
        f"📱 Pedido {order.order_code} entregue via WhatsApp → {phone}"
    )

    # Notifica canal de logs
    try:
        from bot.handlers.admin.notifications import notify_purchase
        from bot.loader import bot

        await notify_purchase(
            bot=bot,
            session=session,
            order_code=order.order_code,
            user_id=user.telegram_id,
            product_name=order.product_name,
            amount=float(order.total_price),
            quantity=order.quantity,
        )
    except Exception as e:
        logger.debug(f"⚠️ Falha ao notificar canal: {e}")

    return {
        "success": True,
        "message": "Pedido entregue com sucesso",
        "phone": phone,
        "order_code": order.order_code,
    }


# ============================================
# 📝 MONTAR MENSAGEM
# ============================================
async def _build_delivery_message(
    session: AsyncSession,
    user: User,
    order: Order,
    items: list[StockItem],
) -> str:
    """
    Monta a mensagem de entrega formatada pro WhatsApp.

    Formatação WhatsApp:
      *negrito* — asterisco
      _itálico_ — underscore
      `código` — backtick
      ~tachado~ — til
    """
    bot_name = await config_service.get_str(
        session, "bot_name", "Larizinha Store"
    )

    purchase_date = _format_date(order.created_at)
    expiration = _format_date(order.expires_at)
    valor = _format_brl(order.total_price)

    # ─── Cabeçalho ───
    lines = [
        "🎉 *COMPRA REALIZADA*",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"⚜️ Serviço: *{order.product_name}*",
        f"🎫 ID: `{order.order_code[:16]}`",
        f"📅 Compra: {purchase_date}",
        f"📆 Vencimento: {expiration}",
        f"💰 Valor: R$ {valor}",
        "",
    ]

    # ─── Dados dos itens (parcialmente mascarados) ───
    # Por segurança, NÃO enviamos login/senha pelo WhatsApp.
    # Enviamos apenas o resumo e o LINK DE ATIVAÇÃO.

    for idx, item in enumerate(items, start=1):
        total = len(items)

        if total > 1:
            lines.append(f"🔐 *Login {idx} de {total}*")
        else:
            lines.append("🔐 *Seus dados estão protegidos*")
        lines.append("")

    # ─── Aviso de segurança ───
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append("⚠️ *POR SEGURANÇA*, os dados do produto")
    lines.append("NÃO são enviados pelo WhatsApp.")
    lines.append("")
    lines.append("🔐 Clique no botão abaixo pra ativar:")
    lines.append("")

    # ─── Link de ativação ───
    # Gera token de ativação (o mesmo do e-mail)
    try:
        from api.routes.activation import generate_activation_token

        token = generate_activation_token(order.order_code)
        activation_url = f"{settings.activation_url.rstrip('/')}/{token}"

        lines.append(f"👉 {activation_url}")
        lines.append("")
        lines.append("_Você precisará digitar sua senha de saque cadastrada._")

    except Exception as e:
        logger.warning(f"⚠️ Falha ao gerar link de ativação: {e}")
        lines.append("💡 Acesse o bot do Telegram para ver os dados do produto.")

    # ─── Rodapé ───
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"💡 _Guarde esta mensagem em local seguro._")
    lines.append("")
    lines.append(f"🤖 {bot_name}")

    message = "\n".join(lines)

    # WhatsApp tem limite (4096 chars por mensagem)
    if len(message) > 4000:
        message = message[:4000] + "\n\n_... (truncado)_"

    return message


# ============================================
# 📦 ENTREGA SIMPLES (com dados visíveis)
# ============================================
async def deliver_order_simple(
    session: AsyncSession,
    order_id: int,
) -> dict[str, Any]:
    """
    Modo ALTERNATIVO: envia os dados do produto DIRETO no WhatsApp.
    Menos seguro, mas mais prático pro cliente.

    Ativa quando `wa_show_data_directly = true` nas configs.
    """
    # Verifica se o modo direto está ativado
    show_directly = await config_service.get_bool(
        session, "wa_show_data_directly", False
    )

    if not show_directly:
        return await deliver_order_via_whatsapp(session, order_id)

    order = await session.get(Order, order_id)
    if order is None:
        return {"success": False, "error": "Pedido não encontrado"}

    user = await session.get(User, order.user_id)
    if user is None or not user.whatsapp:
        return {"success": False, "error": "Usuário sem WhatsApp"}

    items_stmt = select(StockItem).where(StockItem.order_id == order_id)
    items_result = await session.execute(items_stmt)
    items = list(items_result.scalars().all())

    if not items:
        return {"success": False, "error": "Sem itens"}

    # Monta mensagem COM dados visíveis
    message = await _build_direct_message(session, user, order, items)

    result = await wa_client.send_message(
        phone=user.whatsapp,
        message=message,
    )

    if result.get("success"):
        order.status = OrderStatus.DELIVERED
        order.delivered_at = datetime.now(timezone.utc)
        order.delivery_method = "whatsapp"
        order.delivery_target = user.whatsapp
        session.add(order)

        for item in items:
            item.status = StockStatus.DELIVERED
            session.add(item)

        await session.flush()

        return {
            "success": True,
            "order_code": order.order_code,
            "mode": "direct",
        }

    return {"success": False, "error": result.get("error")}


async def _build_direct_message(
    session: AsyncSession,
    user: User,
    order: Order,
    items: list[StockItem],
) -> str:
    """Mensagem com dados visíveis (modo direto)."""
    bot_name = await config_service.get_str(
        session, "bot_name", "Larizinha Store"
    )

    expiration = _format_date(order.expires_at)
    valor = _format_brl(order.total_price)

    lines = [
        "🎉 *COMPRA REALIZADA*",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"⚜️ Serviço: *{order.product_name}*",
        f"🎫 ID: `{order.order_code[:16]}`",
        f"📆 Vencimento: {expiration}",
        f"💰 Valor: R$ {valor}",
        "",
    ]

    for idx, item in enumerate(items, start=1):
        total = len(items)
        lines.append(f"🔐 *Login {idx}/{total}*")
        lines.append("")

        if item.email:
            lines.append(f"📧 Email: `{item.email}`")
        if item.password:
            lines.append(f"🔑 Senha: `{item.password}`")
        if item.code:
            lines.append(f"🔗 Código: {item.code}")
        if item.note:
            lines.append(f"📃 Nota: {item.note}")

        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append("⚠️ _Não compartilhe esses dados._")
    lines.append("_Cada login é único e monitorado._")
    lines.append("")
    lines.append(f"🛡 Garantia: {order.expires_at.strftime('%d/%m/%Y') if order.expires_at else 'N/A'}")
    lines.append("")
    lines.append(f"🤖 {bot_name}")

    message = "\n".join(lines)

    if len(message) > 4000:
        message = message[:4000] + "\n\n_... (truncado)_"

    return message


# ============================================
# 🖼️ ENTREGA COM IMAGEM DO PRODUTO
# ============================================
async def deliver_order_with_image(
    session: AsyncSession,
    order_id: int,
) -> dict[str, Any]:
    """
    Entrega com imagem do produto + link de ativação.
    """
    from core.models import Product

    order = await session.get(Order, order_id)
    if order is None:
        return {"success": False, "error": "Pedido não encontrado"}

    user = await session.get(User, order.user_id)
    if user is None or not user.whatsapp:
        return {"success": False, "error": "Usuário sem WhatsApp"}

    product = await session.get(Product, order.product_id)

    # Busca os itens
    items_stmt = select(StockItem).where(StockItem.order_id == order_id)
    items_result = await session.execute(items_stmt)
    items = list(items_result.scalars().all())

    if not items:
        return {"success": False, "error": "Sem itens"}

    # Monta a legenda
    caption = await _build_delivery_message(session, user, order, items)

    # URL da imagem
    image_url = product.image_url if product else None

    if image_url:
        # Envia com imagem
        result = await wa_client.send_image(
            phone=user.whatsapp,
            image_url=image_url,
            caption=caption,
        )
    else:
        # Sem imagem — só texto
        result = await wa_client.send_message(
            phone=user.whatsapp,
            message=caption,
        )

    if result.get("success"):
        order.status = OrderStatus.DELIVERED
        order.delivered_at = datetime.now(timezone.utc)
        order.delivery_method = "whatsapp"
        order.delivery_target = user.whatsapp
        session.add(order)

        for item in items:
            item.status = StockStatus.DELIVERED
            session.add(item)

        await session.flush()

        return {
            "success": True,
            "order_code": order.order_code,
            "with_image": bool(image_url),
        }

    return {"success": False, "error": result.get("error")}


# ============================================
# 🔐 ATIVAÇÃO VIA WHATSAPP
# ============================================
async def activate_order_via_whatsapp(
    session: AsyncSession,
    order_code: str,
    password: str,
) -> dict[str, Any]:
    """
    Ativa um pedido via WhatsApp (verifica senha).

    Retorna os dados do produto se a senha estiver correta.
    """
    # Busca o pedido
    stmt = select(Order).where(Order.order_code == order_code)
    result = await session.execute(stmt)
    order = result.scalar_one_or_none()

    if order is None:
        return {"success": False, "error": "Pedido não encontrado"}

    if order.status not in (OrderStatus.PAID, OrderStatus.DELIVERED):
        return {"success": False, "error": "Pedido não está ativo"}

    # Busca o usuário
    user = await session.get(User, order.user_id)
    if user is None:
        return {"success": False, "error": "Usuário não encontrado"}

    # Verifica senha
    if not user.withdrawal_password_hash:
        return {
            "success": False,
            "error": "Senha de saque não cadastrada. Cadastre pelo bot.",
        }

    try:
        from passlib.hash import bcrypt
        valid = bcrypt.verify(password, user.withdrawal_password_hash)
    except Exception:
        valid = False

    if not valid:
        return {"success": False, "error": "Senha incorreta"}

    # Busca itens
    items_stmt = select(StockItem).where(StockItem.order_id == order.id)
    items_result = await session.execute(items_stmt)
    items = list(items_result.scalars().all())

    if not items:
        return {"success": False, "error": "Sem itens"}

    # Retorna dados
    return {
        "success": True,
        "product_name": order.product_name,
        "order_code": order.order_code,
        "quantity": order.quantity,
        "expires_at": order.expires_at.isoformat() if order.expires_at else None,
        "items": [
            {
                "email": item.email,
                "password": item.password,
                "code": item.code,
                "note": item.note,
            }
            for item in items
        ],
    }


# ============================================
# 📲 REENVIAR ENTREGA
# ============================================
async def resend_delivery(
    session: AsyncSession,
    order_code: str,
    admin_id: int,
) -> dict[str, Any]:
    """
    Reenvia a entrega do pedido (usado pelo admin).
    """
    stmt = select(Order).where(Order.order_code == order_code)
    result = await session.execute(stmt)
    order = result.scalar_one_or_none()

    if order is None:
        return {"success": False, "error": "Pedido não encontrado"}

    # Reseta status pra forçar reenvio
    if order.status == OrderStatus.DELIVERED:
        order.status = OrderStatus.PAID
        session.add(order)
        await session.flush()

    # Reenvia
    result = await deliver_order_via_whatsapp(session, order.id)

    if result.get("success"):
        # Log de auditoria
        try:
            from core.models import AuditLog

            log = AuditLog(
                admin_telegram_id=admin_id,
                action="resend_delivery_whatsapp",
                target_type="order",
                target_id=order.order_code,
                new_value={"resent_to": order.delivery_target},
            )
            session.add(log)
            await session.flush()
        except Exception:
            pass

    return result


# ============================================
# 📊 VERIFICAR SE WHATSAPP ESTÁ PRONTO
# ============================================
async def check_whatsapp_ready(session: AsyncSession) -> dict[str, Any]:
    """
    Verifica se o WhatsApp está pronto pra entregar.
    Usado pelo bot antes de oferecer entrega via WhatsApp.
    """
    enabled = await config_service.get_bool(session, "wa_auto_deliver", True)

    if not enabled:
        return {
            "ready": False,
            "reason": "Entrega via WhatsApp desativada pelo admin",
        }

    status = await wa_client.get_status()

    if not status.get("ok"):
        return {
            "ready": False,
            "reason": status.get("error", "Serviço WhatsApp indisponível"),
        }

    if not status.get("connected"):
        return {
            "ready": False,
            "reason": "WhatsApp desconectado",
        }

    return {
        "ready": True,
        "phone": status.get("phone_number"),
        "name": status.get("push_name"),
    }


# ============================================
# 🔔 NOTIFICAR ADMIN
# ============================================
async def notify_admin_delivery_failure(
    session: AsyncSession,
    order: Order,
    error: str,
) -> None:
    """Notifica admins se a entrega pelo WhatsApp falhar."""
    try:
        from bot.loader import bot
        from core.models import Admin

        stmt = select(Admin).where(Admin.is_active.is_(True))
        result = await session.execute(stmt)
        admins = list(result.scalars().all())

        text = (
            f"⚠️ <b>Falha na entrega via WhatsApp</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎫 Pedido: <code>{order.order_code[:12]}...</code>\n"
            f"📦 Produto: <b>{order.product_name}</b>\n"
            f"👤 Cliente: <code>{order.user_telegram_id}</code>\n\n"
            f"❌ <b>Erro:</b> {error}\n\n"
            f"💡 Use <b>Ações Rápidas → Reenviar entrega</b> "
            f"pra tentar novamente."
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
        logger.debug(f"⚠️ Falha ao notificar admin: {e}")


# ============================================
# 📊 ESTATÍSTICAS
# ============================================
async def get_whatsapp_delivery_stats(
    session: AsyncSession,
    days: int = 30,
) -> dict[str, Any]:
    """
    Retorna estatísticas de entregas via WhatsApp.
    """
    from datetime import timedelta
    from sqlalchemy import func

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    total = await session.scalar(
        select(func.count(Order.id)).where(
            Order.delivery_method == "whatsapp",
            Order.status == OrderStatus.DELIVERED,
            Order.delivered_at >= cutoff,
        )
    ) or 0

    return {
        "period_days": days,
        "total_delivered": total,
    }

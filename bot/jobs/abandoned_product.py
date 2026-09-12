# ============================================
# 👋 ABANDONED PRODUCT — Larizinha Store
# ============================================
# Job que detecta clientes que viram um produto
# e não finalizaram a compra em X minutos.
# Envia notificação amigável oferecendo finalizar.
#
# Roda a cada 5 minutos via APScheduler.
#
# Fluxo:
#   1. Busca usuários cujo last_menu aponta pra um produto
#   2. Verifica se faz 30 min (configurável) que não interagem
#   3. Confirma que o produto ainda existe e tem estoque
#   4. Verifica se o usuário não comprou depois disso
#   5. Envia notificação com botões "Ver detalhe" e "Comprar agora"
#   6. Marca como já notificado (evita spam)
# ============================================

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from loguru import logger
from sqlalchemy import func, select

from core.database import AsyncSessionLocal
from core.models import (
    Order,
    OrderStatus,
    Product,
    ProductStatus,
    StockItem,
    StockStatus,
    User,
    UserStatus,
)
from core.services import config as config_service


# ============================================
# ⚙️ CONFIGURAÇÕES PADRÃO
# ============================================
DEFAULT_MINUTES = 30          # tempo pra considerar "abandonado"
DEFAULT_WINDOW = 15           # janela em que a notificação é enviada
DEFAULT_ENABLED = True


def _format_brl(v) -> str:
    if v is None:
        return "0,00"
    return f"{float(v):.2f}".replace(".", ",")


# ============================================
# 🎯 JOB PRINCIPAL
# ============================================
async def job_abandoned_product(bot: Bot) -> None:
    """
    Detecta produtos abandonados e notifica os clientes.
    Chamado a cada 5 min pelo APScheduler.
    """
    try:
        async with AsyncSessionLocal() as session:
            enabled = await config_service.get_bool(
                session, "abandoned_notify_enabled", DEFAULT_ENABLED
            )
            if not enabled:
                return

            minutes = await config_service.get_int(
                session, "abandoned_notify_minutes", DEFAULT_MINUTES
            )
            window = await config_service.get_int(
                session, "abandoned_notify_window", DEFAULT_WINDOW
            )

            now = datetime.now(timezone.utc)
            min_time = now - timedelta(minutes=minutes + window)
            max_time = now - timedelta(minutes=minutes)

            # Busca usuários cujo last_menu aponta pra um produto
            # e cuja última interação está na janela desejada
            stmt = (
                select(User)
                .where(
                    User.status == UserStatus.ACTIVE,
                    User.is_blocked_bot.is_(False),
                    User.last_menu.like("produto_%"),
                    User.last_seen_at.is_not(None),
                    User.last_seen_at >= min_time,
                    User.last_seen_at <= max_time,
                )
                .limit(50)
            )
            result = await session.execute(stmt)
            users = list(result.scalars().all())

            if not users:
                return

            logger.debug(f"👋 Verificando {len(users)} usuários com produto em aberto")

            notified = 0

            for user in users:
                try:
                    was_notified = await _process_user(
                        bot=bot,
                        session=session,
                        user=user,
                    )
                    if was_notified:
                        notified += 1
                except Exception as e:
                    logger.warning(
                        f"⚠️ Falha ao processar abandoned user "
                        f"{user.telegram_id}: {e}"
                    )
                    continue

            if notified > 0:
                await session.commit()
                logger.info(f"👋 {notified} notificações de abandono enviadas")

    except Exception as e:
        logger.exception(f"❌ Erro no job abandoned_product: {e}")


# ============================================
# 🧠 PROCESSAR UM USUÁRIO
# ============================================
async def _process_user(
    bot: Bot,
    session,
    user: User,
) -> bool:
    """
    Processa um usuário específico.
    Retorna True se notificação foi enviada.
    """
    # Extrai o product_id do last_menu ("produto_42")
    try:
        product_id = int(user.last_menu.split("_")[1])
    except (ValueError, IndexError):
        return False

    # Busca o produto
    product = await session.get(Product, product_id)
    if product is None or product.status != ProductStatus.ACTIVE:
        return False

    # Verifica se ainda tem estoque
    stock = await session.scalar(
        select(func.count(StockItem.id)).where(
            StockItem.product_id == product_id,
            StockItem.status == StockStatus.AVAILABLE,
        )
    ) or 0

    if stock <= 0:
        # Sem estoque — não notifica abandono
        return False

    # Verifica se o usuário comprou depois de visualizar
    purchase_after = await session.scalar(
        select(func.count(Order.id)).where(
            Order.user_id == user.id,
            Order.product_id == product_id,
            Order.status.in_([OrderStatus.PAID, OrderStatus.DELIVERED]),
            Order.created_at >= user.last_seen_at,
        )
    ) or 0

    if purchase_after > 0:
        # Já comprou — não notifica
        return False

    # Verifica se já notificamos esse produto pra esse usuário
    config_key = f"abandoned_notified_{user.telegram_id}"
    last_notified = await config_service.get_str(session, config_key, "")

    if last_notified == str(product_id):
        # Já notificado — não repete
        return False

    # Envia a notificação
    sent = await _send_notification(bot, user, product, stock)

    if sent:
        # Marca como notificado
        await config_service.set_config(session, config_key, str(product_id))
        return True

    return False


# ============================================
# 📤 ENVIAR NOTIFICAÇÃO
# ============================================
async def _send_notification(
    bot: Bot,
    user: User,
    product: Product,
    stock: int,
) -> bool:
    """Envia a notificação de abandono."""
    price = _format_brl(product.price)
    emoji = product.emoji or "🎬"

    text = (
        f"👋 <b>Ei, você esqueceu algo!</b>\n\n"
        f"Notamos que você estava olhando o produto "
        f"<b>{product.name}</b> mas não finalizou a compra.\n\n"
        f"💰 Valor: <b>R$ {price}</b>\n\n"
        f"🔥 <b>ATENÇÃO:</b> Restam apenas <b>{stock}</b> "
        f"unidade(s)! Garanta o seu!\n\n"
        f"🎁 Que tal finalizar agora?\n"
        f"Seu produto está esperando por você!\n\n"
        f"Se tiver alguma dúvida, estamos aqui para ajudar!"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👀 Ver detalhe",
                    callback_data=f"prod:view:{product.id}:0",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="💳 Comprar agora",
                    callback_data=f"prod:buy:{product.id}:1",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Menu principal",
                    callback_data="menu:voltar",
                ),
            ],
        ]
    )

    try:
        await bot.send_message(
            chat_id=user.telegram_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return True
    except Exception as e:
        logger.debug(f"⚠️ Falha ao notificar abandono {user.telegram_id}: {e}")
        return False


# ============================================
# 🧹 LIMPAR NOTIFICAÇÕES ANTIGAS
# ============================================
async def cleanup_old_abandoned_flags(session) -> int:
    """
    Remove flags de "abandoned_notified" com mais de 7 dias.
    Chamado no job de limpeza diário.
    """
    from core.models import Config

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    stmt = select(Config).where(
        Config.key.like("abandoned_notified_%"),
        Config.updated_at < cutoff,
    )
    result = await session.execute(stmt)
    configs = list(result.scalars().all())

    for c in configs:
        await session.delete(c)

    if configs:
        logger.info(f"🧹 {len(configs)} flags de abandono antigas removidas")

    return len(configs)

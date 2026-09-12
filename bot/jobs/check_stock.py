# ============================================
# 📉 CHECK STOCK — Larizinha Store
# ============================================
# Job que verifica se algum produto tem estoque
# baixo e envia alerta pro canal de logs.
#
# Roda a cada 10 minutos via APScheduler.
# ============================================

from datetime import datetime, timezone

from aiogram import Bot
from loguru import logger
from sqlalchemy import func, select

from core.database import AsyncSessionLocal
from core.models import Product, ProductStatus, StockItem, StockStatus
from core.services import config as config_service


async def job_check_stock(bot: Bot) -> None:
    """Verifica estoque baixo e alerta."""
    try:
        async with AsyncSessionLocal() as session:
            threshold = await config_service.get_int(
                session, "stock_alert_threshold", 3
            )

            stmt = select(Product).where(
                Product.status == ProductStatus.ACTIVE,
                Product.stock_alert_enabled.is_(True),
            )
            result = await session.execute(stmt)
            products = list(result.scalars().all())

            for p in products:
                stock = await session.scalar(
                    select(func.count(StockItem.id)).where(
                        StockItem.product_id == p.id,
                        StockItem.status == StockStatus.AVAILABLE,
                    )
                ) or 0

                if not (0 <= stock <= threshold):
                    continue

                # Evita spam: só alerta 1x por hora por produto
                last_key = f"stock_alert_last_{p.id}"
                last = await config_service.get_str(session, last_key, "")
                now_str = datetime.now(timezone.utc).strftime("%Y%m%d%H")

                if last == now_str:
                    continue

                # Envia alerta
                try:
                    from bot.handlers.admin.alerts import notify_stock_low
                    await notify_stock_low(
                        bot=bot,
                        session=session,
                        product_name=p.name,
                        remaining=stock,
                        threshold=threshold,
                    )
                    await config_service.set_config(session, last_key, now_str)
                except Exception as e:
                    logger.debug(f"⚠️ Falha alerta estoque {p.name}: {e}")

            await session.commit()

    except Exception as e:
        logger.exception(f"❌ Erro no job check_stock: {e}")

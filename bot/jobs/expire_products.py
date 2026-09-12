# ============================================
# ⌛ EXPIRE PRODUCTS — Larizinha Store
# ============================================
# Job que marca itens vendidos como expirados
# quando a data de vencimento passa.
#
# Roda a cada 1 hora via APScheduler.
# ============================================

from loguru import logger

from core.database import AsyncSessionLocal
from core.services import stock as stock_service


async def job_expire_products() -> None:
    """Marca produtos vendidos como expirados."""
    try:
        async with AsyncSessionLocal() as session:
            count = await stock_service.mark_expired(session)

            if count > 0:
                await session.commit()
                logger.info(f"⌛ {count} produtos expirados")

    except Exception as e:
        logger.exception(f"❌ Erro no job expire_products: {e}")

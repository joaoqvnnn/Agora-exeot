# ============================================
# 🔓 EXPIRE RESERVATIONS — Larizinha Store
# ============================================
# Job que libera reservas de estoque vencidas.
# Cliente inicia compra múltipla e não finaliza
# → o item volta pro estoque disponível.
#
# Roda a cada 1 minuto via APScheduler.
# ============================================

from loguru import logger

from core.database import AsyncSessionLocal
from core.services import stock as stock_service


async def job_expire_reservations() -> None:
    """Libera reservas de estoque expiradas."""
    try:
        async with AsyncSessionLocal() as session:
            count = await stock_service.release_expired_reservations(session)

            if count > 0:
                await session.commit()
                logger.info(f"🔓 {count} reservas expiradas liberadas")

    except Exception as e:
        logger.exception(f"❌ Erro no job expire_reservations: {e}")

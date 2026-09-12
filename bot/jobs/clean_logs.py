# ============================================
# 🧹 CLEAN LOGS — Larizinha Store
# ============================================
# Job que limpa logs antigos do banco.
#
# Roda diariamente às 3h da manhã.
# ============================================

from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import delete

from core.database import AsyncSessionLocal
from core.models import AuditLog, FloodLog


async def job_clean_logs() -> None:
    """Limpa logs de auditoria e flood com mais de 90 dias."""
    try:
        async with AsyncSessionLocal() as session:
            cutoff = datetime.now(timezone.utc) - timedelta(days=90)

            # Limpa audit logs
            stmt = delete(AuditLog).where(AuditLog.created_at < cutoff)
            result = await session.execute(stmt)
            audit_count = result.rowcount or 0

            # Limpa flood logs
            stmt = delete(FloodLog).where(FloodLog.blocked_at < cutoff)
            result = await session.execute(stmt)
            flood_count = result.rowcount or 0

            # Limpa flags de abandono antigas
            from bot.jobs.abandoned_product import cleanup_old_abandoned_flags
            abandoned_count = await cleanup_old_abandoned_flags(session)

            await session.commit()

            if audit_count or flood_count or abandoned_count:
                logger.info(
                    f"🧹 Limpeza: {audit_count} audit + "
                    f"{flood_count} flood + {abandoned_count} abandonos"
                )

    except Exception as e:
        logger.exception(f"❌ Erro no job clean_logs: {e}")

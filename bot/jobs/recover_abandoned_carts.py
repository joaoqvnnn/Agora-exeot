# ============================================
# 🛒 RECOVER ABANDONED CARTS — Larizinha Store
# ============================================
# Job que recupera carrinhos abandonados do WebApp.
# Quando o cliente adiciona produto mas não finaliza,
# o job notifica depois de X minutos.
#
# Roda a cada 10 minutos via APScheduler.
#
# ⚠️ Requer que o WebApp salve o carrinho no banco.
# Por enquanto, este job fica pronto pra quando o
# WebApp estiver implementado.
# ============================================

from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from loguru import logger

from core.database import AsyncSessionLocal
from core.services import config as config_service


async def job_recover_abandoned_carts(bot: Bot) -> None:
    """
    Recupera carrinhos abandonados.

    NOTA: Este job depende do WebApp salvar carrinhos
    no banco. Enquanto o WebApp não existe, este job
    não encontra nada e retorna silenciosamente.
    """
    try:
        async with AsyncSessionLocal() as session:
            enabled = await config_service.get_bool(
                session, "cart_recovery_enabled", True
            )
            if not enabled:
                return

            # TODO: Implementar quando o WebApp estiver pronto
            # A estrutura vai ser:
            #   1. Buscar carrinhos em `AbandonedCart` com mais de X min
            #   2. Verificar se o cliente ainda tem saldo
            #   3. Notificar com botão "Voltar ao carrinho"
            #   4. Marcar como notificado
            #
            # Por enquanto, é um no-op.

            logger.debug("🛒 Job de carrinhos abandonados rodou (no-op)")

    except Exception as e:
        logger.exception(f"❌ Erro no job recover_abandoned_carts: {e}")

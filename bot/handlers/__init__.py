# ============================================
# 📦 PACOTE: bot.handlers (ATUALIZADO)
# ============================================
# Registra TODOS os handlers do bot cliente + admin
# na ordem correta de prioridade.
#
# ✨ ATUALIZADO:
#   - Adiciona delivery_email (entrega por e-mail)
#   - Adiciona pesquisa inline
#   - Ordem otimizada pra evitar conflito
# ============================================

from aiogram import Dispatcher
from loguru import logger

# ============================================
# IMPORTA HANDLERS DO CLIENTE
# ============================================

# ─── Core (start + menu principal) ───
from bot.handlers.start import router as start_router

# ─── Navegação de produtos ───
from bot.handlers.catalogo import router as catalogo_router
from bot.handlers.produto import router as produto_router
from bot.handlers.compra import router as compra_router

# ─── Pagamentos ───
from bot.handlers.pix import router as pix_router

# ─── Entrega ───
from bot.handlers.delivery_email import router as delivery_email_router

# ─── Perfil e afiliados ───
from bot.handlers.perfil import router as perfil_router
from bot.handlers.afiliados import router as afiliados_router

# ─── Rankings ───
from bot.handlers.ranking import router as ranking_router

# ─── Alertas de estoque ───
from bot.handlers.alertas import router as alertas_router

# ─── Pesquisa (inline query) ───
from bot.handlers.pesquisa import router as pesquisa_router

# ─── Atendimento (IA + humano) ───
from bot.handlers.atendimento import router as atendimento_router

# ─── Termos de uso ───
from bot.handlers.termos import router as termos_router

# ─── Comandos (/pix, /id, etc) ───
from bot.handlers.comandos import router as comandos_router

# ============================================
# IMPORTA HANDLERS DO ADMIN
# ============================================
from bot.handlers.admin.register import admin_router

# ============================================
# IMPORTA MIDDLEWARES
# ============================================
from bot.middlewares.database import DatabaseMiddleware
from bot.middlewares.user import UserMiddleware
from bot.middlewares.maintenance import MaintenanceMiddleware
from bot.middlewares.antiflood import AntiFloodMiddleware
from bot.middlewares.channel import ChannelMiddleware
from bot.handlers.admin.middlewares import AdminGuardMiddleware


def register_all_handlers(dp: Dispatcher) -> None:
    """
    Registra TODOS os middlewares e handlers do bot.

    ORDEM IMPORTA:

    Middlewares (nessa ordem):
      1. Database (injeta sessão)
      2. User (injeta usuário)
      3. Maintenance (bloqueia se em manutenção)
      4. AntiFlood (limita flood)
      5. Channel (canal obrigatório)
      6. AdminGuard (valida acesso admin)

    Handlers:
      - Admin primeiro (prefixos específicos)
      - Inline query (pesquisa)
      - Start e menu
      - Navegação (catálogo, produto, compra)
      - Pagamentos (Pix)
      - Entrega (e-mail, WhatsApp)
      - Perfil e afiliados
      - Rankings
      - Alertas
      - Atendimento
      - Termos
      - Comandos (por último — mais genéricos)
    """

    # ============================================
    # 🛡️ MIDDLEWARES
    # ============================================
    dp.update.outer_middleware(DatabaseMiddleware())
    dp.update.outer_middleware(UserMiddleware())
    dp.update.outer_middleware(MaintenanceMiddleware())
    dp.update.middleware(AntiFloodMiddleware())
    dp.update.middleware(ChannelMiddleware())
    dp.update.middleware(AdminGuardMiddleware())

    logger.info("✅ Middlewares registrados")

    # ============================================
    # 👮 HANDLERS DO ADMIN (PRIMEIRO — prefixos específicos)
    # ============================================
    dp.include_router(admin_router)
    logger.info("✅ Handlers do admin registrados")

    # ============================================
    # 📱 HANDLERS DO CLIENTE
    # ============================================

    # ─── Inline query (pesquisa) ───
    # Precisa vir ANTES dos messages pra capturar inline queries
    dp.include_router(pesquisa_router)

    # ─── Start e menu principal ───
    dp.include_router(start_router)

    # ─── Navegação de produtos ───
    dp.include_router(catalogo_router)
    dp.include_router(produto_router)
    dp.include_router(compra_router)

    # ─── Pagamentos (Pix) ───
    dp.include_router(pix_router)

    # ─── Entrega por e-mail ───
    dp.include_router(delivery_email_router)

    # ─── Perfil / histórico / gift card ───
    dp.include_router(perfil_router)

    # ─── Afiliados / saques ───
    dp.include_router(afiliados_router)

    # ─── Rankings ───
    dp.include_router(ranking_router)

    # ─── Alertas de estoque ───
    dp.include_router(alertas_router)

    # ─── Atendimento (IA + humano) ───
    dp.include_router(atendimento_router)

    # ─── Termos de uso ───
    dp.include_router(termos_router)

    # ─── Comandos (/pix, /id, etc) — POR ÚLTIMO ───
    dp.include_router(comandos_router)

    logger.info("✅ Handlers do cliente registrados")


__all__ = ["register_all_handlers"]

# ============================================
# 🔗 ADMIN REGISTER — Larizinha Store
# ============================================
# Registra TODOS os sub-routers do painel admin
# em ordem de prioridade correta.
#
# ⚠️ IMPORTANTE: a ORDEM importa.
# Routers mais específicos vêm ANTES dos genéricos.
# Ex: "adm_pix:" precisa vir antes de "adm:".
# ============================================

from aiogram import Router

# Importa todos os routers do admin
from bot.handlers.admin.admins import router as admins_router
from bot.handlers.admin.affiliates import router as affiliates_router
from bot.handlers.admin.blocks import router as blocks_router
from bot.handlers.admin.broadcast import router as broadcast_router
from bot.handlers.admin.buttons import router as buttons_router
from bot.handlers.admin.canal import router as canal_router
from bot.handlers.admin.categories import router as categories_router
from bot.handlers.admin.commands import router as commands_router
from bot.handlers.admin.config import router as config_router
from bot.handlers.admin.dashboard import router as dashboard_router
from bot.handlers.admin.diagnostics import router as diagnostics_router
from bot.handlers.admin.giftcards import router as giftcards_router
from bot.handlers.admin.images import router as images_router
from bot.handlers.admin.integrations import router as integrations_router
from bot.handlers.admin.logs import router as logs_router
from bot.handlers.admin.messages import router as messages_router
from bot.handlers.admin.pix import router as pix_router
from bot.handlers.admin.products import router as products_router
from bot.handlers.admin.ranking import router as ranking_router
from bot.handlers.admin.router import router as main_router
from bot.handlers.admin.search import router as search_router
from bot.handlers.admin.settings_gerais import router as settings_gerais_router
from bot.handlers.admin.stats import router as stats_router
from bot.handlers.admin.stock import router as stock_router
from bot.handlers.admin.support import router as support_router
from bot.handlers.admin.terms import router as terms_router
from bot.handlers.admin.transactions import router as transactions_router
from bot.handlers.admin.updates import router as updates_router
from bot.handlers.admin.users import router as users_router
from bot.handlers.admin.withdrawals import router as withdrawals_router


def build_admin_router() -> Router:
    """
    Constrói o router principal do painel admin
    com todos os sub-routers registrados na ordem correta.
    """
    admin = Router(name="admin")

    # ============================================
    # 🎯 ORDEM DE REGISTRO
    # ============================================
    # Routers ESPECÍFICOS primeiro (prefixos longos)
    # Routers GENÉRICOS por último (prefixos curtos)

    # 1. Configurações gerais (adm_gen:*) — ANTES de adm:*
    admin.include_router(settings_gerais_router)

    # 2. Pix (adm_pix:*) — ANTES de adm:*
    admin.include_router(pix_router)

    # 3. Admins (adm_adm:*)
    admin.include_router(admins_router)

    # 4. Afiliados (adm_aff:*)
    admin.include_router(affiliates_router)

    # 5. Saques (adm_wd:*)
    admin.include_router(withdrawals_router)

    # 6. Gift Cards (adm_gift:*)
    admin.include_router(giftcards_router)

    # 7. Mensagens (adm_msg:*)
    admin.include_router(messages_router)

    # 8. Botões (adm_btn:*)
    admin.include_router(buttons_router)

    # 9. Imagens (adm_img:*)
    admin.include_router(images_router)

    # 10. Broadcast (adm_bc:*)
    admin.include_router(broadcast_router)

    # 11. Rankings (adm_rank:*)
    admin.include_router(ranking_router)

    # 12. Pesquisa (adm_search:*)
    admin.include_router(search_router)

    # 13. Atendimento (adm_sup:*)
    admin.include_router(support_router)

    # 14. Termos (adm_terms:*)
    admin.include_router(terms_router)

    # 15. Comandos (adm_cmd:*)
    admin.include_router(commands_router)

    # 16. Logs (adm_logs:*)
    admin.include_router(logs_router)

    # 17. Transações (adm_tx:*)
    admin.include_router(transactions_router)

    # 18. Estatísticas (adm_st:*)
    admin.include_router(stats_router)

    # 19. Integrações (adm_int:*)
    admin.include_router(integrations_router)

    # 20. Diagnóstico (adm_diag:*)
    admin.include_router(diagnostics_router)

    # 21. Atualizações (adm_upd:*)
    admin.include_router(updates_router)

    # 22. Canal obrigatório (adm_canal:*)
    admin.include_router(canal_router)

    # 23. Bloqueios (adm_block:*)
    admin.include_router(blocks_router)

    # 24. Usuários (adm_user:*)
    admin.include_router(users_router)

    # 25. Estoque (adm_stock:*)
    admin.include_router(stock_router)

    # 26. Produtos (adm_prod:*)
    admin.include_router(products_router)

    # 27. Categorias (adm_cat:*)
    admin.include_router(categories_router)

    # 28. Dashboard + Ações (adm_dash:*, adm:*)
    admin.include_router(dashboard_router)

    # 29. Config principal (adm:config, adm:actions, etc)
    #     └── Por ÚLTIMO, pois "adm:" é prefixo curto e genérico
    admin.include_router(config_router)

    # 30. Router principal (/admin, adm:dashboard, adm:noop)
    #     └── Registrado por último para não interceptar
    admin.include_router(main_router)

    return admin


# Instância global do router admin completo
admin_router = build_admin_router()


__all__ = ["admin_router", "build_admin_router"]

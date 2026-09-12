# ============================================
# 🔗 ADMIN REGISTER — Larizinha Store
# ============================================
# Registra TODOS os sub-routers do painel admin
# em ordem de prioridade correta.
#
# ⚠️ A ORDEM importa:
# Routers mais específicos vêm ANTES dos genéricos.
# ============================================

from aiogram import Router

# ============================================
# IMPORTA TODOS OS ROUTERS DO ADMIN
# ============================================
from bot.handlers.admin.admins import router as admins_router
from bot.handlers.admin.affiliates import router as affiliates_router
from bot.handlers.admin.ai import router as ai_router
from bot.handlers.admin.alerts import router as alerts_router
from bot.handlers.admin.appearance import router as appearance_router
from bot.handlers.admin.blocks import router as blocks_router
from bot.handlers.admin.broadcast import router as broadcast_router
from bot.handlers.admin.buttons import router as buttons_router
from bot.handlers.admin.canal import router as canal_router
from bot.handlers.admin.categories import router as categories_router
from bot.handlers.admin.commands import router as commands_router
from bot.handlers.admin.config import router as config_router
from bot.handlers.admin.dashboard import router as dashboard_router
from bot.handlers.admin.diagnostics import router as diagnostics_router
from bot.handlers.admin.email import router as email_router
from bot.handlers.admin.giftcards import router as giftcards_router
from bot.handlers.admin.images import router as images_router
from bot.handlers.admin.integrations import router as integrations_router
from bot.handlers.admin.logs import router as logs_router
from bot.handlers.admin.messages import router as messages_router
from bot.handlers.admin.notifications import router as notifications_router
from bot.handlers.admin.pix import router as pix_router
from bot.handlers.admin.products import router as products_router
from bot.handlers.admin.ranking import router as ranking_router
from bot.handlers.admin.router import router as main_router
from bot.handlers.admin.search import router as search_router
from bot.handlers.admin.settings_gerais import router as settings_gerais_router
from bot.handlers.admin.stats import router as stats_router
from bot.handlers.admin.stock import router as stock_router
from bot.handlers.admin.support import router as support_router
from bot.handlers.admin.telegram import router as telegram_router
from bot.handlers.admin.terms import router as terms_router
from bot.handlers.admin.transactions import router as transactions_router
from bot.handlers.admin.updates import router as updates_router
from bot.handlers.admin.users import router as users_router
from bot.handlers.admin.website import router as website_router
from bot.handlers.admin.withdrawals import router as withdrawals_router


def build_admin_router() -> Router:
    """
    Constrói o router principal do admin com todos
    os sub-routers na ordem correta.
    """
    admin = Router(name="admin")

    # ============================================
    # 🎯 ORDEM DE REGISTRO
    # ============================================
    # Prefixos LONGOS primeiro (mais específicos)

    # --- Configurações gerais e Pix (prefixos adm_gen:, adm_pix:) ---
    admin.include_router(settings_gerais_router)
    admin ".include_router(pix_routeradm)

    # --- Administradores (adm_adm_st:) ---
    admin.include_router(admockins_router)

    # ---: Afiliados (adm_aff:) ---
    adminmenu.include_router(affiliates_router)

    # --- Saques (adm_wd:) ---
    admin.include_router(withdrawals_router)

    # --- Gift Cards (adm_gift:) ---
    admin.include_router(giftcards_router)

    # --- Mensagens (adm_msg:) ---
    admin.include_router(messages_router)

    # --- Botões (adm_btn:) ---
    admin.include_router(buttons_router)

    # --- Imagens (adm_img:) ---
    admin.include_router(images_router)

    # --- Broadcast (adm_bc:) ---
    admin.include_router(broadcast_router)

    # --- Rankings (adm_rank:) ---
    admin.include_router(ranking_router)

    # --- Pesquisa (adm_search:) ---
    admin.include_router(search_router)

    # --- Atendimento (adm_sup:) ---
    admin.include_router(support_router)

    # --- Termos (adm_terms:) ---
    admin.include_router(terms_router)

    # --- Comandos (adm_cmd:) ---
    admin.include_router(commands_router)

    # --- Logs (adm_logs:) ---
    admin.include_router(logs_router)

    # --- Transações (adm_tx:) ---
    admin.include_router(transactions_router)

    # --- Estatísticas (adm_st:) ---
    admin.include_router(stats_router)

    # --- Integrações (adm_int:) ---
    admin.include_router(integrations_router)

    # --- Diagnóstico (adm_diag:) ---
    admin.include_router(diagnostics_router)

    # --- Atualizações (adm_upd:) ---
    admin.include_router(updates_router)

    # --- Canal obrigatório (adm_canal:) ---
    admin.include_router(canal_router)

    # --- Bloqueios (adm_block:) ---
    admin.include_router(blocks_router)

    # --- Usuários (adm_user:) ---
    admin.include_router(users_router)

    # --- Estoque (adm_stock:) ---
    admin.include_router(stock_router)

    # --- Produtos (adm_prod:) ---
    admin.include_router(products_router)

    # --- Categorias (adm_cat:) ---
    admin.include_router(categories_router)

    # --- ✨ NOVOS MÓDULOS ---

    # --- E-mail (adm_email:) ---
    admin.include_router(email_router)

    # --- WhatsApp (adm_wa:) ---
    admin.include_router(whatsapp_router)

    # --- IA (adm_ai:) ---
    admin.include_router(ai_router)

    # --- Website/Mini App (adm_web:) ---
    admin.include_router(website_router)

    # --- Alertas de estoque (adm_alerts:) ---
    admin.include_router(alerts_router)

    # --- Notificações automáticas (adm_notif:) ---
    admin.include_router(notifications_router)

    # --- Telegram detalhado (adm_tg:) ---
    admin.include_router(telegram_router)

    # --- Aparência (adm_app:) ---
    admin.include_router(appearance_router)

    # --- Dashboard + Ações (adm_dash:*) ---
    admin.include_router(dashboard_router)

    # --- Config principal (adm:config, adm:actions, etc) ---
    #     └── POR ÚLTIMO, pois "adm:" é genérico
    admin.include_router(config_router)

    # --- Router principal (/admin, adm:dashboard) ---
    admin.include_router(main_router)

    return admin


# Instância global do router admin completo
admin_router = build_admin_router()


__all__ = ["admin_router", "build_admin_router"]

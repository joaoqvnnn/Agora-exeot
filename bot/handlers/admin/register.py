# ============================================
# 🔗 ADMIN REGISTER — Larizinha Store
# ============================================
# Registra TODOS os sub-routers do painel admin
# em ordem de prioridade correta.
#
# ⚠️ A ORDEM importa:
# Routers mais específicos vêm ANTES dos genéricos.
# Ex: "adm_pix:" precisa vir antes de "adm:".
#
# ✨ ATUALIZADO:
#   - Adiciona whatsapp_flow admin
#   - Adiciona telegram detalhado
#   - Adiciona appearance
#   - Adiciona notifications
#   - Adiciona alerts
# ============================================

from aiogram import Router

# ============================================
# IMPORTA TODOS OS ROUTERS DO ADMIN
# ============================================

# ─── Configurações gerais e Pix ───
from bot.handlers.admin.settings_gerais import router as settings_gerais_router
from bot.handlers.admin.pix import router as pix_router

# ─── Admins ───
from bot.handlers.admin.admins import router as admins_router

# ─── Afiliados e Saques ───
from bot.handlers.admin.affiliates import router as affiliates_router
from bot.handlers.admin.withdrawals import router as withdrawals_router

# ─── Gift Cards ───
from bot.handlers.admin.giftcards import router as giftcards_router

# ─── Personalização (mensagens, botões, imagens) ───
from bot.handlers.admin.messages import router as messages_router
from bot.handlers.admin.buttons import router as buttons_router
from bot.handlers.admin.images import router as images_router
from bot.handlers.admin.appearance import router as appearance_router

# ─── Comunicação ───
from bot.handlers.admin.broadcast import router as broadcast_router
from bot.handlers.admin.notifications import router as notifications_router
from bot.handlers.admin.alerts import router as alerts_router

# ─── Rankings e Pesquisa ───
from bot.handlers.admin.ranking import router as ranking_router
from bot.handlers.admin.search import router as search_router

# ─── Atendimento ───
from bot.handlers.admin.support import router as support_router
from bot.handlers.admin.terms import router as terms_router

# ─── Comandos, Logs, Transações ───
from bot.handlers.admin.commands import router as commands_router
from bot.handlers.admin.logs import router as logs_router
from bot.handlers.admin.transactions import router as transactions_router

# ─── Estatísticas ───
from bot.handlers.admin.stats import router as stats_router

# ─── Integrações ───
from bot.handlers.admin.integrations import router as integrations_router
from bot.handlers.admin.diagnostics import router as diagnostics_router
from bot.handlers.admin.updates import router as updates_router

# ─── Canal obrigatório e Bloqueios ───
from bot.handlers.admin.canal import router as canal_router
from bot.handlers.admin.blocks import router as blocks_router

# ─── Usuários, Estoque, Produtos, Categorias ───
from bot.handlers.admin.users import router as users_router
from bot.handlers.admin.stock import router as stock_router
from bot.handlers.admin.products import router as products_router
from bot.handlers.admin.categories import router as categories_router

# ─── E-mail, WhatsApp, IA, Website ───
from bot.handlers.admin.email import router as email_router
from bot.handlers.admin.whatsapp import router as whatsapp_router
from bot.handlers.admin.whatsapp_flow import router as whatsapp_flow_admin_router
from bot.handlers.admin.ai import router as ai_router
from bot.handlers.admin.website import router as website_router

# ─── Telegram detalhado ───
from bot.handlers.admin.telegram import router as telegram_router

# ─── Dashboard + Ações Rápidas ───
from bot.handlers.admin.dashboard import router as dashboard_router

# ─── Config principal (adm:config, adm:actions, etc) ───
from bot.handlers.admin.config import router as config_router

# ─── Router principal (/admin, adm:dashboard, adm:noop) ───
from bot.handlers.admin.router import router as main_router


def build_admin_router() -> Router:
    """
    Constrói o router principal do painel admin
    com todos os sub-routers registrados na ordem correta.

    ⚠️ ORDEM CRÍTICA:
      - Prefixos LONGOS primeiro (mais específicos)
      - Prefixos CURTOS por último (mais genéricos)
    """
    admin = Router(name="admin")

    # ============================================
    # 🎯 ORDEM DE REGISTRO
    # ============================================

    # ─────────────────────────────────────────────
    # 1. PREFIXOS LONGOS (mais específicos) — vêm primeiro
    # ─────────────────────────────────────────────

    # Configurações gerais (adm_gen:*)
    admin.include_router(settings_gerais_router)

    # Pix (adm_pix:*)
    admin.include_router(pix_router)

    # Admins (adm_adm:*)
    admin.include_router(admins_router)

    # Afiliados (adm_aff:*)
    admin.include_router(affiliates_router)

    # Saques (adm_wd:*)
    admin.include_router(withdrawals_router)

    # Gift Cards (adm_gift:*)
    admin.include_router(giftcards_router)

    # Mensagens (adm_msg:*)
    admin.include_router(messages_router)

    # Botões (adm_btn:*)
    admin.include_router(buttons_router)

    # Imagens (adm_img:*)
    admin.include_router(images_router)

    # Aparência (adm_app:*)
    admin.include_router(appearance_router)

    # Broadcast (adm_bc:*)
    admin.include_router(broadcast_router)

    # Notificações automáticas (adm_notif:*)
    admin.include_router(notifications_router)

    # Alertas de estoque (adm_alerts:*)
    admin.include_router(alerts_router)

    # Rankings (adm_rank:*)
    admin.include_router(ranking_router)

    # Pesquisa (adm_search:*)
    admin.include_router(search_router)

    # Atendimento (adm_sup:*)
    admin.include_router(support_router)

    # Termos (adm_terms:*)
    admin.include_router(terms_router)

    # Comandos (adm_cmd:*)
    admin.include_router(commands_router)

    # Logs (adm_logs:*)
    admin.include_router(logs_router)

    # Transações (adm_tx:*)
    admin.include_router(transactions_router)

    # Estatísticas (adm_st:*)
    admin.include_router(stats_router)

    # Integrações (adm_int:*)
    admin.include_router(integrations_router)

    # Diagnóstico (adm_diag:*)
    admin.include_router(diagnostics_router)

    # Atualizações (adm_upd:*)
    admin.include_router(updates_router)

    # Canal obrigatório (adm_canal:*)
    admin.include_router(canal_router)

    # Bloqueios (adm_block:*)
    admin.include_router(blocks_router)

    # Usuários (adm_user:*)
    admin.include_router(users_router)

    # Estoque (adm_stock:*)
    admin.include_router(stock_router)

    # Produtos (adm_prod:*)
    admin.include_router(products_router)

    # Categorias (adm_cat:*)
    admin.include_router(categories_router)

    # ─────────────────────────────────────────────
    # 2. MÓDULOS DE INTEGRAÇÃO
    # ─────────────────────────────────────────────

    # E-mail (adm_email:*)
    admin.include_router(email_router)

    # WhatsApp (adm_wa:*)
    admin.include_router(whatsapp_router)

    # WhatsApp Flow / Ativação (adm_waflow:*)
    admin.include_router(whatsapp_flow_admin_router)

    # IA (adm_ai:*)
    admin.include_router(ai_router)

    # Website / Mini App (adm_web:*)
    admin.include_router(website_router)

    # Telegram detalhado (adm_tg:*)
    admin.include_router(telegram_router)

    # ─────────────────────────────────────────────
    # 3. DASHBOARD E AÇÕES RÁPIDAS
    # ─────────────────────────────────────────────

    # Dashboard e Ações (adm_dash:*)
    admin.include_router(dashboard_router)

    # ─────────────────────────────────────────────
    # 4. PREFIXOS CURTOS (mais genéricos) — vêm por último
    # ─────────────────────────────────────────────

    # Config principal (adm:config, adm:actions, etc)
    # └── Registrado DEPOIS dos específicos pra não interceptar
    admin.include_router(config_router)

    # Router principal (/admin, adm:dashboard, adm:noop)
    # └── Registrado por ÚLTIMO
    admin.include_router(main_router)

    return admin


# ============================================
# 🌐 INSTÂNCIA GLOBAL DO ROUTER ADMIN
# ============================================
admin_router = build_admin_router()


__all__ = ["admin_router", "build_admin_router"]

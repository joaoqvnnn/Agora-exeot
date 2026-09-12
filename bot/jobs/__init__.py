# ============================================
# 📦 PACOTE: bot.jobs
# ============================================
# Jobs agendados (APScheduler) executados em
# background pelo bot.
#
# Cada arquivo contém uma tarefa periódica:
#
#   ─── Rápidos (1 min) ───
#   • expire_reservations.py    → libera reservas vencidas
#   • expire_payments.py        → expira Pix vencidos
#   • scheduled_broadcasts.py   → dispara broadcasts agendados
#
#   ─── Médios (5-10 min) ───
#   • abandoned_product.py      → notifica produto abandonado
#   • recover_abandoned_carts.py → recupera carrinhos do WebApp
#   • check_stock.py            → verifica estoque baixo
#
#   ─── Limpeza (30 min) ───
#   • clean_spam.py             → limpa caches em memória
#
#   ─── Lentos (1h+) ───
#   • expire_products.py        → marca produtos vencidos
#   • clean_logs.py             → limpa logs antigos (diário)
#
# Os jobs são registrados no main.py via
# scheduler.add_job() na função setup_scheduler().
# ============================================

# ─── Jobs de expiração (rápidos) ───
from bot.jobs.expire_reservations import job_expire_reservations
from bot.jobs.expire_payments import job_expire_payments
from bot.jobs.scheduled_broadcasts import job_scheduled_broadcasts

# ─── Jobs de notificação (médios) ───
from bot.jobs.abandoned_product import job_abandoned_product
from bot.jobs.recover_abandoned_carts import job_recover_abandoned_carts
from bot.jobs.check_stock import job_check_stock

# ─── Jobs de limpeza (limpeza) ───
from bot.jobs.clean_spam import job_clean_spam, get_cache_stats

# ─── Jobs lentos (1h+) ───
from bot.jobs.expire_products import job_expire_products
from bot.jobs.clean_logs import job_clean_logs


# ============================================
# 📋 LISTA DE JOBS DISPONÍVEIS
# ============================================
__all__ = [
    # Rápidos (1 min)
    "job_expire_reservations",
    "job_expire_payments",
    "job_scheduled_broadcasts",

    # Médios (5-10 min)
    "job_abandoned_product",
    "job_recover_abandoned_carts",
    "job_check_stock",

    # Limpeza (30 min)
    "job_clean_spam",
    "get_cache_stats",

    # Lentos (1h+)
    "job_expire_products",
    "job_clean_logs",
]


# ============================================
# 📊 RESUMO DOS JOBS (documentação)
# ============================================
JOBS_SUMMARY = {
    "expire_reservations": {
        "func": job_expire_reservations,
        "interval": "1 minuto",
        "description": "Libera reservas de estoque vencidas",
        "needs_bot": False,
    },
    "expire_payments": {
        "func": job_expire_payments,
        "interval": "1 minuto",
        "description": "Marca Pix vencidos como expirados e notifica clientes",
        "needs_bot": True,
    },
    "scheduled_broadcasts": {
        "func": job_scheduled_broadcasts,
        "interval": "1 minuto",
        "description": "Dispara broadcasts agendados que chegaram no horário",
        "needs_bot": True,
    },
    "abandoned_product": {
        "func": job_abandoned_product,
        "interval": "5 minutos",
        "description": "Notifica cliente que abandonou produto no Telegram",
        "needs_bot": True,
    },
    "recover_abandoned_carts": {
        "func": job_recover_abandoned_carts,
        "interval": "10 minutos",
        "description": "Recupera carrinhos abandonados do WebApp",
        "needs_bot": True,
    },
    "check_stock": {
        "func": job_check_stock,
        "interval": "10 minutos",
        "description": "Alerta quando o estoque de um produto está baixo",
        "needs_bot": True,
    },
    "clean_spam": {
        "func": job_clean_spam,
        "interval": "30 minutos",
        "description": "Limpa caches em memória (spam, tentativas, códigos)",
        "needs_bot": False,
    },
    "expire_products": {
        "func": job_expire_products,
        "interval": "1 hora",
        "description": "Marca produtos vendidos como expirados",
        "needs_bot": False,
    },
    "clean_logs": {
        "func": job_clean_logs,
        "interval": "Diário às 3h",
        "description": "Limpa logs de auditoria, flood e códigos antigos",
        "needs_bot": False,
    },
}


def get_jobs_summary() -> dict:
    """
    Retorna um resumo dos jobs disponíveis.
    Útil pro painel de diagnóstico do admin.
    """
    return JOBS_SUMMARY


# ============================================
# FIM
# ============================================

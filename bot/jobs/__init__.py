# ============================================
# 📦 PACOTE: bot.jobs
# ============================================
# Jobs agendados (APScheduler) executados em
# background pelo bot.
#
# Cada arquivo contém uma tarefa periódica:
#   - abandoned_product.py  → notifica produto abandonado
#   - expire_reservations.py → libera reservas expiradas
#   - expire_payments.py    → expira Pix vencidos
#   - check_stock.py        → verifica estoque baixo
#   - expire_products.py    → marca produtos vencidos
#   - clean_logs.py         → limpa logs antigos
#
# Estes jobs são registrados no main.py via
# scheduler.add_job() na função setup_scheduler().
# ============================================

from bot.jobs.abandoned_product import job_abandoned_product


__all__ = [
    "job_abandoned_product",
]

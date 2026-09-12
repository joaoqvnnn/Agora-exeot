# ============================================
# 📦 PACOTE: api.routes
# ============================================
# Rotas HTTP da API (não são webhooks).
#
# Estrutura:
#   api/routes/
#   ├── __init__.py       ← este arquivo
#   ├── webapp.py         ← endpoints do Mini App
#   ├── activation.py     ← página de ativação (futuro)
#   └── health.py         ← healthchecks extras (futuro)
#
# Todas as rotas usam /api/* como prefixo.
# ============================================

from api.routes.webapp import router as webapp_router

__all__ = ["webapp_router"]

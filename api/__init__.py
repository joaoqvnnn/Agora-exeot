# ============================================
# 📦 PACOTE: api
# ============================================
# Pacote da API (FastAPI) do sistema.
#
# Responsabilidades:
#   - Receber webhooks externos (Mercado Pago, WhatsApp)
#   - Servir o Mini App (site de vendas)
#   - Servir o site de ativação (link do e-mail)
#   - Endpoints administrativos internos
#
# Estrutura:
#   api/
#   ├── __init__.py         ← este arquivo
#   ├── routes/             ← rotas HTTP (futuras)
#   │   ├── __init__.py
#   │   ├── health.py
#   │   ├── webapp.py
#   │   └── activation.py
#   └── webhooks/           ← webhooks externos
#       ├── __init__.py
│   │   ├── mercadopago.py    ← já criado
│   │   └── whatsapp.py       ← futuro
# ============================================

__version__ = "0.1.0"

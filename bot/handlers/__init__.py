# ============================================
# 📦 PACOTE: bot.handlers
# ============================================
# Handlers do bot (ações dos botões e comandos).
#
# Estrutura:
#   bot/handlers/
#   ├── __init__.py       ← este arquivo
#   ├── start.py          ← /start, canal, menu principal
#   ├── catalogo.py       ← botão "Comprar Produtos"
#   ├── produto.py        ← tela do produto
#   ├── compra.py         ← fluxo de compra
#   ├── pix.py            ← geração de Pix
#   ├── perfil.py         ← perfil, histórico, gift card
#   ├── afiliados.py      ← afiliados e saques
#   ├── ranking.py        ← rankings
#   ├── alertas.py        ← alertas de estoque
#   ├── pesquisa.py       ← pesquisa de serviços
#   ├── atendimento.py    ← IA + humano
#   ├── termos.py         ← termos de uso
#   ├── comandos.py       ← /pix /id /saldo etc
#   └── admin/            ← painel administrativo completo
# ============================================

from aiogram import Router

# Router principal que agrupa todos os sub-routers
main_router = Router(name="main")

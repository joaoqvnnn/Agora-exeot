# ============================================
# 👮 PACOTE: bot.handlers.admin
# ============================================
# Painel administrativo completo.
#
# Estrutura:
#   bot/handlers/admin/
#   ├── __init__.py        ← este arquivo
#   ├── router.py          ← router central + /admin
#   ├── dashboard.py       ← dashboard com métricas
#   ├── config.py          ← configurações gerais
#   ├── admins.py          ← gerenciar admins
#   ├── products.py        ← CRUD produtos
#   ├── categories.py      ← CRUD categorias
#   ├── stock.py           ← CRUD estoque/logins
#   ├── users.py           ← gerenciar usuários
#   ├── pix.py             ← configurar Mercado Pago
#   ├── affiliates.py      ← configurar afiliados
#   ├── withdrawals.py     ← gerenciar saques
#   ├── giftcards.py       ← criar gift cards
#   ├── messages.py        ← editor de mensagens
#   ├── buttons.py         ← editor de botões
#   ├── images.py          ← gerenciador de imagens
#   ├── broadcast.py       ← envio em massa
#   ├── scheduler.py       ← agendador
#   ├── maintenance.py     ← manutenção
#   ├── antiflood.py       ← anti-flood
#   ├── blocks.py          ← bloqueios
#   ├── ranking.py         ← configurar rankings
#   ├── search.py          ← configurar pesquisa
#   ├── support.py         ← atendimento
#   ├── terms.py           ← termos
#   ├── commands.py        ← comandos
#   ├── transactions.py    ← transações
#   ├── logs.py            ← auditoria
#   ├── stats.py           ← estatísticas
#   ├── integrations.py    ← integrações
#   ├── diagnostics.py     ← diagnóstico
#   ├── updates.py         ← atualizações
#   └── middlewares.py     ← filtros (só admin)
# ============================================

from aiogram import Router


# Router principal do painel admin
admin_router = Router(name="admin")

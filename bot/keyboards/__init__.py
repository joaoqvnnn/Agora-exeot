# ============================================
# 📦 PACOTE: bot.keyboards
# ============================================
# Teclados (botões) do bot, tanto inline quanto reply.
#
# Estrutura:
#   bot/keyboards/
#   ├── __init__.py       ← este arquivo
#   ├── main_menu.py      ← teclado do /start
#   ├── catalogo.py       ← teclado do catálogo
#   ├── produto.py        ← teclado do produto
#   ├── pix.py            ← teclado do Pix
#   ├── perfil.py         ← teclado do perfil
#   ├── afiliados.py      ← teclado de afiliados
#   ├── ranking.py        ← teclado dos rankings
#   ├── alertas.py        ← teclado de alertas
#   ├── admin/            ← teclados do painel admin
#   └── callbacks.py      ← fábricas de callback_data
#
# REGRA:
#   Os teclados do bot são MONTADOS DINAMICAMENTE
#   a partir da tabela button_templates (editáveis
#   pelo painel admin).
#
#   Isso significa que mudar o botão no painel já
#   reflete no bot, sem reiniciar nada.
# ============================================

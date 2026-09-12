# ============================================
# 🤖 PACOTE: bot
# ============================================
# Pacote principal do bot Telegram.
#
# Estrutura:
#   bot/
#   ├── __init__.py        ← este arquivo
#   ├── main.py            ← FastAPI + webhook + startup
#   ├── loader.py          ← instancia Bot e Dispatcher
#   ├── handlers/          ← handlers organizados por menu
#   ├── keyboards/         ← teclados inline e reply
#   ├── middlewares/       ← anti-flood, canal, manutenção
#   ├── states/            ← FSM (formulários)
#   ├── filters/           ← filtros customizados
#   └── utils/             ← funções auxiliares do bot
# ============================================

__version__ = "0.1.0"

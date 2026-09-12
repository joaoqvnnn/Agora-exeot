# ============================================
# 📦 PACOTE: bot.middlewares
# ============================================
# Middlewares do aiogram 3.
# Cada middleware intercepta updates ANTES de chegar
# nos handlers e pode:
#   - Bloquear (ex: manutenção, flood, ban)
#   - Injetar dados (ex: user, config)
#   - Modificar (ex: salvar last_message_id)
#
# Middlewares planejados:
#   - DatabaseMiddleware    → injeta sessão do banco
#   - UserMiddleware        → injeta/cria usuário
#   - MaintenanceMiddleware → bloqueia se em manutenção
#   - AntiFloodMiddleware   → conta mensagens, bloqueia flood
#   - ChannelMiddleware     → verifica canal obrigatório
#   - ConfigMiddleware      → injeta configs do painel
#   - ThrottlingMiddleware  → limita velocidade
# ============================================

from bot.middlewares.database import DatabaseMiddleware
from bot.middlewares.user import UserMiddleware
from bot.middlewares.maintenance import MaintenanceMiddleware
from bot.middlewares.antiflood import AntiFloodMiddleware
from bot.middlewares.channel import ChannelMiddleware

__all__ = [
    "DatabaseMiddleware",
    "UserMiddleware",
    "MaintenanceMiddleware",
    "AntiFloodMiddleware",
    "ChannelMiddleware",
]

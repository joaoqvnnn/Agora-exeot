# ============================================
# 🤖 LOADER — Larizinha Store
# ============================================
# Instancia o Bot e o Dispatcher do aiogram 3.
# Centraliza a criação pra ser reaproveitado em
# main.py, webhook e scripts.
# ============================================

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from core.config import settings


# ============================================
# 🤖 BOT CLIENTE
# ============================================
bot = Bot(
    token=settings.telegram_bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)


# ============================================
# 🤖 BOT ADMIN
# ============================================
admin_bot: Bot | None = None
if settings.telegram_admin_bot_token:
    admin_bot = Bot(
        token=settings.telegram_admin_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


# ============================================
# 📦 DISPATCHER CLIENTE
# ============================================
dp = Dispatcher(storage=MemoryStorage())


# ============================================
# 📦 DISPATCHER ADMIN
# ============================================
admin_dp = Dispatcher(storage=MemoryStorage())


# ============================================
# 🔌 FECHAR BOTS
# ============================================
async def close_bots() -> None:
    """Fecha as sessões HTTP dos bots."""
    await bot.session.close()
    if admin_bot:
        await admin_bot.session.close()

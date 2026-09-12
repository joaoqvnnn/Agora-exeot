# ============================================
# 🗄️ MIDDLEWARE: DATABASE — Larizinha Store
# ============================================
# Injeta uma sessão do banco em cada handler.
#
# Como funciona:
#   1. Abre uma sessão do banco
#   2. Coloca em data["session"]
#   3. Handler usa: async def h(msg, session: AsyncSession)
#   4. Ao terminar, faz commit (ou rollback se der erro)
#   5. Fecha a sessão
#
# Vantagem:
#   Você não precisa abrir/fechar sessão em cada handler.
#   O middleware cuida disso automaticamente.
# ============================================

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import AsyncSessionLocal


class DatabaseMiddleware(BaseMiddleware):
    """
    Middleware que injeta sessão do banco em cada update.

    Uso nos handlers:
        async def meu_handler(
            message: Message,
            session: AsyncSession,
        ) -> None:
            user = await session.get(User, 1)
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        session: AsyncSession = AsyncSessionLocal()
        data["session"] = session

        try:
            result = await handler(event, data)
            await session.commit()
            return result
        except Exception as e:
            await session.rollback()
            logger.exception(f"❌ Erro no handler, rollback feito: {e}")
            raise
        finally:
            await session.close()

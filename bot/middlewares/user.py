# ============================================
# 👤 MIDDLEWARE: USER — Larizinha Store
# ============================================
# Garante que todo usuário que interage com o bot
# tenha um registro no banco.
#
# O que faz:
#   1. Pega o telegram_user do evento
#   2. Procura no banco pelo telegram_id
#   3. Se não existir, cria (novo usuário)
#   4. Se existir, atualiza dados (username, nome, etc)
#   5. Atualiza last_seen_at
#   6. Injeta em data["user"]
#
# Uso nos handlers:
#   async def meu_handler(message: Message, user: User):
#       print(user.balance)
# ============================================

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TgUser
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import User, UserStatus


class UserMiddleware(BaseMiddleware):
    """Middleware que injeta/cria o usuário do banco."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Pega o telegram_user do update
        tg_user: TgUser | None = data.get("event_from_user")

        if tg_user is None:
            return await handler(event, data)

        session: AsyncSession | None = data.get("session")
        if session is None:
            logger.error("❌ UserMiddleware precisa do DatabaseMiddleware antes")
            return await handler(event, data)

        # Busca usuário no banco
        stmt = select(User).where(User.telegram_id == tg_user.id)
        result = await session.execute(stmt)
        user: User | None = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)

        if user is None:
            # Cria novo usuário
            user = User(
                telegram_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
                language_code=tg_user.language_code,
                status=UserStatus.ACTIVE,
                last_seen_at=now,
            )
            session.add(user)
            await session.flush()
            logger.info(f"🆕 Novo usuário: {tg_user.id} (@{tg_user.username})")
        else:
            # Atualiza dados que podem ter mudado
            changed = False
            if user.username != tg_user.username:
                user.username = tg_user.username
                changed = True
            if user.first_name != tg_user.first_name:
                user.first_name = tg_user.first_name
                changed = True
            if user.last_name != tg_user.last_name:
                user.last_name = tg_user.last_name
                changed = True
            if user.language_code != tg_user.language_code:
                user.language_code = tg_user.language_code
                changed = True

            user.last_seen_at = now

            if changed:
                session.add(user)

        # Injeta no contexto dos handlers
        data["user"] = user

        return await handler(event, data)

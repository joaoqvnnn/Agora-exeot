# ============================================
# 🔧 MIDDLEWARE: MAINTENANCE — Larizinha Store
# ============================================
# Bloqueia o bot quando está em manutenção.
#
# O que faz:
#   1. Lê a config "maintenance_mode" do banco
#   2. Se estiver ON e o usuário NÃO for admin:
#      → envia mensagem de manutenção e para
#   3. Se o usuário for admin: deixa passar
#   4. Quando o admin desliga, o bot volta ao normal
#
# Vantagens:
#   - Não precisa reiniciar o bot pra entrar em manutenção
#   - Admin continua tendo acesso durante a manutenção
# ============================================

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User as TgUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Admin, Config


class MaintenanceMiddleware(BaseMiddleware):
    """Middleware que bloqueia o bot em manutenção."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        session: AsyncSession | None = data.get("session")
        if session is None:
            return await handler(event, data)

        # Lê config de manutenção
        stmt = select(Config).where(Config.key == "maintenance_mode")
        result = await session.execute(stmt)
        config = result.scalar_one_or_none()

        # Se não existe config ou está OFF, deixa passar
        if config is None or config.value != "true":
            return await handler(event, data)

        # Está em manutenção. Verifica se é admin.
        tg_user: TgUser | None = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        stmt = select(Admin).where(
            Admin.telegram_id == tg_user.id,
            Admin.is_active.is_(True),
        )
        result = await session.execute(stmt)
        admin = result.scalar_one_or_none()

        # Admin passa direto
        if admin is not None:
            return await handler(event, data)

        # Bloqueia usuário comum
        # Lê mensagem de manutenção editável
        stmt = select(Config).where(Config.key == "maintenance_message")
        result = await session.execute(stmt)
        msg_config = result.scalar_one_or_none()
        text = (
            msg_config.value
            if msg_config and msg_config.value
            else "🔧 <b>BOT EM MANUTENÇÃO</b>\n\nEstamos realizando uma manutenção. Tente novamente mais tarde."
        )

        # Envia a mensagem (sem empilhar)
        if isinstance(event, Message):
            await event.answer(text)
        elif isinstance(event, CallbackQuery):
            await event.answer("🔧 Bot em manutenção.", show_alert=True)

        return None

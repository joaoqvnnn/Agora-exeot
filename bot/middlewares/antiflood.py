# ============================================
# 🛡️ MIDDLEWARE: ANTIFLOOD — Larizinha Store
# ============================================
# Conta mensagens do usuário numa janela de tempo.
# Se passar do limite, bloqueia por X segundos.
#
# Configurável pelo painel admin via tabela Config:
#   - antiflood_enabled         → true/false
#   - antiflood_max_messages    → padrão 20
#   - antiflood_window_seconds  → padrão 10
#   - antiflood_block_seconds   → padrão 600 (10 min)
#   - antiflood_message         → mensagem de bloqueio
#
# Admins são isentos.
# ============================================

import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User as TgUser
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Admin, Config, FloodLog, User


# Cache em memória: {telegram_id: [timestamps]}
_flood_cache: dict[int, list[float]] = {}


class AntiFloodMiddleware(BaseMiddleware):
    """Middleware que detecta e bloqueia flood."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        session: AsyncSession | None = data.get("session")
        if session is None:
            return await handler(event, data)

        # Admin é isento
        stmt = select(Admin).where(
            Admin.telegram_id == tg_user.id,
            Admin.is_active.is_(True),
        )
        result = await session.execute(stmt)
        if result.scalar_one_or_none() is not None:
            return await handler(event, data)

        # Lê configs
        configs = await _load_configs(session)

        if not configs["enabled"]:
            return await handler(event, data)

        # Verifica se está bloqueado agora
        user: User | None = data.get("user")
        now = time.time()

        if user is not None and user.flood_blocked_until:
            blocked_until_ts = user.flood_blocked_until.timestamp()
            if now < blocked_until_ts:
                remaining = int(blocked_until_ts - now)
                mins = remaining // 60
                secs = remaining % 60
                text = configs["message"].replace("{tempo}", f"{mins}m {secs}s")
                await _reply(event, text)
                return None

        # Conta mensagem na janela
        timestamps = _flood_cache.get(tg_user.id, [])
        cutoff = now - configs["window"]
        timestamps = [t for t in timestamps if t > cutoff]
        timestamps.append(now)
        _flood_cache[tg_user.id] = timestamps

        # Verifica se passou do limite
        if len(timestamps) > configs["max_messages"]:
            # Bloqueia
            block_until_ts = now + configs["block"]
            if user is not None:
                from datetime import datetime, timezone
                user.flood_blocked_until = datetime.fromtimestamp(
                    block_until_ts, tz=timezone.utc
                )
                user.flood_count = (user.flood_count or 0) + 1
                session.add(user)

            # Log
            log = FloodLog(
                user_telegram_id=tg_user.id,
                message_count=len(timestamps),
                block_seconds=configs["block"],
                reason="auto_antiflood",
            )
            session.add(log)

            logger.warning(
                f"🛡️ Anti-flood: usuário {tg_user.id} bloqueado por "
                f"{configs['block']}s ({len(timestamps)} msgs)"
            )

            mins = configs["block"] // 60
            text = configs["message"].replace("{tempo}", f"{mins}m")
            await _reply(event, text)
            return None

        return await handler(event, data)


# ============================================
# 🧰 AUXILIARES
# ============================================

async def _load_configs(session: AsyncSession) -> dict:
    """Carrega todas as configs do antiflood de uma vez."""
    keys = [
        "antiflood_enabled",
        "antiflood_max_messages",
        "antiflood_window_seconds",
        "antiflood_block_seconds",
        "antiflood_message",
    ]
    stmt = select(Config).where(Config.key.in_(keys))
    result = await session.execute(stmt)
    rows = {c.key: c.value for c in result.scalars().all()}

    def _int(key: str, default: int) -> int:
        try:
            return int(rows.get(key, default))
        except (TypeError, ValueError):
            return default

    return {
        "enabled": rows.get("antiflood_enabled", "true") == "true",
        "max_messages": _int("antiflood_max_messages", 20),
        "window": _int("antiflood_window_seconds", 10),
        "block": _int("antiflood_block_seconds", 600),
        "message": rows.get(
            "antiflood_message",
            "🚫 <b>Você foi bloqueado por flood.</b>\n\n"
            "Aguarde {tempo} para voltar a usar o bot.",
        ),
    }


async def _reply(event: TelegramObject, text: str) -> None:
    """Responde ao evento (mensagem ou callback)."""
    if isinstance(event, Message):
        await event.answer(text)
    elif isinstance(event, CallbackQuery):
        await event.answer("🚫 Você foi bloqueado por flood.", show_alert=True)

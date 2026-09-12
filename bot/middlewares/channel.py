# ============================================
# 📢 MIDDLEWARE: CHANNEL — Larizinha Store
# ============================================
# Verifica se o usuário entrou no canal obrigatório.
#
# O que faz:
#   1. Lê config "required_channel_id" e "required_channel_enabled"
#   2. Se estiver ON, consulta se o usuário é membro
#   3. Se NÃO for, envia mensagem com botão pra entrar
#   4. Se entrar e voltar, libera automaticamente
#   5. Se sair depois, volta a bloquear (verificação real)
#
# Admins são isentos.
# ============================================

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
    User as TgUser,
)
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Admin, Config


# Cache de verificação: {telegram_id: timestamp}
_check_cache: dict[int, float] = {}
CACHE_TTL = 30  # segundos


class ChannelMiddleware(BaseMiddleware):
    """Middleware que exige entrada no canal obrigatório."""

    def __init__(self) -> None:
        super().__init__()
        self._bot = None

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        session: AsyncSession | None = data.get("session")
        if session is None:
            return await handler(event, data)

        # Lê configs
        configs = await _load_configs(session)

        # Se canal não configurado ou desabilitado, libera
        if not configs["enabled"] or not configs["channel_id"]:
            return await handler(event, data)

        tg_user: TgUser | None = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        # Admin é isento
        stmt = select(Admin).where(
            Admin.telegram_id == tg_user.id,
            Admin.is_active.is_(True),
        )
        result = await session.execute(stmt)
        if result.scalar_one_or_none() is not None:
            return await handler(event, data)

        # Pega o bot do data (injetado pelo aiogram)
        bot = data.get("bot")
        if bot is None:
            return await handler(event, data)

        # Verifica se é membro
        is_member = await _check_membership(
            bot=bot,
            channel_id=configs["channel_id"],
            user_id=tg_user.id,
            use_cache=True,
        )

        if is_member:
            return await handler(event, data)

        # Não é membro → bloqueia
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=configs["button_text"],
                        url=configs["channel_link"],
                    )
                ],
            ]
        )

        if isinstance(event, Message):
            # Só responde a /start
            if event.text and event.text.startswith("/start"):
                await event.answer(
                    configs["message"],
                    reply_markup=keyboard,
                    disable_web_page_preview=True,
                )
            # Ignora outras mensagens
            return None

        if isinstance(event, CallbackQuery):
            await event.answer(
                "❗ Você precisa entrar no canal primeiro.",
                show_alert=True,
            )
            return None

        return None


# ============================================
# 🧰 AUXILIARES
# ============================================

async def _load_configs(session: AsyncSession) -> dict:
    """Carrega configs do canal obrigatório."""
    keys = [
        "required_channel_enabled",
        "required_channel_id",
        "required_channel_link",
        "required_channel_message",
        "required_channel_button_text",
    ]
    stmt = select(Config).where(Config.key.in_(keys))
    result = await session.execute(stmt)
    rows = {c.key: c.value for c in result.scalars().all()}

    channel_id_raw = rows.get("required_channel_id", "")
    try:
        channel_id = int(channel_id_raw) if channel_id_raw else 0
    except (TypeError, ValueError):
        channel_id = 0

    return {
        "enabled": rows.get("required_channel_enabled", "false") == "true",
        "channel_id": channel_id,
        "channel_link": rows.get("required_channel_link", "https://t.me/"),
        "message": rows.get(
            "required_channel_message",
            "❗️ <b>Para utilizar nosso serviço é obrigatório que você "
            "entre no nosso grupo.</b>\n\n➡️ Entre no canal abaixo:",
        ),
        "button_text": rows.get(
            "required_channel_button_text", "➡️ ENTRAR NO CANAL"
        ),
    }


async def _check_membership(
    bot,
    channel_id: int,
    user_id: int,
    use_cache: bool = True,
) -> bool:
    """Verifica se o usuário é membro do canal."""
    import time

    now = time.time()

    # Cache
    if use_cache:
        cached = _check_cache.get(user_id)
        if cached and (now - cached) < CACHE_TTL:
            # Ainda tá no cache, mas precisamos confirmar de novo
            # (usuário pode ter saído). Vamos invalidar após TTL.
            pass

    try:
        member = await bot.get_chat_member(
            chat_id=channel_id,
            user_id=user_id,
        )
        # Status que indicam que é membro
        ok = member.status in ("creator", "administrator", "member", "restricted")
        if ok:
            _check_cache[user_id] = now
        else:
            _check_cache.pop(user_id, None)
        return ok
    except TelegramBadRequest as e:
        # Usuário não é membro OU bot não é admin no canal
        logger.warning(f"⚠️ Erro ao verificar membro {user_id}: {e}")
        _check_cache.pop(user_id, None)
        return False
    except Exception as e:
        logger.exception(f"❌ Erro inesperado no check de membro: {e}")
        return False

# ============================================
# 🔐 ADMIN MIDDLEWARES — Larizinha Store
# ============================================
# Filtros e middlewares específicos do painel admin.
# Garante que só admins acessem os handlers do painel.
# ============================================

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message, TelegramObject, User as TgUser
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Admin


# ============================================
# 🎯 FILTRO: É ADMIN?
# ============================================
class IsAdminFilter(BaseFilter):
    """
    Filtro que libera apenas administradores ativos.

    Uso:
        @router.message(Command("admin"), IsAdminFilter())
        async def cmd_admin(...):
            ...
    """

    async def __call__(
        self,
        event: TelegramObject,
        session: AsyncSession,
    ) -> bool:
        user: TgUser | None = getattr(event, "from_user", None)
        if user is None:
            return False

        stmt = select(Admin).where(
            Admin.telegram_id == user.id,
            Admin.is_active.is_(True),
        )
        result = await session.execute(stmt)
        admin = result.scalar_one_or_none()

        if admin is None:
            logger.debug(f"🚫 Acesso admin negado: {user.id}")
            return False

        return True


# ============================================
# 🎯 FILTRO: É DONO?
# ============================================
class IsOwnerFilter(BaseFilter):
    """Filtro que libera apenas o DONO do bot."""

    async def __call__(
        self,
        event: TelegramObject,
        session: AsyncSession,
    ) -> bool:
        user: TgUser | None = getattr(event, "from_user", None)
        if user is None:
            return False

        stmt = select(Admin).where(
            Admin.telegram_id == user.id,
            Admin.is_active.is_(True),
            Admin.is_owner.is_(True),
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None


# ============================================
# 🛡️ MIDDLEWARE: ADMIN GUARD
# ============================================
class AdminGuardMiddleware(BaseMiddleware):
    """
    Bloqueia callbacks que começam com "adm" caso
    o usuário não seja admin. Ação silenciosa (só
    responde "Sem acesso").
    """

    ADMIN_PREFIXES = (
        "adm:",
        "adm_",
        "adm-",
    )

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Verifica só callbacks
        callback_data: str | None = None
        if isinstance(event, CallbackQuery):
            callback_data = event.data or ""
        elif isinstance(event, Message):
            # Comandos começando com /adm (exceto /admin que tem filtro próprio)
            if event.text and event.text.startswith("/adm") and not event.text.startswith("/admin"):
                callback_data = event.text
            elif event.text and event.text.startswith("/admin"):
                callback_data = "/admin"

        # Se não é ação de admin, deixa passar
        if callback_data is None:
            return await handler(event, data)

        is_admin_action = any(
            callback_data.startswith(prefix)
            for prefix in self.ADMIN_PREFIXES
        ) or callback_data.startswith("/admin")

        if not is_admin_action:
            return await handler(event, data)

        # É ação de admin — valida
        user: TgUser | None = data.get("event_from_user")
        session: AsyncSession | None = data.get("session")

        if user is None or session is None:
            return await handler(event, data)

        stmt = select(Admin).where(
            Admin.telegram_id == user.id,
            Admin.is_active.is_(True),
        )
        result = await session.execute(stmt)
        admin = result.scalar_one_or_none()

        if admin is None:
            logger.warning(f"🚫 Tentativa de acesso admin: {user.id} → {callback_data[:50]}")
            if isinstance(event, CallbackQuery):
                await event.answer("🚫 Sem acesso.", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("🚫 Você não tem acesso ao painel.")
            return None

        # Passa pro handler
        data["admin"] = admin
        return await handler(event, data)


# ============================================
# 🛡️ MIDDLEWARE: CONFIRMA AÇÃO PERIGOSA
# ============================================
class ConfirmDangerousActionMiddleware(BaseMiddleware):
    """
    Ações perigosas (zerar estoque, remover admin, etc)
    só passam se o usuário já confirmou via callback
    específico (confirm:yes:*).
    """

    DANGEROUS_PREFIXES = (
        "adm_stock:clear_confirm",
        "adm_prod:confirm_delete",
        "adm_cat:confirm_delete",
        "adm_gift:revoke_all_confirm",
        "adm_terms:reset_confirm",
        "adm_user:block_dur",
        "confirm:yes:",
    )

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Este middleware apenas documenta o padrão;
        # a confirmação real acontece nos próprios handlers,
        # que exigem um segundo clique antes de executar.
        return await handler(event, data)

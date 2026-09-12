# ============================================
# 👮 ADMIN ROUTER — Larizinha Store
# ============================================
# Router central do painel administrativo.
# Registra todos os sub-routers do admin.
# Também contém o /admin, o /menu_admin e o callback
# de voltar pro painel principal.
# ============================================

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.admin.main import build_admin_main_keyboard
from core.models import Admin
from core.services.messages import render_message


router = Router(name="admin_router")


# ============================================
# /admin — entrada do painel
# ============================================
@router.message(Command("admin"))
async def cmd_admin(
    message: Message,
    session: AsyncSession,
) -> None:
    """Entrada do painel administrativo."""
    admin = await _get_admin(session, message.from_user.id)
    if admin is None:
        await message.answer("🚫 Você não tem acesso ao painel administrativo.")
        return

    text = _build_panel_text(admin)
    keyboard = build_admin_main_keyboard(is_owner=admin.is_owner)

    await message.answer(text, reply_markup=keyboard)


# ============================================
# CALLBACK: voltar ao painel principal
# ============================================
@router.callback_query(F.data == "adm:dashboard")
async def cb_dashboard(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    admin = await _get_admin(session, callback.from_user.id)
    if admin is None:
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text = _build_panel_text(admin)
    keyboard = build_admin_main_keyboard(is_owner=admin.is_owner)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# CALLBACK: noop (botões informativos do admin)
# ============================================
@router.callback_query(F.data == "adm:noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()


# ============================================
# 🧰 AUXILIARES
# ============================================
async def _get_admin(
    session: AsyncSession,
    telegram_id: int,
) -> Admin | None:
    """Busca o admin no banco pelo telegram_id."""
    stmt = select(Admin).where(
        Admin.telegram_id == telegram_id,
        Admin.is_active.is_(True),
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _build_panel_text(admin: Admin) -> str:
    """Monta o texto do painel principal."""
    from core.config import settings

    role = "👑 Dono" if admin.is_owner else "👮 Admin"
    version = "V4.1.0"
    bot_name = settings.telegram_bot_username or "Bot"

    return (
        f"👮 <b>PAINEL ADMINISTRATIVO</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🤖 Bot: <b>@{bot_name}</b>\n"
        f"🆔 Admin: <code>{admin.telegram_id}</code>\n"
        f"🎖 Cargo: <b>{role}</b>\n"
        f"📦 Versão: <code>{version}</code>\n\n"
        f"Use os botões abaixo para configurar o bot."
    )

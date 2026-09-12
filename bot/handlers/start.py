# ============================================
# 🏠 START — Larizinha Store
# ============================================

from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import CallbackQuery, Message
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import build_main_menu
from core.config import settings
from core.models import User
from core.services.messages import render_message


router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    user: User,
    session: AsyncSession,
) -> None:
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        await _handle_referral(args[1], user, session)

    text = await render_message(
        session,
        key="start",
        variables=_user_variables(user),
    )

    keyboard = await build_main_menu(session, webapp_url=settings.webapp_url)

    if user.last_message_id:
        try:
            await message.bot.delete_message(
                chat_id=message.chat.id,
                message_id=user.last_message_id,
            )
        except Exception:
            pass

    sent = await message.answer(text, reply_markup=keyboard)
    user.last_message_id = sent.message_id
    user.last_menu = "start"
    session.add(user)


@router.message(Command("menu"))
async def cmd_menu(
    message: Message,
    user: User,
    session: AsyncSession,
) -> None:
    await cmd_start(message, user, session)


@router.callback_query(F.data == "menu:voltar")
async def cb_voltar_inicio(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    text = await render_message(
        session,
        key="start",
        variables=_user_variables(user),
    )
    keyboard = await build_main_menu(session, webapp_url=settings.webapp_url)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    user.last_message_id = callback.message.message_id
    user.last_menu = "start"
    session.add(user)
    await callback.answer()


@router.callback_query(F.data == "menu:sobre")
async def cb_sobre(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    text = await render_message(
        session,
        key="sobre",
        variables=_user_variables(user),
    )
    keyboard = await build_main_menu(session, webapp_url=settings.webapp_url)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    user.last_menu = "sobre"
    session.add(user)
    await callback.answer()


@router.callback_query(F.data == "menu:noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()


def _user_variables(user: User) -> dict:
    saldo = user.balance if user.balance is not None else Decimal("0.00")
    return {
        "USER_ID": user.telegram_id,
        "USERNAME": user.username or user.first_name or "Usuário",
        "FIRST_NAME": user.first_name or "",
        "BALANCE": f"{saldo:.2f}".replace(".", ","),
        "POINTS": str(user.points or 0),
        "AFFILIATE_BALANCE": f"{(user.affiliate_balance or Decimal('0.00')):.2f}".replace(".", ","),
    }


async def _handle_referral(
    ref_arg: str,
    user: User,
    session: AsyncSession,
) -> None:
    if user.referred_by is not None:
        return
    try:
        referrer_id = int(ref_arg)
    except (TypeError, ValueError):
        return
    if referrer_id == user.telegram_id:
        return
    user.referred_by = referrer_id
    session.add(user)
    logger.info(f"🤝 Usuário {user.telegram_id} indicado por {referrer_id}")

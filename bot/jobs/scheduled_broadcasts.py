# ============================================
# 📢 SCHEDULED BROADCASTS — Larizinha Store
# ============================================
# Job que dispara broadcasts agendados que
# chegaram no horário.
#
# Roda a cada 1 minuto via APScheduler.
# ============================================

import asyncio
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from loguru import logger
from sqlalchemy import select

from core.database import AsyncSessionLocal
from core.models import (
    Broadcast,
    BroadcastStatus,
    User,
    UserStatus,
)


async def job_scheduled_broadcasts(bot: Bot) -> None:
    """Dispara broadcasts agendados no horário."""
    try:
        async with AsyncSessionLocal() as session:
            now = datetime.now(timezone.utc)

            stmt = select(Broadcast).where(
                Broadcast.status == BroadcastStatus.SCHEDULED,
                Broadcast.scheduled_at <= now,
            )
            result = await session.execute(stmt)
            broadcasts = list(result.scalars().all())

            if not broadcasts:
                return

            for bc in broadcasts:
                logger.info(f"📢 Disparando broadcast agendado #{bc.id}")
                asyncio.create_task(_run_broadcast(bot, bc.id))

    except Exception as e:
        logger.exception(f"❌ Erro no job scheduled_broadcasts: {e}")


async def _run_broadcast(bot: Bot, broadcast_id: int) -> None:
    """Executa o broadcast."""
    sent = 0
    failed = 0

    try:
        # Carrega o broadcast
        async with AsyncSessionLocal() as session:
            bc = await session.get(Broadcast, broadcast_id)
            if bc is None:
                return

            # Monta keyboard
            reply_markup = None
            if bc.buttons:
                rows = []
                for b in bc.buttons:
                    try:
                        rows.append([
                            InlineKeyboardButton(text=b["text"], url=b["url"])
                        ])
                    except Exception:
                        continue
                if rows:
                    reply_markup = InlineKeyboardMarkup(inline_keyboard=rows)

            text = bc.message_text or ""
            media_type = bc.media_type or "none"
            media_id = bc.media_url

            # Busca usuários
            stmt = select(User).where(
                User.status == UserStatus.ACTIVE,
                User.is_blocked_bot.is_(False),
            )
            users_result = await session.execute(stmt)
            users = list(users_result.scalars().all())

            bc.total_targets = len(users)
            bc.status = BroadcastStatus.SENDING
            session.add(bc)
            await session.commit()

        # Envia
        for u in users:
            try:
                if media_type == "photo" and media_id:
                    await bot.send_photo(
                        chat_id=u.telegram_id,
                        photo=media_id,
                        caption=text or None,
                        reply_markup=reply_markup,
                        parse_mode="HTML",
                    )
                elif media_type == "video" and media_id:
                    await bot.send_video(
                        chat_id=u.telegram_id,
                        video=media_id,
                        caption=text or None,
                        reply_markup=reply_markup,
                        parse_mode="HTML",
                    )
                else:
                    await bot.send_message(
                        chat_id=u.telegram_id,
                        text=text,
                        reply_markup=reply_markup,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                sent += 1
            except Exception:
                failed += 1

            await asyncio.sleep(0.05)

            if sent % 50 == 0:
                async with AsyncSessionLocal() as session:
                    bc = await session.get(Broadcast, broadcast_id)
                    if bc:
                        bc.sent_count = sent
                        bc.failed_count = failed
                        session.add(bc)
                        await session.commit()

        # Finaliza
        async with AsyncSessionLocal() as session:
            bc = await session.get(Broadcast, broadcast_id)
            if bc:
                bc.sent_count = sent
                bc.failed_count = failed
                bc.status = BroadcastStatus.SENT
                bc.sent_at = datetime.now(timezone.utc)
                session.add(bc)
                await session.commit()

        logger.success(f"📢 Broadcast #{broadcast_id}: {sent} enviados, {failed} falhas")

    except Exception as e:
        logger.exception(f"❌ Erro no broadcast #{broadcast_id}: {e}")


async def job_scheduled_broadcasts_wrapper(bot: Bot) -> None:
    """Wrapper pra chamar do scheduler."""
    await job_scheduled_broadcasts(bot)

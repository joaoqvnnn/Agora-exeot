# ============================================
# ⌛ EXPIRE PAYMENTS — Larizinha Store
# ============================================
# Job que marca Pix pendentes vencidos como
# expirados e notifica o cliente.
#
# Roda a cada 1 minuto via APScheduler.
# ============================================

from aiogram import Bot
from loguru import logger
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from core.database import AsyncSessionLocal
from core.services import payment as payment_service


def _format_brl(v) -> str:
    if v is None:
        return "0,00"
    return f"{float(v):.2f}".replace(".", ",")


async def job_expire_payments(bot: Bot) -> None:
    """Expira pagamentos vencidos e notifica clientes."""
    try:
        async with AsyncSessionLocal() as session:
            payments = await payment_service.expire_overdue_payments(session)

            if not payments:
                return

            await session.commit()
            logger.info(f"⌛ {len(payments)} pagamentos expirados")

            # Notifica clientes
            for p in payments:
                try:
                    await _notify_expired(bot, p)
                except Exception as e:
                    logger.debug(f"⚠️ Falha ao notificar expiração: {e}")

    except Exception as e:
        logger.exception(f"❌ Erro no job expire_payments: {e}")


async def _notify_expired(bot: Bot, payment) -> None:
    """Notifica cliente sobre Pix expirado."""
    text = (
        f"⌛️ <b>PAGAMENTO PIX EXPIRADO</b>\n\n"
        f"⚠️ O tempo limite para realizar este pagamento foi excedido.\n\n"
        f"🆔 Referência: <code>{payment.payment_id}</code>\n"
        f"💸 Valor Solicitado: <b>R$ {_format_brl(payment.amount)}</b>\n\n"
        f"💡 Use o menu abaixo para gerar um novo Pix."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💰 Recarregar", callback_data="menu:recarregar")],
            [InlineKeyboardButton(text="🔙 Menu principal", callback_data="menu:voltar")],
        ]
    )

    try:
        await bot.send_message(
            chat_id=payment.user_telegram_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    except Exception:
        pass

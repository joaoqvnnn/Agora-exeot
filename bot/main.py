# ============================================
# 🚀 MAIN — Larizinha Store
# ============================================
# Arquivo principal que sobe TUDO:
#   - FastAPI (webhook Telegram + webhooks externos)
#   - Bot do Telegram (via webhook)
#   - APScheduler (tarefas agendadas)
#   - Startup / Shutdown
#
# ⚠️ Este é o arquivo que o Render vai executar.
# ============================================

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from aiogram.types import BotCommand, Update
from fastapi import FastAPI, Request, Response
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from api.webhooks.mercadopago import router as mercadopago_router
from bot.loader import bot, dp, close_bots
from bot.handlers import register_all_handlers
from core.config import settings
from core.database import close_database, init_database


# ============================================
# ⏰ AGENDADOR DE TAREFAS
# ============================================
scheduler = AsyncIOScheduler(timezone=settings.timezone)


# ============================================
# 🎯 CICLO DE VIDA (startup/shutdown)
# ============================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup e shutdown do app.
    Roda ANTES e DEPOIS do servidor subir.
    """
    # ================================
    # 🟢 STARTUP
    # ================================
    logger.info("🚀 Iniciando Larizinha Store...")

    # 1. Banco de dados
    try:
        await init_database()
        logger.success("✅ Banco conectado")
    except Exception as e:
        logger.error(f"❌ Erro ao conectar no banco: {e}")
        raise

    # 2. Configura webhook do Telegram
    try:
        await setup_telegram_webhook()
    except Exception as e:
        logger.error(f"❌ Erro ao configurar webhook: {e}")
        # Não falha o startup — talvez esteja em modo polling

    # 3. Registra os comandos do bot
    try:
        await setup_bot_commands()
    except Exception as e:
        logger.warning(f"⚠️ Falha ao registrar comandos: {e}")

    # 4. Inicia o agendador
    try:
        setup_scheduler()
        scheduler.start()
        logger.success("✅ Agendador iniciado")
    except Exception as e:
        logger.error(f"❌ Erro no agendador: {e}")

    # 5. Notifica admins que o bot está online
    try:
        await notify_bot_online()
    except Exception as e:
        logger.debug(f"⚠️ Falha ao notificar online: {e}")

    logger.success("🎉 Larizinha Store pronta!")

    yield

    # ================================
    # 🔴 SHUTDOWN
    # ================================
    logger.info("🛑 Encerrando...")

    try:
        scheduler.shutdown(wait=False)
        logger.info("✅ Agendador parado")
    except Exception:
        pass

    try:
        await close_bots()
        logger.info("✅ Bots fechados")
    except Exception:
        pass

    try:
        await close_database()
        logger.info("✅ Banco fechado")
    except Exception:
        pass

    logger.info("👋 Até logo!")


# ============================================
# 🌐 FASTAPI APP
# ============================================
app = FastAPI(
    title="Larizinha Store API",
    description="Bot + Webhooks + Mini App backend",
    version="4.1.0",
    lifespan=lifespan,
)


# ============================================
# 📥 REGISTRA ROUTERS
# ============================================
app.include_router(mercadopago_router)


# ============================================
# 🏥 HEALTHCHECK (Render usa pra saber se está vivo)
# ============================================
@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "Larizinha Store",
        "version": "4.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health")
async def health():
    """Endpoint de healthcheck do Render."""
    from core.database import check_database_connection

    db_ok = await check_database_connection()

    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "ok" if db_ok else "down",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ============================================
# 🤖 WEBHOOK DO TELEGRAM
# ============================================
@app.post(f"/webhook/telegram/{settings.telegram_webhook_secret}")
async def telegram_webhook(request: Request) -> Response:
    """
    Recebe updates do Telegram via webhook.
    """
    try:
        update_data = await request.json()
        update = Update.model_validate(update_data, context={"bot": bot})

        # Processa em background
        asyncio.create_task(dp.feed_update(bot, update))

        return Response(status_code=200)
    except Exception as e:
        logger.exception(f"❌ Erro no webhook Telegram: {e}")
        return Response(status_code=200)  # Sempre 200 pro TG não reenviar


# ============================================
# 🔧 CONFIGURAÇÕES
# ============================================
async def setup_telegram_webhook() -> None:
    """Configura o webhook do Telegram."""
    if not settings.telegram_webhook_url:
        logger.warning("⚠️ TELEGRAM_WEBHOOK_URL não configurada")
        return

    if "seu-servico" in settings.telegram_webhook_url:
        logger.warning("⚠️ URL do webhook não foi configurada (placeholder)")
        return

    try:
        webhook_url = settings.telegram_webhook_full_url

        # Remove webhook antigo
        await bot.delete_webhook(drop_pending_updates=True)

        # Seta novo
        await bot.set_webhook(
            url=webhook_url,
            secret_token=settings.telegram_webhook_secret or None,
            drop_pending_updates=True,
            max_connections=40,
            allowed_updates=[
                "message",
                "callback_query",
                "inline_query",
                "chosen_inline_result",
                "pre_checkout_query",
            ],
        )
        logger.success(f"✅ Webhook Telegram: {webhook_url}")

    except Exception as e:
        logger.error(f"❌ Falha ao configurar webhook: {e}")
        raise


async def setup_bot_commands() -> None:
    """Registra os comandos no Telegram (menu /)."""
    commands = [
        BotCommand(command="start", description="🚀 Iniciar o bot"),
        BotCommand(command="menu", description="📱 Menu principal"),
        BotCommand(command="comprar", description="🛍 Comprar produtos"),
        BotCommand(command="perfil", description="👤 Meu perfil"),
        BotCommand(command="saldo", description="💰 Meu saldo"),
        BotCommand(command="pix", description="💳 Gerar Pix"),
        BotCommand(command="historico", description="📜 Histórico de compras"),
        BotCommand(command="afiliados", description="🤝 Programa de afiliados"),
        BotCommand(command="ranking", description="🏆 Rankings"),
        BotCommand(command="alertas", description="🔔 Alertas de estoque"),
        BotCommand(command="gift", description="🎁 Resgatar Gift Card"),
        BotCommand(command="atendimento", description="🎧 Atendimento"),
        BotCommand(command="termos", description="📜 Termos de uso"),
        BotCommand(command="cancelar", description="❌ Cancelar operação"),
    ]

    try:
        await bot.set_my_commands(commands)
        logger.success(f"✅ {len(commands)} comandos registrados")
    except Exception as e:
        logger.warning(f"⚠️ Falha ao registrar comandos: {e}")


# ============================================
# ⏰ TAREFAS AGENDADAS (APScheduler)
# ============================================
def setup_scheduler() -> None:
    """
    Configura todas as tarefas automáticas:
      - Verificar pagamentos expirados (1 min)
      - Liberar reservas expiradas (1 min)
      - Verificar estoque baixo (5 min)
      - Notificar expiração de produtos (1 hora)
      - Limpar logs antigos (diário)
      - Enviar broadcasts agendados (1 min)
    """

    # ─── Pagamentos expirados ───
    scheduler.add_job(
        _job_expire_payments,
        "interval",
        minutes=1,
        id="expire_payments",
        replace_existing=True,
        misfire_grace_time=30,
    )

    # ─── Reservas expiradas ───
    scheduler.add_job(
        _job_release_reservations,
        "interval",
        minutes=1,
        id="release_reservations",
        replace_existing=True,
        misfire_grace_time=30,
    )

    # ─── Broadcasts agendados ───
    scheduler.add_job(
        _job_check_scheduled_broadcasts,
        "interval",
        minutes=1,
        id="check_broadcasts",
        replace_existing=True,
        misfire_grace_time=30,
    )

    # ─── Estoque baixo ───
    scheduler.add_job(
        _job_check_low_stock,
        "interval",
        minutes=10,
        id="check_low_stock",
        replace_existing=True,
        misfire_grace_time=60,
    )

    # ─── Produtos expirados ───
    scheduler.add_job(
        _job_expire_products,
        "interval",
        hours=1,
        id="expire_products",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # ─── Limpar logs antigos (diário) ───
    scheduler.add_job(
        _job_clean_old_logs,
        "cron",
        hour=3,
        minute=0,
        id="clean_old_logs",
        replace_existing=True,
    )

    logger.info("📅 Tarefas agendadas:")
    for job in scheduler.get_jobs():
        logger.info(f"   • {job.id}")


# ============================================
# 🔄 JOBS
# ============================================
async def _job_expire_payments() -> None:
    """Marca pagamentos pendentes vencidos como expirados."""
    from core.database import AsyncSessionLocal
    from core.services import payment as payment_service

    try:
        async with AsyncSessionLocal() as session:
            payments = await payment_service.expire_overdue_payments(session)
            if payments:
                await session.commit()
                logger.info(f"⌛ {len(payments)} pagamentos expirados")

                # Notifica clientes
                for p in payments:
                    try:
                        await bot.send_message(
                            chat_id=p.user_telegram_id,
                            text=(
                                f"⌛️ <b>PIX EXPIRADO</b>\n\n"
                                f"🆔 <code>{p.payment_id}</code>\n"
                                f"💸 R$ {float(p.amount):.2f}\n\n"
                                f"Gere um novo em /menu."
                            ),
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass
    except Exception as e:
        logger.exception(f"❌ Erro job expire_payments: {e}")


async def _job_release_reservations() -> None:
    """Libera reservas de estoque expiradas."""
    from core.database import AsyncSessionLocal
    from core.services import stock as stock_service

    try:
        async with AsyncSessionLocal() as session:
            count = await stock_service.release_expired_reservations(session)
            if count:
                await session.commit()
                logger.info(f"🔓 {count} reservas expiradas liberadas")
    except Exception as e:
        logger.exception(f"❌ Erro job release_reservations: {e}")


async def _job_check_scheduled_broadcasts() -> None:
    """Dispara broadcasts agendados que chegou a hora."""
    from core.database import AsyncSessionLocal
    from core.models import Broadcast, BroadcastStatus
    from core.models import User, UserStatus
    from sqlalchemy import select

    try:
        async with AsyncSessionLocal() as session:
            now = datetime.now(timezone.utc)

            stmt = select(Broadcast).where(
                Broadcast.status == BroadcastStatus.SCHEDULED,
                Broadcast.scheduled_at <= now,
            )
            result = await session.execute(stmt)
            broadcasts = list(result.scalars().all())

            for bc in broadcasts:
                logger.info(f"📢 Disparando broadcast #{bc.id}")

                # Coleta usuários
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

                # Dispara em background
                asyncio.create_task(
                    _run_scheduled_broadcast(bc.id, users)
                )

    except Exception as e:
        logger.exception(f"❌ Erro job check_broadcasts: {e}")


async def _run_scheduled_broadcast(broadcast_id: int, users: list) -> None:
    """Executa o broadcast agendado."""
    from core.database import AsyncSessionLocal
    from core.models import Broadcast, BroadcastStatus
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    sent = 0
    failed = 0

    try:
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
        logger.exception(f"❌ Erro broadcast {broadcast_id}: {e}")


async def _job_check_low_stock() -> None:
    """Verifica se algum produto tem estoque baixo."""
    from core.database import AsyncSessionLocal
    from core.models import Product, ProductStatus, StockItem, StockStatus
    from core.services import config as config_service
    from bot.handlers.admin.alerts import notify_stock_low
    from sqlalchemy import func, select

    try:
        async with AsyncSessionLocal() as session:
            threshold = await config_service.get_int(
                session, "stock_alert_threshold", 3
            )

            stmt = select(Product).where(
                Product.status == ProductStatus.ACTIVE,
                Product.stock_alert_enabled.is_(True),
            )
            result = await session.execute(stmt)
            products = list(result.scalars().all())

            for p in products:
                stock = await session.scalar(
                    select(func.count(StockItem.id)).where(
                        StockItem.product_id == p.id,
                        StockItem.status == StockStatus.AVAILABLE,
                    )
                ) or 0

                # Só alerta se acabou de ficar baixo (evita spam)
                # Simples: envia se está em 0 ou abaixo do threshold
                if 0 <= stock <= threshold:
                    # Evita alertar repetidamente
                    from core.services import config as cfg
                    last_alert = await cfg.get_str(
                        session, f"stock_alert_last_{p.id}", ""
                    )
                    now_str = datetime.now(timezone.utc).strftime("%Y%m%d%H")

                    if last_alert != now_str:
                        await notify_stock_low(
                            bot=bot,
                            session=session,
                            product_name=p.name,
                            remaining=stock,
                            threshold=threshold,
                        )
                        await cfg.set_config(
                            session, f"stock_alert_last_{p.id}", now_str
                        )
                        await session.commit()

    except Exception as e:
        logger.exception(f"❌ Erro job low_stock: {e}")


async def _job_expire_products() -> None:
    """Marca itens de estoque vendidos como expirados."""
    from core.database import AsyncSessionLocal
    from core.services import stock as stock_service

    try:
        async with AsyncSessionLocal() as session:
            count = await stock_service.mark_expired(session)
            if count:
                await session.commit()
                logger.info(f"⌛ {count} produtos expirados")
    except Exception as e:
        logger.exception(f"❌ Erro job expire_products: {e}")


async def _job_clean_old_logs() -> None:
    """Remove logs de auditoria com mais de 90 dias."""
    from core.database import AsyncSessionLocal
    from core.models import AuditLog
    from datetime import timedelta
    from sqlalchemy import delete

    try:
        async with AsyncSessionLocal() as session:
            cutoff = datetime.now(timezone.utc) - timedelta(days=90)
            stmt = delete(AuditLog).where(AuditLog.created_at < cutoff)
            result = await session.execute(stmt)
            await session.commit()

            count = result.rowcount or 0
            if count:
                logger.info(f"🧹 {count} logs antigos removidos")
    except Exception as e:
        logger.exception(f"❌ Erro job clean_logs: {e}")


# ============================================
# 📢 NOTIFICA BOT ONLINE
# ============================================
async def notify_bot_online() -> None:
    """Notifica os admins que o bot está online."""
    from core.database import AsyncSessionLocal
    from core.models import Admin
    from sqlalchemy import select

    try:
        async with AsyncSessionLocal() as session:
            stmt = select(Admin).where(Admin.is_active.is_(True))
            result = await session.execute(stmt)
            admins = list(result.scalars().all())

            now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M:%S")

            for adm in admins:
                try:
                    await bot.send_message(
                        chat_id=adm.telegram_id,
                        text=(
                            f"🟢 <b>BOT ONLINE</b>\n\n"
                            f"⏰ {now}\n"
                            f"🚀 Sistema iniciado com sucesso!"
                        ),
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"⚠️ Falha ao notificar online: {e}")


# ============================================
# 📌 REGISTRA HANDLERS
# ============================================
# A função register_all_handlers() será definida
# no bot/handlers/__init__.py atualizado.
try:
    register_all_handlers(dp)
    logger.success("✅ Handlers registrados")
except Exception as e:
    logger.error(f"❌ Erro ao registrar handlers: {e}")


# ============================================
# 🚀 ENTRYPOINT
# ============================================
if __name__ == "__main__":
    # Modo desenvolvimento local
    import os

    port = int(os.getenv("PORT", 8000))

    logger.info(f"🚀 Iniciando em modo dev na porta {port}")

    uvicorn.run(
        "bot.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level=settings.log_level.lower(),
    )

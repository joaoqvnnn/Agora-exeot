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
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from aiogram.types import BotCommand, Update
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request, Response
from loguru import logger

# ============================================
# 📥 IMPORTAÇÕES DO PROJETO
# ============================================
from api.webhooks.mercadopago import router as mercadopago_router
from bot.loader import bot, dp, close_bots
from bot.handlers import register_all_handlers
from core.config import settings
from core.database import close_database, init_database

# Jobs agendados
from bot.jobs.abandoned_product import job_abandoned_product
from bot.jobs.check_stock import job_check_stock
from bot.jobs.clean_logs import job_clean_logs
from bot.jobs.expire_payments import job_expire_payments
from bot.jobs.expire_products import job_expire_products
from bot.jobs.expire_reservations import job_expire_reservations
from bot.jobs.recover_abandoned_carts import job_recover_abandoned_carts
from bot.jobs.scheduled_broadcasts import job_scheduled_broadcasts


# ============================================
# ⏰ AGENDADOR
# ============================================
scheduler = AsyncIOScheduler(timezone=settings.timezone)


# ============================================
# 🎯 CICLO DE VIDA (startup / shutdown)
# ============================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Executado ANTES e DEPOIS do servidor subir.
    """
    # ========================================
    # 🟢 STARTUP
    # ========================================
    logger.info("🚀 Iniciando Larizinha Store...")

    # 1. Banco de dados
    try:
        await init_database()
        logger.success("✅ Banco conectado")
    except Exception as e:
        logger.error(f"❌ Erro ao conectar no banco: {e}")
        raise

    # 2. Webhook Telegram
    try:
        await setup_telegram_webhook()
    except Exception as e:
        logger.error(f"❌ Erro ao configurar webhook: {e}")

    # 3. Comandos do bot
    try:
        await setup_bot_commands()
    except Exception as e:
        logger.warning(f"⚠️ Falha ao registrar comandos: {e}")

    # 4. Agendador
    try:
        setup_scheduler()
        scheduler.start()
        logger.success("✅ Agendador iniciado")
    except Exception as e:
        logger.error(f"❌ Erro no agendador: {e}")

    # 5. Notifica admins
    try:
        await notify_bot_online()
    except Exception as e:
        logger.debug(f"⚠️ Falha ao notificar online: {e}")

    logger.success("🎉 Larizinha Store pronta!")

    yield

    # ========================================
    # 🔴 SHUTDOWN
    # ========================================
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
# 🔧 SETUP DO WEBHOOK
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


# ============================================
# 🧩 COMANDOS DO BOT
# ============================================
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
# ⏰ AGENDADOR DE TAREFAS
# ============================================
def setup_scheduler() -> None:
    """
    Configura todos os jobs automáticos:
      - Reservas expiradas       (1 min)
      - Pagamentos expirados     (1 min)
      - Broadcasts agendados     (1 min)
      - Abandono de produto      (5 min)
      - Carrinhos abandonados    (10 min)
      - Estoque baixo            (10 min)
      - Produtos expirados       (1 hora)
      - Limpar logs antigos      (diário, 3h)
    """

    # ─── Reservas expiradas (1 min) ───
    scheduler.add_job(
        job_expire_reservations,
        "interval",
        minutes=1,
        id="expire_reservations",
        replace_existing=True,
        misfire_grace_time=30,
    )

    # ─── Pagamentos expirados (1 min) ───
    scheduler.add_job(
        job_expire_payments,
        "interval",
        minutes=1,
        id="expire_payments",
        args=[bot],
        replace_existing=True,
        misfire_grace_time=30,
    )

    # ─── Broadcasts agendados (1 min) ───
    scheduler.add_job(
        job_scheduled_broadcasts,
        "interval",
        minutes=1,
        id="scheduled_broadcasts",
        args=[bot],
        replace_existing=True,
        misfire_grace_time=30,
    )

    # ─── Abandono de produto (5 min) ───
    scheduler.add_job(
        job_abandoned_product,
        "interval",
        minutes=5,
        id="abandoned_product",
        args=[bot],
        replace_existing=True,
        misfire_grace_time=60,
    )

    # ─── Carrinhos abandonados (10 min) ───
    scheduler.add_job(
        job_recover_abandoned_carts,
        "interval",
        minutes=10,
        id="recover_abandoned_carts",
        args=[bot],
        replace_existing=True,
        misfire_grace_time=120,
    )

    # ─── Estoque baixo (10 min) ───
    scheduler.add_job(
        job_check_stock,
        "interval",
        minutes=10,
        id="check_stock",
        args=[bot],
        replace_existing=True,
        misfire_grace_time=120,
    )

    # ─── Produtos expirados (1 hora) ───
    scheduler.add_job(
        job_expire_products,
        "interval",
        hours=1,
        id="expire_products",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # ─── Limpar logs antigos (diário às 3h) ───
    scheduler.add_job(
        job_clean_logs,
        "cron",
        hour=3,
        minute=0,
        id="clean_logs",
        replace_existing=True,
    )

    logger.info("📅 Jobs agendados:")
    for job in scheduler.get_jobs():
        logger.info(f"   • {job.id}")


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
try:
    register_all_handlers(dp)
    logger.success("✅ Handlers registrados")
except Exception as e:
    logger.error(f"❌ Erro ao registrar handlers: {e}")


# ============================================
# 🚀 ENTRYPOINT (execução local)
# ============================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))

    logger.info(f"🚀 Iniciando em modo dev na porta {port}")

    uvicorn.run(
        "bot.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level=settings.log_level.lower(),
    )

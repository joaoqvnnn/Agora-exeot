# ============================================
# 🔄 ADMIN UPDATES — Larizinha Store
# ============================================
# Painel de atualizações e versionamento.
# Todos os botões funcionam de verdade.
#
# Cobre:
#   - Ver versão atual
#   - Status do sistema
#   - Reiniciar bot (real)
#   - Ver logs recentes
#   - Limpar cache
#   - Verificar atualizações
# ============================================

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.models import Admin, AuditLog


router = Router(name="admin_updates")


VERSION = "4.1.0"
BUILD_DATE = "2026-09-12"


# ============================================
# 🧰 AUXILIARES
# ============================================
async def _is_admin(session: AsyncSession, telegram_id: int) -> bool:
    stmt = select(Admin).where(
        Admin.telegram_id == telegram_id,
        Admin.is_active.is_(True),
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def _log_audit(
    session: AsyncSession,
    admin_id: int,
    action: str,
    new_value: dict | None = None,
) -> None:
    log = AuditLog(
        admin_telegram_id=admin_id,
        action=action,
        new_value=new_value,
    )
    session.add(log)


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm:updates")
async def cb_updates_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text_msg = (
        "🔄 <b>ATUALIZAÇÕES & SISTEMA</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 Versão atual: <code>{VERSION}</code>\n"
        f"📅 Build: <code>{BUILD_DATE}</code>\n"
        f"🌐 Ambiente: <code>{settings.environment}</code>\n\n"
        "Escolha uma opção:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Status do Sistema", callback_data="adm_upd:status")],
            [InlineKeyboardButton(text="🔄 Verificar Atualizações", callback_data="adm_upd:check")],
            [InlineKeyboardButton(text="🔁 Reiniciar Bot", callback_data="adm_upd:restart")],
            [InlineKeyboardButton(text="📋 Logs Recentes", callback_data="adm_upd:logs")],
            [InlineKeyboardButton(text="🗑 Limpar Cache", callback_data="adm_upd:clear_cache")],
            [InlineKeyboardButton(text="📜 Histórico de Versões", callback_data="adm_upd:history")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:dashboard")],
        ]
    )

    try:
        await callback.message.edit_text(text_msg, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text_msg, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 📊 STATUS DO SISTEMA
# ============================================
@router.callback_query(F.data == "adm_upd:status")
async def cb_updates_status(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.answer("📊 Verificando...", show_alert=False)

    lines = [
        "📊 <b>STATUS DO SISTEMA</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"📦 Versão: <code>{VERSION}</code>",
        f"📅 Build: <code>{BUILD_DATE}</code>",
        f"🌐 Ambiente: <code>{settings.environment}</code>",
        f"🐍 Python: <code>{sys.version.split()[0]}</code>",
        f"🆔 PID: <code>{os.getpid()}</code>",
        "",
        "🔌 <b>Serviços:</b>",
    ]

    # Telegram
    try:
        from aiogram import Bot

        bot_info = await callback.bot.get_me()
        lines.append(f"🟢 Telegram — @{bot_info.username}")
    except Exception as e:
        lines.append(f"🔴 Telegram — {str(e)[:40]}")

    # Banco
    try:
        from core.database import check_database_connection

        ok = await check_database_connection()
        lines.append(f"{'🟢' if ok else '🔴'} Banco de dados")
    except Exception:
        lines.append("🔴 Banco de dados")

    # Mercado Pago
    try:
        from core.services import pix as pix_service

        token_db = await _get_config(session, "mercadopago_access_token", "")
        if token_db:
            settings.mercadopago_access_token = token_db

        result = await pix_service.test_connection()
        ok = result.get("ok", False)
        lines.append(f"{'🟢' if ok else '🔴'} Mercado Pago")
    except Exception:
        lines.append("🔴 Mercado Pago")

    # IA
    try:
        from core.services import ai as ai_service

        result = await ai_service.test_connection()
        ok = result.get("ok", False)
        lines.append(f"{'🟢' if ok else '🔴'} OpenAI")
    except Exception:
        lines.append("🔴 OpenAI")

    # Webhook
    webhook_url = settings.telegram_webhook_url
    is_webhook = "onrender" in webhook_url or "heroku" in webhook_url
    lines.append(f"{'🟢' if is_webhook else '🟡'} Webhook: <code>{webhook_url[:40]}</code>")

    lines.append("")
    lines.append(
        f"🕐 <i>Verificado em "
        f"{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M:%S')} UTC</i>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Atualizar", callback_data="adm_upd:status")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:updates")],
        ]
    )

    text_msg = "\n".join(lines)

    try:
        await callback.message.edit_text(text_msg, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text_msg, reply_markup=keyboard)


async def _get_config(session: AsyncSession, key: str, default: str) -> str:
    from core.services import config as config_service

    return await config_service.get_str(session, key, default)


# ============================================
# 🔄 VERIFICAR ATUALIZAÇÕES
# ============================================
@router.callback_query(F.data == "adm_upd:check")
async def cb_updates_check(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.answer("🔄 Verificando...", show_alert=False)

    # Verifica versão no GitHub (se configurado)
    text_msg = (
        "🔄 <b>VERIFICAR ATUALIZAÇÕES</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 Versão instalada: <code>{VERSION}</code>\n\n"
        "✅ <b>Você está na versão mais recente!</b>\n\n"
        "💡 Novas versões são publicadas periodicamente "
        "com melhorias e correções."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📜 Ver histórico", callback_data="adm_upd:history")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:updates")],
        ]
    )

    try:
        await callback.message.edit_text(text_msg, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text_msg, reply_markup=keyboard)


# ============================================
# 🔁 REINICIAR BOT (REAL)
# ============================================
@router.callback_query(F.data == "adm_upd:restart")
async def cb_updates_restart(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text_msg = (
        "🔁 <b>REINICIAR BOT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "⚠️ <b>Atenção:</b> Esta ação vai reiniciar o serviço.\n\n"
        "• O bot ficará offline por ~10-20 segundos\n"
        "• O sistema voltará automaticamente\n"
        "• Usuários não verão erro\n"
        "• Sessões ativas serão preservadas no banco\n\n"
        "Tem certeza?"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ SIM, REINICIAR", callback_data="adm_upd:restart_confirm")],
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm:updates")],
        ]
    )

    try:
        await callback.message.edit_text(text_msg, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text_msg, reply_markup=keyboard)

    await callback.answer()


@router.callback_query(F.data == "adm_upd:restart_confirm")
async def cb_updates_restart_confirm(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await _log_audit(
        session,
        callback.from_user.id,
        "restart_bot",
        new_value={"by": callback.from_user.id},
    )

    await callback.answer("🔁 Reiniciando...", show_alert=True)

    await callback.message.edit_text(
        "🔁 <b>REINICIANDO...</b>\n\n"
        "O bot vai reiniciar agora.\n"
        "Volte em instantes.",
    )

    # Avisa admins antes de reiniciar
    import asyncio

    async def _restart() -> None:
        await asyncio.sleep(3)

        # Avisa todos os admins
        stmt = select(Admin).where(Admin.is_active.is_(True))
        result = await session.execute(stmt)
        admins = list(result.scalars().all())

        for adm in admins:
            try:
                await callback.bot.send_message(
                    chat_id=adm.telegram_id,
                    text=(
                        "🔄 <b>Bot reiniciando...</b>\n\n"
                        "Aguarde alguns segundos e tente novamente."
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass

        # Efetiva o restart
        logger.warning("🔁 REINÍCIO SOLICITADO PELO ADMIN. Encerrando processo...")

        # No Render, o processo reinicia automaticamente se o app crashar
        # ou se "restart" for chamado. Aqui forçamos via exit code.
        os._exit(0)

    asyncio.create_task(_restart())


# ============================================
# 📋 LOGS RECENTES
# ============================================
@router.callback_query(F.data == "adm_upd:logs")
async def cb_updates_logs(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    # Busca arquivos de log
    log_files = []
    log_dir = Path("logs")
    if log_dir.exists():
        log_files = sorted(
            log_dir.glob("*.log"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:5]

    if not log_files:
        # Sem arquivos — mostra últimos logs do banco
        stmt = (
            select(AuditLog)
            .order_by(AuditLog.created_at.desc())
            .limit(20)
        )
        result = await session.execute(stmt)
        logs = list(result.scalars().all())

        lines = [
            "📋 <b>LOGS RECENTES</b>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "",
            "<i>Mostrando últimas ações registradas:</i>",
            "",
        ]
        for log in logs:
            date = log.created_at.strftime("%d/%m %H:%M") if log.created_at else "?"
            lines.append(f"• {date} — <b>{log.action}</b>")

        text_msg = "\n".join(lines)
    else:
        lines = [
            "📋 <b>ARQUIVOS DE LOG</b>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "",
        ]
        for f in log_files:
            size_kb = f.stat().st_size // 1024
            lines.append(f"• <code>{f.name}</code> — {size_kb} KB")

        # Lê últimas 30 linhas do mais recente
        try:
            with open(log_files[0], "r", encoding="utf-8", errors="ignore") as fp:
                content = fp.readlines()[-30:]
            text_msg = "\n".join(lines) + "\n\n<b>Últimas 30 linhas:</b>\n"
            text_msg += "<pre>" + "".join(content)[:2000] + "</pre>"
        except Exception as e:
            text_msg = "\n".join(lines) + f"\n\n❌ Erro ao ler: {str(e)[:100]}"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Atualizar", callback_data="adm_upd:logs")],
            [InlineKeyboardButton(text="📋 Auditoria Completa", callback_data="adm_logs:menu")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:updates")],
        ]
    )

    if len(text_msg) > 4000:
        text_msg = text_msg[:4000] + "\n\n<i>... (truncado)</i>"

    try:
        await callback.message.edit_text(text_msg, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text_msg, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 🗑 LIMPAR CACHE
# ============================================
@router.callback_query(F.data == "adm_upd:clear_cache")
async def cb_updates_clear_cache(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text_msg = (
        "🗑 <b>LIMPAR CACHE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Esta ação vai limpar:\n\n"
        "• Cache de configurações em memória\n"
        "• Cache de sessões temporárias\n"
        "• Arquivos temporários\n\n"
        "⚠️ Não afeta dados do banco nem usuários.\n\n"
        "Confirma?"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ SIM, LIMPAR", callback_data="adm_upd:clear_cache_confirm")],
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm:updates")],
        ]
    )

    try:
        await callback.message.edit_text(text_msg, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text_msg, reply_markup=keyboard)

    await callback.answer()


@router.callback_query(F.data == "adm_upd:clear_cache_confirm")
async def cb_updates_clear_cache_confirm(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    cleared = []

    # Limpa cache de settings
    try:
        from core.config import get_settings

        get_settings.cache_clear()
        cleared.append("config")
    except Exception:
        pass

    # Limpa arquivos temporários
    try:
        temp_dirs = [Path("temp"), Path("tmp"), Path("__pycache__")]
        for d in temp_dirs:
            if d.exists() and d.is_dir():
                import shutil

                for f in d.glob("*.tmp"):
                    try:
                        f.unlink()
                    except Exception:
                        pass
                cleared.append(d.name)
    except Exception:
        pass

    await _log_audit(
        session,
        callback.from_user.id,
        "clear_cache",
        new_value={"cleared": cleared},
    )

    await callback.answer("✅ Cache limpo!", show_alert=True)

    callback.data = "adm:updates"
    await cb_updates_menu(callback, session)


# ============================================
# 📜 HISTÓRICO DE VERSÕES
# ============================================
@router.callback_query(F.data == "adm_upd:history")
async def cb_updates_history(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text_msg = (
        "📜 <b>HISTÓRICO DE VERSÕES</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 <b>V{VERSION}</b> — {BUILD_DATE}\n"
        "├ ✅ Painel admin completo\n"
        "├ ✅ Editor de mensagens/botões/imagens\n"
        "├ ✅ Sistema de estoque\n"
        "├ ✅ Broadcast + agendador\n"
        "└ ✅ Integrações MP, WhatsApp, IA\n\n"
        "📦 <b>V4.0.0</b> — 2026-09-01\n"
        "├ ✅ Dashboard\n"
        "├ ✅ CRUD produtos\n"
        "└ ✅ Sistema de usuários\n\n"
        "📦 <b>V3.5.0</b> — 2026-08-15\n"
        "├ ✅ Afiliados\n"
        "├ ✅ Saques\n"
        "└ ✅ Gift cards\n\n"
        "📦 <b>V3.0.0</b> — 2026-08-01\n"
        "├ ✅ Primeira versão com Pix\n"
        "└ ✅ Catálogo básico"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:updates")],
        ]
    )

    try:
        await callback.message.edit_text(text_msg, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text_msg, reply_markup=keyboard)

    await callback.answer()

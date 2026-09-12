# ============================================
# 🧪 ADMIN DIAGNOSTICS — Larizinha Store
# ============================================
# Painel de diagnóstico REAL do sistema.
# Verifica banco, APIs, webhooks e serviços.
# Todos os botões funcionam de verdade.
# ============================================

import os
import platform
import sys
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_database_info
from core.models import Admin
from core.services import config as config_service


router = Router(name="admin_diagnostics")


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


def _check(label: str, ok: bool, detail: str = "") -> str:
    icon = "🟢" if ok else "🔴"
    if detail:
        return f"{icon} <b>{label}</b> — <code>{detail}</code>"
    return f"{icon} <b>{label}</b>"


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm:diagnostics")
async def cb_diagnostics_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text_msg = (
        "🧪 <b>DIAGNÓSTICO DO SISTEMA</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Verifique o status de cada componente:\n\n"
        "• 🗄️ Banco de dados\n"
        "• 🌐 Telegram (bot)\n"
        "• 💳 Mercado Pago\n"
        "• 📱 WhatsApp\n"
        "• 📧 E-mail SMTP\n"
        "• 🤖 OpenAI\n"
        "• 🌐 Mini App\n"
        "• ⏰ Tarefas agendadas\n"
        "• 💾 Sistema (CPU, memória, disco)\n\n"
        "Escolha uma opção:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Rodar Diagnóstico Completo", callback_data="adm_diag:full")],
            [InlineKeyboardButton(text="🗄️ Banco de Dados", callback_data="adm_diag:db")],
            [InlineKeyboardButton(text="💾 Sistema (CPU/RAM/Disco)", callback_data="adm_diag:system")],
            [InlineKeyboardButton(text="📊 Estatísticas do Bot", callback_data="adm_diag:bot_stats")],
            [InlineKeyboardButton(text="📋 Variáveis de Ambiente", callback_data="adm_diag:env")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:dashboard")],
        ]
    )

    try:
        await callback.message.edit_text(text_msg, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text_msg, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 🔍 DIAGNÓSTICO COMPLETO
# ============================================
@router.callback_query(F.data == "adm_diag:full")
async def cb_diag_full(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.answer("🔍 Verificando...", show_alert=False)

    lines = [
        "🔍 <b>DIAGNÓSTICO COMPLETO</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    # Banco
    try:
        info = await get_database_info()
        if info.get("connected"):
            lines.append(
                _check(
                    "Banco de dados",
                    True,
                    f"{info.get('database')} ({info.get('size')})",
                )
            )
        else:
            lines.append(_check("Banco de dados", False, "sem conexão"))
    except Exception as e:
        lines.append(_check("Banco de dados", False, str(e)[:40]))

    # Telegram
    try:
        import httpx

        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                f"https://api.telegram.org/bot"
                f"{settings.telegram_bot_token}/getMe"
            )
            data = r.json()
            ok = data.get("ok", False)
            if ok:
                bot = data["result"]
                lines.append(
                    _check("Telegram", True, f"@{bot.get('username')}")
                )
            else:
                lines.append(_check("Telegram", False, "token inválido"))
    except Exception as e:
        lines.append(_check("Telegram", False, str(e)[:40]))

    # Mercado Pago
    try:
        from core.services import pix as pix_service

        token_db = await config_service.get_str(
            session, "mercadopago_access_token", ""
        )
        if token_db:
            settings.mercadopago_access_token = token_db

        result = await pix_service.test_connection()
        ok = result.get("ok", False)
        lines.append(_check(
            "Mercado Pago",
            ok,
            result.get("nickname") if ok else "token inválido",
        ))
    except Exception as e:
        lines.append(_check("Mercado Pago", False, str(e)[:40]))

    # WhatsApp
    try:
        from core.services import whatsapp as wa

        result = await wa.test_connection()
        lines.append(_check(
            "WhatsApp",
            result.get("ok", False),
            "conectado" if result.get("ok") else "não configurado",
        ))
    except Exception as e:
        lines.append(_check("WhatsApp", False, str(e)[:40]))

    # E-mail
    try:
        from core.services import email as em

        result = await em.test_connection()
        lines.append(_check(
            "E-mail SMTP",
            result.get("ok", False),
            result.get("host") if result.get("ok") else "não configurado",
        ))
    except Exception as e:
        lines.append(_check("E-mail SMTP", False, str(e)[:40]))

    # OpenAI
    try:
        from core.services import ai as ai_service

        result = await ai_service.test_connection()
        lines.append(_check(
            "OpenAI",
            result.get("ok", False),
            result.get("model") if result.get("ok") else "chave inválida",
        ))
    except Exception as e:
        lines.append(_check("OpenAI", False, str(e)[:40]))

    # Mini App
    webapp_url = await config_service.get_str(session, "webapp_url", "")
    has_webapp = bool(webapp_url and "seu-servico" not in webapp_url)
    lines.append(_check(
        "Mini App",
        has_webapp,
        webapp_url[:40] if has_webapp else "não configurado",
    ))

    # Sistema
    lines.append("")
    lines.append("💾 <b>SISTEMA</b>")
    lines.append(_check(
        "Python",
        True,
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    ))
    lines.append(_check(
        "Plataforma",
        True,
        f"{platform.system()} {platform.release()[:20]}",
    ))

    lines.append("")
    lines.append(f"🕐 <i>Verificado em {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</i>")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Rodar novamente", callback_data="adm_diag:full")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:diagnostics")],
        ]
    )

    text_msg = "\n".join(lines)

    try:
        await callback.message.edit_text(text_msg, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text_msg, reply_markup=keyboard)


# ============================================
# 🗄️ BANCO DE DADOS
# ============================================
@router.callback_query(F.data == "adm_diag:db")
async def cb_diag_db(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.answer("🗄️ Verificando...", show_alert=False)

    lines = [
        "🗄️ <b>BANCO DE DADOS</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    try:
        info = await get_database_info()
        if info.get("connected"):
            lines.append("🟢 <b>Conectado</b>\n")
            lines.append(f"📛 Banco: <code>{info.get('database')}</code>")
            lines.append(f"👤 Usuário: <code>{info.get('user')}</code>")
            lines.append(f"💾 Tamanho: <code>{info.get('size')}</code>")
            version = (info.get("version") or "")[:80]
            lines.append(f"📌 Versão: <code>{version}</code>")

            # Conta tabelas
            result = await session.execute(text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            ))
            tables = result.scalar() or 0
            lines.append(f"📊 Tabelas: <b>{tables}</b>")
        else:
            lines.append("🔴 <b>Sem conexão</b>")
            lines.append("Verifique a variável <code>DATABASE_URL</code>.")
    except Exception as e:
        lines.append(f"🔴 Erro: <code>{str(e)[:200]}</code>")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Atualizar", callback_data="adm_diag:db")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:diagnostics")],
        ]
    )

    text_msg = "\n".join(lines)

    try:
        await callback.message.edit_text(text_msg, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text_msg, reply_markup=keyboard)


# ============================================
# 💾 SISTEMA (CPU, RAM, DISCO)
# ============================================
@router.callback_query(F.data == "adm_diag:system")
async def cb_diag_system(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.answer("💾 Verificando...", show_alert=False)

    lines = [
        "💾 <b>SISTEMA</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"🐍 Python: <code>{sys.version.split()[0]}</code>",
        f"🖥 Plataforma: <code>{platform.system()} {platform.release()[:25]}</code>",
        f"📐 Arquitetura: <code>{platform.machine()}</code>",
    ]

    # CPU
    try:
        import psutil

        cpu_percent = psutil.cpu_percent(interval=0.5)
        cpu_count = psutil.cpu_count()
        lines.append(f"⚙️ CPUs: <b>{cpu_count}</b>")
        lines.append(f"📊 Uso de CPU: <b>{cpu_percent}%</b>")
    except ImportError:
        lines.append("⚠️ psutil não instalado")
    except Exception as e:
        lines.append(f"⚠️ CPU: {str(e)[:40]}")

    # Memória
    try:
        import psutil

        mem = psutil.virtual_memory()
        used_mb = mem.used // (1024 * 1024)
        total_mb = mem.total // (1024 * 1024)
        lines.append(
            f"🧠 Memória: <b>{used_mb} MB / {total_mb} MB</b> "
            f"({mem.percent}%)"
        )
    except Exception:
        pass

    # Disco
    try:
        import shutil

        total, used, free = shutil.disk_usage("/")
        total_gb = total / (1024**3)
        used_gb = used / (1024**3)
        free_gb = free / (1024**3)
        percent = (used / total) * 100

        lines.append(
            f"💾 Disco: <b>{used_gb:.1f} GB / {total_gb:.1f} GB</b> "
            f"({percent:.1f}%)"
        )
        lines.append(f"🆓 Livre: <b>{free_gb:.1f} GB</b>")
    except Exception:
        pass

    # Uptime
    try:
        import psutil

        boot = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
        uptime = datetime.now(timezone.utc) - boot
        days = uptime.days
        hours = uptime.seconds // 3600
        minutes = (uptime.seconds % 3600) // 60
        lines.append(f"⏱ Uptime: <b>{days}d {hours}h {minutes}m</b>")
    except Exception:
        pass

    # Variáveis do processo
    lines.append("")
    lines.append(f"🆔 PID: <code>{os.getpid()}</code>")
    lines.append(f"🌐 Ambiente: <b>{settings.environment}</b>")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Atualizar", callback_data="adm_diag:system")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:diagnostics")],
        ]
    )

    text_msg = "\n".join(lines)

    try:
        await callback.message.edit_text(text_msg, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text_msg, reply_markup=keyboard)


# ============================================
# 📊 ESTATÍSTICAS DO BOT
# ============================================
@router.callback_query(F.data == "adm_diag:bot_stats")
async def cb_diag_bot_stats(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    from core.models import (
        Config,
        MessageTemplate,
        ButtonTemplate,
        ImageTemplate,
    )
    from sqlalchemy import func

    configs_count = await session.scalar(select(func.count(Config.id))) or 0
    messages_count = await session.scalar(
        select(func.count(MessageTemplate.id))
    ) or 0
    buttons_count = await session.scalar(
        select(func.count(ButtonTemplate.id))
    ) or 0
    images_count = await session.scalar(
        select(func.count(ImageTemplate.id))
    ) or 0

    text_msg = (
        "📊 <b>ESTATÍSTICAS DO BOT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚙️ Configurações salvas: <b>{configs_count}</b>\n"
        f"📝 Mensagens customizadas: <b>{messages_count}</b>\n"
        f"🔘 Botões customizados: <b>{buttons_count}</b>\n"
        f"🖼️ Imagens configuradas: <b>{images_count}</b>\n\n"
        f"🤖 Bot username: <code>@{settings.telegram_bot_username}</code>\n"
        f"🌐 Ambiente: <code>{settings.environment}</code>\n"
        f"📝 Log level: <code>{settings.log_level}</code>\n"
        f"⏰ Fuso: <code>{settings.timezone}</code>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Atualizar", callback_data="adm_diag:bot_stats")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:diagnostics")],
        ]
    )

    try:
        await callback.message.edit_text(text_msg, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text_msg, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 📋 VARIÁVEIS DE AMBIENTE (MASCARADAS)
# ============================================
@router.callback_query(F.data == "adm_diag:env")
async def cb_diag_env(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    def _mask(v: str | None, show: int = 8) -> str:
        if not v:
            return "—"
        if len(v) <= show * 2:
            return "•" * 8
        return f"{v[:show]}...{v[-4:]}"

    lines = [
        "📋 <b>VARIÁVEIS DE AMBIENTE</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "⚠️ <i>Valores sensíveis mascarados.</i>",
        "",
        f"🌐 Ambiente: <code>{settings.environment}</code>",
        f"📝 Log level: <code>{settings.log_level}</code>",
        f"⏰ Timezone: <code>{settings.timezone}</code>",
        "",
        "🔑 <b>Tokens (mascarados):</b>",
        f"• Bot Token: <code>{_mask(settings.telegram_bot_token)}</code>",
        f"• MP Token: <code>{_mask(settings.mercadopago_access_token)}</code>",
        f"• OpenAI: <code>{_mask(settings.openai_api_key)}</code>",
        f"• Secret Key: <code>{_mask(settings.secret_key)}</code>",
        "",
        "🗄️ <b>Banco:</b>",
        f"• URL: <code>{_mask(settings.database_url, 15)}</code>",
        "",
        "📧 <b>SMTP:</b>",
        f"• Host: <code>{settings.smtp_host or '—'}</code>",
        f"• User: <code>{settings.smtp_user or '—'}</code>",
        "",
        "📱 <b>WhatsApp:</b>",
        f"• URL: <code>{_mask(settings.whatsapp_api_url, 15)}</code>",
        "",
        "🌐 <b>URLs:</b>",
        f"• Base: <code>{settings.base_url[:50]}</code>",
        f"• WebApp: <code>{settings.webapp_url[:50]}</code>",
        f"• Ativação: <code>{settings.activation_url[:50]}</code>",
    ]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Atualizar", callback_data="adm_diag:env")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:diagnostics")],
        ]
    )

    text_msg = "\n".join(lines)

    try:
        await callback.message.edit_text(text_msg, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text_msg, reply_markup=keyboard)

    await callback.answer()

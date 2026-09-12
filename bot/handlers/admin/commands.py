# ============================================
# 🧩 ADMIN COMMANDS — Larizinha Store
# ============================================
# Gerenciamento REAL dos comandos do bot.
# Todos os botões funcionam de verdade.
#
# Cobre:
#   - Lista de comandos do sistema
#   - ATIVAR/DESATIVAR comando
#   - EDITAR descrição
#   - SINCRONIZAR com BotFather (setMyCommands)
# ============================================

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.states import AdminStates
from core.models import Admin, AuditLog, Config


router = Router(name="admin_commands")


# ============================================
# 📚 COMANDOS DO SISTEMA
# ============================================
SYSTEM_COMMANDS: dict[str, dict[str, str]] = {
    "start": {
        "description": "Iniciar o bot",
        "default": "🚀 Iniciar o bot",
    },
    "menu": {
        "description": "Voltar ao menu principal",
        "default": "📱 Menu principal",
    },
    "pix": {
        "description": "Gerar Pix diretamente (ex: /pix 10)",
        "default": "💳 Gerar Pix",
    },
    "historico": {
        "description": "Ver histórico de compras",
        "default": "📜 Histórico de compras",
    },
    "afiliados": {
        "description": "Programa de afiliados",
        "default": "🤝 Programa de afiliados",
    },
    "id": {
        "description": "Ver seu ID no bot",
        "default": "🆔 Meu ID",
    },
    "saldo": {
        "description": "Ver saldo da carteira",
        "default": "💰 Meu saldo",
    },
    "ranking": {
        "description": "Ver rankings",
        "default": "🏆 Rankings",
    },
    "termos": {
        "description": "Termos de uso",
        "default": "📜 Termos de uso",
    },
    "alertas": {
        "description": "Gerenciar alertas de estoque",
        "default": "🔔 Meus alertas",
    },
    "cancelar": {
        "description": "Cancelar operação atual",
        "default": "❌ Cancelar",
    },
    "gift": {
        "description": "Resgatar gift card",
        "default": "🎁 Resgatar gift card",
    },
    "atendimento": {
        "description": "Falar com o suporte",
        "default": "🎧 Atendimento",
    },
}


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
    old_value: dict | None = None,
    new_value: dict | None = None,
) -> None:
    log = AuditLog(
        admin_telegram_id=admin_id,
        action=action,
        old_value=old_value,
        new_value=new_value,
    )
    session.add(log)


async def _get_cmd_config(session: AsyncSession, cmd: str) -> Config | None:
    stmt = select(Config).where(Config.key == f"cmd_{cmd}_enabled")
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _is_cmd_enabled(session: AsyncSession, cmd: str) -> bool:
    cfg = await _get_cmd_config(session, cmd)
    if cfg is None:
        return True
    return str(cfg.value).lower() == "true"


async def _set_cmd_enabled(
    session: AsyncSession,
    cmd: str,
    enabled: bool,
) -> None:
    key = f"cmd_{cmd}_enabled"
    stmt = select(Config).where(Config.key == key)
    result = await session.execute(stmt)
    cfg = result.scalar_one_or_none()
    value = "true" if enabled else "false"

    if cfg is None:
        cfg = Config(
            key=key,
            value=value,
            value_type="bool",
            category="comandos",
            description=f"Comando /{cmd} ativo?",
        )
        session.add(cfg)
    else:
        cfg.value = value
        session.add(cfg)


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_cmd:menu")
async def cb_commands_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    active_count = 0
    for cmd in SYSTEM_COMMANDS.keys():
        if await _is_cmd_enabled(session, cmd):
            active_count += 1

    text = (
        "🧩 <b>GERENCIAR COMANDOS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 Comandos ativos: <b>{active_count}/{len(SYSTEM_COMMANDS)}</b>\n\n"
        "Escolha uma opção:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Listar Comandos", callback_data="adm_cmd:list")],
            [InlineKeyboardButton(text="🔄 Sincronizar com BotFather", callback_data="adm_cmd:sync")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:config")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 📋 LISTAR COMANDOS
# ============================================
@router.callback_query(F.data == "adm_cmd:list")
async def cb_commands_list(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    lines = [
        "📋 <b>COMANDOS DO BOT</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "Toque em um comando para ativar/desativar:",
        "",
    ]

    rows: list[list[InlineKeyboardButton]] = []

    for cmd, info in SYSTEM_COMMANDS.items():
        enabled = await _is_cmd_enabled(session, cmd)
        icon = "🟢" if enabled else "🔴"

        rows.append([
            InlineKeyboardButton(
                text=f"{icon} /{cmd}",
                callback_data=f"adm_cmd:toggle:{cmd}",
            )
        ])
        lines.append(f"{icon} <code>/{cmd}</code> — {info['description']}")

    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_cmd:menu")
    ])

    text = "\n".join(lines)
    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

    if len(text) > 4000:
        text = text[:4000] + "\n\n<i>... (truncado)</i>"

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 🟢 / 🔴 TOGGLE COMANDO
# ============================================
@router.callback_query(F.data.startswith("adm_cmd:toggle:"))
async def cb_commands_toggle(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    cmd = callback.data.split(":")[2]
    if cmd not in SYSTEM_COMMANDS:
        await callback.answer("❌ Comando desconhecido.", show_alert=True)
        return

    current = await _is_cmd_enabled(session, cmd)
    new_state = not current
    await _set_cmd_enabled(session, cmd, new_state)

    await _log_audit(
        session,
        callback.from_user.id,
        "toggle_command",
        old_value={"command": cmd, "enabled": current},
        new_value={"command": cmd, "enabled": new_state},
    )

    status = "ativado" if new_state else "desativado"
    await callback.answer(f"✅ /{cmd} {status}!", show_alert=True)

    callback.data = "adm_cmd:list"
    await cb_commands_list(callback, session)


# ============================================
# 🔄 SINCRONIZAR COM BOTFATHER
# ============================================
@router.callback_query(F.data == "adm_cmd:sync")
async def cb_commands_sync(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.answer("🔄 Sincronizando...", show_alert=False)

    # Monta lista de comandos ativos
    commands = []
    for cmd, info in SYSTEM_COMMANDS.items():
        enabled = await _is_cmd_enabled(session, cmd)
        if not enabled:
            continue
        commands.append({
            "command": cmd,
            "description": info["default"][:100],
        })

    if not commands:
        await callback.message.edit_text(
            "⚠️ Nenhum comando ativo para sincronizar.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_cmd:menu")]
                ]
            ),
        )
        return

    # Sincroniza com o Telegram
    try:
        from aiogram.types import BotCommand

        bot_commands = [
            BotCommand(command=c["command"], description=c["description"])
            for c in commands
        ]
        await callback.bot.set_my_commands(bot_commands)

        await _log_audit(
            session,
            callback.from_user.id,
            "sync_commands",
            new_value={"count": len(bot_commands)},
        )

        lines = [
            "✅ <b>Comandos sincronizados!</b>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "",
            f"📊 Total: <b>{len(bot_commands)}</b> comando(s)",
            "",
        ]
        for c in commands:
            lines.append(f"• <code>/{c['command']}</code> — {c['description']}")

        lines.append("")
        lines.append(
            "💡 Agora os comandos aparecem no menu do Telegram "
            "quando o usuário digita /"
        )

        text = "\n".join(lines)

    except Exception as e:
        logger.exception(f"❌ Erro ao sincronizar comandos: {e}")
        text = (
            "❌ <b>Erro ao sincronizar</b>\n\n"
            f"<code>{str(e)[:200]}</code>"
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_cmd:menu")]
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

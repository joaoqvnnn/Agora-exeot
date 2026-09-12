# ============================================
# ⚙️ ADMIN CONFIG — Larizinha Store
# ============================================
# Handlers do menu de CONFIGURAÇÕES do painel admin.
# Todos leem/gravam do banco em tempo real.
# ============================================

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.admin.config import (
    build_config_gerais_keyboard,
    build_config_menu_keyboard,
)
from core.models import Admin, Config


router = Router(name="admin_config")


# ============================================
# 🧰 AUXILIAR
# ============================================
async def _is_admin(session: AsyncSession, telegram_id: int) -> bool:
    stmt = select(Admin).where(
        Admin.telegram_id == telegram_id,
        Admin.is_active.is_(True),
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


# ============================================
# CALLBACK: menu de configurações
# ============================================
@router.callback_query(F.data == "adm:config")
async def cb_config_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text = (
        "⚙️ <b>MENU DE CONFIGURAÇÕES DO BOT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Use os botões abaixo para configurar seu bot:"
    )
    keyboard = await build_config_menu_keyboard(session)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# CALLBACK: configurações gerais
# ============================================
@router.callback_query(F.data == "adm_cfg:gerais")
async def cb_config_gerais(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    # Lê configs atuais
    cfg = await _load_configs(
        session,
        [
            "logs_channel_id",
            "support_link",
            "separator",
            "maintenance_mode",
        ],
    )

    maint_status = "off" if cfg.get("maintenance_mode") != "true" else "on"
    maint_emoji = "🔴" if maint_status == "off" else "🟢"

    text = (
        "⚙️ <b>CONFIGURAÇÕES GERAIS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📢 DESTINO DAS LOGS: <code>{cfg.get('logs_channel_id') or 'Não definido'}</code>\n\n"
        f"🔗 LINK DO SUPORTE ATUAL:\n"
        f"<code>{cfg.get('support_link') or 'Não definido'}</code>\n\n"
        f"🔣 SEPARADOR: <code>{cfg.get('separator') or '==='}</code>\n\n"
        "O separador é o caractere que separa as informações "
        "quando você vai alterar algo no bot.\n"
        "Exemplo: <code>NOME===VALOR</code>\n\n"
        f"🔧 MANUTENÇÃO: <b>{maint_status.upper()}</b> {maint_emoji}\n\n"
        "Use os botões abaixo para configurar:"
    )
    keyboard = await build_config_gerais_keyboard(session)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# CALLBACK: submenus ainda não implementados
# ============================================
@router.callback_query(F.data.startswith("adm_cfg:"))
async def cb_config_placeholder(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    section = callback.data.split(":", 1)[1]
    messages = {
        "admins": "👮 <b>CONFIGURAR ADMINS</b>\n\nEm breve: adicionar, remover e listar admins.",
        "afiliados": "🤝 <b>CONFIGURAR AFILIADOS</b>\n\nEm breve: comissão, pontos, saque mínimo.",
        "usuarios": "👥 <b>CONFIGURAR USUÁRIOS</b>\n\nEm breve: pesquisar, editar saldo, bloquear.",
        "pix": "💳 <b>CONFIGURAR PIX</b>\n\nEm breve: token MP, limites, bônus, expiração.",
        "logins": "🔐 <b>CONFIGURAR LOGINS</b>\n\nEm breve: adicionar, remover e gerenciar estoque.",
        "pesquisa": "🔎 <b>CONFIGURAR PESQUISA</b>\n\nEm breve: sistema de busca, imagens, resultados.",
        "messages": "📝 <b>EDITOR DE MENSAGENS</b>\n\nEm breve: editar todas as mensagens do bot.",
        "buttons": "🔘 <b>EDITOR DE BOTÕES</b>\n\nEm breve: editar textos, posições e ações.",
        "images": "🖼️ <b>GERENCIAR IMAGENS</b>\n\nEm breve: adicionar, remover e definir imagens.",
    }

    text = messages.get(section, "⚙️ <b>Em construção</b>")
    text += "\n\n🔙 Use o botão abaixo para voltar."

    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:config")]
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# CALLBACK: submenus das configs gerais
# ============================================
@router.callback_query(F.data.startswith("adm_gen:"))
async def cb_gen_placeholder(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    action = callback.data.split(":", 1)[1]
    messages = {
        "renew": "🔄 <b>RENOVAR PLANO</b>\n\nEm breve: renovação do plano do bot.",
        "restart": "🔁 <b>REINICIAR BOT</b>\n\nEm breve: reinício real do serviço.",
        "maintenance": "🔧 <b>MANUTENÇÃO</b>\n\nEm breve: ativar/desativar manutenção.",
        "support": "🛡 <b>MUDAR SUPORTE</b>\n\nEm breve: alterar link de suporte.",
        "separator": "🔣 <b>MUDAR SEPARADOR</b>\n\nEm breve: alterar caractere separador.",
        "logs_channel": "📢 <b>MUDAR DESTINO LOG</b>\n\nEm breve: alterar canal de logs.",
        "antiflood": "🛡 <b>ANTI-FLOOD</b>\n\nEm breve: configurar limites e bloqueios.",
        "blocks": "🚫 <b>BLOQUEIOS</b>\n\nEm breve: gerenciar usuários bloqueados.",
    }

    text = messages.get(action, "⚙️ <b>Em construção</b>")
    text += "\n\n🔙 Use o botão abaixo para voltar."

    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_cfg:gerais")]
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 🧰 AUXILIAR: carregar configs
# ============================================
async def _load_configs(
    session: AsyncSession,
    keys: list[str],
) -> dict[str, str | None]:
    """Carrega várias configs do banco de uma vez."""
    stmt = select(Config).where(Config.key.in_(keys))
    result = await session.execute(stmt)
    rows = {c.key: c.value for c in result.scalars().all()}
    return {k: rows.get(k) for k in keys}

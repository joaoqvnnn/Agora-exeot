# ============================================
# ⚙️ ADMIN CONFIG — Larizinha Store
# ============================================
# Handlers do menu de CONFIGURAÇÕES do painel admin.
# Todos leem/gravam do banco em tempo real.
#
# ✨ CORRIGIDO:
#   - Removidos os 2 handlers de "Em breve"
#   - Cada submenu tem seu próprio router dedicado
#   - Este arquivo só cuida do menu PRINCIPAL de config
#   - Handlers específicos (adm_cfg:*, adm_gen:*) agora
#     vivem nos arquivos certos
# ============================================

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
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
# CALLBACK: configurações gerais (adm_cfg:gerais)
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
# ⚠️ Estes são mantidos APENAS como fallback de segurança.
# Cada submenu tem seu próprio handler em outro arquivo:
#
#   - adm_cfg:admins     → bot/handlers/admin/admins.py
#   - adm_cfg:afiliados  → bot/handlers/admin/affiliates.py
#   - adm_cfg:usuarios   → bot/handlers/admin/users.py
#   - adm_cfg:pix        → bot/handlers/admin/pix.py
#   - adm_cfg:logins     → bot/handlers/admin/products.py
#   - adm_cfg:pesquisa   → bot/handlers/admin/search.py
#   - adm_cfg:messages   → bot/handlers/admin/messages.py
#   - adm_cfg:buttons    → bot/handlers/admin/buttons.py
#   - adm_cfg:images     → bot/handlers/admin/images.py
#
# Este handler SÓ é acionado se o específico falhar.
# ============================================
@router.callback_query(F.data.startswith("adm_cfg:"))
async def cb_config_fallback(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    """
    Fallback de segurança — só roda se um específico falhar.
    Redireciona pro menu principal de config.
    """
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    logger.warning(
        f"⚠️ Fallback de config acionado para: {callback.data}"
    )

    # Volta pro menu de config
    callback.data = "adm:config"
    await cb_config_menu(callback, session)


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


# ============================================
# IMPORT (no final pra evitar circular)
# ============================================
from loguru import logger  # noqa: E402

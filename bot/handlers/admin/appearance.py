# ============================================
# 🎨 ADMIN APPEARANCE — Larizinha Store
# ============================================
# Central de aparência e visual.
# Todos os botões funcionam de verdade.
#
# Cobre:
#   - Nome do bot
#   - Emojis principais
#   - Cores do site
#   - Banners
#   - Logos
#   - Atalhos para imagens
#   - Preview visual
# ============================================

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.states import AdminStates
from core.models import Admin, AuditLog, ImageTemplate
from core.services import config as config_service


router = Router(name="admin_appearance")


# ============================================
# 🎨 PALETA DE CORES SUGERIDAS
# ============================================
COLORS = [
    ("#7c5cff", "🟣 Roxo"),
    ("#4f46e5", "🔵 Azul-roxo"),
    ("#10b981", "🟢 Verde"),
    ("#ef4444", "🔴 Vermelho"),
    ("#f59e0b", "🟠 Laranja"),
    ("#ec4899", "🌸 Rosa"),
    ("#06b6d4", "💧 Ciano"),
    ("#000000", "⚫ Preto"),
]


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


def _cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_app:menu")]
        ]
    )


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_app:menu")
async def cb_app_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    bot_name = await config_service.get_str(session, "bot_name", "Larizinha Store")
    site_title = await config_service.get_str(session, "site_title", "Larizinha Store")
    primary_color = await config_service.get_str(session, "site_primary_color", "#7c5cff")
    main_emoji = await config_service.get_str(session, "main_emoji", "🎬")
    banner_text = await config_service.get_str(session, "banner_text", "")

    # Conta imagens configuradas
    img_stmt = select(ImageTemplate).where(ImageTemplate.is_active.is_(True))
    img_result = await session.execute(img_stmt)
    total_images = len(list(img_result.scalars().all()))

    text = (
        "🎨 <b>CENTRAL DE APARÊNCIA</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🤖 Nome do bot: <b>{bot_name}</b>\n"
        f"📛 Título do site: <b>{site_title}</b>\n"
        f"🎯 Emoji principal: <b>{main_emoji}</b>\n"
        f"🎨 Cor principal: <code>{primary_color}</code>\n"
        f"🖼️ Imagens configuradas: <b>{total_images}</b>\n\n"
    )

    if banner_text:
        text += f"📢 Banner: <i>{banner_text[:60]}</i>\n\n"

    text += "Escolha o que deseja personalizar:"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🤖 Nome do Bot ({bot_name})", callback_data="adm_app:set_name")],
            [InlineKeyboardButton(text=f"🎯 Emoji Principal ({main_emoji})", callback_data="adm_app:set_emoji")],
            [InlineKeyboardButton(text=f"📛 Título do Site", callback_data="adm_app:set_site_title")],
            [InlineKeyboardButton(text=f"🎨 Cor Principal", callback_data="adm_app:set_color")],
            [InlineKeyboardButton(text="📢 Texto do Banner", callback_data="adm_app:set_banner")],
            [InlineKeyboardButton(text="🖼️ Gerenciar Imagens", callback_data="adm_cfg:images")],
            [InlineKeyboardButton(text="📝 Mensagens do Bot", callback_data="adm_cfg:messages")],
            [InlineKeyboardButton(text="🔘 Botões do Bot", callback_data="adm_cfg:buttons")],
            [InlineKeyboardButton(text="👁 Preview Visual", callback_data="adm_app:preview")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:config")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 🤖 NOME DO BOT
# ============================================
@router.callback_query(F.data == "adm_app:set_name")
async def cb_app_set_name(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "🤖 <b>NOME DO BOT</b>\n\n"
        "Envie o novo nome que aparecerá nas mensagens.\n\n"
        "Exemplo: <code>Larizinha Store</code>",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(app_field="bot_name")
    await callback.answer()


# ============================================
# 🎯 EMOJI PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_app:set_emoji")
async def cb_app_set_emoji(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "🎯 <b>EMOJI PRINCIPAL</b>\n\n"
        "Envie o emoji que aparece no início das mensagens.\n\n"
        "Exemplos:\n"
        "• 🎬 (cinema)\n"
        "• 🛍 (sacola)\n"
        "• 💎 (diamante)\n"
        "• 🚀 (foguete)",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(app_field="main_emoji")
    await callback.answer()


# ============================================
# 📛 TÍTULO DO SITE
# ============================================
@router.callback_query(F.data == "adm_app:set_site_title")
async def cb_app_set_site_title(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "📛 <b>TÍTULO DO SITE</b>\n\n"
        "Aparece na aba do navegador e no Mini App.",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(app_field="site_title")
    await callback.answer()


# ============================================
# 🎨 COR PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_app:set_color")
async def cb_app_set_color(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    rows: list[list[InlineKeyboardButton]] = []

    # Botões rápidos de cor
    for i in range(0, len(COLORS), 2):
        row: list[InlineKeyboardButton] = []
        for hex_color, label in COLORS[i : i + 2]:
            row.append(
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"adm_app:color:{hex_color}",
                )
            )
        rows.append(row)

    rows.append([
        InlineKeyboardButton(text="✏️ Cor Personalizada", callback_data="adm_app:color_custom")
    ])
    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_app:menu")
    ])

    await callback.message.edit_text(
        "🎨 <b>COR PRINCIPAL</b>\n\n"
        "Escolha uma cor ou envie hexadecimal:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_app:color:"))
async def cb_app_color_set(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    try:
        hex_color = callback.data.split(":", 2)[2]
    except IndexError:
        await callback.answer("❌ Valor inválido.", show_alert=True)
        return

    old = await config_service.get_str(session, "site_primary_color", "#7c5cff")
    await config_service.set_config(session, "site_primary_color", hex_color)

    await _log_audit(
        session,
        callback.from_user.id,
        "edit_site_color",
        old_value={"color": old},
        new_value={"color": hex_color},
    )

    await callback.answer(f"✅ Cor: {hex_color}", show_alert=True)

    callback.data = "adm_app:menu"
    await cb_app_menu(callback, session)


@router.callback_query(F.data == "adm_app:color_custom")
async def cb_app_color_custom(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "🎨 Envie a cor em formato hexadecimal.\n\n"
        "Exemplo: <code>#7c5cff</code>",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(app_field="site_primary_color")
    await callback.answer()


# ============================================
# 📢 TEXTO DO BANNER
# ============================================
@router.callback_query(F.data == "adm_app:set_banner")
async def cb_app_set_banner(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "📢 <b>TEXTO DO BANNER</b>\n\n"
        "Mensagem que aparece em destaque no topo do Mini App.\n\n"
        "Exemplos:\n"
        "• 🎉 Promoção: 10% de bônus em recargas acima de R$ 20\n"
        "• ⚡ Entrega instantânea 24h\n"
        "• 🎁 Resgate seu gift card agora!\n\n"
        "Ou envie <code>-</code> pra remover o banner.",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(app_field="banner_text")
    await callback.answer()


# ============================================
# 💾 SALVAR VALOR
# ============================================
@router.message(AdminStates.editing_config_value)
async def msg_app_save(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    data = await state.get_data()
    field = data.get("app_field")

    if not field:
        await state.clear()
        return

    raw = (message.text or message.caption or "").strip()

    if field == "banner_text" and raw == "-":
        raw = ""

    if not raw and field != "banner_text":
        await message.answer("❌ Valor vazio.")
        return

    # Validações
    if field == "site_primary_color":
        if not raw.startswith("#") or len(raw) not in (4, 7):
            await message.answer(
                "❌ Cor inválida. Use formato hex: <code>#7c5cff</code>"
            )
            return

    if field == "main_emoji":
        if len(raw) > 4:
            await message.answer("❌ Envie apenas 1 emoji.")
            return

    old = await config_service.get_str(session, field, "")
    await config_service.set_config(session, field, raw)

    await _log_audit(
        session,
        message.from_user.id,
        f"edit_appearance_{field}",
        old_value={field: old},
        new_value={field: raw},
    )

    label = field.replace("_", " ").title()
    await message.answer(f"✅ <b>{label}</b> atualizado!")
    await state.clear()


# ============================================
# 👁 PREVIEW VISUAL
# ============================================
@router.callback_query(F.data == "adm_app:preview")
async def cb_app_preview(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    bot_name = await config_service.get_str(session, "bot_name", "Larizinha Store")
    site_title = await config_service.get_str(session, "site_title", "Larizinha Store")
    primary_color = await config_service.get_str(session, "site_primary_color", "#7c5cff")
    main_emoji = await config_service.get_str(session, "main_emoji", "🎬")
    banner_text = await config_service.get_str(session, "banner_text", "")

    preview_lines = [
        f"{main_emoji} <b>Bem-vindo à {bot_name}!</b>",
        "",
        "A sua central de streamings com entrega 100% automática.",
        "",
        "💠 <b>Seus Dados:</b>",
        "├👤 ID: <code>6995978182</code>",
        "└💰 Saldo Atual: <b>R$ 0,00</b>",
        "",
        "👇 <b>COMO COMEÇAR:</b>",
        "Clique no botão abaixo para ver o catálogo.",
    ]

    preview = "\n".join(preview_lines)

    text = (
        "👁 <b>PREVIEW VISUAL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📛 Título: <b>" + site_title + "</b>\n"
        "🎨 Cor: <code>" + primary_color + "</code>\n"
        "🎯 Emoji: " + main_emoji + "\n\n"
    )

    if banner_text:
        text += f"📢 Banner: <i>{banner_text}</i>\n\n"

    text += "━━━━━━━━━━━━━━━━━━━━━━\n"
    text += "<b>Prévia da mensagem /start:</b>\n\n"
    text += preview
    text += "\n\n━━━━━━━━━━━━━━━━━━━━━━"
    text += "\n<i>Este é o preview. A cor só aparece no site/Mini App.</i>"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎨 Trocar Cor", callback_data="adm_app:set_color")],
            [InlineKeyboardButton(text="📢 Trocar Banner", callback_data="adm_app:set_banner")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_app:menu")],
        ]
    )

    if len(text) > 4000:
        text = text[:4000] + "\n\n<i>... (truncado)</i>"

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()

# ============================================
# 🌐 ADMIN WEBSITE / MINI APP — Larizinha Store
# ============================================
# Configuração REAL do Website / Mini App.
# Todos os botões funcionam de verdade.
#
# Cobre:
#   - URL do Mini App
#   - URL do site de ativação
#   - Título, logo, favicon
#   - Cores do site
#   - Carrinho (limites)
#   - Página de ativação
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
from core.config import settings
from core.models import Admin, AuditLog
from core.services import config as config_service


router = Router(name="admin_website")


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
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_web:menu")]
        ]
    )


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_web:menu")
async def cb_web_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    webapp_url = await config_service.get_str(session, "webapp_url", settings.webapp_url)
    activation_url = await config_service.get_str(session, "activation_url", settings.activation_url)
    site_title = await config_service.get_str(session, "site_title", "Larizinha Store")
    site_color = await config_service.get_str(session, "site_primary_color", "#7c5cff")
    cart_max = await config_service.get_str(session, "cart_max_items", "20")
    cart_max_qty = await config_service.get_str(session, "cart_max_quantity_per_item", "10")
    activation_days = await config_service.get_str(session, "activation_link_days", "30")

    text = (
        "🌐 <b>WEBSITE / MINI APP</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔗 URL Mini App:\n<code>{(webapp_url or '—')[:60]}</code>\n\n"
        f"🔐 URL Ativação:\n<code>{(activation_url or '—')[:60]}</code>\n\n"
        f"📛 Título: <b>{site_title}</b>\n"
        f"🎨 Cor principal: <code>{site_color}</code>\n\n"
        "🛒 <b>Carrinho:</b>\n"
        f"├ Máx. itens: <b>{cart_max}</b>\n"
        f"└ Máx. por item: <b>{cart_max_qty}</b>\n\n"
        f"⏰ Link de ativação expira em: <b>{activation_days} dias</b>\n\n"
        "Escolha o que deseja configurar:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 URL do Mini App", callback_data="adm_web:set_webapp_url")],
            [InlineKeyboardButton(text="🔐 URL de Ativação", callback_data="adm_web:set_activation_url")],
            [InlineKeyboardButton(text="📛 Título do Site", callback_data="adm_web:set_title")],
            [InlineKeyboardButton(text="🎨 Cor Principal", callback_data="adm_web:set_color")],
            [InlineKeyboardButton(text="🖼️ Logo / Favicon", callback_data="adm_img:view:webapp_image")],
            [InlineKeyboardButton(text="🛒 Configurar Carrinho", callback_data="adm_web:cart")],
            [InlineKeyboardButton(text="🔐 Página de Ativação", callback_data="adm_web:activation")],
            [InlineKeyboardButton(text="👁 Preview", callback_data="adm_web:preview")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:config")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 🔗 URL DO MINI APP
# ============================================
@router.callback_query(F.data == "adm_web:set_webapp_url")
async def cb_web_set_url(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "🔗 <b>URL DO MINI APP</b>\n\n"
        "Envie a URL pública do seu Mini App.\n\n"
        "Exemplo: <code>https://seuapp.com/webapp</code>\n\n"
        "⚠️ Deve começar com <code>https://</code>.",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(web_field="webapp_url")
    await callback.answer()


# ============================================
# 🔐 URL DE ATIVAÇÃO
# ============================================
@router.callback_query(F.data == "adm_web:set_activation_url")
async def cb_web_set_activation(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "🔐 <b>URL DO SITE DE ATIVAÇÃO</b>\n\n"
        "Página onde o cliente ativa o produto que recebeu por e-mail.\n\n"
        "Exemplo: <code>https://seuapp.com/ativar</code>",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(web_field="activation_url")
    await callback.answer()


# ============================================
# 📛 TÍTULO DO SITE
# ============================================
@router.callback_query(F.data == "adm_web:set_title")
async def cb_web_set_title(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "📛 <b>TÍTULO DO SITE</b>\n\n"
        "Aparece na aba do navegador e no topo do Mini App.\n\n"
        "Exemplo: <code>Larizinha Store</code>",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(web_field="site_title")
    await callback.answer()


# ============================================
# 🎨 COR PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_web:set_color")
async def cb_web_set_color(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "🎨 <b>COR PRINCIPAL</b>\n\n"
        "Envie a cor em formato hexadecimal.\n\n"
        "Exemplos:\n"
        "• <code>#7c5cff</code> (roxo)\n"
        "• <code>#4f46e5</code> (azul-roxo)\n"
        "• <code>#10b981</code> (verde)\n"
        "• <code>#ef4444</code> (vermelho)",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(web_field="site_primary_color")
    await callback.answer()


# ============================================
# 💾 SALVAR VALOR
# ============================================
@router.message(AdminStates.editing_config_value)
async def msg_web_save(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    data = await state.get_data()
    field = data.get("web_field")

    if not field:
        await state.clear()
        return

    raw = (message.text or "").strip()
    if not raw:
        await message.answer("❌ Valor vazio.")
        return

    # Validações
    if field in ("webapp_url", "activation_url"):
        if not raw.startswith(("http://", "https://")):
            await message.answer("❌ URL inválida. Deve começar com https://")
            return

    if field == "site_primary_color":
        if not raw.startswith("#") or len(raw) not in (4, 7):
            await message.answer(
                "❌ Cor inválida. Use formato hex: <code>#7c5cff</code>"
            )
            return

    old = await config_service.get_str(session, field, "")
    await config_service.set_config(session, field, raw)

    # Atualiza settings em runtime
    try:
        if field == "webapp_url":
            settings.webapp_url = raw
        elif field == "activation_url":
            settings.activation_url = raw
    except Exception:
        pass

    await _log_audit(
        session,
        message.from_user.id,
        f"edit_website_{field}",
        old_value={field: old},
        new_value={field: raw},
    )

    label = field.replace("_", " ").title()
    await message.answer(f"✅ <b>{label}</b> atualizado!")
    await state.clear()


# ============================================
# 🛒 CONFIGURAR CARRINHO
# ============================================
@router.callback_query(F.data == "adm_web:cart")
async def cb_web_cart(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    cart_max = await config_service.get_str(session, "cart_max_items", "20")
    cart_max_qty = await config_service.get_str(session, "cart_max_quantity_per_item", "10")
    allow_clear = await config_service.get_bool(session, "cart_allow_clear", True)
    allow_change = await config_service.get_bool(session, "cart_allow_change_qty", True)

    text = (
        "🛒 <b>CONFIGURAÇÃO DO CARRINHO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 Máximo de itens (produtos diferentes): <b>{cart_max}</b>\n"
        f"🔢 Máx. quantidade por item: <b>{cart_max_qty}</b>\n\n"
        f"{'🟢' if allow_clear else '🔴'} Permitir limpar carrinho\n"
        f"{'🟢' if allow_change else '🔴'} Permitir alterar quantidade\n\n"
        "Configurações do carrinho do Mini App."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"📦 Máx. Itens ({cart_max})",
                callback_data="adm_web:cart_max",
            )],
            [InlineKeyboardButton(
                text=f"🔢 Máx. Qtd por Item ({cart_max_qty})",
                callback_data="adm_web:cart_max_qty",
            )],
            [InlineKeyboardButton(
                text=f"{'🟢' if allow_clear else '🔴'} Limpar Carrinho",
                callback_data="adm_web:cart_toggle_clear",
            )],
            [InlineKeyboardButton(
                text=f"{'🟢' if allow_change else '🔴'} Alterar Quantidade",
                callback_data="adm_web:cart_toggle_change",
            )],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_web:menu")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


@router.callback_query(F.data == "adm_web:cart_max")
async def cb_web_cart_max(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await callback.message.answer(
        "📦 Envie o máximo de <b>itens diferentes</b> no carrinho (1-100):",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(web_field="cart_max_items")
    await callback.answer()


@router.callback_query(F.data == "adm_web:cart_max_qty")
async def cb_web_cart_max_qty(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await callback.message.answer(
        "🔢 Envie o máximo de <b>quantidade por item</b> (1-100):",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(web_field="cart_max_quantity_per_item")
    await callback.answer()


@router.callback_query(F.data == "adm_web:cart_toggle_clear")
async def cb_web_toggle_clear(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    current = await config_service.get_bool(session, "cart_allow_clear", True)
    new = not current
    await config_service.set_config(session, "cart_allow_clear", "true" if new else "false")
    await callback.answer(f"{'🟢' if new else '🔴'}", show_alert=True)
    await cb_web_cart(callback, session)


@router.callback_query(F.data == "adm_web:cart_toggle_change")
async def cb_web_toggle_change(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    current = await config_service.get_bool(session, "cart_allow_change_qty", True)
    new = not current
    await config_service.set_config(session, "cart_allow_change_qty", "true" if new else "false")
    await callback.answer(f"{'🟢' if new else '🔴'}", show_alert=True)
    await cb_web_cart(callback, session)


# ============================================
# 🔐 PÁGINA DE ATIVAÇÃO
# ============================================
@router.callback_query(F.data == "adm_web:activation")
async def cb_web_activation(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    days = await config_service.get_str(session, "activation_link_days", "30")
    max_attempts = await config_service.get_str(session, "activation_max_attempts", "5")
    session_hours = await config_service.get_str(session, "activation_session_hours", "24")

    text = (
        "🔐 <b>PÁGINA DE ATIVAÇÃO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⏰ Link expira em: <b>{days} dias</b>\n"
        f"🔢 Máx. tentativas de senha: <b>{max_attempts}</b>\n"
        f"🕐 Sessão dura: <b>{session_hours} horas</b>\n\n"
        "Configuração do site de ativação que o cliente acessa "
        "por link enviado no e-mail."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"⏰ Expiração ({days} dias)",
                callback_data="adm_web:act_days",
            )],
            [InlineKeyboardButton(
                text=f"🔢 Máx. Tentativas ({max_attempts})",
                callback_data="adm_web:act_attempts",
            )],
            [InlineKeyboardButton(
                text=f"🕐 Duração da Sessão ({session_hours}h)",
                callback_data="adm_web:act_session",
            )],
            [InlineKeyboardButton(
                text="📝 Mensagem de Sucesso",
                callback_data="adm_msg:view:activation_success:0",
            )],
            [InlineKeyboardButton(
                text="📝 Mensagem de Erro",
                callback_data="adm_msg:view:activation_error:0",
            )],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_web:menu")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


@router.callback_query(F.data == "adm_web:act_days")
async def cb_web_act_days(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await callback.message.answer(
        "⏰ Envie o número de <b>dias</b> que o link fica válido (1-365):",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(web_field="activation_link_days")
    await callback.answer()


@router.callback_query(F.data == "adm_web:act_attempts")
async def cb_web_act_attempts(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await callback.message.answer(
        "🔢 Envie o máximo de <b>tentativas</b> de senha (1-20):",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(web_field="activation_max_attempts")
    await callback.answer()


@router.callback_query(F.data == "adm_web:act_session")
async def cb_web_act_session(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await callback.message.answer(
        "🕐 Envie a duração da <b>sessão em horas</b> (1-168):",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(web_field="activation_session_hours")
    await callback.answer()


# ============================================
# 👁 PREVIEW
# ============================================
@router.callback_query(F.data == "adm_web:preview")
async def cb_web_preview(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    webapp_url = await config_service.get_str(session, "webapp_url", "")
    activation_url = await config_service.get_str(session, "activation_url", "")
    site_title = await config_service.get_str(session, "site_title", "Larizinha Store")
    site_color = await config_service.get_str(session, "site_primary_color", "#7c5cff")

    text = (
        "👁 <b>PREVIEW DO SITE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📛 Título: <b>{site_title}</b>\n"
        f"🎨 Cor: <code>{site_color}</code>\n\n"
        f"🔗 Mini App:\n<code>{webapp_url or 'não configurado'}</code>\n\n"
        f"🔐 Ativação:\n<code>{activation_url or 'não configurado'}</code>\n\n"
        "💡 Abra os links acima pra ver o resultado."
    )

    rows: list[list[InlineKeyboardButton]] = []

    if webapp_url and webapp_url.startswith("http"):
        rows.append([
            InlineKeyboardButton(text="🌐 Abrir Mini App", url=webapp_url)
        ])

    if activation_url and activation_url.startswith("http"):
        rows.append([
            InlineKeyboardButton(text="🔐 Abrir Ativação", url=activation_url)
        ])

    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_web:menu")
    ])

    try:
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            disable_web_page_preview=True,
        )
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            disable_web_page_preview=True,
        )

    await callback.answer()

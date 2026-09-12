# ============================================
# 📝 ADMIN MESSAGES — Larizinha Store
# ============================================
# Editor REAL de mensagens do bot.
# Todas as mensagens que o bot envia vêm da tabela
# message_templates e são editáveis por aqui.
#
# ✨ CORRIGIDO:
#   - Bug de sintaxe na linha 449 (string mal fechada)
#   - Parse mode "clean" agora usa string vazia
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
from core.models import Admin, AuditLog, MessageTemplate
from core.services.messages import DEFAULT_MESSAGES, render_message


router = Router(name="admin_messages")


# ============================================
# 📚 CATEGORIAS DISPONÍVEIS
# ============================================
CATEGORIES: dict[str, str] = {
    "start": "🎬 Início / Start",
    "canal": "📢 Canal Obrigatório",
    "catalogo": "📱 Catálogo",
    "produto": "📦 Produto",
    "compra": "🛒 Compra",
    "pix": "💳 Pix / Recarga",
    "perfil": "👤 Perfil",
    "historico": "📜 Histórico",
    "gift_card": "🎁 Gift Card",
    "afiliados": "🤝 Afiliados",
    "ranking": "🏆 Ranking",
    "pesquisa": "🔎 Pesquisa",
    "alertas": "🔔 Alertas",
    "manutencao": "🔧 Manutenção",
    "erros": "❌ Erros",
    "sucesso": "✅ Sucesso",
    "entrega": "📦 Entrega",
    "whatsapp": "📱 WhatsApp",
    "email": "📧 E-mail",
    "geral": "⚙️ Geral",
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


async def _get_or_create_template(
    session: AsyncSession,
    key: str,
) -> MessageTemplate:
    """Busca o template; cria do DEFAULT se não existir."""
    stmt = select(MessageTemplate).where(MessageTemplate.key == key)
    result = await session.execute(stmt)
    tpl = result.scalar_one_or_none()

    if tpl is not None:
        return tpl

    default = DEFAULT_MESSAGES.get(key)
    if default is None:
        tpl = MessageTemplate(
            key=key,
            category="geral",
            title=key,
            text="⚠️ Mensagem não configurada.",
        )
    else:
        tpl = MessageTemplate(
            key=key,
            category=default["category"],
            title=default["title"],
            text=default["text"],
        )

    session.add(tpl)
    await session.flush()
    return tpl


def _short(text: str, limit: int = 60) -> str:
    text = text.replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_cfg:messages")
async def cb_messages_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    total = len(DEFAULT_MESSAGES)

    text = (
        "📝 <b>EDITOR DE MENSAGENS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📚 Mensagens configuráveis: <b>{total}</b>\n\n"
        "Escolha uma <b>categoria</b> para ver e editar as mensagens:"
    )

    rows: list[list[InlineKeyboardButton]] = []
    items = list(CATEGORIES.items())
    for i in range(0, len(items), 2):
        row: list[InlineKeyboardButton] = []
        for key, label in items[i : i + 2]:
            row.append(
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"adm_msg:cat:{key}:0",
                )
            )
        rows.append(row)

    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:config")
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 📂 LISTAR MENSAGENS DA CATEGORIA
# ============================================
@router.callback_query(F.data.startswith("adm_msg:cat:"))
async def cb_messages_category(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    parts = callback.data.split(":")
    category = parts[2]
    page = int(parts[3]) if len(parts) > 3 else 0

    await _show_category(callback, session, category, page)


async def _show_category(
    callback: CallbackQuery,
    session: AsyncSession,
    category: str,
    page: int = 0,
) -> None:
    PER_PAGE = 8

    # Pega as chaves que pertencem a essa categoria
    keys_in_cat = [
        k for k, v in DEFAULT_MESSAGES.items()
        if v.get("category") == category
    ]

    # Também pega as que estão no banco mas não estão no default
    stmt = select(MessageTemplate).where(MessageTemplate.category == category)
    result = await session.execute(stmt)
    for t in result.scalars().all():
        if t.key not in keys_in_cat:
            keys_in_cat.append(t.key)

    total = len(keys_in_cat)
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    start = page * PER_PAGE
    keys_page = keys_in_cat[start : start + PER_PAGE]

    cat_label = CATEGORIES.get(category, category)

    lines = [
        f"📝 <b>MENSAGENS — {cat_label}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📊 Total: <b>{total}</b>",
        "",
    ]

    rows: list[list[InlineKeyboardButton]] = []

    if not keys_page:
        lines.append("Nenhuma mensagem nesta categoria.")
    else:
        for k in keys_page:
            tpl = await _get_or_create_template(session, k)
            preview = _short(tpl.text, 40)
            rows.append([
                InlineKeyboardButton(
                    text=f"✏️ {tpl.title or k}",
                    callback_data=f"adm_msg:view:{k}:0",
                )
            ])
            lines.append(f"• <b>{k}</b> — <i>{preview}</i>")

    # Navegação
    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                text="⬅️",
                callback_data=f"adm_msg:cat:{category}:{page - 1}",
            ))
        nav.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="adm:noop",
        ))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(
                text="➡️",
                callback_data=f"adm_msg:cat:{category}:{page + 1}",
            ))
        rows.append(nav)

    rows.append([
        InlineKeyboardButton(text="🔙 Categorias", callback_data="adm_cfg:messages")
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

    try:
        await callback.message.edit_text("\n".join(lines), reply_markup=keyboard)
    except Exception:
        await callback.message.answer("\n".join(lines), reply_markup=keyboard)

    await callback.answer()


# ============================================
# 👁️ VER MENSAGEM
# ============================================
@router.callback_query(F.data.startswith("adm_msg:view:"))
async def cb_messages_view(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    key = callback.data.split(":")[2]
    tpl = await _get_or_create_template(session, key)

    text = (
        f"📝 <b>EDITAR MENSAGEM</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔑 Chave: <code>{tpl.key}</code>\n"
        f"📂 Categoria: <b>{tpl.category}</b>\n"
        f"🏷 Título: <b>{tpl.title or '—'}</b>\n"
        f"🎨 Parse mode: <b>{tpl.parse_mode}</b>\n"
        f"📊 Status: <b>{'🟢 Ativa' if tpl.is_active else '🔴 Inativa'}</b>\n\n"
        "📄 <b>Conteúdo atual:</b>\n"
        f"<pre>{tpl.text[:900]}</pre>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Editar texto", callback_data=f"adm_msg:edit_text:{key}:0")],
            [InlineKeyboardButton(text="🎨 Trocar parse mode", callback_data=f"adm_msg:mode:{key}:0")],
            [InlineKeyboardButton(
                text="🔴 Desativar" if tpl.is_active else "🟢 Ativar",
                callback_data=f"adm_msg:toggle:{key}:0",
            )],
            [InlineKeyboardButton(text="👁 Preview renderizado", callback_data=f"adm_msg:preview:{key}:0")],
            [InlineKeyboardButton(text="♻️ Restaurar padrão", callback_data=f"adm_msg:reset:{key}:0")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data=f"adm_msg:cat:{tpl.category}:0")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# ✏️ EDITAR TEXTO
# ============================================
@router.callback_query(F.data.startswith("adm_msg:edit_text:"))
async def cb_messages_edit_text(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    key = callback.data.split(":")[2]

    text = (
        f"✏️ <b>EDITAR TEXTO</b>\n"
        f"🔑 Chave: <code>{key}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Envie o <b>novo texto</b> da mensagem.\n\n"
        "💡 Você pode usar HTML:\n"
        "• <code>&lt;b&gt;negrito&lt;/b&gt;</code>\n"
        "• <code>&lt;i&gt;itálico&lt;/i&gt;</code>\n"
        "• <code>&lt;code&gt;monoespaçado&lt;/code&gt;</code>\n"
        "• <code>&lt;pre&gt;bloco&lt;/pre&gt;</code>\n\n"
        "📌 <b>Variáveis disponíveis:</b>\n"
        "<code>{USER_ID}</code> <code>{USERNAME}</code> "
        "<code>{BALANCE}</code> <code>{PRODUCT_NAME}</code> "
        "<code>{PRODUCT_PRICE}</code> <code>{STOCK}</code> "
        "<code>{ORDER_ID}</code> <code>{PAYMENT_ID}</code> "
        "<code>{DATE}</code> <code>{EXPIRATION}</code> "
        "<code>{BONUS}</code> <code>{AFFILIATE_BALANCE}</code>"
    )

    await callback.message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Cancelar", callback_data=f"adm_msg:view:{key}:0")]
            ]
        ),
    )

    await state.update_data(msg_key=key)
    await state.set_state(AdminStates.editing_message_text)
    await callback.answer()


@router.message(AdminStates.editing_message_text)
async def msg_save_message_text(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    data = await state.get_data()
    key = data.get("msg_key")

    new_text = message.text or message.caption or ""
    if not new_text.strip():
        await message.answer("❌ Texto vazio. Envie novamente.")
        return

    tpl = await _get_or_create_template(session, key)
    old_text = tpl.text
    tpl.text = new_text
    session.add(tpl)

    await _log_audit(
        session,
        message.from_user.id,
        "edit_message",
        old_value={"key": key, "text_preview": old_text[:80]},
        new_value={"key": key, "text_preview": new_text[:80]},
    )

    await message.answer(
        f"✅ Mensagem <code>{key}</code> atualizada!\n\n"
        "Ela já está valendo no bot em tempo real.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="👁 Ver mensagem", callback_data=f"adm_msg:view:{key}:0")],
                [InlineKeyboardButton(text="✏️ Editar novamente", callback_data=f"adm_msg:edit_text:{key}:0")],
                [InlineKeyboardButton(text="📝 Editor", callback_data="adm_cfg:messages")],
            ]
        ),
    )
    await state.clear()


# ============================================
# 🎨 TROCAR PARSE MODE
# ============================================
@router.callback_query(F.data.startswith("adm_msg:mode:"))
async def cb_messages_mode(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    key = callback.data.split(":")[2]

    text = (
        f"🎨 <b>TROCAR PARSE MODE</b>\n"
        f"🔑 Chave: <code>{key}</code>\n\n"
        "Escolha o modo de formatação:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="HTML (recomendado)", callback_data=f"adm_msg:set_mode:{key}:HTML")],
            [InlineKeyboardButton(text="Markdown", callback_data=f"adm_msg:set_mode:{key}:Markdown")],
            [InlineKeyboardButton(text="MarkdownV2", callback_data=f"adm_msg:set_mode:{key}:MarkdownV2")],
            [InlineKeyboardButton(text="Sem formatação", callback_data=f"adm_msg:set_mode:{key}:clean")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data=f"adm_msg:view:{key}:0")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


@router.callback_query(F.data.startswith("adm_msg:set_mode:"))
async def cb_messages_set_mode(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    parts = callback.data.split(":", 3)
    key = parts[2]
    mode = parts[3]

    if mode == "clean":
        mode = ""

    tpl = await _get_or_create_template(session, key)
    tpl.parse_mode = mode or "HTML"
    session.add(tpl)

    await _log_audit(
        session,
        callback.from_user.id,
        "edit_message_mode",
        new_value={"key": key, "parse_mode": tpl.parse_mode},
    )

    await callback.answer(f"✅ Modo: {tpl.parse_mode}", show_alert=True)

    callback.data = f"adm_msg:view:{key}:0"
    await cb_messages_view(callback, session)


# ============================================
# 🟢 / 🔴 TOGGLE ATIVA
# ============================================
@router.callback_query(F.data.startswith("adm_msg:toggle:"))
async def cb_messages_toggle(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    key = callback.data.split(":")[2]
    tpl = await _get_or_create_template(session, key)

    tpl.is_active = not tpl.is_active
    session.add(tpl)

    await _log_audit(
        session,
        callback.from_user.id,
        "toggle_message",
        new_value={"key": key, "is_active": tpl.is_active},
    )

    status = "ativada" if tpl.is_active else "desativada"
    await callback.answer(f"✅ Mensagem {status}!", show_alert=True)

    callback.data = f"adm_msg:view:{key}:0"
    await cb_messages_view(callback, session)


# ============================================
# 👁 PREVIEW RENDERIZADO
# ============================================
@router.callback_query(F.data.startswith("adm_msg:preview:"))
async def cb_messages_preview(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    key = callback.data.split(":")[2]

    example_vars = {
        "USER_ID": "6995978182",
        "USERNAME": "cliente_exemplo",
        "FIRST_NAME": "Cliente",
        "BALANCE": "0,00",
        "PRODUCT_NAME": "HBO MAX",
        "PRODUCT_PRICE": "8,00",
        "STOCK": "4",
        "ORDER_ID": "81c5465d-e71e-4b43-903a-e1dc567272ea",
        "PAYMENT_ID": "52b718fd9d074396bf71607c3efbfe96",
        "DATE": "31/01/2026",
        "EXPIRATION": "02/03/2026",
        "BONUS": "0,00",
        "AFFILIATE_BALANCE": "0,00",
        "WHATSAPP": "44999998888",
        "PURCHASES": "2",
        "TOTAL_SPENT": "2,00",
        "TOTAL_RECHARGED": "0,00",
        "GIFTS": "0,00",
        "POINTS": "0",
    }

    rendered = await render_message(session, key=key, variables=example_vars)
    tpl = await _get_or_create_template(session, key)

    text = (
        f"👁 <b>PREVIEW</b>\n"
        f"🔑 Chave: <code>{key}</code>\n"
        f"🎨 Modo: <b>{tpl.parse_mode}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{rendered[:3500]}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Este é apenas um preview com valores de exemplo.</i>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Editar", callback_data=f"adm_msg:edit_text:{key}:0")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data=f"adm_msg:view:{key}:0")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# ♻️ RESTAURAR PADRÃO
# ============================================
@router.callback_query(F.data.startswith("adm_msg:reset:"))
async def cb_messages_reset(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    key = callback.data.split(":")[2]

    default = DEFAULT_MESSAGES.get(key)
    if default is None:
        await callback.answer("❌ Não há padrão pra essa mensagem.", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Sim, restaurar", callback_data=f"adm_msg:reset_confirm:{key}:0")],
            [InlineKeyboardButton(text="❌ Cancelar", callback_data=f"adm_msg:view:{key}:0")],
        ]
    )

    await callback.message.edit_text(
        f"♻️ <b>RESTAURAR PADRÃO</b>\n\n"
        f"🔑 Chave: <code>{key}</code>\n\n"
        "⚠️ O texto atual será substituído pelo padrão de fábrica.\n\n"
        "Confirma?",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_msg:reset_confirm:"))
async def cb_messages_reset_confirm(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    key = callback.data.split(":")[2]
    default = DEFAULT_MESSAGES.get(key)
    if default is None:
        await callback.answer("❌ Sem padrão.", show_alert=True)
        return

    tpl = await _get_or_create_template(session, key)
    old_text = tpl.text
    tpl.text = default["text"]
    tpl.category = default["category"]
    tpl.title = default["title"]
    session.add(tpl)

    await _log_audit(
        session,
        callback.from_user.id,
        "reset_message",
        old_value={"key": key, "text_preview": old_text[:80]},
        new_value={"key": key, "text_preview": default["text"][:80]},
    )

    await callback.answer("♻️ Restaurado para o padrão!", show_alert=True)

    callback.data = f"adm_msg:view:{key}:0"
    await cb_messages_view(callback, session)

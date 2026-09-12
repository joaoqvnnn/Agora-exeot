# ============================================
# 🔘 ADMIN BUTTONS — Larizinha Store
# ============================================
# Editor REAL de botões do bot.
# Todos os botões do /start, catálogo, admin, etc
# são editáveis por aqui (via button_templates).
#
# Todos os botões funcionam:
#   - LISTAR por menu
#   - VER detalhes
#   - EDITAR texto
#   - EDITAR callback/URL
#   - EDITAR linha/posição
#   - ATIVAR/DESATIVAR
#   - ADICIONAR novo botão
#   - REMOVER
#   - RESTAURAR padrão
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
from core.models import Admin, AuditLog, ButtonTemplate


router = Router(name="admin_buttons")


# ============================================
# 📚 MENUS DISPONÍVEIS
# ============================================
MENUS: dict[str, str] = {
    "start": "🏠 Menu /start (cliente)",
    "catalogo": "📱 Catálogo (cliente)",
    "produto": "📦 Produto (cliente)",
    "pix": "💳 Pix (cliente)",
    "perfil": "👤 Perfil (cliente)",
    "afiliados": "🤝 Afiliados (cliente)",
    "ranking": "🏆 Ranking (cliente)",
    "admin_main": "👮 Painel Admin - Principal",
    "admin_config": "⚙️ Painel Admin - Configurações",
    "admin_config_gerais": "⚙️ Painel Admin - Config Geral",
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


def _cancel_keyboard(back_data: str = "adm_cfg:buttons") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancelar", callback_data=back_data)]
        ]
    )


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_cfg:buttons")
async def cb_buttons_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    # Conta botões por menu
    total_buttons = 0
    menu_summary = []

    for menu_key, menu_label in MENUS.items():
        stmt = select(ButtonTemplate).where(ButtonTemplate.menu == menu_key)
        result = await session.execute(stmt)
        count = len(list(result.scalars().all()))
        total_buttons += count
        menu_summary.append(f"• {menu_label}: <b>{count}</b>")

    text = (
        "🔘 <b>EDITOR DE BOTÕES</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 Total de botões customizados: <b>{total_buttons}</b>\n\n"
        "⚠️ Se um menu estiver vazio, o bot usa os padrões.\n"
        "Ao adicionar/customizar, os padrões são substituídos.\n\n"
        "Escolha o menu para editar:"
    )

    rows: list[list[InlineKeyboardButton]] = []
    items = list(MENUS.items())
    for i in range(0, len(items), 1):
        key, label = items[i]
        rows.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"adm_btn:menu:{key}",
            )
        ])

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
# 📂 LISTAR BOTÕES DE UM MENU
# ============================================
@router.callback_query(F.data.startswith("adm_btn:menu:"))
async def cb_buttons_list(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    menu_key = callback.data.split(":")[2]
    await _show_buttons_list(callback, session, menu_key)


async def _show_buttons_list(
    callback: CallbackQuery,
    session: AsyncSession,
    menu_key: str,
) -> None:
    stmt = (
        select(ButtonTemplate)
        .where(ButtonTemplate.menu == menu_key)
        .order_by(ButtonTemplate.row, ButtonTemplate.position)
    )
    result = await session.execute(stmt)
    buttons = list(result.scalars().all())

    menu_label = MENUS.get(menu_key, menu_key)

    lines = [
        f"🔘 <b>BOTÕES — {menu_label}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    rows: list[list[InlineKeyboardButton]] = []

    if not buttons:
        lines.append(
            "📭 Nenhum botão customizado neste menu.\n"
            "O bot está usando os <b>padrões de fábrica</b>.\n"
        )
        lines.append(
            "Para customizar, clique em <b>➕ Adicionar</b> abaixo "
            "e crie os botões conforme desejar."
        )
    else:
        lines.append(f"📊 Total: <b>{len(buttons)}</b> botões\n")

        for b in buttons:
            status = "🟢" if b.is_active else "🔴"
            rows.append([
                InlineKeyboardButton(
                    text=f"{status} {b.text[:35]}",
                    callback_data=f"adm_btn:view:{b.id}",
                )
            ])
            lines.append(
                f"{status} <b>{b.text}</b>\n"
                f"   ↳ Linha {b.row} / Col {b.position} / "
                f"<code>{b.action_type}</code>"
            )

    rows.append([
        InlineKeyboardButton(
            text="➕ Adicionar Botão",
            callback_data=f"adm_btn:add:{menu_key}",
        )
    ])

    if buttons:
        rows.append([
            InlineKeyboardButton(
                text="🗑 Limpar Menu (volta pro padrão)",
                callback_data=f"adm_btn:clear:{menu_key}",
            )
        ])

    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_cfg:buttons")
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    text = "\n".join(lines)

    if len(text) > 4000:
        text = text[:4000] + "\n\n<i>... (truncado)</i>"

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 👁️ VER BOTÃO
# ============================================
@router.callback_query(F.data.startswith("adm_btn:view:"))
async def cb_buttons_view(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    btn_id = int(callback.data.split(":")[2])
    btn = await session.get(ButtonTemplate, btn_id)
    if btn is None:
        await callback.answer("❌ Botão não encontrado.", show_alert=True)
        return

    status = "🟢 Ativo" if btn.is_active else "🔴 Inativo"
    menu_label = MENUS.get(btn.menu, btn.menu)

    text = (
        f"🔘 <b>EDITAR BOTÃO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 ID: <code>{btn.id}</code>\n"
        f"📂 Menu: <b>{menu_label}</b>\n"
        f"📊 Status: <b>{status}</b>\n\n"
        f"📝 Texto: <b>{btn.text}</b>\n"
        f"🎬 Tipo de ação: <code>{btn.action_type}</code>\n"
        f"📌 Dados: <code>{btn.action_data or '—'}</code>\n\n"
        f"📍 Linha: <b>{btn.row}</b> | Coluna: <b>{btn.position}</b>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Editar Texto", callback_data=f"adm_btn:edit_text:{btn.id}")],
            [InlineKeyboardButton(text="🎬 Editar Ação", callback_data=f"adm_btn:edit_action:{btn.id}")],
            [InlineKeyboardButton(text="📌 Editar Dados (callback/URL)", callback_data=f"adm_btn:edit_data:{btn.id}")],
            [InlineKeyboardButton(text="📍 Editar Posição", callback_data=f"adm_btn:edit_pos:{btn.id}")],
            [InlineKeyboardButton(
                text="🔴 Desativar" if btn.is_active else "🟢 Ativar",
                callback_data=f"adm_btn:toggle:{btn.id}",
            )],
            [InlineKeyboardButton(text="🗑 Remover", callback_data=f"adm_btn:delete:{btn.id}")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data=f"adm_btn:menu:{btn.menu}")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# ➕ ADICIONAR BOTÃO
# ============================================
@router.callback_query(F.data.startswith("adm_btn:add:"))
async def cb_buttons_add(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    menu_key = callback.data.split(":")[2]

    text = (
        f"➕ <b>NOVO BOTÃO</b>\n"
        f"📂 Menu: <b>{MENUS.get(menu_key, menu_key)}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📝 Envie o <b>texto do botão</b>.\n\n"
        "Pode incluir emojis.\n"
        "Exemplos:\n"
        "• <code>🛍 Comprar Produtos</code>\n"
        "• <code>👤 Meu Perfil</code>\n"
        "• <code>💰 Recarregar</code>"
    )

    await callback.message.answer(
        text,
        reply_markup=_cancel_keyboard(f"adm_btn:menu:{menu_key}"),
    )

    await state.update_data(btn_menu=menu_key)
    await state.set_state(AdminStates.editing_button_text)
    await callback.answer()


@router.message(AdminStates.editing_button_text)
async def msg_button_text(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    data = await state.get_data()
    menu_key = data.get("btn_menu")

    text = (message.text or "").strip()
    if not text:
        await message.answer("❌ Texto vazio.")
        return

    if len(text) > 60:
        await message.answer("❌ Texto muito longo. Máx. 60 caracteres.")
        return

    await state.update_data(btn_text=text)

    # Pergunta o tipo de ação
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Callback (bot responde)", callback_data="adm_btn:new_type:callback")],
            [InlineKeyboardButton(text="URL (abre link)", callback_data="adm_btn:new_type:url")],
            [InlineKeyboardButton(text="Web App (abre mini app)", callback_data="adm_btn:new_type:webapp")],
            [InlineKeyboardButton(text="❌ Cancelar", callback_data=f"adm_btn:menu:{menu_key}")],
        ]
    )

    await message.answer(
        f"✅ Texto: <b>{text}</b>\n\n"
        "Agora escolha o <b>tipo de ação</b>:",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("adm_btn:new_type:"))
async def cb_button_new_type(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    action_type = callback.data.split(":")[2]
    await state.update_data(btn_action_type=action_type)

    hints = {
        "callback": (
            "📌 Envie o <b>callback_data</b> do botão.\n\n"
            "O callback é o que o bot recebe quando o usuário clica.\n"
            "Exemplos:\n"
            "• <code>menu:comprar</code>\n"
            "• <code>menu:perfil</code>\n"
            "• <code>menu:afiliados</code>\n"
            "• <code>adm:config</code>"
        ),
        "url": (
            "🔗 Envie a <b>URL</b> que o botão vai abrir.\n\n"
            "Exemplos:\n"
            "• <code>https://t.me/seucanal</code>\n"
            "• <code>https://wa.me/5511999999999</code>"
        ),
        "webapp": (
            "🌐 Envie a <b>URL do Web App</b>.\n\n"
            "Exemplo: <code>https://seusite.com/webapp</code>\n\n"
            "💡 Ou envie <code>webapp</code> pra usar a URL padrão "
            "configurada no sistema."
        ),
    }

    await callback.message.answer(
        hints.get(action_type, "Envie o valor:"),
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_button_url)
    await callback.answer()


@router.message(AdminStates.editing_button_url)
async def msg_button_action_data(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    data = await state.get_data()
    menu_key = data.get("btn_menu")
    btn_text = data.get("btn_text")
    action_type = data.get("btn_action_type")

    action_data = (message.text or "").strip()
    if not action_data:
        await message.answer("❌ Valor vazio.")
        return

    # Valida URL
    if action_type == "url" and not action_data.startswith(("http://", "https://", "tg://")):
        await message.answer(
            "❌ URL inválida. Deve começar com http://, https:// ou tg://"
        )
        return

    # Próxima linha (row)
    max_row_stmt = select(ButtonTemplate.row).where(ButtonTemplate.menu == menu_key)
    result = await session.execute(max_row_stmt)
    rows_list = [r for r in result.scalars().all() if r is not None]
    next_row = (max(rows_list) + 1) if rows_list else 0

    new_btn = ButtonTemplate(
        menu=menu_key,
        text=btn_text,
        action_type=action_type,
        action_data=action_data,
        row=next_row,
        position=0,
        is_active=True,
    )
    session.add(new_btn)
    await session.flush()

    await _log_audit(
        session,
        message.from_user.id,
        "add_button",
        new_value={
            "menu": menu_key,
            "text": btn_text,
            "action_type": action_type,
        },
    )

    await message.answer(
        f"✅ Botão criado com sucesso!\n\n"
        f"📝 Texto: <b>{btn_text}</b>\n"
        f"🎬 Tipo: <code>{action_type}</code>\n"
        f"📌 Dados: <code>{action_data}</code>\n"
        f"📍 Linha: <b>{next_row}</b>, Coluna: <b>0</b>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="👁 Ver botão", callback_data=f"adm_btn:view:{new_btn.id}")],
                [InlineKeyboardButton(text="➕ Adicionar outro", callback_data=f"adm_btn:add:{menu_key}")],
                [InlineKeyboardButton(text="📋 Ver menu", callback_data=f"adm_btn:menu:{menu_key}")],
            ]
        ),
    )
    await state.clear()


# ============================================
# ✏️ EDITAR TEXTO
# ============================================
@router.callback_query(F.data.startswith("adm_btn:edit_text:"))
async def cb_button_edit_text(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    btn_id = int(callback.data.split(":")[2])
    btn = await session.get(ButtonTemplate, btn_id)
    if btn is None:
        await callback.answer("❌ Botão não encontrado.", show_alert=True)
        return

    await state.update_data(btn_id=btn_id)
    await callback.message.answer(
        f"✏️ <b>EDITAR TEXTO</b>\n\n"
        f"<b>Atual:</b> {btn.text}\n\n"
        "Envie o novo texto:",
        reply_markup=_cancel_keyboard(f"adm_btn:view:{btn_id}"),
    )
    await state.set_state(AdminStates.editing_button_text)
    await callback.answer()


# ============================================
# 🎬 EDITAR AÇÃO
# ============================================
@router.callback_query(F.data.startswith("adm_btn:edit_action:"))
async def cb_button_edit_action(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    btn_id = int(callback.data.split(":")[2])

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Callback", callback_data=f"adm_btn:set_action:{btn_id}:callback")],
            [InlineKeyboardButton(text="URL", callback_data=f"adm_btn:set_action:{btn_id}:url")],
            [InlineKeyboardButton(text="Web App", callback_data=f"adm_btn:set_action:{btn_id}:webapp")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data=f"adm_btn:view:{btn_id}")],
        ]
    )

    await callback.message.edit_text(
        "🎬 <b>EDITAR TIPO DE AÇÃO</b>\n\nEscolha:",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_btn:set_action:"))
async def cb_button_set_action(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    parts = callback.data.split(":")
    btn_id = int(parts[2])
    action_type = parts[3]

    btn = await session.get(ButtonTemplate, btn_id)
    if btn is None:
        await callback.answer("❌ Botão não encontrado.", show_alert=True)
        return

    btn.action_type = action_type
    session.add(btn)

    await _log_audit(
        session,
        callback.from_user.id,
        "edit_button_action",
        new_value={"button_id": btn_id, "action_type": action_type},
    )

    await callback.answer(f"✅ Tipo: {action_type}", show_alert=True)

    callback.data = f"adm_btn:view:{btn_id}"
    await cb_buttons_view(callback, session)


# ============================================
# 📌 EDITAR DADOS
# ============================================
@router.callback_query(F.data.startswith("adm_btn:edit_data:"))
async def cb_button_edit_data(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    btn_id = int(callback.data.split(":")[2])
    btn = await session.get(ButtonTemplate, btn_id)
    if btn is None:
        await callback.answer("❌ Botão não encontrado.", show_alert=True)
        return

    await state.update_data(btn_id=btn_id)
    await callback.message.answer(
        f"📌 <b>EDITAR DADOS DO BOTÃO</b>\n\n"
        f"🎬 Tipo: <code>{btn.action_type}</code>\n"
        f"<b>Atual:</b> <code>{btn.action_data or '—'}</code>\n\n"
        "Envie o novo valor:",
        reply_markup=_cancel_keyboard(f"adm_btn:view:{btn_id}"),
    )
    await state.set_state(AdminStates.editing_button_url)
    await callback.answer()


# ============================================
# 📍 EDITAR POSIÇÃO
# ============================================
@router.callback_query(F.data.startswith("adm_btn:edit_pos:"))
async def cb_button_edit_pos(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    btn_id = int(callback.data.split(":")[2])
    btn = await session.get(ButtonTemplate, btn_id)
    if btn is None:
        await callback.answer("❌ Botão não encontrado.", show_alert=True)
        return

    await state.update_data(btn_id=btn_id)
    await callback.message.answer(
        f"📍 <b>EDITAR POSIÇÃO</b>\n\n"
        f"Atual: Linha <b>{btn.row}</b>, Coluna <b>{btn.position}</b>\n\n"
        "Envie no formato <code>LINHA,COLUNA</code>.\n"
        "Exemplo: <code>0,0</code> (primeiro botão do menu)\n"
        "Exemplo: <code>1,1</code> (segundo botão da segunda linha)",
        reply_markup=_cancel_keyboard(f"adm_btn:view:{btn_id}"),
    )
    await state.set_state(AdminStates.editing_button_url)
    await callback.answer()


# ============================================
# 🟢 / 🔴 TOGGLE
# ============================================
@router.callback_query(F.data.startswith("adm_btn:toggle:"))
async def cb_button_toggle(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    btn_id = int(callback.data.split(":")[2])
    btn = await session.get(ButtonTemplate, btn_id)
    if btn is None:
        await callback.answer("❌ Botão não encontrado.", show_alert=True)
        return

    btn.is_active = not btn.is_active
    session.add(btn)

    await _log_audit(
        session,
        callback.from_user.id,
        "toggle_button",
        new_value={"button_id": btn_id, "is_active": btn.is_active},
    )

    status = "ativado" if btn.is_active else "desativado"
    await callback.answer(f"✅ Botão {status}!", show_alert=True)

    callback.data = f"adm_btn:view:{btn_id}"
    await cb_buttons_view(callback, session)


# ============================================
# 🗑 REMOVER
# ============================================
@router.callback_query(F.data.startswith("adm_btn:delete:"))
async def cb_button_delete(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    btn_id = int(callback.data.split(":")[2])
    btn = await session.get(ButtonTemplate, btn_id)
    if btn is None:
        await callback.answer("❌ Botão não encontrado.", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Sim, remover", callback_data=f"adm_btn:confirm_del:{btn_id}")],
            [InlineKeyboardButton(text="❌ Cancelar", callback_data=f"adm_btn:view:{btn_id}")],
        ]
    )

    await callback.message.edit_text(
        f"⚠️ <b>REMOVER BOTÃO</b>\n\n"
        f"Remover <b>{btn.text}</b>?",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_btn:confirm_del:"))
async def cb_button_confirm_delete(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    btn_id = int(callback.data.split(":")[2])
    btn = await session.get(ButtonTemplate, btn_id)
    if btn is None:
        await callback.answer("❌ Botão não encontrado.", show_alert=True)
        return

    menu_key = btn.menu

    await _log_audit(
        session,
        callback.from_user.id,
        "delete_button",
        old_value={"button_id": btn_id, "text": btn.text, "menu": menu_key},
    )

    await session.delete(btn)
    await callback.answer("🗑 Botão removido.", show_alert=True)

    callback.data = f"adm_btn:menu:{menu_key}"
    await cb_buttons_list(callback, session)


# ============================================
# 🗑 LIMPAR MENU INTEIRO
# ============================================
@router.callback_query(F.data.startswith("adm_btn:clear:"))
async def cb_button_clear(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    menu_key = callback.data.split(":")[2]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ SIM, LIMPAR", callback_data=f"adm_btn:clear_confirm:{menu_key}")],
            [InlineKeyboardButton(text="❌ Cancelar", callback_data=f"adm_btn:menu:{menu_key}")],
        ]
    )

    await callback.message.edit_text(
        f"⚠️ <b>LIMPAR MENU</b>\n\n"
        f"Vai remover TODOS os botões customizados do menu "
        f"<b>{MENUS.get(menu_key, menu_key)}</b>.\n\n"
        "O bot voltará a usar os <b>padrões de fábrica</b> neste menu.\n\n"
        "Confirma?",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_btn:clear_confirm:"))
async def cb_button_clear_confirm(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    menu_key = callback.data.split(":")[2]

    stmt = select(ButtonTemplate).where(ButtonTemplate.menu == menu_key)
    result = await session.execute(stmt)
    buttons = list(result.scalars().all())

    for b in buttons:
        await session.delete(b)

    await _log_audit(
        session,
        callback.from_user.id,
        "clear_button_menu",
        old_value={"menu": menu_key, "removed": len(buttons)},
    )

    await callback.answer(
        f"🗑 {len(buttons)} botão(ões) removido(s). Padrões restaurados.",
        show_alert=True,
    )

    callback.data = f"adm_btn:menu:{menu_key}"
    await cb_buttons_list(callback, session)

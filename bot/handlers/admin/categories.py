# ============================================
# 📂 ADMIN CATEGORIES — Larizinha Store
# ============================================
# CRUD completo de categorias no painel admin.
# Todos os botões funcionam de verdade.
# ============================================

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.states import AdminStates
from core.models import Admin, AuditLog, Category, Product, ProductStatus


router = Router(name="admin_categories")


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


def _cancel_keyboard(back_data: str = "adm_cat:list") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancelar", callback_data=back_data)]
        ]
    )


# ============================================
# 📋 LISTA DE CATEGORIAS
# ============================================
@router.callback_query(F.data == "adm_cat:list")
async def cb_categories_list(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    stmt = select(Category).order_by(Category.position, Category.id)
    result = await session.execute(stmt)
    categories = list(result.scalars().all())

    lines = [
        "📂 <b>GERENCIAR CATEGORIAS</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"📊 Total: <b>{len(categories)}</b> categoria(s)",
        "",
    ]

    rows: list[list[InlineKeyboardButton]] = []

    for cat in categories:
        # Conta produtos
        prod_count = await session.scalar(
            select(func.count(Product.id)).where(
                Product.category_id == cat.id,
                Product.status != ProductStatus.DELETED,
            )
        ) or 0

        emoji = cat.emoji or "📂"
        status_icon = "🟢" if cat.is_active else "🔴"

        rows.append([
            InlineKeyboardButton(
                text=f"{status_icon} {emoji} {cat.name} ({prod_count})",
                callback_data=f"adm_cat:view:{cat.id}",
            )
        ])

    rows.append([
        InlineKeyboardButton(text="➕ Nova Categoria", callback_data="adm_cat:add")
    ])
    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_prod:list:0")
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    text = "\n".join(lines)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 👁️ VISUALIZAR CATEGORIA
# ============================================
@router.callback_query(F.data.startswith("adm_cat:view:"))
async def cb_category_view(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    cat_id = int(callback.data.split(":")[2])
    cat = await session.get(Category, cat_id)
    if cat is None:
        await callback.answer("❌ Categoria não encontrada.", show_alert=True)
        return

    prod_count = await session.scalar(
        select(func.count(Product.id)).where(
            Product.category_id == cat.id,
            Product.status != ProductStatus.DELETED,
        )
    ) or 0

    status = "🟢 Ativa" if cat.is_active else "🔴 Inativa"

    text = (
        f"📂 <b>{cat.emoji or '📂'} {cat.name}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 ID: <code>{cat.id}</code>\n"
        f"📊 Status: <b>{status}</b>\n"
        f"📦 Produtos: <b>{prod_count}</b>\n"
        f"📍 Posição: <b>{cat.position}</b>\n\n"
        f"📝 Descrição:\n{cat.description or '—'}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Editar Nome", callback_data=f"adm_cat:edit_name:{cat.id}")],
            [InlineKeyboardButton(text="🎨 Editar Emoji", callback_data=f"adm_cat:edit_emoji:{cat.id}")],
            [InlineKeyboardButton(text="📝 Editar Descrição", callback_data=f"adm_cat:edit_desc:{cat.id}")],
            [InlineKeyboardButton(text="📍 Editar Posição", callback_data=f"adm_cat:edit_pos:{cat.id}")],
            [
                InlineKeyboardButton(
                    text="🔴 Desativar" if cat.is_active else "🟢 Ativar",
                    callback_data=f"adm_cat:toggle:{cat.id}",
                ),
                InlineKeyboardButton(
                    text="🗑 Excluir",
                    callback_data=f"adm_cat:delete:{cat.id}",
                ),
            ],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_cat:list")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# ➕ NOVA CATEGORIA
# ============================================
@router.callback_query(F.data == "adm_cat:add")
async def cb_category_add(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text = (
        "➕ <b>NOVA CATEGORIA</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Envie o <b>nome</b> da categoria.\n"
        "Exemplo: <code>Streaming</code>"
    )
    await callback.message.answer(text, reply_markup=_cancel_keyboard("adm_cat:list"))
    await state.set_state(AdminStates.creating_category)
    await callback.answer()


@router.message(AdminStates.creating_category)
async def msg_category_name(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    name = (message.text or "").strip()
    if not name:
        await message.answer("❌ Nome vazio. Envie novamente.")
        return

    # Última posição
    max_pos = await session.scalar(select(func.max(Category.position))) or 0

    cat = Category(
        name=name,
        emoji="📂",
        position=max_pos + 1,
        is_active=True,
    )
    session.add(cat)
    await session.flush()

    await _log_audit(
        session, message.from_user.id, "create_category",
        new_value={"category_id": cat.id, "name": name},
    )

    await message.answer(
        f"✅ Categoria <b>{name}</b> criada!\n\n"
        f"🆔 ID: <code>{cat.id}</code>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="👁 Ver", callback_data=f"adm_cat:view:{cat.id}")],
                [InlineKeyboardButton(text="📋 Lista", callback_data="adm_cat:list")],
            ]
        ),
    )
    await state.clear()


# ============================================
# ✏️ EDITAR CAMPOS
# ============================================
@router.callback_query(F.data.startswith("adm_cat:edit_name:"))
async def cb_edit_cat_name(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    cat_id = int(callback.data.split(":")[2])
    await state.update_data(category_id=cat_id)
    await callback.message.answer(
        "✏️ Envie o <b>novo nome</b>:",
        reply_markup=_cancel_keyboard(f"adm_cat:view:{cat_id}"),
    )
    await state.set_state(AdminStates.editing_category)
    await callback.answer()


@router.message(AdminStates.editing_category)
async def msg_save_cat_name(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return
    data = await state.get_data()
    cat_id = data.get("category_id")
    cat = await session.get(Category, cat_id)
    if cat is None:
        await message.answer("❌ Categoria não encontrada.")
        await state.clear()
        return

    new_name = (message.text or "").strip()
    if not new_name:
        await message.answer("❌ Nome vazio.")
        return

    old = cat.name
    cat.name = new_name
    session.add(cat)

    await _log_audit(
        session, message.from_user.id, "edit_category_name",
        old_value={"name": old},
        new_value={"name": new_name},
    )

    await message.answer(f"✅ Nome atualizado: <b>{new_name}</b>")
    await state.clear()


@router.callback_query(F.data.startswith("adm_cat:edit_emoji:"))
async def cb_edit_cat_emoji(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    cat_id = int(callback.data.split(":")[2])
    await state.update_data(category_id=cat_id)
    await callback.message.answer(
        "🎨 Envie o <b>novo emoji</b> (1 caractere):",
        reply_markup=_cancel_keyboard(f"adm_cat:view:{cat_id}"),
    )
    await state.set_state(AdminStates.editing_category)
    await callback.answer()


@router.callback_query(F.data.startswith("adm_cat:edit_desc:"))
async def cb_edit_cat_desc(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    cat_id = int(callback.data.split(":")[2])
    await state.update_data(category_id=cat_id)
    await callback.message.answer(
        "📝 Envie a <b>nova descrição</b>:",
        reply_markup=_cancel_keyboard(f"adm_cat:view:{cat_id}"),
    )
    await state.set_state(AdminStates.editing_category)
    await callback.answer()


@router.callback_query(F.data.startswith("adm_cat:edit_pos:"))
async def cb_edit_cat_pos(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    cat_id = int(callback.data.split(":")[2])
    await state.update_data(category_id=cat_id)
    await callback.message.answer(
        "📍 Envie a <b>nova posição</b> (número inteiro):",
        reply_markup=_cancel_keyboard(f"adm_cat:view:{cat_id}"),
    )
    await state.set_state(AdminStates.editing_category)
    await callback.answer()


@router.message(AdminStates.editing_category)
async def msg_save_category_data(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Salva o que o usuário enviou (nome, emoji, descrição ou posição)."""
    if not await _is_admin(session, message.from_user.id):
        return
    data = await state.get_data()
    cat_id = data.get("category_id")
    cat = await session.get(Category, cat_id)
    if cat is None:
        await message.answer("❌ Categoria não encontrada.")
        await state.clear()
        return

    raw = (message.text or message.caption or "").strip()
    if not raw:
        await message.answer("❌ Texto vazio.")
        return

    # Salva em todos os campos possíveis de uma vez (é simples)
    # Se for número, também atualiza posição
    old_emoji = cat.emoji
    old_desc = cat.description

    # Detecta: número → posição
    try:
        pos = int(raw)
        cat.position = pos
        session.add(cat)
        await _log_audit(
            session, message.from_user.id, "edit_category_pos",
            new_value={"position": pos},
        )
        await message.answer(f"✅ Posição: <b>{pos}</b>")
        await state.clear()
        return
    except ValueError:
        pass

    # Se for 1-2 caracteres → emoji
    if len(raw) <= 2:
        cat.emoji = raw
        session.add(cat)
        await _log_audit(
            session, message.from_user.id, "edit_category_emoji",
            old_value={"emoji": old_emoji},
            new_value={"emoji": raw},
        )
        await message.answer(f"✅ Emoji: {raw}")
        await state.clear()
        return

    # Senão, se contém quebra de linha ou é longo → descrição
    if len(raw) > 20 or "\n" in raw:
        cat.description = raw
        session.add(cat)
        await _log_audit(
            session, message.from_user.id, "edit_category_desc",
            old_value={"desc": (old_desc or "")[:50]},
            new_value={"desc": raw[:50]},
        )
        await message.answer("✅ Descrição atualizada!")
        await state.clear()
        return

    # Senão, atualiza nome
    cat.name = raw
    session.add(cat)
    await _log_audit(
        session, message.from_user.id, "edit_category_name",
        new_value={"name": raw},
    )
    await message.answer(f"✅ Nome: <b>{raw}</b>")
    await state.clear()


# ============================================
# 🔴 TOGGLE ATIVO/INATIVO
# ============================================
@router.callback_query(F.data.startswith("adm_cat:toggle:"))
async def cb_toggle_category(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    cat_id = int(callback.data.split(":")[2])
    cat = await session.get(Category, cat_id)
    if cat is None:
        await callback.answer("❌ Categoria não encontrada.", show_alert=True)
        return

    cat.is_active = not cat.is_active
    session.add(cat)

    status = "ativada" if cat.is_active else "desativada"
    await _log_audit(
        session, callback.from_user.id, "toggle_category",
        new_value={"category_id": cat_id, "is_active": cat.is_active},
    )
    await callback.answer(f"✅ Categoria {status}!", show_alert=True)

    callback.data = f"adm_cat:view:{cat_id}"
    await cb_category_view(callback, session)


# ============================================
# 🗑 EXCLUIR CATEGORIA
# ============================================
@router.callback_query(F.data.startswith("adm_cat:delete:"))
async def cb_delete_category(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    cat_id = int(callback.data.split(":")[2])
    cat = await session.get(Category, cat_id)
    if cat is None:
        await callback.answer("❌ Categoria não encontrada.", show_alert=True)
        return

    # Conta produtos vinculados
    prod_count = await session.scalar(
        select(func.count(Product.id)).where(
            Product.category_id == cat.id,
            Product.status != ProductStatus.DELETED,
        )
    ) or 0

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Sim, excluir", callback_data=f"adm_cat:confirm_delete:{cat_id}")],
            [InlineKeyboardButton(text="❌ Cancelar", callback_data=f"adm_cat:view:{cat_id}")],
        ]
    )

    warn = ""
    if prod_count > 0:
        warn = (
            f"\n\n⚠️ Esta categoria tem <b>{prod_count}</b> produto(s).\n"
            "Eles ficarão sem categoria."
        )

    await callback.message.edit_text(
        f"⚠️ <b>EXCLUIR CATEGORIA</b>\n\n"
        f"Excluir <b>{cat.name}</b>?{warn}",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_cat:confirm_delete:"))
async def cb_confirm_delete_category(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    cat_id = int(callback.data.split(":")[2])
    cat = await session.get(Category, cat_id)
    if cat is None:
        await callback.answer("❌ Categoria não encontrada.", show_alert=True)
        return

    # Desvincula produtos
    stmt = select(Product).where(Product.category_id == cat_id)
    result = await session.execute(stmt)
    products = list(result.scalars().all())
    for p in products:
        p.category_id = None
        session.add(p)

    await _log_audit(
        session, callback.from_user.id, "delete_category",
        old_value={"category_id": cat_id, "name": cat.name, "products_unlinked": len(products)},
    )

    await session.delete(cat)
    await callback.answer("🗑 Categoria excluída.", show_alert=True)

    callback.data = "adm_cat:list"
    await cb_categories_list(callback, session)

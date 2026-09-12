# ============================================
# 📦 ADMIN PRODUCTS — Larizinha Store
# ============================================
# CRUD completo de produtos no painel admin.
# Todos os botões funcionam de verdade.
# ============================================

from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.states import AdminStates
from core.models import (
    Admin,
    AuditLog,
    Category,
    Product,
    ProductStatus,
    StockItem,
    StockStatus,
)


router = Router(name="admin_products")


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


def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:config")]
        ]
    )


def _cancel_keyboard(back_data: str = "adm_prod:list") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancelar", callback_data=back_data)]
        ]
    )


# ============================================
# 📋 LISTA DE PRODUTOS
# ============================================
@router.callback_query(F.data == "adm_cfg:logins")
async def cb_products_root(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    """Entrada: gerenciar produtos e estoque."""
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await _show_products_list(callback, session, page=0)


@router.callback_query(F.data.startswith("adm_prod:list"))
async def cb_products_list(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    parts = callback.data.split(":")
    page = int(parts[2]) if len(parts) > 2 else 0
    await _show_products_list(callback, session, page)


async def _show_products_list(
    callback: CallbackQuery,
    session: AsyncSession,
    page: int = 0,
) -> None:
    PER_PAGE = 10

    total = await session.scalar(
        select(func.count(Product.id)).where(Product.status != ProductStatus.DELETED)
    ) or 0

    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    stmt = (
        select(Product)
        .where(Product.status != ProductStatus.DELETED)
        .order_by(Product.position, Product.id)
        .offset(page * PER_PAGE)
        .limit(PER_PAGE)
    )
    result = await session.execute(stmt)
    products = list(result.scalars().all())

    lines = [
        "📦 <b>GERENCIAR PRODUTOS</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"📊 Total: <b>{total}</b> produto(s)",
        "",
    ]

    rows: list[list[InlineKeyboardButton]] = []

    for p in products:
        stock = await session.scalar(
            select(func.count(StockItem.id)).where(
                StockItem.product_id == p.id,
                StockItem.status == StockStatus.AVAILABLE,
            )
        ) or 0

        emoji = p.emoji or "🎬"
        price = f"{p.price:.2f}".replace(".", ",")
        status_icon = "🟢" if p.status == ProductStatus.ACTIVE else "🔴"

        rows.append([
            InlineKeyboardButton(
                text=f"{status_icon} {emoji} {p.name} — R$ {price} ({stock})",
                callback_data=f"adm_prod:view:{p.id}",
            )
        ])

    if total_pages > 1:
        nav_row: list[InlineKeyboardButton] = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(
                text="⬅️",
                callback_data=f"adm_prod:list:{page - 1}",
            ))
        nav_row.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="adm:noop",
        ))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                text="➡️",
                callback_data=f"adm_prod:list:{page + 1}",
            ))
        rows.append(nav_row)

    rows.append([
        InlineKeyboardButton(text="➕ Novo Produto", callback_data="adm_prod:add")
    ])
    rows.append([
        InlineKeyboardButton(text="📂 Categorias", callback_data="adm_cat:list")
    ])
    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:config")
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    text = "\n".join(lines)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 👁️ VISUALIZAR PRODUTO
# ============================================
@router.callback_query(F.data.startswith("adm_prod:view:"))
async def cb_product_view(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    product_id = int(callback.data.split(":")[2])
    product = await session.get(Product, product_id)
    if product is None:
        await callback.answer("❌ Produto não encontrado.", show_alert=True)
        return

    stock_total = await session.scalar(
        select(func.count(StockItem.id)).where(StockItem.product_id == product.id)
    ) or 0
    stock_available = await session.scalar(
        select(func.count(StockItem.id)).where(
            StockItem.product_id == product.id,
            StockItem.status == StockStatus.AVAILABLE,
        )
    ) or 0

    cat_name = "—"
    if product.category_id:
        cat = await session.get(Category, product.category_id)
        cat_name = cat.name if cat else "—"

    price = f"{product.price:.2f}".replace(".", ",")

    text = (
        f"📦 <b>{product.emoji or '🎬'} {product.name}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 ID: <code>{product.id}</code>\n"
        f"💰 Preço: <b>R$ {price}</b>\n"
        f"📂 Categoria: <b>{cat_name}</b>\n"
        f"📊 Status: <b>{product.status.value}</b>\n"
        f"⏳ Duração: <b>{product.duration_days} dias</b>\n"
        f"🛡 Garantia: <b>{product.warranty_days} dias</b>\n"
        f"🔢 Min/Max: <b>{product.min_quantity}/{product.max_quantity}</b>\n\n"
        f"📦 Estoque total: <b>{stock_total}</b>\n"
        f"🟢 Disponível: <b>{stock_available}</b>\n\n"
        f"📝 Descrição:\n{product.description or '—'}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Editar Nome", callback_data=f"adm_prod:edit_name:{product.id}")],
            [InlineKeyboardButton(text="💰 Editar Preço", callback_data=f"adm_prod:edit_price:{product.id}")],
            [InlineKeyboardButton(text="📝 Editar Descrição", callback_data=f"adm_prod:edit_desc:{product.id}")],
            [InlineKeyboardButton(text="🎨 Editar Emoji", callback_data=f"adm_prod:edit_emoji:{product.id}")],
            [InlineKeyboardButton(text="⏳ Editar Duração", callback_data=f"adm_prod:edit_duration:{product.id}")],
            [InlineKeyboardButton(text="🛡 Editar Garantia", callback_data=f"adm_prod:edit_warranty:{product.id}")],
            [InlineKeyboardButton(text="🔢 Editar Min/Max", callback_data=f"adm_prod:edit_qty:{product.id}")],
            [InlineKeyboardButton(text="📂 Mudar Categoria", callback_data=f"adm_prod:edit_cat:{product.id}")],
            [
                InlineKeyboardButton(
                    text="🔴 Pausar" if product.status == ProductStatus.ACTIVE else "🟢 Ativar",
                    callback_data=f"adm_prod:toggle:{product.id}",
                ),
                InlineKeyboardButton(
                    text="🗑 Excluir",
                    callback_data=f"adm_prod:delete:{product.id}",
                ),
            ],
            [InlineKeyboardButton(text="🔐 Estoque deste produto", callback_data=f"adm_stock:view:{product.id}")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_prod:list:0")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# ➕ NOVO PRODUTO
# ============================================
@router.callback_query(F.data == "adm_prod:add")
async def cb_product_add(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text = (
        "➕ <b>NOVO PRODUTO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Envie o <b>nome</b> do produto.\n"
        "Exemplo: <code>HBO MAX</code>"
    )
    await callback.message.answer(text, reply_markup=_cancel_keyboard("adm_prod:list:0"))
    await state.set_state(AdminStates.creating_product)
    await callback.answer()


@router.message(AdminStates.creating_product)
async def msg_product_name(
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

    # Cria produto com valores padrão
    product = Product(
        name=name,
        price=Decimal("0.00"),
        description="Descrição do produto.",
        status=ProductStatus.ACTIVE,
        duration_days=30,
        warranty_days=30,
        min_quantity=1,
        max_quantity=10,
    )
    session.add(product)
    await session.flush()

    await _log_audit(
        session, message.from_user.id, "create_product",
        new_value={"product_id": product.id, "name": name},
    )

    await message.answer(
        f"✅ Produto <b>{name}</b> criado!\n\n"
        f"🆔 ID: <code>{product.id}</code>\n\n"
        "Configure preço, descrição e categoria.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="👁 Ver produto", callback_data=f"adm_prod:view:{product.id}")],
                [InlineKeyboardButton(text="📋 Lista", callback_data="adm_prod:list:0")],
            ]
        ),
    )
    await state.clear()


# ============================================
# ✏️ EDITAR CAMPOS
# ============================================
@router.callback_query(F.data.startswith("adm_prod:edit_name:"))
async def cb_edit_name(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    pid = int(callback.data.split(":")[2])
    await state.update_data(product_id=pid)
    await callback.message.answer(
        "✏️ Envie o <b>novo nome</b> do produto:",
        reply_markup=_cancel_keyboard(f"adm_prod:view:{pid}"),
    )
    await state.set_state(AdminStates.editing_product_name)
    await callback.answer()


@router.message(AdminStates.editing_product_name)
async def msg_save_name(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return
    data = await state.get_data()
    pid = data.get("product_id")
    product = await session.get(Product, pid)
    if product is None:
        await message.answer("❌ Produto não encontrado.")
        await state.clear()
        return

    new_name = (message.text or "").strip()
    if not new_name:
        await message.answer("❌ Nome vazio.")
        return

    old = product.name
    product.name = new_name
    session.add(product)

    await _log_audit(
        session, message.from_user.id, "edit_product_name",
        old_value={"name": old},
        new_value={"name": new_name},
    )

    await message.answer(f"✅ Nome atualizado: <b>{new_name}</b>")
    await state.clear()


@router.callback_query(F.data.startswith("adm_prod:edit_price:"))
async def cb_edit_price(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    pid = int(callback.data.split(":")[2])
    await state.update_data(product_id=pid)
    await callback.message.answer(
        "💰 Envie o <b>novo preço</b> em reais (ex: <code>8.00</code>):",
        reply_markup=_cancel_keyboard(f"adm_prod:view:{pid}"),
    )
    await state.set_state(AdminStates.editing_product_price)
    await callback.answer()


@router.message(AdminStates.editing_product_price)
async def msg_save_price(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return
    data = await state.get_data()
    pid = data.get("product_id")
    product = await session.get(Product, pid)
    if product is None:
        await message.answer("❌ Produto não encontrado.")
        await state.clear()
        return

    raw = (message.text or "").replace(",", ".").strip()
    try:
        val = Decimal(raw)
        if val < 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer("❌ Valor inválido. Ex: <code>8.00</code>")
        return

    old = f"{product.price:.2f}"
    product.price = val.quantize(Decimal("0.01"))
    session.add(product)

    await _log_audit(
        session, message.from_user.id, "edit_product_price",
        old_value={"price": old},
        new_value={"price": str(product.price)},
    )

    await message.answer(f"✅ Preço atualizado: <b>R$ {product.price:.2f}</b>")
    await state.clear()


@router.callback_query(F.data.startswith("adm_prod:edit_desc:"))
async def cb_edit_desc(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    pid = int(callback.data.split(":")[2])
    await state.update_data(product_id=pid)
    await callback.message.answer(
        "📝 Envie a <b>nova descrição</b> (pode usar várias linhas):",
        reply_markup=_cancel_keyboard(f"adm_prod:view:{pid}"),
    )
    await state.set_state(AdminStates.editing_product_description)
    await callback.answer()


@router.message(AdminStates.editing_product_description)
async def msg_save_desc(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return
    data = await state.get_data()
    pid = data.get("product_id")
    product = await session.get(Product, pid)
    if product is None:
        await message.answer("❌ Produto não encontrado.")
        await state.clear()
        return

    new_desc = message.text or message.caption or ""
    product.description = new_desc
    session.add(product)

    await _log_audit(
        session, message.from_user.id, "edit_product_desc",
        new_value={"description_preview": new_desc[:100]},
    )

    await message.answer("✅ Descrição atualizada!")
    await state.clear()


@router.callback_query(F.data.startswith("adm_prod:edit_emoji:"))
async def cb_edit_emoji(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    pid = int(callback.data.split(":")[2])
    await state.update_data(product_id=pid)
    await callback.message.answer(
        "🎨 Envie o <b>novo emoji</b> (1 caractere):",
        reply_markup=_cancel_keyboard(f"adm_prod:view:{pid}"),
    )
    await state.set_state(AdminStates.editing_product_image)
    await callback.answer()


@router.message(AdminStates.editing_product_image)
async def msg_save_emoji(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return
    data = await state.get_data()
    pid = data.get("product_id")
    product = await session.get(Product, pid)
    if product is None:
        await message.answer("❌ Produto não encontrado.")
        await state.clear()
        return

    emoji = (message.text or "").strip()[:2]
    product.emoji = emoji
    session.add(product)
    await message.answer(f"✅ Emoji atualizado: {emoji}")
    await state.clear()


@router.callback_query(F.data.startswith("adm_prod:edit_duration:"))
async def cb_edit_duration(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    pid = int(callback.data.split(":")[2])
    await state.update_data(product_id=pid)
    await callback.message.answer(
        "⏳ Envie a <b>duração em dias</b> (ex: <code>30</code>):",
        reply_markup=_cancel_keyboard(f"adm_prod:view:{pid}"),
    )
    await state.set_state(AdminStates.editing_product_duration)
    await callback.answer()


@router.message(AdminStates.editing_product_duration)
async def msg_save_duration(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return
    data = await state.get_data()
    pid = data.get("product_id")
    product = await session.get(Product, pid)
    if product is None:
        await message.answer("❌ Produto não encontrado.")
        await state.clear()
        return
    try:
        val = int((message.text or "").strip())
        if val <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Número inválido.")
        return
    product.duration_days = val
    session.add(product)
    await message.answer(f"✅ Duração: <b>{val} dias</b>")
    await state.clear()


@router.callback_query(F.data.startswith("adm_prod:edit_warranty:"))
async def cb_edit_warranty(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    pid = int(callback.data.split(":")[2])
    await state.update_data(product_id=pid)
    await callback.message.answer(
        "🛡 Envie a <b>garantia em dias</b>:",
        reply_markup=_cancel_keyboard(f"adm_prod:view:{pid}"),
    )
    await state.set_state(AdminStates.editing_product_warranty)
    await callback.answer()


@router.message(AdminStates.editing_product_warranty)
async def msg_save_warranty(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return
    data = await state.get_data()
    pid = data.get("product_id")
    product = await session.get(Product, pid)
    if product is None:
        await message.answer("❌ Produto não encontrado.")
        await state.clear()
        return
    try:
        val = int((message.text or "").strip())
        if val < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Número inválido.")
        return
    product.warranty_days = val
    session.add(product)
    await message.answer(f"✅ Garantia: <b>{val} dias</b>")
    await state.clear()


@router.callback_query(F.data.startswith("adm_prod:edit_qty:"))
async def cb_edit_qty(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    pid = int(callback.data.split(":")[2])
    await state.update_data(product_id=pid)
    await callback.message.answer(
        "🔢 Envie o <b>min e max</b> separados por vírgula.\n"
        "Exemplo: <code>1,10</code>",
        reply_markup=_cancel_keyboard(f"adm_prod:view:{pid}"),
    )
    await state.set_state(AdminStates.editing_product_min_qty)
    await callback.answer()


@router.message(AdminStates.editing_product_min_qty)
async def msg_save_qty(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return
    data = await state.get_data()
    pid = data.get("product_id")
    product = await session.get(Product, pid)
    if product is None:
        await message.answer("❌ Produto não encontrado.")
        await state.clear()
        return
    raw = (message.text or "").replace(" ", "")
    parts = raw.split(",")
    if len(parts) != 2:
        await message.answer("❌ Envie no formato <code>1,10</code>.")
        return
    try:
        mn = int(parts[0])
        mx = int(parts[1])
        if mn <= 0 or mx < mn:
            raise ValueError
    except ValueError:
        await message.answer("❌ Valores inválidos.")
        return
    product.min_quantity = mn
    product.max_quantity = mx
    session.add(product)
    await message.answer(f"✅ Min/Max: <b>{mn}/{mx}</b>")
    await state.clear()


# ============================================
# 📂 MUDAR CATEGORIA
# ============================================
@router.callback_query(F.data.startswith("adm_prod:edit_cat:"))
async def cb_edit_cat(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    pid = int(callback.data.split(":")[2])

    stmt = select(Category).where(Category.is_active.is_(True)).order_by(Category.name)
    result = await session.execute(stmt)
    categories = list(result.scalars().all())

    if not categories:
        await callback.answer("❌ Nenhuma categoria cadastrada.", show_alert=True)
        return

    rows: list[list[InlineKeyboardButton]] = []
    for cat in categories:
        emoji = cat.emoji or "📂"
        rows.append([
            InlineKeyboardButton(
                text=f"{emoji} {cat.name}",
                callback_data=f"adm_prod:set_cat:{pid}:{cat.id}",
            )
        ])
    rows.append([
        InlineKeyboardButton(text="❌ Sem categoria", callback_data=f"adm_prod:set_cat:{pid}:0")
    ])
    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data=f"adm_prod:view:{pid}")
    ])

    await callback.message.edit_text(
        "📂 <b>Mudar Categoria</b>\n\nEscolha:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_prod:set_cat:"))
async def cb_set_cat(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    parts = callback.data.split(":")
    pid, cat_id = int(parts[2]), int(parts[3])

    product = await session.get(Product, pid)
    if product is None:
        await callback.answer("❌ Produto não encontrado.", show_alert=True)
        return

    product.category_id = cat_id if cat_id > 0 else None
    session.add(product)
    await callback.answer("✅ Categoria atualizada!", show_alert=True)

    # Reexibe o produto
    callback.data = f"adm_prod:view:{pid}"
    await cb_product_view(callback, session)


# ============================================
# 🔴 TOGGLE ATIVO/PAUSADO
# ============================================
@router.callback_query(F.data.startswith("adm_prod:toggle:"))
async def cb_toggle_product(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    pid = int(callback.data.split(":")[2])
    product = await session.get(Product, pid)
    if product is None:
        await callback.answer("❌ Produto não encontrado.", show_alert=True)
        return

    if product.status == ProductStatus.ACTIVE:
        product.status = ProductStatus.PAUSED
        new_status = "pausado"
    else:
        product.status = ProductStatus.ACTIVE
        new_status = "ativado"

    session.add(product)
    await _log_audit(
        session, callback.from_user.id, "toggle_product",
        new_value={"product_id": pid, "status": product.status.value},
    )
    await callback.answer(f"✅ Produto {new_status}!", show_alert=True)

    callback.data = f"adm_prod:view:{pid}"
    await cb_product_view(callback, session)


# ============================================
# 🗑 EXCLUIR PRODUTO
# ============================================
@router.callback_query(F.data.startswith("adm_prod:delete:"))
async def cb_delete_product(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    pid = int(callback.data.split(":")[2])
    product = await session.get(Product, pid)
    if product is None:
        await callback.answer("❌ Produto não encontrado.", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Sim, excluir", callback_data=f"adm_prod:confirm_delete:{pid}")],
            [InlineKeyboardButton(text="❌ Cancelar", callback_data=f"adm_prod:view:{pid}")],
        ]
    )

    await callback.message.edit_text(
        f"⚠️ <b>EXCLUIR PRODUTO</b>\n\n"
        f"Você tem certeza que quer excluir <b>{product.name}</b>?\n\n"
        f"Os logins vinculados continuarão no banco, mas o produto "
        f"não aparecerá mais no catálogo.",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_prod:confirm_delete:"))
async def cb_confirm_delete(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    pid = int(callback.data.split(":")[2])
    product = await session.get(Product, pid)
    if product is None:
        await callback.answer("❌ Produto não encontrado.", show_alert=True)
        return

    product.status = ProductStatus.DELETED
    session.add(product)
    await _log_audit(
        session, callback.from_user.id, "delete_product",
        old_value={"product_id": pid, "name": product.name},
    )
    await callback.answer("🗑 Produto excluído.", show_alert=True)

    callback.data = "adm_prod:list:0"
    await cb_products_list(callback, session)

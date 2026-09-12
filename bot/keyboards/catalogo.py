# ============================================
# 📂 CATÁLOGO — Larizinha Store
# ============================================
# Teclados do catálogo de produtos e navegação
# por categorias. Suporta paginação.
# ============================================

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Category, Product, ProductStatus, StockItem, StockStatus


# ============================================
# 📄 CONFIGURAÇÃO DE PAGINAÇÃO
# ============================================
ITEMS_PER_PAGE = 8


# ============================================
# 🗂️ TECLADO DE CATEGORIAS
# ============================================
async def build_categories_keyboard(
    session: AsyncSession,
    page: int = 0,
) -> InlineKeyboardMarkup:
    """Lista categorias ativas com paginação."""
    total = await session.scalar(
        select(func.count(Category.id)).where(Category.is_active.is_(True))
    ) or 0

    total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    stmt = (
        select(Category)
        .where(Category.is_active.is_(True))
        .order_by(Category.position, Category.id)
        .offset(page * ITEMS_PER_PAGE)
        .limit(ITEMS_PER_PAGE)
    )
    result = await session.execute(stmt)
    categories = result.scalars().all()

    rows: list[list[InlineKeyboardButton]] = []

    for cat in categories:
        emoji = cat.emoji or "📦"
        text = f"{emoji} {cat.name}"
        rows.append([
            InlineKeyboardButton(
                text=text,
                callback_data=f"cat:open:{cat.id}:0",
            )
        ])

    # Paginação
    if total_pages > 1:
        nav_row: list[InlineKeyboardButton] = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(
                text="⬅️ Anterior",
                callback_data=f"cat:page:{page - 1}",
            ))
        nav_row.append(InlineKeyboardButton(
            text=f"📄 {page + 1}/{total_pages}",
            callback_data="cat:noop",
        ))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                text="Próxima ➡️",
                callback_data=f"cat:page:{page + 1}",
            ))
        rows.append(nav_row)

    # Voltar
    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="menu:voltar")
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================
# 📦 TECLADO DE PRODUTOS DA CATEGORIA
# ============================================
async def build_products_keyboard(
    session: AsyncSession,
    category_id: int,
    page: int = 0,
) -> InlineKeyboardMarkup:
    """Lista produtos de uma categoria com paginação."""
    base_filter = (
        Product.category_id == category_id,
        Product.status == ProductStatus.ACTIVE,
    )

    total = await session.scalar(
        select(func.count(Product.id)).where(*base_filter)
    ) or 0

    total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    stmt = (
        select(Product)
        .where(*base_filter)
        .order_by(Product.position, Product.id)
        .offset(page * ITEMS_PER_PAGE)
        .limit(ITEMS_PER_PAGE)
    )
    result = await session.execute(stmt)
    products = result.scalars().all()

    rows: list[list[InlineKeyboardButton]] = []

    for prod in products:
        # Conta estoque disponível
        stock_count = await session.scalar(
            select(func.count(StockItem.id)).where(
                StockItem.product_id == prod.id,
                StockItem.status == StockStatus.AVAILABLE,
            )
        ) or 0

        emoji = prod.emoji or "🎬"
        price = f"R$ {prod.price:.2f}".replace(".", ",")
        text = f"{emoji} {prod.name} — {price}"

        if stock_count == 0:
            text = f"❌ {prod.name} — ESGOTADO"

        rows.append([
            InlineKeyboardButton(
                text=text,
                callback_data=f"prod:view:{prod.id}:0",
            )
        ])

    # Paginação
    if total_pages > 1:
        nav_row: list[InlineKeyboardButton] = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(
                text="⬅️ Anterior",
                callback_data=f"cat:open:{category_id}:{page - 1}",
            ))
        nav_row.append(InlineKeyboardButton(
            text=f"📄 {page + 1}/{total_pages}",
            callback_data="cat:noop",
        ))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                text="Próxima ➡️",
                callback_data=f"cat:open:{category_id}:{page + 1}",
            ))
        rows.append(nav_row)

    # Voltar para categorias
    rows.append([
        InlineKeyboardButton(
            text="🔙 Voltar",
            callback_data="cat:voltar",
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================
# 🗂️ TECLADO DE CATÁLOGO COMPLETO (sem categoria)
# ============================================
async def build_full_catalog_keyboard(
    session: AsyncSession,
    page: int = 0,
) -> InlineKeyboardMarkup:
    """Lista TODOS os produtos ativos (ignora categoria)."""
    base_filter = (Product.status == ProductStatus.ACTIVE,)

    total = await session.scalar(
        select(func.count(Product.id)).where(*base_filter)
    ) or 0

    total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    stmt = (
        select(Product)
        .where(*base_filter)
        .order_by(Product.position, Product.id)
        .offset(page * ITEMS_PER_PAGE)
        .limit(ITEMS_PER_PAGE)
    )
    result = await session.execute(stmt)
    products = result.scalars().all()

    rows: list[list[InlineKeyboardButton]] = []

    for prod in products:
        stock_count = await session.scalar(
            select(func.count(StockItem.id)).where(
                StockItem.product_id == prod.id,
                StockItem.status == StockStatus.AVAILABLE,
            )
        ) or 0

        emoji = prod.emoji or "🎬"
        price = f"R$ {prod.price:.2f}".replace(".", ",")
        text = f"{emoji} {prod.name} — {price}"

        if stock_count == 0:
            text = f"❌ {prod.name} — ESGOTADO"

        rows.append([
            InlineKeyboardButton(
                text=text,
                callback_data=f"prod:view:{prod.id}:0",
            )
        ])

    if total_pages > 1:
        nav_row: list[InlineKeyboardButton] = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(
                text="⬅️ Anterior",
                callback_data=f"cat:full:{page - 1}",
            ))
        nav_row.append(InlineKeyboardButton(
            text=f"📄 {page + 1}/{total_pages}",
            callback_data="cat:noop",
        ))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                text="Próxima ➡️",
                callback_data=f"cat:full:{page + 1}",
            ))
        rows.append(nav_row)

    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="menu:voltar")
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)

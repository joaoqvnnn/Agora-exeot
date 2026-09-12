# ============================================
# 🔔 ALERTAS (CLIENTE) — Larizinha Store
# ============================================
# Cliente escolhe produtos para ser notificado
# quando voltarem ao estoque.
# Uma única mensagem editada, com paginação.
# ============================================

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import (
    Product,
    ProductStatus,
    StockAlert,
    StockItem,
    StockStatus,
    User,
)


router = Router(name="alertas_cliente")


# ============================================
# 🧰 AUXILIARES
# ============================================
async def _edit_or_send(callback: CallbackQuery, text: str, keyboard) -> None:
    try:
        await callback.message.edit_text(
            text, reply_markup=keyboard, disable_web_page_preview=True
        )
    except Exception:
        try:
            await callback.message.answer(
                text, reply_markup=keyboard, disable_web_page_preview=True
            )
        except Exception as e:
            logger.warning(f"⚠️ Falha ao exibir alertas: {e}")


async def _count_available_stock(
    session: AsyncSession,
    product_id: int,
) -> int:
    return await session.scalar(
        select(func.count(StockItem.id)).where(
            StockItem.product_id == product_id,
            StockItem.status == StockStatus.AVAILABLE,
        )
    ) or 0


async def _is_subscribed(
    session: AsyncSession,
    user_telegram_id: int,
    product_id: int,
) -> bool:
    result = await session.scalar(
        select(StockAlert).where(
            StockAlert.user_telegram_id == user_telegram_id,
            StockAlert.product_id == product_id,
            StockAlert.is_active.is_(True),
        )
    )
    return result is not None


# ============================================
# 🔔 MENU DE ALERTAS
# ============================================
@router.callback_query(F.data == "menu:alertas")
async def cb_alerts_menu(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    """Abre o menu de alertas."""
    from core.services import config as config_service

    enabled = await config_service.get_bool(session, "stock_alerts_enabled", True)

    if not enabled:
        await callback.answer(
            "⚠️ Sistema de alertas temporariamente desativado.",
            show_alert=True,
        )
        return

    await _show_alerts_page(callback, user, session, page=0)
    await callback.answer()


# ============================================
# 📄 EXIBIR PÁGINA DE ALERTAS
# ============================================
async def _show_alerts_page(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    page: int = 0,
) -> None:
    PER_PAGE = 8

    # Busca produtos ativos que permitem alerta
    stmt = (
        select(Product)
        .where(
            Product.status == ProductStatus.ACTIVE,
            Product.stock_alert_enabled.is_(True),
        )
        .order_by(Product.position, Product.name)
    )
    result = await session.execute(stmt)
    products = list(result.scalars().all())

    if not products:
        text = (
            "⚠️ <b>Sistema de Alertas</b>\n\n"
            "Nenhum produto disponível para alertas no momento."
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Voltar", callback_data="menu:voltar")]
            ]
        )
        await _edit_or_send(callback, text, keyboard)
        return

    total = len(products)
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    start = page * PER_PAGE
    page_products = products[start : start + PER_PAGE]

    # Monta cabeçalho
    text_lines = [
        "⚠️ <b>Sistema de /alertas</b>",
        "",
        "Seja notificado quando seu serviço favorito for abastecido 🤩",
        "",
        "🎯 Basta selecionar abaixo os serviços que você deseja ser "
        "notificado, e eu lhe avisarei sempre que for abastecido novas unidades.",
        "",
        "✅ Nossos produtos são de grandes demandas e acabam rápido, "
        "é importante que você seja notificado para aproveitar antes que acabe!",
        "",
        "📋 <b>Lista de serviços que você pode ser notificado:</b>",
        "",
    ]

    rows: list[list[InlineKeyboardButton]] = []

    for product in page_products:
        subscribed = await _is_subscribed(session, user.telegram_id, product.id)
        icon = "✅" if subscribed else "❌"

        stock = await _count_available_stock(session, product.id)
        stock_icon = "🟢" if stock > 0 else "🔴"

        emoji = product.emoji or "🎬"

        rows.append([
            InlineKeyboardButton(
                text=f"{icon} {emoji} {product.name} ({stock_icon} {stock})",
                callback_data=f"alert:toggle:{product.id}:{page}",
            )
        ])

    # Navegação
    if total_pages > 1:
        nav_row: list[InlineKeyboardButton] = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(
                text="⬅️ Anterior",
                callback_data=f"alert:page:{page - 1}",
            ))
        nav_row.append(InlineKeyboardButton(
            text=f"📄 {page + 1}/{total_pages}",
            callback_data="alert:noop",
        ))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                text="Próxima ➡️",
                callback_data=f"alert:page:{page + 1}",
            ))
        rows.append(nav_row)

    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="menu:voltar")
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    text = "\n".join(text_lines)

    if len(text) > 4000:
        text = text[:4000] + "\n\n<i>... (truncado)</i>"

    await _edit_or_send(callback, text, keyboard)

    user.last_menu = f"alertas_{page}"
    session.add(user)


# ============================================
# 🔔 TOGGLE ALERTA (inscrever/desinscrever)
# ============================================
@router.callback_query(F.data.startswith("alert:toggle:"))
async def cb_toggle_alert(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    parts = callback.data.split(":")
    try:
        product_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 0
    except (ValueError, IndexError):
        await callback.answer("❌ Dados inválidos.", show_alert=True)
        return

    product = await session.get(Product, product_id)
    if product is None:
        await callback.answer("❌ Produto não encontrado.", show_alert=True)
        return

    # Verifica se já existe
    stmt = select(StockAlert).where(
        StockAlert.user_telegram_id == user.telegram_id,
        StockAlert.product_id == product_id,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is not None and existing.is_active:
        # Desativa
        existing.is_active = False
        session.add(existing)
        await callback.answer(
            f"🔕 Você não será mais notificado sobre {product.name}.",
            show_alert=True,
        )
    else:
        if existing is not None:
            # Reativa
            existing.is_active = True
            session.add(existing)
        else:
            # Cria novo
            new_alert = StockAlert(
                user_telegram_id=user.telegram_id,
                product_id=product_id,
                is_active=True,
            )
            session.add(new_alert)
        await callback.answer(
            f"🔔 Você será notificado quando {product.name} for reabastecido!",
            show_alert=True,
        )

    # Recarrega a página
    await _show_alerts_page(callback, user, session, page=page)


# ============================================
# 📄 PAGINAÇÃO
# ============================================
@router.callback_query(F.data.startswith("alert:page:"))
async def cb_alerts_page(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    try:
        page = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        page = 0

    await _show_alerts_page(callback, user, session, page=page)
    await callback.answer()


# ============================================
# 🔘 NOOP
# ============================================
@router.callback_query(F.data == "alert:noop")
async def cb_alert_noop(callback: CallbackQuery) -> None:
    await callback.answer()

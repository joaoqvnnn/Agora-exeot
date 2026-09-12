# ============================================
# 🔎 PESQUISA (CLIENTE) — Larizinha Store
# ============================================
# Pesquisa inline de serviços.
# Cliente clica no botão → abre a pesquisa inline
# do Telegram (não polui o chat).
# ============================================

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
)
from loguru import logger
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.states import SearchStates
from core.config import settings
from core.models import (
    Product,
    ProductStatus,
    StockItem,
    StockStatus,
    User,
)
from core.services import config as config_service


router = Router(name="pesquisa")


# ============================================
# 🧰 AUXILIARES
# ============================================
def _format_brl(v) -> str:
    if v is None:
        return "0,00"
    return f"{float(v):.2f}".replace(".", ",")


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
            logger.warning(f"⚠️ Falha ao exibir: {e}")


# ============================================
# 🔎 BOTÃO "PESQUISAR SERVIÇOS" DO /start
# ============================================
@router.callback_query(F.data == "menu:pesquisa")
async def cb_search_menu(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    """Abre a interface de pesquisa."""
    enabled = await config_service.get_bool(session, "search_enabled", True)

    if not enabled:
        await callback.answer(
            "⚠️ A pesquisa está temporariamente desativada.",
            show_alert=True,
        )
        return

    bot_username = settings.telegram_bot_username or "meu_bot"

    text = (
        f"🔎 <b>Pesquisar Serviços</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Para pesquisar, toque no botão abaixo.\n\n"
        f"💡 Você também pode digitar em qualquer chat:\n"
        f"<code>@{bot_username} hbo</code>\n\n"
        f"Ou clique no botão para abrir a busca direto:"
    )

    # Link que abre a pesquisa inline já preparada
    query_url = f"https://t.me/{bot_username}?startchannel=1&start=psearch"

    # Botão de busca (via URL do próprio bot pra abrir inline)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🔎 Abrir busca",
                switch_inline_query_current_chat="",
            )],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="menu:voltar")],
        ]
    )

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()

    user.last_menu = "pesquisa"
    session.add(user)


# ============================================
# 🔎 INLINE QUERY — BUSCA INLINE
# ============================================
@router.inline_query()
async def inline_search(
    inline_query: InlineQuery,
    session: AsyncSession,
) -> None:
    """
    Handler de pesquisa inline.
    Cliente digita @bot nome_produto e vê os resultados.
    """
    query = (inline_query.query or "").strip().lower()

    # Configs
    max_results = await config_service.get_int(session, "search_max_results", 10)
    enabled = await config_service.get_bool(session, "search_enabled", True)

    if not enabled:
        await inline_query.answer(
            results=[],
            cache_time=5,
            is_personal=True,
        )
        return

    # Busca produtos
    stmt = (
        select(Product)
        .where(
            Product.status == ProductStatus.ACTIVE,
            Product.allow_search.is_(True),
        )
        .order_by(Product.position, Product.name)
        .limit(30)
    )

    if query:
        stmt = stmt.where(
            or_(
                Product.name.ilike(f"%{query}%"),
                Product.description.ilike(f"%{query}%"),
            )
        )

    result = await session.execute(stmt)
    products = list(result.scalars().all())

    if not products:
        # Sem resultados
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id="no_results",
                    title="Nenhum serviço encontrado",
                    description=f'Nada encontrado para "{inline_query.query}"',
                    input_message_content=InputTextMessageContent(
                        message_text=(
                            f"🔎 <b>Nenhum resultado encontrado</b>\n\n"
                            f'Você pesquisou por: <b>{inline_query.query}</b>\n\n'
                            f"💡 Tente outro nome ou verifique o catálogo."
                        ),
                        parse_mode="HTML",
                    ),
                )
            ],
            cache_time=5,
            is_personal=True,
        )
        return

    # Resultados
    results: list[InlineQueryResultArticle] = []

    for product in products[:max_results]:
        stock = await _count_available_stock(session, product.id)
        price_str = _format_brl(product.price)

        # Título e descrição
        title = f"{product.emoji or '🎬'} {product.name}"
        description = product.description or "Sem descrição."
        description = description.replace("\n", " ")[:80]

        # Status de estoque
        stock_status = "🟢 Disponível" if stock > 0 else "🔴 Esgotado"

        # Botão "Comprar" no resultado
        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="👁 Ver produto",
                    callback_data=f"prod:view:{product.id}:0",
                )],
            ]
        )

        input_content = InputTextMessageContent(
            message_text=(
                f"🎯 <b>{product.name}</b>\n"
                f"💲 Valor: <b>R$ {price_str}</b>\n"
                f"📝 {product.description or ''}\n\n"
                f"📦 Status: {stock_status}\n"
                f"🔢 Estoque: <b>{stock}</b>\n\n"
                f"Para comprar, clique no botão abaixo."
            ),
            parse_mode="HTML",
        )

        results.append(
            InlineQueryResultArticle(
                id=str(product.id),
                title=title,
                description=f"R$ {price_str} • {stock_status} • {description}",
                input_message_content=input_content,
                reply_markup=reply_markup,
                thumb_url=None,
                thumb_width=0,
                thumb_height=0,
            )
        )

    await inline_query.answer(
        results=results,
        cache_time=5,
        is_personal=True,
    )


# ============================================
# 🔎 PESQUISA POR TEXTO (fallback)
# ============================================
@router.message(SearchStates.waiting_query)
async def msg_search_query(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """Busca por texto digitado no chat."""
    query = (message.text or "").strip().lower()

    if not query:
        await message.answer("❌ Envie um termo para pesquisar.")
        return

    if query.startswith("/cancelar") or query.startswith("/start"):
        await state.clear()
        await message.answer("❌ Pesquisa cancelada.")
        return

    await state.clear()

    # Busca
    max_results = await config_service.get_int(session, "search_max_results", 10)

    stmt = (
        select(Product)
        .where(
            Product.status == ProductStatus.ACTIVE,
            Product.allow_search.is_(True),
            or_(
                Product.name.ilike(f"%{query}%"),
                Product.description.ilike(f"%{query}%"),
            ),
        )
        .order_by(Product.position, Product.name)
        .limit(max_results)
    )
    result = await session.execute(stmt)
    products = list(result.scalars().all())

    if not products:
        await message.answer(
            f"❌ <b>Nenhum serviço encontrado</b>\n\n"
            f"Você pesquisou por: <b>{query}</b>\n\n"
            f"💡 Tente outro nome ou veja o catálogo completo com /start."
        )
        return

    # Monta lista
    lines = [
        f"🔎 <b>Resultados para:</b> <i>{query}</i>",
        f"━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    keyboard_rows: list[list[InlineKeyboardButton]] = []

    for product in products:
        stock = await _count_available_stock(session, product.id)
        price_str = _format_brl(product.price)
        emoji = product.emoji or "🎬"
        stock_icon = "🟢" if stock > 0 else "🔴"

        lines.append(f"{emoji} <b>{product.name}</b>")
        lines.append(f"💲 R$ {price_str} — {stock_icon} {stock} em estoque")
        lines.append("")

        keyboard_rows.append([
            InlineKeyboardButton(
                text=f"{emoji} {product.name} — R$ {price_str}",
                callback_data=f"prod:view:{product.id}:0",
            )
        ])

    keyboard_rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="menu:voltar")
    ])

    await message.answer(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
    )

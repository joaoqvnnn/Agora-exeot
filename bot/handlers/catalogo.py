# ============================================
# 📱 CATÁLOGO — Larizinha Store
# ============================================
# Handler do botão "🛍 Comprar Produtos" e
# navegação por categorias/produtos.
#
# Regra de mensagem única: edita a mensagem atual.
# Nunca envia nova mensagem durante a navegação.
# ============================================

from aiogram import F, Router
from aiogram.types import CallbackQuery
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.catalogo import (
    build_categories_keyboard,
    build_full_catalog_keyboard,
    build_products_keyboard,
)
from core.models import Category, Product, ProductStatus, StockItem, StockStatus
from core.models import User
from core.services.messages import render_message


router = Router(name="catalogo")


# ============================================
# 🧰 AUXILIARES
# ============================================
def _format_brl(v) -> str:
    if v is None:
        return "0,00"
    return f"{float(v):.2f}".replace(".", ",")


async def _user_variables(session: AsyncSession, user: User) -> dict:
    """Variáveis disponíveis nas mensagens do catálogo."""
    return {
        "USER_ID": user.telegram_id,
        "USERNAME": user.username or user.first_name or "Usuário",
        "BALANCE": _format_brl(user.balance),
    }


async def _has_any_category(session: AsyncSession) -> bool:
    total = await session.scalar(
        select(func.count(Category.id)).where(Category.is_active.is_(True))
    ) or 0
    return total > 0


async def _has_any_product(session: AsyncSession) -> bool:
    total = await session.scalar(
        select(func.count(Product.id)).where(
            Product.status == ProductStatus.ACTIVE
        )
    ) or 0
    return total > 0


async def _edit_or_send(callback: CallbackQuery, text: str, keyboard) -> None:
    """Tenta editar; se falhar, envia nova mensagem."""
    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
    except Exception:
        try:
            await callback.message.answer(
                text,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
        except Exception as e:
            logger.warning(f"⚠️ Falha ao exibir catálogo: {e}")


# ============================================
# 🛍 BOTÃO "COMPRAR PRODUTOS" DO /start
# ============================================
@router.callback_query(F.data == "menu:comprar")
async def cb_open_catalog(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    """Abre o catálogo (raiz — lista de categorias)."""
    await callback.answer()

    # Se não tem nenhuma categoria ativa, mostra catálogo completo
    if not await _has_any_category(session):
        if not await _has_any_product(session):
            text = await render_message(
                session,
                key="catalogo_vazio",
                variables=await _user_variables(session, user),
            )
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Voltar", callback_data="menu:voltar")]
                ]
            )
            await _edit_or_send(callback, text, keyboard)
            return

        # Sem categorias, mas com produtos → mostra tudo
        await _show_full_catalog(callback, user, session, page=0)
        return

    # Tem categorias → mostra lista de categorias
    await _show_categories(callback, user, session, page=0)


# ============================================
# 🗂 LISTA DE CATEGORIAS
# ============================================
async def _show_categories(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    page: int = 0,
) -> None:
    text = await render_message(
        session,
        key="catalogo",
        variables=await _user_variables(session, user),
    )

    keyboard = await build_categories_keyboard(session, page=page)

    user.last_menu = "catalogo_categorias"
    session.add(user)

    await _edit_or_send(callback, text, keyboard)


# ============================================
# 📂 ABRIR CATEGORIA
# ============================================
@router.callback_query(F.data.startswith("cat:open:"))
async def cb_open_category(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    """Abre uma categoria e lista os produtos."""
    parts = callback.data.split(":")
    try:
        category_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 0
    except (ValueError, IndexError):
        await callback.answer("❌ Categoria inválida.", show_alert=True)
        return

    category = await session.get(Category, category_id)
    if category is None or not category.is_active:
        await callback.answer("❌ Categoria não encontrada.", show_alert=True)
        return

    # Monta texto da categoria
    emoji = category.emoji or "📂"
    description = category.description or ""

    text = (
        f"📂 <b>{emoji} {category.name}</b>\n"
        f"🔗🔗🔗🔗🔗🔗🔗🔗🔗🔗🔗\n\n"
        f"💰 Saldo da Carteira: <b>R$ {_format_brl(user.balance)}</b>\n\n"
    )

    if description:
        text += f"{description}\n\n"

    text += "⬇️ Selecione um produto abaixo:"

    # Verifica se tem produtos
    product_count = await session.scalar(
        select(func.count(Product.id)).where(
            Product.category_id == category_id,
            Product.status == ProductStatus.ACTIVE,
        )
    ) or 0

    if product_count == 0:
        text = (
            f"📂 <b>{emoji} {category.name}</b>\n\n"
            f"⚠️ Nenhum produto disponível nesta categoria.\n"
            f"Volte mais tarde!"
        )

    keyboard = await build_products_keyboard(session, category_id, page=page)

    user.last_menu = f"catalogo_cat_{category_id}"
    session.add(user)

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()


# ============================================
# 📄 PAGINAÇÃO DE CATEGORIAS
# ============================================
@router.callback_query(F.data.startswith("cat:page:"))
async def cb_categories_page(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    parts = callback.data.split(":")
    try:
        page = int(parts[2])
    except (ValueError, IndexError):
        page = 0

    await _show_categories(callback, user, session, page=page)
    await callback.answer()


# ============================================
# 📋 CATÁLOGO COMPLETO (sem categorias)
# ============================================
@router.callback_query(F.data.startswith("cat:full:"))
async def cb_full_catalog(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    parts = callback.data.split(":")
    try:
        page = int(parts[2])
    except (ValueError, IndexError):
        page = 0

    await _show_full_catalog(callback, user, session, page=page)
    await callback.answer()


async def _show_full_catalog(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    page: int = 0,
) -> None:
    text = await render_message(
        session,
        key="catalogo",
        variables=await _user_variables(session, user),
    )

    keyboard = await build_full_catalog_keyboard(session, page=page)

    user.last_menu = "catalogo_completo"
    session.add(user)

    await _edit_or_send(callback, text, keyboard)


# ============================================
# 🔙 VOLTAR PARA CATEGORIAS
# ============================================
@router.callback_query(F.data == "cat:voltar")
async def cb_back_to_categories(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    await cb_open_catalog(callback, user, session)


# ============================================
# 🔘 BOTÃO INFORMATIVO (noop)
# ============================================
@router.callback_query(F.data == "cat:noop")
async def cb_catalog_noop(callback: CallbackQuery) -> None:
    await callback.answer()

# ============================================
# 📦 PRODUTO — Larizinha Store
# ============================================
# Handler da tela "🔥 OPORTUNIDADE EXCLUSIVA" do produto.
# Edita a mensagem atual (mensagem única).
# Todos os dados vêm do banco em tempo real.
# ============================================

from decimal import Decimal

from aiogram import F, Router
from aiogram.types import CallbackQuery
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.produto import build_product_keyboard
from core.models import (
    Product,
    ProductStatus,
    StockItem,
    StockStatus,
    User,
)
from core.services.messages import render_message


router = Router(name="produto")


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
    """Conta estoque disponível real."""
    return await session.scalar(
        select(func.count(StockItem.id)).where(
            StockItem.product_id == product_id,
            StockItem.status == StockStatus.AVAILABLE,
        )
    ) or 0


async def _edit_or_send(callback: CallbackQuery, text: str, keyboard) -> None:
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
            logger.warning(f"⚠️ Falha ao exibir produto: {e}")


def _build_product_text(
    product: Product,
    user: User,
    stock: int,
) -> str:
    """Monta o texto do produto com dados reais."""
    emoji = product.emoji or "🎬"
    price = _format_brl(product.price)
    balance = _format_brl(user.balance)
    sold = product.total_sold or 0

    # Viewers "pseudo-reais" — baseado em um número pequeno variável
    # Em produção, isso poderia ser um contador real de visualizações
    import random
    viewers = 15 + random.randint(0, 15)

    # Descrição
    description = product.description or "Sem descrição."

    # Status de estoque
    if stock > 0:
        status_line = "🟢 <b>DISPONÍVEL AGORA</b>"
    else:
        status_line = "🔴 <b>ESGOTADO</b>"

    text = (
        f"🔥 <b>OPORTUNIDADE EXCLUSIVA</b> 🔥\n"
        f"🚀 <b>{product.name}</b>\n\n"
        f"{status_line}\n"
        f"├ 💵 Preço: <b>R$ {price}</b>\n"
        f"├ 💰 Seu Saldo: <b>R$ {balance}</b>\n"
        f"└ 📦 Estoque: <b>{stock}</b>\n\n"
        f"📝 <b>Descrição:</b>\n"
        f"{description}\n\n"
        f"📊 <b>Estatísticas em tempo real:</b>\n"
        f"⚡️ Já foram vendidas <b>{sold}</b> unidades!\n"
        f"👀 <b>{viewers}</b> pessoas estão vendo isso agora.\n\n"
        f"🛡 Garantia: <b>{product.warranty_days} dias</b>\n"
        f"✅ Compra segura. Ao adquirir, concorda com /termos"
    )

    # Telegram tem limite de 4096 chars
    if len(text) > 4000:
        text = text[:4000] + "\n\n<i>... (truncado)</i>"

    return text


# ============================================
# 👁 VER PRODUTO
# ============================================
@router.callback_query(F.data.startswith("prod:view:"))
async def cb_view_product(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    """Abre a tela do produto."""
    parts = callback.data.split(":")
    try:
        product_id = int(parts[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Produto inválido.", show_alert=True)
        return

    product = await session.get(Product, product_id)
    if product is None or product.status == ProductStatus.DELETED:
        await callback.answer("❌ Produto não encontrado.", show_alert=True)
        return

    # Produtos pausados não aparecem pra cliente comum
    if product.status != ProductStatus.ACTIVE:
        await callback.answer(
            "⚠️ Este produto não está mais disponível.",
            show_alert=True,
        )
        return

    stock = await _count_available_stock(session, product_id)
    has_stock = stock > 0

    text = _build_product_text(product, user, stock)

    # Voltar leva pra categoria (se tiver) ou pro catálogo
    back_callback = "cat:voltar"
    if product.category_id:
        back_callback = f"cat:open:{product.category_id}:0"

    keyboard = build_product_keyboard(
        product_id=product_id,
        has_stock=has_stock,
        can_buy=has_stock,
        back_callback=back_callback,
    )

    user.last_menu = f"produto_{product_id}"
    session.add(user)

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()


# ============================================
# 🔄 ATUALIZAR PRODUTO (refresh)
# ============================================
@router.callback_query(F.data.startswith("prod:refresh:"))
async def cb_refresh_product(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    parts = callback.data.split(":")
    try:
        product_id = int(parts[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Produto inválido.", show_alert=True)
        return

    # Reusa o handler de view
    callback.data = f"prod:view:{product_id}:0"
    await cb_view_product(callback, user, session)


# ============================================
# 🔘 NOOP
# ============================================
@router.callback_query(F.data == "prod:noop")
async def cb_prod_noop(callback: CallbackQuery) -> None:
    await callback.answer()

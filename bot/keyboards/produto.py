# ============================================
# 📦 PRODUTO — Larizinha Store
# ============================================
# Teclado exibido na tela de um produto específico.
# ============================================

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


# ============================================
# 🎬 TECLADO DO PRODUTO
# ============================================
def build_product_keyboard(
    product_id: int,
    has_stock: bool = True,
    can_buy: bool = True,
    back_callback: str = "cat:voltar",
) -> InlineKeyboardMarkup:
    """
    Monta o teclado do produto.

    has_stock: se tem estoque disponível
    can_buy: se o usuário pode comprar (não bloqueado)
    back_callback: pra onde o botão Voltar aponta
    """
    rows: list[list[InlineKeyboardButton]] = []

    if has_stock and can_buy:
        rows.append([
            InlineKeyboardButton(
                text="💳 Comprar",
                callback_data=f"prod:buy:{product_id}:1",
            )
        ])
        rows.append([
            InlineKeyboardButton(
                text="🛒 Comprar Vários",
                callback_data=f"prod:quantity:{product_id}:1",
            )
        ])
    elif not has_stock:
        rows.append([
            InlineKeyboardButton(
                text="🔔 Me avise quando voltar",
                callback_data=f"alert:toggle:{product_id}:0",
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="📜 Termos",
            callback_data="terms:view",
        )
    ])

    rows.append([
        InlineKeyboardButton(
            text="🔙 Voltar",
            callback_data=back_callback,
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================
# 🔢 TECLADO DE QUANTIDADE
# ============================================
def build_quantity_keyboard(
    product_id: int,
    current_quantity: int = 1,
    max_quantity: int = 10,
) -> InlineKeyboardMarkup:
    """Teclado mostrado ao escolher quantidade na compra múltipla."""
    rows: list[list[InlineKeyboardButton]] = []

    # Botões rápidos de quantidade
    quick_row: list[InlineKeyboardButton] = []
    for qty in (1, 2, 3, 5):
        if qty <= max_quantity:
            quick_row.append(
                InlineKeyboardButton(
                    text=str(qty),
                    callback_data=f"buy:quantity_ok:{product_id}:{qty}",
                )
            )
    if quick_row:
        rows.append(quick_row)

    rows.append([
        InlineKeyboardButton(
            text="❌ Cancelar",
            callback_data=f"buy:cancel:{product_id}:0",
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================
# 💳 TECLADO PÓS-SELEÇÃO DE QUANTIDADE
# ============================================
def build_quantity_confirm_keyboard(
    product_id: int,
    quantity: int,
) -> InlineKeyboardMarkup:
    """Confirmação depois de escolher a quantidade."""
    rows = [
        [
            InlineKeyboardButton(
                text="✅ Confirmar Compra",
                callback_data=f"buy:confirm:{product_id}:{quantity}",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔄 Alterar Quantidade",
                callback_data=f"prod:quantity:{product_id}:{quantity}",
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Cancelar",
                callback_data=f"buy:cancel:{product_id}:0",
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

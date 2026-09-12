# ============================================
# 💳 PIX — Larizinha Store
# ============================================
# Teclados do fluxo de pagamento Pix (recarga e compra).
# ============================================

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


# ============================================
# 💰 TECLADO DO MENU DE RECARGA
# ============================================
def build_recharge_menu_keyboard() -> InlineKeyboardMarkup:
    """Menu inicial de recarga de saldo."""
    rows = [
        [
            InlineKeyboardButton(
                text="💠 Pix Rápido",
                callback_data="pix:gerar:0:",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Voltar",
                callback_data="menu:voltar",
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================
# 💰 TECLADO DE VALOR SUGERIDO (BÔNUS)
# ============================================
def build_bonus_keyboard(
    current_amount: str,
    suggested_amount: str,
) -> InlineKeyboardMarkup:
    """
    Teclado exibido quando o usuário pode ganhar bônus
    recarregando um valor maior.
    """
    rows = [
        [
            InlineKeyboardButton(
                text=f"✅ Continuar com R$ {current_amount}",
                callback_data=f"pix:gerar:{current_amount}:",
            )
        ],
        [
            InlineKeyboardButton(
                text=f"🎁 Recarregar R$ {suggested_amount} e ganhar bônus",
                callback_data=f"pix:gerar:{suggested_amount}:",
            )
        ],
        [
            InlineKeyboardButton(
                text="✏️ Digitar outro valor",
                callback_data="pix:digitar",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Voltar",
                callback_data="pix:voltar",
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================
# 💳 TECLADO DO PIX GERADO
# ============================================
def build_pix_keyboard(
    payment_id: str,
) -> InlineKeyboardMarkup:
    """Teclado exibido com o Pix copia e cola pronto."""
    rows = [
        [
            InlineKeyboardButton(
                text="📋 Copiar Pix",
                callback_data=f"pix:copiar:{payment_id}",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔄 Verificar Pagamento",
                callback_data=f"pix:verificar:{payment_id}",
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Cancelar",
                callback_data=f"pix:cancelar:{payment_id}",
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================
# ❌ TECLADO DE SALDO INSUFICIENTE
# ============================================
def build_insufficient_balance_keyboard(
    amount: str,
    product_id: int = 0,
    quantity: int = 1,
) -> InlineKeyboardMarkup:
    """
    Teclado exibido quando o saldo é insuficiente.
    Oferece gerar Pix ou cancelar.
    """
    if product_id:
        gerar_cb = f"buy:gerar_pix:{product_id}:{quantity}"
    else:
        gerar_cb = f"pix:gerar:{amount}:"

    rows = [
        [
            InlineKeyboardButton(
                text=f"💠 Gerar Pix de R$ {amount}",
                callback_data=gerar_cb,
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Cancelar",
                callback_data="pix:cancelar:0",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Voltar",
                callback_data="menu:voltar",
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================
# ✅ TECLADO DE PAGAMENTO APROVADO
# ============================================
def build_payment_approved_keyboard(
    back_callback: str = "menu:voltar",
) -> InlineKeyboardMarkup:
    """Teclado exibido após pagamento confirmado."""
    rows = [
        [
            InlineKeyboardButton(
                text="🛍 Comprar Produtos",
                callback_data="menu:comprar",
            )
        ],
        [
            InlineKeyboardButton(
                text="👤 Meu Perfil",
                callback_data="menu:perfil",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Voltar ao Início",
                callback_data=back_callback,
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================
# ❌ TECLADO DE PIX EXPIRADO
# ============================================
def build_pix_expired_keyboard() -> InlineKeyboardMarkup:
    """Teclado exibido quando o Pix expira."""
    rows = [
        [
            InlineKeyboardButton(
                text="🔄 Gerar novo Pix",
                callback_data="pix:gerar:0:",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Voltar ao Início",
                callback_data="menu:voltar",
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

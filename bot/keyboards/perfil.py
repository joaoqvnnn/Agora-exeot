# ============================================
# 👤 PERFIL — Larizinha Store
# ============================================
# Teclados do menu de perfil, histórico de compras,
# gift card e alteração de dados.
# ============================================

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


# ============================================
# 👤 TECLADO PRINCIPAL DO PERFIL
# ============================================
def build_profile_keyboard() -> InlineKeyboardMarkup:
    """Menu principal do perfil."""
    rows = [
        [
            InlineKeyboardButton(
                text="📜 Histórico de Compras",
                callback_data="prof:historico:0",
            )
        ],
        [
            InlineKeyboardButton(
                text="🎁 Resgatar Gift Card",
                callback_data="gift:resgatar",
            )
        ],
        [
            InlineKeyboardButton(
                text="✏️ Alterar Dados",
                callback_data="prof:alterar",
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
# 📜 HISTÓRICO DE COMPRAS — NAVEGAÇÃO
# ============================================
def build_history_keyboard(
    current_page: int,
    total_pages: int,
    has_active: bool = False,
) -> InlineKeyboardMarkup:
    """
    Teclado do histórico de compras.
    Inclui paginação e filtro "ativas".
    """
    rows: list[list[InlineKeyboardButton]] = []

    # Navegação entre páginas
    nav_row: list[InlineKeyboardButton] = []

    if current_page > 0:
        nav_row.append(
            InlineKeyboardButton(
                text="⬅️ Anterior",
                callback_data=f"prof:historico:{current_page - 1}",
            )
        )

    if total_pages > 1:
        nav_row.append(
            InlineKeyboardButton(
                text=f"📄 {current_page + 1}/{total_pages}",
                callback_data="prof:noop",
            )
        )

    if current_page < total_pages - 1:
        nav_row.append(
            InlineKeyboardButton(
                text="Avançar ➡️",
                callback_data=f"prof:historico:{current_page + 1}",
            )
        )

    if nav_row:
        rows.append(nav_row)

    # Ver apenas compras ativas
    rows.append([
        InlineKeyboardButton(
            text="✅ Ver Apenas Ativas",
            callback_data="prof:historico_ativas:0",
        )
    ])

    rows.append([
        InlineKeyboardButton(
            text="🔙 Voltar",
            callback_data="prof:voltar",
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================
# 📜 HISTÓRICO — SEM COMPRAS ATIVAS
# ============================================
def build_no_active_keyboard() -> InlineKeyboardMarkup:
    """Exibido quando o usuário não tem compras ativas."""
    rows = [
        [
            InlineKeyboardButton(
                text="📋 Ver Todas as Compras",
                callback_data="prof:historico:0",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Voltar",
                callback_data="prof:voltar",
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================
# 📜 DETALHE DE UMA COMPRA
# ============================================
def build_order_detail_keyboard(
    order_id: int,
    has_activation_link: bool = False,
    activation_url: str = "",
) -> InlineKeyboardMarkup:
    """Teclado do detalhe de uma compra."""
    rows: list[list[InlineKeyboardButton]] = []

    if has_activation_link and activation_url:
        rows.append([
            InlineKeyboardButton(
                text="🔓 Ativar Produto",
                url=activation_url,
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="🔙 Voltar ao Histórico",
            callback_data="prof:historico:0",
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================
# 🎁 GIFT CARD
# ============================================
def build_gift_card_keyboard() -> InlineKeyboardMarkup:
    """Teclado exibido ao pedir o código do gift card."""
    rows = [
        [
            InlineKeyboardButton(
                text="❌ Cancelar",
                callback_data="gift:cancelar",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Voltar",
                callback_data="prof:voltar",
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================
# ✏️ ALTERAR DADOS
# ============================================
def build_change_data_keyboard(
    whatsapp: str | None = None,
    email: str | None = None,
) -> InlineKeyboardMarkup:
    """Menu de alteração de dados."""
    zap_label = f"📱 WhatsApp: {whatsapp}" if whatsapp else "📱 WhatsApp: Não cadastrado"
    email_label = f"📧 E-mail: {email}" if email else "📧 E-mail: Não cadastrado"

    rows = [
        [
            InlineKeyboardButton(
                text=zap_label,
                callback_data="prof:changing_whatsapp",
            )
        ],
        [
            InlineKeyboardButton(
                text=email_label,
                callback_data="prof:changing_email",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Voltar",
                callback_data="prof:voltar",
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================
# ✏️ ALTERANDO WHATSAPP / E-MAIL
# ============================================
def build_change_cancel_keyboard(
    back_action: str = "prof:alterar",
) -> InlineKeyboardMarkup:
    """Teclado com Cancelar/Voltar para fluxos de alteração."""
    rows = [
        [
            InlineKeyboardButton(
                text="❌ Cancelar",
                callback_data="prof:cancelar",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Voltar",
                callback_data=back_action,
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================
# 📧 VERIFICAÇÃO DE E-MAIL (CÓDIGO)
# ============================================
def build_email_code_keyboard() -> InlineKeyboardMarkup:
    """Teclado exibido ao aguardar o código do e-mail."""
    rows = [
        [
            InlineKeyboardButton(
                text="🔄 Reenviar Código",
                callback_data="prof:reenviar_codigo",
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Cancelar",
                callback_data="prof:cancelar",
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

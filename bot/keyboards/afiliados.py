# ============================================
# 🤝 AFILIADOS — Larizinha Store
# ============================================
# Teclados do programa de afiliados, saques,
# cadastro de senha, e-mail e dados bancários.
# ============================================

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


# ============================================
# 🤝 TECLADO PRINCIPAL DE AFILIADOS
# ============================================
def build_affiliate_keyboard(
    has_password: bool = False,
    has_email: bool = False,
) -> InlineKeyboardMarkup:
    """Menu principal do afiliado."""
    rows: list[list[InlineKeyboardButton]] = []

    rows.append([
        InlineKeyboardButton(
            text="📊 Histórico de Saques",
            callback_data="aff:historico",
        )
    ])

    rows.append([
        InlineKeyboardButton(
            text="🏦 Cadastrar Dados Bancários",
            callback_data="aff:cadastrar_banco",
        )
    ])

    rows.append([
        InlineKeyboardButton(
            text="💠 Cadastrar Chave Pix",
            callback_data="aff:cadastrar_pix",
        )
    ])

    # Senha de saque
    if has_password:
        rows.append([
            InlineKeyboardButton(
                text="🔐 Alterar Senha de Saque",
                callback_data="aff:alterar_senha",
            )
        ])
    else:
        rows.append([
            InlineKeyboardButton(
                text="🔐 Cadastrar Senha de Saque",
                callback_data="aff:cadastrar_senha",
            )
        ])

    # E-mail de recuperação
    if has_email:
        rows.append([
            InlineKeyboardButton(
                text="📧 Alterar E-mail de Recuperação",
                callback_data="aff:alterar_email",
            )
        ])
    else:
        rows.append([
            InlineKeyboardButton(
                text="📧 Cadastrar E-mail de Recuperação",
                callback_data="aff:cadastrar_email",
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="💸 Solicitar Saque",
            callback_data="aff:saque",
        )
    ])

    rows.append([
        InlineKeyboardButton(
            text="🔙 Voltar",
            callback_data="menu:voltar",
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================
# 📊 HISTÓRICO DE SAQUES
# ============================================
def build_withdrawal_history_keyboard(
    current_page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """Teclado do histórico de saques."""
    rows: list[list[InlineKeyboardButton]] = []

    if total_pages > 1:
        nav_row: list[InlineKeyboardButton] = []
        if current_page > 0:
            nav_row.append(
                InlineKeyboardButton(
                    text="⬅️ Anterior",
                    callback_data=f"aff:historico:{current_page - 1}",
                )
            )
        nav_row.append(
            InlineKeyboardButton(
                text=f"📄 {current_page + 1}/{total_pages}",
                callback_data="aff:noop",
            )
        )
        if current_page < total_pages - 1:
            nav_row.append(
                InlineKeyboardButton(
                    text="Próxima ➡️",
                    callback_data=f"aff:historico:{current_page + 1}",
                )
            )
        rows.append(nav_row)

    rows.append([
        InlineKeyboardButton(
            text="🔙 Voltar",
            callback_data="aff:voltar",
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================
# 💸 SOLICITAR SAQUE — MÉTODO
# ============================================
def build_withdrawal_method_keyboard() -> InlineKeyboardMarkup:
    """Escolha do método de saque."""
    rows = [
        [
            InlineKeyboardButton(
                text="💠 Sacar por Pix",
                callback_data="wd:pix:",
            )
        ],
        [
            InlineKeyboardButton(
                text="🏦 Sacar por Banco",
                callback_data="wd:banco:",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Voltar",
                callback_data="aff:voltar",
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================
# 💠 TIPO DE CHAVE PIX
# ============================================
def build_pix_type_keyboard() -> InlineKeyboardMarkup:
    """Escolha do tipo de chave Pix."""
    rows = [
        [
            InlineKeyboardButton(text="🆔 CPF", callback_data="wd:pix_cpf:"),
            InlineKeyboardButton(text="🏢 CNPJ", callback_data="wd:pix_cnpj:"),
        ],
        [
            InlineKeyboardButton(text="📧 E-mail", callback_data="wd:pix_email:"),
            InlineKeyboardButton(text="📱 Telefone", callback_data="wd:pix_phone:"),
        ],
        [
            InlineKeyboardButton(text="🎲 Aleatória", callback_data="wd:pix_random:"),
        ],
        [
            InlineKeyboardButton(text="🔙 Voltar", callback_data="wd:voltar"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================
# 💸 CONFIRMAÇÃO DE SAQUE
# ============================================
def build_withdrawal_confirm_keyboard(
    has_password: bool = True,
) -> InlineKeyboardMarkup:
    """Confirmação antes de efetivar o saque."""
    rows: list[list[InlineKeyboardButton]] = []

    if has_password:
        rows.append([
            InlineKeyboardButton(
                text="✅ Confirmar Saque",
                callback_data="wd:confirmar",
            )
        ])
        rows.append([
            InlineKeyboardButton(
                text="✏️ Editar Chave",
                callback_data="wd:editar_chave",
            )
        ])
    else:
        rows.append([
            InlineKeyboardButton(
                text="🔐 Cadastrar Senha de Saque",
                callback_data="aff:cadastrar_senha",
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="❌ Cancelar",
            callback_data="wd:cancelar",
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================
# 🔐 SENHA DE SAQUE
# ============================================
def build_password_keyboard() -> InlineKeyboardMarkup:
    """Teclado exibido ao cadastrar senha de saque."""
    rows = [
        [
            InlineKeyboardButton(
                text="❌ Cancelar",
                callback_data="wd:cancelar",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Voltar",
                callback_data="aff:voltar",
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================
# 🔐 RECUPERAÇÃO DE SENHA POR E-MAIL
# ============================================
def build_password_recovery_keyboard() -> InlineKeyboardMarkup:
    """Teclado exibido ao recuperar senha."""
    rows = [
        [
            InlineKeyboardButton(
                text="📧 Recuperar via E-mail",
                callback_data="aff:recuperar_email",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Voltar",
                callback_data="aff:voltar",
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================
# 🏦 DADOS BANCÁRIOS
# ============================================
def build_bank_data_keyboard() -> InlineKeyboardMarkup:
    """Teclado pra cadastrar dados bancários."""
    rows = [
        [
            InlineKeyboardButton(
                text="🏦 Abrir Formulário",
                callback_data="aff:banco_form",
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Cancelar",
                callback_data="aff:voltar",
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================
# 💸 SAQUE POR BANCO — CONFIRMAÇÃO
# ============================================
def build_bank_withdrawal_confirm_keyboard() -> InlineKeyboardMarkup:
    """Confirmação do saque via banco."""
    rows = [
        [
            InlineKeyboardButton(
                text="✅ Confirmar Transferência",
                callback_data="wd:confirmar_banco",
            )
        ],
        [
            InlineKeyboardButton(
                text="✏️ Editar Dados",
                callback_data="aff:cadastrar_banco",
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Cancelar",
                callback_data="wd:cancelar",
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================
# 📧 CADASTRO DE E-MAIL DE RECUPERAÇÃO
# ============================================
def build_email_register_keyboard() -> InlineKeyboardMarkup:
    """Teclado exibido ao cadastrar e-mail."""
    rows = [
        [
            InlineKeyboardButton(
                text="❌ Cancelar",
                callback_data="wd:cancelar",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Voltar",
                callback_data="aff:voltar",
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================
# 🔢 CONFIRMAÇÃO FINAL DO SAQUE
# ============================================
def build_withdrawal_final_keyboard() -> InlineKeyboardMarkup:
    """Última confirmação antes de enviar o saque."""
    rows = [
        [
            InlineKeyboardButton(
                text="✅ Enviar Solicitação",
                callback_data="wd:enviar",
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Cancelar",
                callback_data="wd:cancelar",
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

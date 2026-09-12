# ============================================
# ⚙️ ADMIN CONFIG KEYBOARD — Larizinha Store
# ============================================
# Teclados do menu de CONFIGURAÇÕES do painel admin.
# Montados dinamicamente do banco quando possível.
# ============================================

from collections import defaultdict

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import ButtonTemplate


# ============================================
# 🔘 FALLBACK: MENU CONFIGURAÇÕES
# ============================================
FALLBACK_CONFIG: list[dict] = [
    {"text": "⚙️ CONFIGURAÇÕES GERAIS", "callback_data": "adm_cfg:gerais", "row": 0, "position": 0},
    {"text": "👮 CONFIGURAR ADMINS", "callback_data": "adm_cfg:admins", "row": 1, "position": 0},
    {"text": "🤝 CONFIGURAR AFILIADOS", "callback_data": "adm_cfg:afiliados", "row": 2, "position": 0},
    {"text": "👥 CONFIGURAR USUÁRIOS", "callback_data": "adm_cfg:usuarios", "row": 3, "position": 0},
    {"text": "💳 CONFIGURAR PIX", "callback_data": "adm_cfg:pix", "row": 4, "position": 0},
    {"text": "🔐 CONFIGURAR LOGINS", "callback_data": "adm_cfg:logins", "row": 5, "position": 0},
    {"text": "🔎 CONFIGURAR PESQUISA", "callback_data": "adm_cfg:pesquisa", "row": 6, "position": 0},
    {"text": "📝 EDITOR DE MENSAGENS", "callback_data": "adm_cfg:messages", "row": 7, "position": 0},
    {"text": "🔘 EDITOR DE BOTÕES", "callback_data": "adm_cfg:buttons", "row": 8, "position": 0},
    {"text": "🖼️ GERENCIAR IMAGENS", "callback_data": "adm_cfg:images", "row": 9, "position": 0},
    {"text": "🔙 VOLTAR", "callback_data": "adm:dashboard", "row": 10, "position": 0},
]


# ============================================
# 🔘 FALLBACK: CONFIGURAÇÕES GERAIS
# ============================================
FALLBACK_GERAIS: list[dict] = [
    {"text": "🔄 RENOVAR PLANO", "callback_data": "adm_gen:renew", "row": 0, "position": 0},
    {"text": "🔁 REINICIAR BOT", "callback_data": "adm_gen:restart", "row": 1, "position": 0},
    {"text": "🔧 MANUTENÇÃO", "callback_data": "adm_gen:maintenance", "row": 2, "position": 0},
    {"text": "🛡 MUDAR SUPORTE", "callback_data": "adm_gen:support", "row": 3, "position": 0},
    {"text": "🔣 MUDAR SEPARADOR", "callback_data": "adm_gen:separator", "row": 4, "position": 0},
    {"text": "📢 MUDAR DESTINO LOG", "callback_data": "adm_gen:logs_channel", "row": 5, "position": 0},
    {"text": "🛡 ANTI-FLOOD", "callback_data": "adm_gen:antiflood", "row": 6, "position": 0},
    {"text": "🚫 BLOQUEIOS", "callback_data": "adm_gen:blocks", "row": 7, "position": 0},
    {"text": "🔙 VOLTAR", "callback_data": "adm:config", "row": 8, "position": 0},
]


# ============================================
# 🏗️ BUILD GENÉRICO
# ============================================
async def _build_from_menu(
    session: AsyncSession | None,
    menu_key: str,
    fallback: list[dict],
) -> InlineKeyboardMarkup:
    """Monta teclado lendo do banco; se vazio, usa fallback."""
    buttons: list[dict] = []

    if session is not None:
        stmt = (
            select(ButtonTemplate)
            .where(
                ButtonTemplate.menu == menu_key,
                ButtonTemplate.is_active.is_(True),
            )
            .order_by(ButtonTemplate.row, ButtonTemplate.position)
        )
        result = await session.execute(stmt)
        rows = list(result.scalars().all())
        if rows:
            buttons = [
                {
                    "text": b.text,
                    "callback_data": b.action_data or "",
                    "row": b.row,
                    "position": b.position,
                }
                for b in rows
            ]

    if not buttons:
        buttons = fallback

    return _assemble(buttons)


def _assemble(buttons: list[dict]) -> InlineKeyboardMarkup:
    grouped: dict[int, list[tuple[int, dict]]] = defaultdict(list)
    for b in buttons:
        grouped[int(b.get("row", 0))].append((int(b.get("position", 0)), b))

    keyboard_rows: list[list[InlineKeyboardButton]] = []
    for row_index in sorted(grouped.keys()):
        items = sorted(grouped[row_index], key=lambda x: x[0])
        row_buttons: list[InlineKeyboardButton] = []
        for _, btn in items:
            row_buttons.append(
                InlineKeyboardButton(
                    text=btn["text"],
                    callback_data=btn["callback_data"],
                )
            )
        keyboard_rows.append(row_buttons)

    return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


# ============================================
# 🔧 TECLADOS ESPECÍFICOS
# ============================================
async def build_config_menu_keyboard(
    session: AsyncSession | None = None,
) -> InlineKeyboardMarkup:
    return await _build_from_menu(session, "admin_config", FALLBACK_CONFIG)


async def build_config_gerais_keyboard(
    session: AsyncSession | None = None,
) -> InlineKeyboardMarkup:
    return await _build_from_menu(session, "admin_config_gerais", FALLBACK_GERAIS)


# ============================================
# 🔙 BOTÃO VOLTAR SIMPLES
# ============================================
def build_back_button(callback_data: str, text: str = "🔙 Voltar") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=callback_data)]
        ]
    )


def build_confirm_keyboard(
    context: str,
    target_id: str = "",
    yes_text: str = "✅ Confirmar",
    no_text: str = "❌ Cancelar",
    back_data: str = "adm:dashboard",
) -> InlineKeyboardMarkup:
    """Teclado de confirmação genérico."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=yes_text,
                    callback_data=f"confirm:yes:{context}:{target_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=no_text,
                    callback_data=back_data,
                )
            ],
        ]
    )

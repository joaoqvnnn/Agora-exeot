# ============================================
# 👮 ADMIN MAIN KEYBOARD — Larizinha Store
# ============================================
# Teclado principal do painel administrativo.
# Montado dinamicamente a partir do banco
# (button_templates com menu="admin_main").
# ============================================

from collections import defaultdict

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import ButtonTemplate


# ============================================
# 🔘 FALLBACK (usado se o banco estiver vazio)
# ============================================
FALLBACK_BUTTONS: list[dict] = [
    {"text": "⚙️ CONFIGURAÇÕES", "callback_data": "adm:config", "row": 0, "position": 0},
    {"text": "⚡ AÇÕES", "callback_data": "adm:actions", "row": 1, "position": 0},
    {"text": "💳 TRANSAÇÕES", "callback_data": "adm:transactions", "row": 2, "position": 0},
    {"text": "🔄 ATUALIZAÇÕES", "callback_data": "adm:updates", "row": 3, "position": 0},
    {"text": "📊 ESTATÍSTICAS", "callback_data": "adm:stats", "row": 4, "position": 0},
    {"text": "🧪 DIAGNÓSTICO", "callback_data": "adm:diagnostics", "row": 5, "position": 0},
    {"text": "🔌 INTEGRAÇÕES", "callback_data": "adm:integrations", "row": 6, "position": 0},
]


# ============================================
# 🏗️ BUILD
# ============================================
async def build_admin_main_keyboard(
    session: AsyncSession | None = None,
    is_owner: bool = False,
) -> InlineKeyboardMarkup:
    """
    Monta o teclado principal do painel admin.
    Lê do banco; se vazio, usa o fallback.
    """
    rows_db: list[ButtonTemplate] = []

    if session is not None:
        stmt = (
            select(ButtonTemplate)
            .where(
                ButtonTemplate.menu == "admin_main",
                ButtonTemplate.is_active.is_(True),
            )
            .order_by(ButtonTemplate.row, ButtonTemplate.position)
        )
        result = await session.execute(stmt)
        rows_db = list(result.scalars().all())

    if rows_db:
        buttons = [
            {
                "text": b.text,
                "callback_data": b.action_data or "",
                "row": b.row,
                "position": b.position,
            }
            for b in rows_db
        ]
    else:
        buttons = FALLBACK_BUTTONS

    return _build_keyboard(buttons, is_owner)


# ============================================
# 🧰 MONTAGEM
# ============================================
def _build_keyboard(
    buttons: list[dict],
    is_owner: bool,
) -> InlineKeyboardMarkup:
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

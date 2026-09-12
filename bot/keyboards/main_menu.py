# ============================================
# 🏠 MAIN MENU — Larizinha Store
# ============================================
# Monta o teclado do /start dinamicamente a partir
# da tabela button_templates (editável pelo admin).
#
# Se não houver botões cadastrados no banco, usa um
# fallback padrão pra não deixar o usuário sem menu.
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
    {"text": "🛍 Comprar Produtos", "action_type": "callback",
     "action_data": "menu:comprar", "row": 0, "position": 0},
    {"text": "🌐 Abrir Loja", "action_type": "webapp",
     "action_data": "webapp", "row": 1, "position": 0},
    {"text": "👤 Meu Perfil", "action_type": "callback",
     "action_data": "menu:perfil", "row": 2, "position": 0},
    {"text": "💰 Recarregar Saldo", "action_type": "callback",
     "action_data": "menu:recarregar", "row": 2, "position": 1},
    {"text": "🤝 Afiliados", "action_type": "callback",
     "action_data": "menu:afiliados", "row": 3, "position": 0},
    {"text": "🏆 Top Compradores", "action_type": "callback",
     "action_data": "menu:ranking", "row": 3, "position": 1},
    {"text": "🎧 Atendimento", "action_type": "callback",
     "action_data": "menu:atendimento", "row": 4, "position": 0},
    {"text": "ℹ️ Sobre o Bot", "action_type": "callback",
     "action_data": "menu:sobre", "row": 4, "position": 1},
    {"text": "🔎 Pesquisar Serviços", "action_type": "callback",
     "action_data": "menu:pesquisa", "row": 5, "position": 0},
]


# ============================================
# 🏗️ BUILD
# ============================================
async def build_main_menu(
    session: AsyncSession,
    webapp_url: str | None = None,
) -> InlineKeyboardMarkup:
    """
    Monta o teclado do /start lendo os botões ativos
    do banco. Se o banco estiver vazio, usa o fallback.
    """
    stmt = (
        select(ButtonTemplate)
        .where(
            ButtonTemplate.menu == "start",
            ButtonTemplate.is_active.is_(True),
        )
        .order_by(ButtonTemplate.row, ButtonTemplate.position)
    )
    result = await session.execute(stmt)
    rows_db = result.scalars().all()

    if rows_db:
        buttons_data = [
            {
                "text": b.text,
                "action_type": b.action_type,
                "action_data": b.action_data or "",
                "row": b.row,
                "position": b.position,
            }
            for b in rows_db
        ]
    else:
        buttons_data = FALLBACK_BUTTONS

    return _build_keyboard(buttons_data, webapp_url)


# ============================================
# 🧰 MONTAGEM DO TECLADO
# ============================================
def _build_keyboard(
    buttons: list[dict],
    webapp_url: str | None = None,
) -> InlineKeyboardMarkup:
    """Agrupa botões por linha e monta o InlineKeyboardMarkup."""
    grouped: dict[int, list[tuple[int, dict]]] = defaultdict(list)
    for b in buttons:
        grouped[int(b["row"])].append((int(b["position"]), b))

    keyboard_rows: list[list[InlineKeyboardButton]] = []
    for row_index in sorted(grouped.keys()):
        items = sorted(grouped[row_index], key=lambda x: x[0])
        row_buttons: list[InlineKeyboardButton] = []
        for _, btn in items:
            row_buttons.append(_make_button(btn, webapp_url))
        keyboard_rows.append(row_buttons)

    return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


def _make_button(
    btn: dict,
    webapp_url: str | None,
) -> InlineKeyboardButton:
    """Cria um InlineKeyboardButton conforme o action_type."""
    action_type = btn.get("action_type", "callback")
    action_data = btn.get("action_data", "")
    text = btn.get("text", "—")

    if action_type == "url":
        return InlineKeyboardButton(text=text, url=action_data)

    if action_type == "webapp":
        url = action_data if action_data.startswith("http") else (webapp_url or "")
        return InlineKeyboardButton(text=text, web_app={"url": url})

    # default: callback
    return InlineKeyboardButton(text=text, callback_data=action_data)

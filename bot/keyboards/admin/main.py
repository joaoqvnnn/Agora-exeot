# ============================================
# 👮 ADMIN MAIN KEYBOARD — Larizinha Store
# ============================================
# Teclado principal do painel administrativo.
# Atualizado com TODOS os módulos disponíveis.
# ============================================

from collections import defaultdict

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import ButtonTemplate


# ============================================
# 🔘 MENU PRINCIPAL COMPLETO
# ============================================
FALLBACK_BUTTONS: list[dict] = [
    # Linha 0: Ações rápidas
    {"text": "⚡ AÇÕES RÁPIDAS", "callback_data": "adm:actions", "row": 0, "position": 0},

    # Linha 1: Dashboard
    {"text": "📊 DASHBOARD", "callback_data": "adm_dash:full", "row": 1, "position": 0},

    # Linha 2: Configurações
    {"text": "⚙️ CONFIGURAÇÕES", "callback_data": "adm:config", "row": 2, "position": 0},

    # Linha 3: Personalização
    {"text": "🎨 APARÊNCIA", "callback_data": "adm_app:menu", "row": 3, "position": 0},
    {"text": "📝 MENSAGENS", "callback_data": "adm_cfg:messages", "row": 3, "position": 1},

    # Linha 4: Botões e imagens
    {"text": "🔘 BOTÕES", "callback_data": "adm_cfg:buttons", "row": 4, "position": 0},
    {"text": "🖼️ IMAGENS", "callback_data": "adm_cfg:images", "row": 4, "position": 1},

    # Linha 5: Produtos
    {"text": "📦 PRODUTOS", "callback_data": "adm_cfg:logins", "row": 5, "position": 0},
    {"text": "📂 CATEGORIAS", "callback_data": "adm_cat:list", "row": 5, "position": 1},

    # Linha 6: Estoque
    {"text": "🔐 ESTOQUE", "callback_data": "adm_stock:menu", "row": 6, "position": 0},

    # Linha 7: Usuários
    {"text": "👥 USUÁRIOS", "callback_data": "adm_cfg:usuarios", "row": 7, "position": 0},
    {"text": "🚫 BLOQUEIOS", "callback_data": "adm_block:menu", "row": 7, "position": 1},

    # Linha 8: Financeiro
    {"text": "💳 PIX", "callback_data": "adm_cfg:pix", "row": 8, "position": 0},
    {"text": "💸 SAQUES", "callback_data": "adm_wd:list", "row": 8, "position": 1},

    # Linha 9: Afiliados
    {"text": "🤝 AFILIADOS", "callback_data": "adm_cfg:afiliados", "row": 9, "position": 0},
    {"text": "🎁 GIFT CARDS", "callback_data": "adm_gift:menu", "row": 9, "position": 1},

    # Linha 10: Rankings e Pesquisa
    {"text": "🏆 RANKINGS", "callback_data": "adm_rank:menu", "row": 10, "position": 0},
    {"text": "🔎 PESQUISA", "callback_data": "adm_cfg:pesquisa", "row": 10, "position": 1},

    # Linha 11: Comunicação
    {"text": "📢 BROADCAST", "callback_data": "adm_bc:menu", "row": 11, "position": 0},
    {"text": "🔔 ALERTAS", "callback_data": "adm_alerts:menu", "row": 11, "position": 1},

    # Linha 12: Notificações automáticas
    {"text": "🔔 NOTIFICAÇÕES", "callback_data": "adm_notif:menu", "row": 12, "position": 0},

    # Linha 13: Atendimento
    {"text": "🎧 ATENDIMENTO", "callback_data": "adm_sup:menu", "row": 13, "position": 0},
    {"text": "🤖 IA", "callback_data": "adm_ai:menu", "row": 13, "position": 1},

    # Linha 14: Integrações - parte 1
    {"text": "📱 TELEGRAM", "callback_data": "adm_tg:menu", "row": 14, "position": 0},
    {"text": "📲 WHATSAPP", "callback_data": "adm_wa:menu", "row": 14, "position": 1},

    # Linha 15: Integrações - parte 2
    {"text": "📧 E-MAIL", "callback_data": "adm_email:menu", "row": 15, "position": 0},
    {"text": "🌐 WEBSITE", "callback_data": "adm_web:menu", "row": 15, "position": 1},

    # Linha 16: Integrações - parte 3
    {"text": "🔌 INTEGRAÇÕES", "callback_data": "adm:integrations", "row": 16, "position": 0},

    # Linha 17: Sistema
    {"text": "🛡 SEGURANÇA", "callback_data": "adm_gen:antiflood", "row": 17, "position": 0},
    {"text": "📋 LOGS", "callback_data": "adm_logs:menu", "row": 17, "position": 1},

    # Linha 18: Transações
    {"text": "💳 TRANSAÇÕES", "callback_data": "adm:transactions", "row": 18, "position": 0},
    {"text": "📈 ESTATÍSTICAS", "callback_data": "adm:stats", "row": 18, "position": 1},

    # Linha 19: Manutenção
    {"text": "🔧 MANUTENÇÃO", "callback_data": "adm_gen:maintenance", "row": 19, "position": 0},
    {"text": "📢 CANAL OBRIGATÓRIO", "callback_data": "adm_canal:menu", "row": 19, "position": 1},

    # Linha 20: Comandos e termos
    {"text": "🧩 COMANDOS", "callback_data": "adm_cmd:menu", "row": 20, "position": 0},
    {"text": "📜 TERMOS", "callback_data": "adm_terms:menu", "row": 20, "position": 1},

    # Linha 21: Sistema e diagnóstico
    {"text": "🧪 DIAGNÓSTICO", "callback_data": "adm:diagnostics", "row": 21, "position": 0},
    {"text": "🔄 ATUALIZAÇÕES", "callback_data": "adm:updates", "row": 21, "position": 1},
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
    Lê do banco (button_templates.menu="admin_main");
    se vazio, usa o fallback completo.
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

# ============================================
# 🧩 COMANDOS (CLIENTE) — Larizinha Store
# ============================================
# Comandos slash do cliente:
#   /pix, /historico, /afiliados, /id, /saldo,
#   /ranking, /alertas, /gift, /cancelar,
#   /atendimento, /termos, /menu
#
# Cada comando respeita a config "cmd_X_enabled"
# configurável pelo painel admin.
# ============================================

from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.states import RechargeStates
from core.models import User
from core.services import config as config_service


router = Router(name="comandos")


# ============================================
# 🧰 AUXILIARES
# ============================================
def _format_brl(v) -> str:
    if v is None:
        return "0,00"
    return f"{float(v):.2f}".replace(".", ",")


async def _is_command_enabled(
    session: AsyncSession,
    cmd: str,
) -> bool:
    """Verifica se o comando está ativo no painel admin."""
    value = await config_service.get_str(session, f"cmd_{cmd}_enabled", "true")
    return str(value).lower() == "true"


async def _check_enabled(
    target: Message,
    session: AsyncSession,
    cmd: str,
) -> bool:
    """Verifica se comando está ativo; se não, avisa."""
    enabled = await _is_command_enabled(session, cmd)
    if not enabled:
        await target.answer(
            f"⚠️ O comando /{cmd} está temporariamente desativado."
        )
        return False
    return True


# ============================================
# /menu — VOLTAR AO INÍCIO
# ============================================
@router.message(Command("menu"))
async def cmd_menu(
    message: Message,
    user: User,
    session: AsyncSession,
) -> None:
    if not await _check_enabled(message, session, "menu"):
        return

    from bot.keyboards.main_menu import build_main_menu
    from core.config import settings
    from core.services.messages import render_message

    text = await render_message(
        session,
        key="start",
        variables={
            "USER_ID": user.telegram_id,
            "USERNAME": user.username or user.first_name or "Usuário",
            "BALANCE": _format_brl(user.balance),
        },
    )
    keyboard = await build_main_menu(session, webapp_url=settings.webapp_url)
    await message.answer(text, reply_markup=keyboard)


# ============================================
# /id — MOSTRA O ID DO CLIENTE
# ============================================
@router.message(Command("id"))
async def cmd_id(
    message: Message,
    user: User,
    session: AsyncSession,
) -> None:
    if not await _check_enabled(message, session, "id"):
        return

    await message.answer(
        f"🆔 <b>Seu id é:</b> <code>{user.telegram_id}</code>"
    )


# ============================================
# /saldo — MOSTRA O SALDO
# ============================================
@router.message(Command("saldo"))
async def cmd_saldo(
    message: Message,
    user: User,
    session: AsyncSession,
) -> None:
    if not await _check_enabled(message, session, "saldo"):
        return

    balance = _format_brl(user.balance)

    text = (
        f"╭───────────────────╮\n"
        f"💰 Carteira id: <code>{user.telegram_id}</code>\n"
        f"💸 Saldo: <b>R$ {balance}</b>\n"
        f"╰───────────────────╯"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💰 Recarregar", callback_data="menu:recarregar")],
            [InlineKeyboardButton(text="👤 Meu Perfil", callback_data="menu:perfil")],
        ]
    )

    await message.answer(text, reply_markup=keyboard)


# ============================================
# /pix — GERAR PIX DIRETO
# ============================================
@router.message(Command("pix"))
async def cmd_pix(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    if not await _check_enabled(message, session, "pix"):
        return

    arg = (command.args or "").strip()

    # Sem argumento → mostra exemplo
    if not arg:
        await message.answer(
            f"⚠️ <b>Você enviou em um formato incorreto.</b>\n\n"
            f"Envie /pix e o valor que deseja recarregar.\n\n"
            f"<b>Exemplos:</b>\n"
            f"• <code>/pix 10</code>\n"
            f"• <code>/pix 5.25</code>\n"
            f"• <code>/pix 50</code>"
        )
        return

    # Normaliza
    raw = arg.replace(",", ".").replace("R$", "").strip()

    try:
        amount = Decimal(raw)
        if amount <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer(
            f"❌ <b>Valor inválido.</b>\n\n"
            f"Envie apenas números. Exemplo:\n"
            f"• <code>/pix 10</code>\n"
            f"• <code>/pix 5.25</code>"
        )
        return

    amount = amount.quantize(Decimal("0.01"))

    # Valida limites
    min_amount = await config_service.get_decimal(session, "pix_min", "4.00")
    max_amount = await config_service.get_decimal(session, "pix_max", "500.00")

    if amount < min_amount:
        await message.answer(
            f"❌ Valor mínimo para recarga: <b>R$ {_format_brl(min_amount)}</b>"
        )
        return

    if amount > max_amount:
        await message.answer(
            f"❌ Valor máximo para recarga: <b>R$ {_format_brl(max_amount)}</b>"
        )
        return

    # Gera o Pix
    from bot.handlers.pix import _create_pix_message

    await _create_pix_message(
        message=message,
        user=user,
        session=session,
        amount=amount,
        purpose="recharge",
    )


# ============================================
# /historico — HISTÓRICO DE COMPRAS
# ============================================
@router.message(Command("historico"))
async def cmd_historico(
    message: Message,
    user: User,
    session: AsyncSession,
) -> None:
    if not await _check_enabled(message, session, "historico"):
        return

    # Reusa o handler do perfil via callback fake
    # (mais simples e evita duplicação)
    from bot.handlers.perfil import _show_history

    # Cria um CallbackQuery "fake" a partir da mensagem
    # Não é possível criar diretamente — então vamos replicar
    # a lógica aqui de forma simples:

    from datetime import datetime, timezone
    from sqlalchemy import func

    now = datetime.now(timezone.utc)

    from core.models import Order, OrderStatus, StockItem

    stmt = (
        select(Order)
        .where(
            Order.user_id == user.id,
            Order.status.in_([OrderStatus.PAID, OrderStatus.DELIVERED]),
        )
        .order_by(Order.created_at.desc())
        .limit(10)
    )
    result = await session.execute(stmt)
    orders = list(result.scalars().all())

    if not orders:
        await message.answer(
            f"📜 <b>Histórico de compras</b>\n\n"
            f"Você ainda não realizou nenhuma compra.\n\n"
            f"🛍 Use /menu para ver o catálogo."
        )
        return

    total = len(orders)

    lines = [
        f"📜 <b>Histórico de compras</b>",
        f"━━━━━━━━━━━━━━━━━━━━━━",
        f"📊 Total: <b>{total}</b>",
        "",
    ]

    for order in orders[:5]:
        date = order.created_at.strftime("%d/%m/%Y") if order.created_at else "—"
        exp = order.expires_at.strftime("%d/%m/%Y") if order.expires_at else "—"

        lines.append(f"🛍 <b>{order.product_name}</b>")
        lines.append(
            f"├ ⏰ {date} → {exp}\n"
            f"├ 💰 R$ {_format_brl(order.total_price)}\n"
            f"├ 🎫 <code>{order.order_code[:16]}...</code>"
        )

        # Pega primeiro item
        item_stmt = select(StockItem).where(
            StockItem.order_id == order.id
        ).limit(1)
        item_result = await session.execute(item_stmt)
        item = item_result.scalar_one_or_none()

        if item:
            lines.append(f"├ 📧 <code>{item.email or 'N/A'}</code>")
            lines.append(f"└ 🔑 <code>{item.password or 'N/A'}</code>")

        lines.append("")

    if total > 5:
        lines.append(f"<i>+{total - 5} compras antigas (veja no perfil)</i>")

    text = "\n".join(lines)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👤 Ver completo", callback_data="menu:perfil")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="menu:voltar")],
        ]
    )

    if len(text) > 4000:
        text = text[:4000] + "\n\n<i>... (truncado)</i>"

    await message.answer(text, reply_markup=keyboard)


# ============================================
# /afiliados — PROGRAMA DE AFILIADOS
# ============================================
@router.message(Command("afiliados"))
async def cmd_afiliados(
    message: Message,
    user: User,
    session: AsyncSession,
) -> None:
    if not await _check_enabled(message, session, "afiliados"):
        return

    enabled = await config_service.get_bool(session, "affiliate_enabled", True)
    if not enabled:
        await message.answer("⚠️ O programa de afiliados está temporariamente desativado.")
        return

    # Reusa a lógica de afiliados enviando uma mensagem nova
    from sqlalchemy import func
    from core.models import AffiliateCommission
    from core.config import settings

    commission = await config_service.get_str(session, "affiliate_commission", "20.0")
    min_withdrawal = await config_service.get_str(session, "affiliate_min_withdrawal", "20.00")

    referrals = await session.scalar(
        select(func.count(User.id)).where(User.referred_by == user.telegram_id)
    ) or 0

    total_earned = await session.scalar(
        select(func.coalesce(func.sum(AffiliateCommission.commission), 0)).where(
            AffiliateCommission.affiliate_telegram_id == user.telegram_id
        )
    ) or Decimal("0.00")

    media = (
        (total_earned / referrals).quantize(Decimal("0.01"))
        if referrals > 0 else Decimal("0.00")
    )

    bot_username = settings.telegram_bot_username or "meu_bot"
    referral_link = f"https://t.me/{bot_username}?start={user.telegram_id}"

    text = (
        f"💰 <b>PROGRAMA DE AFILIADOS</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚙️ Status: <b>🟢 Ativo</b>\n"
        f"🧲 Sua comissão: <b>{commission}%</b>\n\n"
        f"👥 Indicações: <b>{referrals}</b>\n"
        f"🪙 Total ganho: <b>R$ {_format_brl(total_earned)}</b>\n"
        f"📊 Média: <b>R$ {_format_brl(media)}</b>\n"
        f"💰 Saque mínimo: <b>R$ {min_withdrawal}</b>\n\n"
        f"🔥 Saldo de comissões: <b>R$ {_format_brl(user.affiliate_balance)}</b>\n\n"
        f"🔗 Seu link:\n<code>{referral_link}</code>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🤝 Abrir programa", callback_data="menu:afiliados")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="menu:voltar")],
        ]
    )

    await message.answer(text, reply_markup=keyboard)


# ============================================
# /ranking — RANKINGS
# ============================================
@router.message(Command("ranking"))
async def cmd_ranking(
    message: Message,
    user: User,
    session: AsyncSession,
) -> None:
    if not await _check_enabled(message, session, "ranking"):
        return

    # Redireciona pro menu de ranking
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏆 Ver rankings", callback_data="menu:ranking")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="menu:voltar")],
        ]
    )

    await message.answer(
        f"🏆 <b>Rankings</b>\n\n"
        f"Clique no botão abaixo para ver os rankings completos.",
        reply_markup=keyboard,
    )


# ============================================
# /alertas — ALERTAS DE ESTOQUE
# ============================================
@router.message(Command("alertas"))
async def cmd_alertas(
    message: Message,
    user: User,
    session: AsyncSession,
) -> None:
    if not await _check_enabled(message, session, "alertas"):
        return

    enabled = await config_service.get_bool(session, "stock_alerts_enabled", True)
    if not enabled:
        await message.answer("⚠️ O sistema de alertas está temporariamente desativado.")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔔 Gerenciar alertas", callback_data="menu:alertas")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="menu:voltar")],
        ]
    )

    await message.answer(
        f"🔔 <b>Sistema de Alertas</b>\n\n"
        f"Escolha quais produtos você quer ser notificado quando voltarem ao estoque.",
        reply_markup=keyboard,
    )


# ============================================
# /gift — RESGATAR GIFT CARD
# ============================================
@router.message(Command("gift"))
async def cmd_gift(
    message: Message,
    user: User,
    session: AsyncSession,
) -> None:
    if not await _check_enabled(message, session, "gift"):
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Resgatar Gift Card", callback_data="gift:resgatar")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="menu:voltar")],
        ]
    )

    await message.answer(
        f"🎁 <b>Resgatar Gift Card</b>\n\n"
        f"Clique no botão abaixo para resgatar seu código.",
        reply_markup=keyboard,
    )


# ============================================
# /atendimento — ATENDIMENTO
# ============================================
@router.message(Command("atendimento"))
async def cmd_atendimento(
    message: Message,
    user: User,
    session: AsyncSession,
) -> None:
    if not await _check_enabled(message, session, "atendimento"):
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎧 Abrir atendimento", callback_data="menu:atendimento")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="menu:voltar")],
        ]
    )

    await message.answer(
        f"🎧 <b>Atendimento</b>\n\n"
        f"Escolha como deseja ser atendido.",
        reply_markup=keyboard,
    )


# ============================================
# /cancelar — CANCELA ESTADO ATUAL
# ============================================
@router.message(Command("cancelar"))
async def cmd_cancelar(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    current = await state.get_state()

    if current is None:
        await message.answer("ℹ️ Nada para cancelar.")
        return

    # Se tem reserva, libera
    data = await state.get_data()
    product_id = data.get("product_id")

    if product_id:
        from core.services import stock as stock_service
        await stock_service.release_reservation(
            session, user.telegram_id, product_id
        )

    await state.clear()

    await message.answer(
        f"❌ <b>Operação cancelada!</b>\n\n"
        f"Use /menu para voltar ao início."
    )


# ============================================
# 🔘 FALLBACK: mensagem solta sem estado
# ============================================
@router.message(F.text.regexp(r"^\d+([.,]\d{1,2})?$"))
async def msg_number_without_state(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """
    Se o usuário mandar um número solto sem contexto,
    sugerimos /pix ou avisamos que não há operação ativa.
    """
    current_state = await state.get_state()

    # Se tem estado, deixa os outros handlers tratarem
    if current_state is not None:
        return

    raw = (message.text or "").strip()
    try:
        amount = Decimal(raw.replace(",", "."))
    except (InvalidOperation, ValueError):
        return

    if amount <= 0:
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"💠 Gerar Pix de R$ {_format_brl(amount)}",
                callback_data=f"pix:gerar:{amount}:",
            )],
            [InlineKeyboardButton(text="🔙 Menu principal", callback_data="menu:voltar")],
        ]
    )

    await message.answer(
        f"💡 Você enviou <b>R$ {_format_brl(amount)}</b>.\n\n"
        f"Deseja gerar um Pix nesse valor?",
        reply_markup=keyboard,
    )

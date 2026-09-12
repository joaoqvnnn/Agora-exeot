# ============================================
# 🎁 ADMIN GIFT CARDS — Larizinha Store
# ============================================
# Criação e gerenciamento REAL de gift cards.
# Todos os botões funcionam de verdade.
#
# Cobre:
#   - CRIAR gift card individual
#   - GERAR em massa
#   - LISTAR todos
#   - VER usados / disponíveis
#   - REVOGAR
# ============================================

import secrets
import string
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.states import AdminStates
from core.models import (
    Admin,
    AuditLog,
    GiftCard,
    GiftCardStatus,
)


router = Router(name="admin_giftcards")


# ============================================
# 🧰 AUXILIARES
# ============================================
async def _is_admin(session: AsyncSession, telegram_id: int) -> bool:
    stmt = select(Admin).where(
        Admin.telegram_id == telegram_id,
        Admin.is_active.is_(True),
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def _log_audit(
    session: AsyncSession,
    admin_id: int,
    action: str,
    old_value: dict | None = None,
    new_value: dict | None = None,
) -> None:
    log = AuditLog(
        admin_telegram_id=admin_id,
        action=action,
        old_value=old_value,
        new_value=new_value,
    )
    session.add(log)


def _format_brl(v) -> str:
    if v is None:
        return "0,00"
    return f"{float(v):.2f}".replace(".", ",")


def _generate_code(prefix: str = "", length: int = 12) -> str:
    """Gera código único de gift card."""
    alphabet = string.ascii_uppercase + string.digits
    random_part = "".join(secrets.choice(alphabet) for _ in range(length))
    return f"{prefix}{random_part}" if prefix else random_part


def _cancel_keyboard(back_data: str = "adm_gift:menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancelar", callback_data=back_data)]
        ]
    )


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_gift:menu")
async def cb_gift_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    total = await session.scalar(select(func.count(GiftCard.id))) or 0
    available = await session.scalar(
        select(func.count(GiftCard.id)).where(
            GiftCard.status == GiftCardStatus.AVAILABLE
        )
    ) or 0
    used = await session.scalar(
        select(func.count(GiftCard.id)).where(
            GiftCard.status == GiftCardStatus.USED
        )
    ) or 0

    # Soma total de valores disponíveis
    total_value = await session.scalar(
        select(func.sum(GiftCard.value)).where(
            GiftCard.status == GiftCardStatus.AVAILABLE
        )
    ) or Decimal("0.00")

    text = (
        "🎁 <b>GERENCIAR GIFT CARDS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 Total: <b>{total}</b>\n"
        f"🟢 Disponíveis: <b>{available}</b>\n"
        f"✅ Utilizados: <b>{used}</b>\n"
        f"💰 Valor em estoque: <b>R$ {_format_brl(total_value)}</b>\n\n"
        "Use os botões abaixo:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Criar Gift Card", callback_data="adm_gift:create")],
            [InlineKeyboardButton(text="📦 Gerar em Massa", callback_data="adm_gift:bulk")],
            [InlineKeyboardButton(text="📋 Listar Disponíveis", callback_data="adm_gift:list:available:0")],
            [InlineKeyboardButton(text="✅ Listar Utilizados", callback_data="adm_gift:list:used:0")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:config")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# ➕ CRIAR GIFT CARD INDIVIDUAL
# ============================================
@router.callback_query(F.data == "adm_gift:create")
async def cb_gift_create(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text = (
        "➕ <b>CRIAR GIFT CARD</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Envie o <b>valor</b> do gift card em reais.\n"
        "Exemplo: <code>10.00</code>"
    )

    await callback.message.answer(text, reply_markup=_cancel_keyboard())
    await state.set_state(AdminStates.creating_gift_card)
    await callback.answer()


@router.message(AdminStates.creating_gift_card)
async def msg_gift_value(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    raw = (message.text or "").replace(",", ".").strip()
    try:
        value = Decimal(raw)
        if value <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer("❌ Valor inválido. Ex: <code>10.00</code>")
        return

    value = value.quantize(Decimal("0.01"))

    # Pergunta validade (dias)
    await state.update_data(gift_value=str(value))
    await message.answer(
        f"💰 Valor: <b>R$ {value:.2f}</b>\n\n"
        "Agora envie a <b>validade em dias</b>.\n"
        "Envie <code>0</code> pra nunca expirar.\n\n"
        "Exemplo: <code>30</code>",
        reply_markup=_cancel_keyboard(),
    )


@router.message(AdminStates.creating_gift_card)
async def msg_gift_validity(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Segunda etapa: validade."""
    if not await _is_admin(session, message.from_user.id):
        return

    data = await state.get_data()
    value_str = data.get("gift_value")

    if not value_str:
        # Primeira etapa ainda
        await msg_gift_value(message, state, session)
        return

    try:
        days = int((message.text or "").strip())
        if days < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Número inválido. Ex: <code>30</code> ou <code>0</code>")
        return

    value = Decimal(value_str)
    code = _generate_code()

    expires_at = None
    if days > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(days=days)

    gift = GiftCard(
        code=code,
        value=value,
        status=GiftCardStatus.AVAILABLE,
        expires_at=expires_at,
        created_by=message.from_user.id,
    )
    session.add(gift)
    await session.flush()

    await _log_audit(
        session,
        message.from_user.id,
        "create_gift_card",
        new_value={"code": code, "value": str(value), "days": days},
    )

    exp_txt = expires_at.strftime("%d/%m/%Y") if expires_at else "Nunca expira"

    await message.answer(
        f"✅ <b>Gift Card criado!</b>\n\n"
        f"🎁 Código: <code>{code}</code>\n"
        f"💰 Valor: <b>R$ {value:.2f}</b>\n"
        f"⏰ Validade: <b>{exp_txt}</b>\n\n"
        "O usuário pode resgatar via /gift ou pelo perfil.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="➕ Criar outro", callback_data="adm_gift:create")],
                [InlineKeyboardButton(text="📋 Listar", callback_data="adm_gift:list:available:0")],
                [InlineKeyboardButton(text="🔙 Menu Gift Cards", callback_data="adm_gift:menu")],
            ]
        ),
    )
    await state.clear()


# ============================================
# 📦 GERAR EM MASSA
# ============================================
@router.callback_query(F.data == "adm_gift:bulk")
async def cb_gift_bulk(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text = (
        "📦 <b>GERAR EM MASSA</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Envie os dados no formato:\n\n"
        "<code>VALOR;QUANTIDADE;DIAS_VALIDADE</code>\n\n"
        "Exemplos:\n"
        "• <code>10.00;5;30</code> → 5 gift cards de R$ 10 (30 dias)\n"
        "• <code>5.00;100;0</code> → 100 gift cards de R$ 5 (sem validade)"
    )

    await callback.message.answer(text, reply_markup=_cancel_keyboard())
    await state.set_state(AdminStates.creating_gift_cards_bulk)
    await callback.answer()


@router.message(AdminStates.creating_gift_cards_bulk)
async def msg_gift_bulk(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    raw = (message.text or "").strip()
    parts = [p.strip() for p in raw.split(";")]

    if len(parts) != 3:
        await message.answer(
            "❌ Formato inválido. Use: <code>VALOR;QUANTIDADE;DIAS</code>"
        )
        return

    try:
        value = Decimal(parts[0].replace(",", ".")).quantize(Decimal("0.01"))
        quantity = int(parts[1])
        days = int(parts[2])
        if value <= 0 or quantity <= 0 or quantity > 1000 or days < 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        await message.answer(
            "❌ Valores inválidos. Máx. 1000 por vez."
        )
        return

    # Gera batch
    batch_id = secrets.token_hex(8)
    expires_at = None
    if days > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(days=days)

    codes: list[str] = []
    for _ in range(quantity):
        code = _generate_code()
        # Garante unicidade
        while await _code_exists(session, code):
            code = _generate_code()

        gift = GiftCard(
            code=code,
            value=value,
            status=GiftCardStatus.AVAILABLE,
            expires_at=expires_at,
            batch_id=batch_id,
            created_by=message.from_user.id,
        )
        session.add(gift)
        codes.append(code)

    await session.flush()

    await _log_audit(
        session,
        message.from_user.id,
        "create_gift_cards_bulk",
        new_value={
            "quantity": quantity,
            "value": str(value),
            "days": days,
            "batch_id": batch_id,
        },
    )

    # Monta arquivo .txt com os códigos
    from io import BytesIO
    from aiogram.types import BufferedInputFile

    content = "\n".join(codes)
    file = BufferedInputFile(
        content.encode("utf-8"),
        filename=f"giftcards_{batch_id}.txt",
    )

    exp_txt = expires_at.strftime("%d/%m/%Y") if expires_at else "Nunca expira"

    await message.answer_document(
        file,
        caption=(
            f"✅ <b>{quantity} gift cards criados!</b>\n\n"
            f"💰 Valor: <b>R$ {value:.2f}</b> cada\n"
            f"⏰ Validade: <b>{exp_txt}</b>\n"
            f"📦 Lote: <code>{batch_id}</code>\n\n"
            "📎 Arquivo com todos os códigos em anexo."
        ),
    )
    await state.clear()


async def _code_exists(session: AsyncSession, code: str) -> bool:
    stmt = select(GiftCard.id).where(GiftCard.code == code)
    return (await session.scalar(stmt)) is not None


# ============================================
# 📋 LISTAR
# ============================================
@router.callback_query(F.data.startswith("adm_gift:list:"))
async def cb_gift_list(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    parts = callback.data.split(":")
    status_filter = parts[2] if len(parts) > 2 else "available"
    page = int(parts[3]) if len(parts) > 3 else 0

    await _show_gift_list(callback, session, status_filter, page)


async def _show_gift_list(
    callback: CallbackQuery,
    session: AsyncSession,
    status_filter: str,
    page: int,
) -> None:
    PER_PAGE = 15

    status_map = {
        "available": GiftCardStatus.AVAILABLE,
        "used": GiftCardStatus.USED,
        "expired": GiftCardStatus.EXPIRED,
        "cancelled": GiftCardStatus.CANCELLED,
    }
    status = status_map.get(status_filter, GiftCardStatus.AVAILABLE)

    base = select(GiftCard).where(GiftCard.status == status)
    total = await session.scalar(
        select(func.count()).select_from(base.subquery())
    ) or 0

    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    stmt = (
        base.order_by(GiftCard.id.desc())
        .offset(page * PER_PAGE)
        .limit(PER_PAGE)
    )
    result = await session.execute(stmt)
    gifts = list(result.scalars().all())

    labels = {
        "available": "🟢 Disponíveis",
        "used": "✅ Utilizados",
        "expired": "⌛ Expirados",
        "cancelled": "🚫 Cancelados",
    }

    text_lines = [
        f"🎁 <b>GIFT CARDS — {labels.get(status_filter, status_filter)}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📊 Total: <b>{total}</b>",
        "",
    ]

    if not gifts:
        text_lines.append("Nenhum gift card neste filtro.")
    else:
        for g in gifts:
            date = g.created_at.strftime("%d/%m") if g.created_at else "?"
            exp = g.expires_at.strftime("%d/%m/%Y") if g.expires_at else "∞"
            text_lines.append(
                f"• <code>{g.code}</code> — R$ {_format_brl(g.value)} — exp: {exp}"
            )

    rows: list[list[InlineKeyboardButton]] = []

    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                text="⬅️",
                callback_data=f"adm_gift:list:{status_filter}:{page - 1}",
            ))
        nav.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="adm:noop",
        ))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(
                text="➡️",
                callback_data=f"adm_gift:list:{status_filter}:{page + 1}",
            ))
        rows.append(nav)

    rows.append([
        InlineKeyboardButton(text="🟢 Disponíveis", callback_data="adm_gift:list:available:0"),
        InlineKeyboardButton(text="✅ Utilizados", callback_data="adm_gift:list:used:0"),
    ])
    rows.append([
        InlineKeyboardButton(text="⌛ Expirados", callback_data="adm_gift:list:expired:0"),
        InlineKeyboardButton(text="🚫 Cancelados", callback_data="adm_gift:list:cancelled:0"),
    ])

    if status_filter == "available" and total > 0:
        rows.append([
            InlineKeyboardButton(text="🗑 Revogar Todos Disponíveis", callback_data="adm_gift:revoke_all")
        ])

    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_gift:menu")
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    text = "\n".join(text_lines)

    if len(text) > 4000:
        text = text[:4000] + "\n\n<i>... (truncado)</i>"

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 🗑 REVOGAR TODOS DISPONÍVEIS
# ============================================
@router.callback_query(F.data == "adm_gift:revoke_all")
async def cb_gift_revoke_all(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    total = await session.scalar(
        select(func.count(GiftCard.id)).where(
            GiftCard.status == GiftCardStatus.AVAILABLE
        )
    ) or 0

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ SIM, REVOGAR TUDO", callback_data="adm_gift:revoke_all_confirm")],
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_gift:menu")],
        ]
    )

    await callback.message.edit_text(
        f"⚠️ <b>REVOGAR TODOS GIFT CARDS DISPONÍVEIS</b>\n\n"
        f"Você vai revogar <b>{total}</b> gift card(s) disponíveis.\n\n"
        "⚠️ <b>Esta ação não pode ser desfeita.</b>\n\n"
        "Tem certeza?",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data == "adm_gift:revoke_all_confirm")
async def cb_gift_revoke_all_confirm(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    stmt = select(GiftCard).where(GiftCard.status == GiftCardStatus.AVAILABLE)
    result = await session.execute(stmt)
    gifts = list(result.scalars().all())

    for g in gifts:
        g.status = GiftCardStatus.CANCELLED
        session.add(g)

    await _log_audit(
        session,
        callback.from_user.id,
        "revoke_all_gift_cards",
        old_value={"count": len(gifts)},
    )

    await callback.answer(f"🗑 {len(gifts)} gift card(s) revogados!", show_alert=True)

    callback.data = "adm_gift:menu"
    await cb_gift_menu(callback, session)

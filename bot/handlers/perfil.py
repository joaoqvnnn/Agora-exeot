# ============================================
# 👤 PERFIL — Larizinha Store
# ============================================
# Perfil do cliente + histórico + gift card + alterar dados.
# Mensagem única (edita, não acumula).
# ============================================

from datetime import datetime, timezone
from decimal import Decimal

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.perfil import (
    build_change_cancel_keyboard,
    build_change_data_keyboard,
    build_email_code_keyboard,
    build_gift_card_keyboard,
    build_history_keyboard,
    build_no_active_keyboard,
    build_order_detail_keyboard,
    build_profile_keyboard,
)
from bot.states.states import GiftCardStates, ProfileStates
from core.models import (
    GiftCard,
    GiftCardStatus,
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
    StockItem,
    StockStatus,
    User,
)
from core.services.messages import render_message


router = Router(name="perfil")


# ============================================
# 🧰 AUXILIARES
# ============================================
def _format_brl(v) -> str:
    if v is None:
        return "0,00"
    return f"{float(v):.2f}".replace(".", ",")


def _format_date(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%d/%m/%Y")


async def _edit_or_send(callback: CallbackQuery, text: str, keyboard) -> None:
    try:
        await callback.message.edit_text(
            text, reply_markup=keyboard, disable_web_page_preview=True
        )
    except Exception:
        try:
            await callback.message.answer(
                text, reply_markup=keyboard, disable_web_page_preview=True
            )
        except Exception as e:
            logger.warning(f"⚠️ Falha ao exibir: {e}")


# ============================================
# 👤 MEU PERFIL
# ============================================
@router.callback_query(F.data == "menu:perfil")
async def cb_profile(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    await _show_profile(callback, user, session)
    await callback.answer()


async def _show_profile(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    # Estatísticas reais
    purchases = await session.scalar(
        select(func.count(Order.id)).where(
            Order.user_id == user.id,
            Order.status.in_([OrderStatus.PAID, OrderStatus.DELIVERED]),
        )
    ) or 0

    total_spent = user.total_spent or Decimal("0.00")
    total_recharged = user.total_recharged or Decimal("0.00")

    # Gifts resgatados
    gifts_total = await session.scalar(
        select(func.coalesce(func.sum(GiftCard.value), 0)).where(
            GiftCard.redeemed_by == user.telegram_id,
            GiftCard.status == GiftCardStatus.USED,
        )
    ) or Decimal("0.00")

    whatsapp = user.whatsapp or "Não cadastrado"

    text = (
        f"👤 <b>Meu perfil</b>\n\n"
        f"🔍 Veja aqui os detalhes da sua conta:\n\n"
        f"- 👤 <b>Informações:</b>\n"
        f"🆔 ID da Carteira: <code>{user.telegram_id}</code>\n"
        f"💰 Saldo Atual: <b>R$ {_format_brl(user.balance)}</b>\n"
        f"📲 Seu Whatsapp: {whatsapp}\n\n"
        f"─── 📊 <b>Suas Movimentações:</b>\n"
        f"ー 🛒 Compras Realizadas: <b>{purchases}</b>\n"
        f"ー 💰 Total Gasto Em Compras: <b>R$ {_format_brl(total_spent)}</b>\n"
        f"ー 💠 Pix Inseridos: <b>R$ {_format_brl(total_recharged)}</b>\n"
        f"ー 🎁 Gifts Resgatados: <b>R$ {_format_brl(gifts_total)}</b>"
    )

    keyboard = build_profile_keyboard()

    await _edit_or_send(callback, text, keyboard)

    user.last_menu = "perfil"
    session.add(user)


# ============================================
# 🔙 VOLTAR AO PERFIL
# ============================================
@router.callback_query(F.data == "prof:voltar")
async def cb_back_profile(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    await cb_profile(callback, user, session)


# ============================================
# 📜 HISTÓRICO DE COMPRAS
# ============================================
@router.callback_query(F.data.startswith("prof:historico:"))
async def cb_history(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    parts = callback.data.split(":")
    try:
        page = int(parts[2])
    except (ValueError, IndexError):
        page = 0

    await _show_history(callback, user, session, page=page)
    await callback.answer()


@router.callback_query(F.data == "prof:historico_ativas:0")
async def cb_history_active(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    await _show_history(callback, user, session, page=0, only_active=True)
    await callback.answer()


async def _show_history(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    page: int = 0,
    only_active: bool = False,
) -> None:
    now = datetime.now(timezone.utc)

    # Busca pedidos
    stmt = select(Order).where(
        Order.user_id == user.id,
        Order.status.in_([OrderStatus.PAID, OrderStatus.DELIVERED]),
    ).order_by(Order.created_at.desc())

    if only_active:
        stmt = stmt.where(
            Order.expires_at.is_not(None),
            Order.expires_at > now,
        )

    result = await session.execute(stmt)
    orders = list(result.scalars().all())

    total_orders = len(orders)

    if not orders:
        if only_active:
            text = "Você não tem compras ativas (não vencidas) no bot.\n\nUse o botão abaixo para ver todas as compras."
            keyboard = build_no_active_keyboard()
        else:
            text = (
                f"📜 <b>Histórico de compras</b>\n\n"
                f"Você ainda não realizou nenhuma compra.\n\n"
                f"🛍 Use o botão abaixo para ver nosso catálogo."
            )
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🛍 Comprar Produtos", callback_data="menu:comprar")],
                    [InlineKeyboardButton(text="🔙 Voltar", callback_data="prof:voltar")],
                ]
            )
        await _edit_or_send(callback, text, keyboard)
        return

    # Paginação
    PER_PAGE = 1  # mostra 1 por vez (padrão original)
    total_pages = max(1, (total_orders + PER_PAGE - 1) // PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    order = orders[page]

    # Itens do estoque vinculados
    items_stmt = select(StockItem).where(StockItem.order_id == order.id)
    items_result = await session.execute(items_stmt)
    items = list(items_result.scalars().all())

    # Monta texto
    purchase_date = _format_date(order.created_at)
    expiration = _format_date(order.expires_at)

    text_lines = [
        f"🛍 Compras: <b>{total_orders}</b>",
        "",
        f"⏰ Data da compra: {purchase_date}",
        f"📆 Vencimento: {expiration}",
        f"💰 Valor: <b>R$ {_format_brl(order.total_price)}</b>",
        f"🎫 ID da compra: <code>{order.order_code}</code>",
        f"⚜️ Serviço: <b>{order.product_name}</b>",
    ]

    if items:
        item = items[0]
        email = item.email or "N/A"
        password = item.password or "N/A"
        note = item.note or "Use o link abaixo para ativar:"

        text_lines.append(f"📧 Email: <code>{email}</code>")
        text_lines.append(f"🔐 Senha: <code>{password}</code>")
        text_lines.append(f"📃 Nota: {note}")

        if item.code:
            text_lines.append(f"🔗 Ativação: {item.code}")

        if len(items) > 1:
            text_lines.append("")
            text_lines.append(f"<i>+{len(items) - 1} login(s) extra(s) nesta compra.</i>")

    text = "\n".join(text_lines)

    # Verifica se está ativa
    is_active = order.expires_at and order.expires_at > now

    keyboard = build_history_keyboard(
        current_page=page,
        total_pages=total_pages,
        has_active=is_active,
    )

    await _edit_or_send(callback, text, keyboard)


# ============================================
# 📄 VER ITEM DO HISTÓRICO (detalhe)
# ============================================
@router.callback_query(F.data.startswith("prof:order:"))
async def cb_order_detail(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    parts = callback.data.split(":")
    try:
        order_id = int(parts[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Pedido inválido.", show_alert=True)
        return

    order = await session.get(Order, order_id)
    if order is None or order.user_id != user.id:
        await callback.answer("❌ Pedido não encontrado.", show_alert=True)
        return

    items_stmt = select(StockItem).where(StockItem.order_id == order.id)
    items_result = await session.execute(items_stmt)
    items = list(items_result.scalars().all())

    now = datetime.now(timezone.utc)
    is_active = order.expires_at and order.expires_at > now

    text_lines = [
        f"📦 <b>Detalhes do Pedido</b>",
        "",
        f"🎫 ID: <code>{order.order_code}</code>",
        f"⚜️ Produto: <b>{order.product_name}</b>",
        f"📅 Data: {_format_date(order.created_at)}",
        f"📆 Vence: {_format_date(order.expires_at)}",
        f"💰 Valor: <b>R$ {_format_brl(order.total_price)}</b>",
        f"📊 Status: {'🟢 Ativo' if is_active else '⚪ Expirado'}",
        "",
    ]

    for idx, item in enumerate(items, start=1):
        text_lines.append(f"🔐 <b>Login {idx}/{len(items)}</b>")
        text_lines.append(f"📧 Email: <code>{item.email or 'N/A'}</code>")
        text_lines.append(f"🔑 Senha: <code>{item.password or 'N/A'}</code>")
        if item.code:
            text_lines.append(f"🔗 Código: <code>{item.code}</code>")
        if item.note:
            text_lines.append(f"📃 Nota: {item.note}")
        text_lines.append("")

    text = "\n".join(text_lines)

    keyboard = build_order_detail_keyboard(
        order_id=order.id,
        has_activation_link=False,
    )

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()


# ============================================
# 🎁 RESGATAR GIFT CARD
# ============================================
@router.callback_query(F.data == "gift:resgatar")
async def cb_gift_start(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    text = (
        f"🎁 <b>RESGATAR GIFT CARD</b>\n\n"
        f"Digite o código do seu gift card abaixo:\n\n"
        f"Exemplo: <code>ABC123XYZ456</code>"
    )

    keyboard = build_gift_card_keyboard()

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()

    await state.set_state(GiftCardStates.waiting_code)


@router.message(GiftCardStates.waiting_code)
async def msg_gift_code(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    raw = (message.text or "").strip().upper()

    if not raw:
        await message.answer("❌ Código vazio. Envie novamente ou /cancelar.")
        return

    if raw.startswith("/CANCELAR") or raw.startswith("/START"):
        await state.clear()
        await message.answer("❌ Operação cancelada.")
        return

    # Busca o gift card
    stmt = select(GiftCard).where(GiftCard.code == raw)
    result = await session.execute(stmt)
    gift = result.scalar_one_or_none()

    if gift is None:
        await message.answer("❌ Gift não encontrado.")
        return

    if gift.status == GiftCardStatus.USED:
        await message.answer("❌ Este gift card já foi utilizado.")
        return

    if gift.status == GiftCardStatus.CANCELLED:
        await message.answer("❌ Este gift card foi cancelado.")
        return

    if gift.status == GiftCardStatus.EXPIRED:
        await message.answer("❌ Este gift card expirou.")
        return

    # Verifica validade
    if gift.expires_at:
        now = datetime.now(timezone.utc)
        if gift.expires_at < now:
            gift.status = GiftCardStatus.EXPIRED
            session.add(gift)
            await message.answer("❌ Este gift card expirou.")
            return

    # Verifica se já foi resgatado pelo mesmo usuário
    if gift.redeemed_by == user.telegram_id:
        await message.answer("❌ Você já resgatou este gift card.")
        return

    # Aplica o valor
    gift.status = GiftCardStatus.USED
    gift.redeemed_by = user.telegram_id
    gift.redeemed_at = datetime.now(timezone.utc)
    session.add(gift)

    old_balance = user.balance or Decimal("0.00")
    user.balance = old_balance + gift.value
    session.add(user)

    await message.answer(
        f"🎉 <b>Gift card resgatado com sucesso!</b>\n\n"
        f"💰 Valor: <b>R$ {_format_brl(gift.value)}</b>\n"
        f"💸 Novo saldo: <b>R$ {_format_brl(user.balance)}</b>"
    )

    # Notifica canal de logs
    try:
        from bot.handlers.admin.notifications import notify_gift_redeemed

        await notify_gift_redeemed(
            bot=message.bot,
            session=session,
            user_id=user.telegram_id,
            value=float(gift.value),
            code=gift.code,
        )
    except Exception as e:
        logger.debug(f"⚠️ Falha ao notificar gift: {e}")

    await state.clear()

    # Volta pro perfil
    await message.answer(
        "Use /start para voltar ao menu principal.",
    )


@router.callback_query(F.data == "gift:cancelar")
async def cb_gift_cancel(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    await state.clear()
    await cb_profile(callback, user, session)


# ============================================
# ✏️ ALTERAR DADOS
# ============================================
@router.callback_query(F.data == "prof:alterar")
async def cb_change_data(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    text = (
        f"✏️ <b>Alterar Dados</b>\n\n"
        f"Selecione o dado que deseja alterar:\n\n"
        f"📱 WhatsApp: {user.whatsapp or 'Não cadastrado'}"
    )

    keyboard = build_change_data_keyboard(
        whatsapp=user.whatsapp,
        email=user.email,
    )

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()


# ============================================
# 📱 ALTERAR WHATSAPP
# ============================================
@router.callback_query(F.data == "prof:changing_whatsapp")
async def cb_change_whatsapp(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    text = (
        f"📱 <b>Envie seu número de WhatsApp</b>\n\n"
        f"Formato: DDD + Número (apenas números)\n"
        f"Exemplo: <code>11999998888</code>\n\n"
        f"⚠️ Envie <b>remover</b> para remover o número cadastrado."
    )

    keyboard = build_change_cancel_keyboard()

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()

    await state.set_state(ProfileStates.changing_whatsapp)


@router.message(ProfileStates.changing_whatsapp)
async def msg_save_whatsapp(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    raw = (message.text or "").strip().lower()

    if raw.startswith("/cancelar") or raw.startswith("/start"):
        await state.clear()
        await message.answer("❌ Operação cancelada.")
        return

    # Remover
    if raw == "remover":
        user.whatsapp = None
        session.add(user)
        await state.clear()
        await message.answer("✅ WhatsApp removido com sucesso!")
        return

    # Valida número
    digits = "".join(c for c in raw if c.isdigit())

    if len(digits) < 10 or len(digits) > 13:
        await message.answer(
            "❌ Número inválido. Use DDD + Número (10-11 dígitos).\n"
            "Exemplo: <code>11999998888</code>"
        )
        return

    user.whatsapp = digits
    session.add(user)

    await state.clear()

    await message.answer(
        f"✅ WhatsApp salvo: <code>{digits}</code>"
    )


# ============================================
# 📧 ALTERAR E-MAIL
# ============================================
@router.callback_query(F.data == "prof:changing_email")
async def cb_change_email(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    text = (
        f"📧 <b>Envie seu e-mail</b>\n\n"
        f"Será enviado um código de verificação para confirmar.\n\n"
        f"Exemplo: <code>seuemail@gmail.com</code>"
    )

    keyboard = build_change_cancel_keyboard()

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()

    await state.set_state(ProfileStates.changing_email)


@router.message(ProfileStates.changing_email)
async def msg_save_email(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    import re

    raw = (message.text or "").strip().lower()

    if raw.startswith("/cancelar") or raw.startswith("/start"):
        await state.clear()
        await message.answer("❌ Operação cancelada.")
        return

    # Valida
    if not re.match(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", raw):
        await message.answer(
            "❌ E-mail inválido. Tente novamente:\n"
            "Exemplo: <code>seuemail@gmail.com</code>"
        )
        return

    # Guarda o e-mail no state pra confirmar depois
    await state.update_data(new_email=raw)

    # Envia código
    from core.services import email as email_service

    code = email_service.generate_verification_code()

    await state.update_data(email_code=code)

    result = await email_service.send_verification_code(
        to_email=raw,
        code=code,
        purpose="Verificação de e-mail",
    )

    if not result.get("success"):
        await message.answer(
            f"❌ <b>Erro ao enviar e-mail.</b>\n\n"
            f"<code>{result.get('error', 'Erro desconhecido')}</code>"
        )
        return

    await message.answer(
        f"📩 Enviamos um código para <b>{raw}</b>.\n\n"
        f"Digite o código de 6 dígitos recebido:"
    )
    await state.set_state(ProfileStates.waiting_email_code)


@router.message(ProfileStates.waiting_email_code)
async def msg_verify_email_code(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    raw = (message.text or "").strip()

    if raw.startswith("/cancelar") or raw.startswith("/start"):
        await state.clear()
        await message.answer("❌ Operação cancelada.")
        return

    data = await state.get_data()
    expected = data.get("email_code")
    new_email = data.get("new_email")

    if not expected or not new_email:
        await message.answer("❌ Sessão expirada. Recomece em /start.")
        await state.clear()
        return

    if raw != expected:
        await message.answer("❌ Código incorreto. Tente novamente.")
        return

    # Salva
    user.email = new_email
    user.email_verified = True
    session.add(user)

    await state.clear()

    await message.answer(
        f"✅ <b>E-mail verificado e salvo!</b>\n\n"
        f"📧 <code>{new_email}</code>"
    )


# ============================================
# ❌ CANCELAR ALTERAÇÃO
# ============================================
@router.callback_query(F.data == "prof:cancelar")
async def cb_cancel_change(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    await state.clear()
    await cb_profile(callback, user, session)


# ============================================
# 🔄 REENVIAR CÓDIGO
# ============================================
@router.callback_query(F.data == "prof:reenviar_codigo")
async def cb_resend_code(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    new_email = data.get("new_email")

    if not new_email:
        await callback.answer("❌ Sessão expirada.", show_alert=True)
        return

    from core.services import email as email_service

    code = email_service.generate_verification_code()
    await state.update_data(email_code=code)

    result = await email_service.send_verification_code(
        to_email=new_email,
        code=code,
        purpose="Verificação de e-mail",
    )

    if result.get("success"):
        await callback.answer("📩 Código reenviado!", show_alert=True)
    else:
        await callback.answer("❌ Erro ao reenviar.", show_alert=True)


# ============================================
# 🔘 NOOP
# ============================================
@router.callback_query(F.data == "prof:noop")
async def cb_prof_noop(callback: CallbackQuery) -> None:
    await callback.answer()

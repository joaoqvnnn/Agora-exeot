# ============================================
# 🛒 COMPRA — Larizinha Store
# ============================================
# Fluxo completo de compra:
#   - Comprar 1 unidade
#   - Comprar vários (FSM)
#   - Verificação de saldo
#   - Reserva de estoque
#   - Débito + criação de pedido
#   - Entrega imediata
#   - Saldo insuficiente → Pix
#
# Regra de mensagem única (edita, não acumula).
# ============================================

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.pix import build_insufficient_balance_keyboard
from bot.keyboards.produto import (
    build_quantity_confirm_keyboard,
    build_quantity_keyboard,
)
from bot.states.states import PurchaseStates
from core.models import (
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
    PaymentType,
    Product,
    ProductStatus,
    StockItem,
    StockStatus,
    User,
)
from core.services import delivery as delivery_service
from core.services import stock as stock_service
from core.services.messages import render_message


router = Router(name="compra")


# ============================================
# 🧰 AUXILIARES
# ============================================
def _format_brl(v) -> str:
    if v is None:
        return "0,00"
    return f"{float(v):.2f}".replace(".", ",")


def _generate_order_code() -> str:
    """Gera código único de pedido."""
    return str(uuid.uuid4())


async def _count_available_stock(
    session: AsyncSession,
    product_id: int,
) -> int:
    return await session.scalar(
        select(func.count(StockItem.id)).where(
            StockItem.product_id == product_id,
            StockItem.status == StockStatus.AVAILABLE,
        )
    ) or 0


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
            logger.warning(f"⚠️ Falha ao editar/enviar: {e}")


# ============================================
# 💳 COMPRAR 1 UNIDADE
# ============================================
@router.callback_query(F.data.startswith("prod:buy:"))
async def cb_buy_single(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    """Compra de 1 unidade."""
    parts = callback.data.split(":")
    try:
        product_id = int(parts[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Produto inválido.", show_alert=True)
        return

    await _process_purchase(
        callback=callback,
        user=user,
        session=session,
        product_id=product_id,
        quantity=1,
    )


# ============================================
# 🛒 COMPRAR MAIS DE UM (FSM)
# ============================================
@router.callback_query(F.data.startswith("prod:quantity:"))
async def cb_ask_quantity(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """Pergunta quantos logins o usuário quer."""
    parts = callback.data.split(":")
    try:
        product_id = int(parts[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Produto inválido.", show_alert=True)
        return

    product = await session.get(Product, product_id)
    if product is None or product.status != ProductStatus.ACTIVE:
        await callback.answer("❌ Produto não disponível.", show_alert=True)
        return

    stock = await _count_available_stock(session, product_id)
    if stock <= 0:
        await callback.answer("❌ Sem estoque disponível.", show_alert=True)
        return

    # Define estado FSM
    await state.update_data(product_id=product_id)
    await state.set_state(PurchaseStates.waiting_quantity)

    text = (
        f"Quantos logins deseja comprar?\n\n"
        f"📦 Estoque disponível: <b>{stock}</b>\n\n"
        f"💡 Digite /cancelar a qualquer momento para sair."
    )

    keyboard = build_quantity_keyboard(
        product_id=product_id,
        max_quantity=min(product.max_quantity, stock),
    )

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()

    user.last_menu = f"compra_quantity_{product_id}"
    session.add(user)


@router.message(PurchaseStates.waiting_quantity)
async def msg_quantity(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """Recebe a quantidade digitada."""
    text = (message.text or "").strip()

    # /cancelar
    if text.startswith("/cancelar"):
        await _cancel_purchase(message, state, user, session)
        return

    # Aceita "4", "quatro" etc — por simplicidade, só números
    try:
        quantity = int(text)
    except ValueError:
        await message.answer(
            "❌ <b>Quantidade inválida.</b>\n"
            "Envie apenas números (ex: <code>3</code>)."
        )
        return

    if quantity <= 0:
        await message.answer("❌ Quantidade deve ser maior que zero.")
        return

    data = await state.get_data()
    product_id = data.get("product_id")
    if not product_id:
        await message.answer("❌ Sessão expirada. Use /start.")
        await state.clear()
        return

    product = await session.get(Product, product_id)
    if product is None:
        await message.answer("❌ Produto não encontrado.")
        await state.clear()
        return

    stock = await _count_available_stock(session, product_id)

    if quantity > stock:
        await message.answer(
            f"❌ <b>Estoque insuficiente!</b>\n\n"
            f"📦 Disponível: <b>{stock}</b>\n"
            f"🔢 Você pediu: <b>{quantity}</b>"
        )
        return

    if quantity > product.max_quantity:
        await message.answer(
            f"❌ Máximo por compra: <b>{product.max_quantity}</b>"
        )
        return

    await state.clear()

    # Processa a compra
    await _process_purchase_message(
        message=message,
        user=user,
        session=session,
        product_id=product_id,
        quantity=quantity,
    )


# ============================================
# 🔢 QUANTIDADE RÁPIDA (botões 1/2/3/5)
# ============================================
@router.callback_query(F.data.startswith("buy:quantity_ok:"))
async def cb_quick_quantity(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """Quantidade escolhida pelos botões rápidos."""
    parts = callback.data.split(":")
    try:
        product_id = int(parts[2])
        quantity = int(parts[3])
    except (ValueError, IndexError):
        await callback.answer("❌ Valor inválido.", show_alert=True)
        return

    await state.clear()

    await _process_purchase(
        callback=callback,
        user=user,
        session=session,
        product_id=product_id,
        quantity=quantity,
    )


# ============================================
# ❌ CANCELAR
# ============================================
@router.callback_query(F.data.startswith("buy:cancel:"))
async def cb_cancel_purchase(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """Cancela a compra (libera reservas)."""
    parts = callback.data.split(":")
    try:
        product_id = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        product_id = 0

    # Libera reservas do usuário
    await stock_service.release_reservation(
        session, user.telegram_id, product_id or None
    )

    await state.clear()

    text = await render_message(
        session,
        key="compra_cancelada",
        variables={},
    )

    # Volta pro /start
    from bot.keyboards.main_menu import build_main_menu
    from core.config import settings

    keyboard = await build_main_menu(session, webapp_url=settings.webapp_url)

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()


@router.message(F.text.startswith("/cancelar"))
async def msg_cancel(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """Comando /cancelar em qualquer estado."""
    current_state = await state.get_state()

    if current_state is None:
        await message.answer("ℹ️ Nada para cancelar.")
        return

    await _cancel_purchase(message, state, user, session)


async def _cancel_purchase(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """Cancela e volta pro início."""
    data = await state.get_data()
    product_id = data.get("product_id")

    if product_id:
        await stock_service.release_reservation(
            session, user.telegram_id, product_id
        )

    await state.clear()

    text = await render_message(session, key="compra_cancelada", variables={})

    from bot.keyboards.main_menu import build_main_menu
    from core.config import settings

    keyboard = await build_main_menu(session, webapp_url=settings.webapp_url)

    await message.answer(text, reply_markup=keyboard)


# ============================================
# 💰 PROCESSAR COMPRA (via callback)
# ============================================
async def _process_purchase(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    product_id: int,
    quantity: int,
) -> None:
    """Lógica central da compra a partir de callback."""
    await callback.answer()

    product = await session.get(Product, product_id)
    if product is None or product.status != ProductStatus.ACTIVE:
        await callback.answer("❌ Produto indisponível.", show_alert=True)
        return

    stock = await _count_available_stock(session, product_id)
    if stock < quantity:
        await _edit_or_send(
            callback,
            f"❌ <b>Estoque insuficiente!</b>\n\n"
            f"📦 Disponível: <b>{stock}</b>\n"
            f"🔢 Você pediu: <b>{quantity}</b>",
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(
                        text="◀️ Voltar",
                        callback_data=f"prod:view:{product_id}:0",
                    )]
                ]
            ),
        )
        return

    total_price = (product.price * quantity).quantize(Decimal("0.01"))
    balance = user.balance or Decimal("0.00")

    # Verifica saldo
    if balance < total_price:
        await _show_insufficient_balance(
            callback=callback,
            user=user,
            session=session,
            product=product,
            quantity=quantity,
            total_price=total_price,
        )
        return

    # Tem saldo suficiente → executa compra
    await _execute_purchase(
        callback=callback,
        user=user,
        session=session,
        product=product,
        quantity=quantity,
        total_price=total_price,
    )


# ============================================
# 💰 PROCESSAR COMPRA (via mensagem FSM)
# ============================================
async def _process_purchase_message(
    message: Message,
    user: User,
    session: AsyncSession,
    product_id: int,
    quantity: int,
) -> None:
    """Lógica central da compra a partir de mensagem."""
    product = await session.get(Product, product_id)
    if product is None or product.status != ProductStatus.ACTIVE:
        await message.answer("❌ Produto indisponível.")
        return

    stock = await _count_available_stock(session, product_id)
    if stock < quantity:
        await message.answer(
            f"❌ <b>Estoque insuficiente!</b>\n\n"
            f"📦 Disponível: <b>{stock}</b>\n"
            f"🔢 Você pediu: <b>{quantity}</b>"
        )
        return

    total_price = (product.price * quantity).quantize(Decimal("0.01"))
    balance = user.balance or Decimal("0.00")

    if balance < total_price:
        await _show_insufficient_balance_message(
            message=message,
            user=user,
            session=session,
            product=product,
            quantity=quantity,
            total_price=total_price,
        )
        return

    await _execute_purchase_message(
        message=message,
        user=user,
        session=session,
        product=product,
        quantity=quantity,
        total_price=total_price,
    )


# ============================================
# ❌ SALDO INSUFICIENTE
# ============================================
async def _show_insufficient_balance(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    product: Product,
    quantity: int,
    total_price: Decimal,
) -> None:
    """Mostra tela de saldo insuficiente (via callback)."""
    balance = user.balance or Decimal("0.00")
    missing = (total_price - balance).quantize(Decimal("0.01"))

    if quantity == 1:
        key = "saldo_insuficiente"
        variables = {
            "BALANCE": _format_brl(balance),
            "PRODUCT_PRICE": _format_brl(total_price),
            "MISSING": _format_brl(missing),
        }
    else:
        key = "saldo_insuficiente_total"
        variables = {
            "BALANCE": _format_brl(balance),
            "TOTAL": _format_brl(total_price),
            "MISSING": _format_brl(missing),
        }

    text = await render_message(session, key=key, variables=variables)

    keyboard = build_insufficient_balance_keyboard(
        amount=_format_brl(missing),
        product_id=product.id,
        quantity=quantity,
    )

    await _edit_or_send(callback, text, keyboard)
    user.last_menu = f"saldo_insuf_{product.id}"
    session.add(user)


async def _show_insufficient_balance_message(
    message: Message,
    user: User,
    session: AsyncSession,
    product: Product,
    quantity: int,
    total_price: Decimal,
) -> None:
    """Mostra tela de saldo insuficiente (via mensagem)."""
    balance = user.balance or Decimal("0.00")
    missing = (total_price - balance).quantize(Decimal("0.01"))

    if quantity == 1:
        key = "saldo_insuficiente"
        variables = {
            "BALANCE": _format_brl(balance),
            "PRODUCT_PRICE": _format_brl(total_price),
            "MISSING": _format_brl(missing),
        }
    else:
        key = "saldo_insuficiente_total"
        variables = {
            "BALANCE": _format_brl(balance),
            "TOTAL": _format_brl(total_price),
            "MISSING": _format_brl(missing),
        }

    text = await render_message(session, key=key, variables=variables)

    keyboard = build_insufficient_balance_keyboard(
        amount=_format_brl(missing),
        product_id=product.id,
        quantity=quantity,
    )

    await message.answer(text, reply_markup=keyboard)


# ============================================
# ✅ EXECUTAR COMPRA (callback)
# ============================================
async def _execute_purchase(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    product: Product,
    quantity: int,
    total_price: Decimal,
) -> None:
    """Executa a compra: reserva → debita → cria pedido → entrega."""
    result = await _do_purchase(session, user, product, quantity, total_price)

    if not result.get("success"):
        await _edit_or_send(
            callback,
            f"❌ <b>Erro na compra</b>\n\n{result.get('error', 'Erro desconhecido.')}",
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(
                        text="◀️ Voltar",
                        callback_data=f"prod:view:{product.id}:0",
                    )]
                ]
            ),
        )
        return

    # Entrega no Telegram
    await _deliver(
        bot=callback.bot,
        session=session,
        user=user,
        order=result["order"],
        items=result["items"],
        product=product,
        callback=callback,
    )


async def _execute_purchase_message(
    message: Message,
    user: User,
    session: AsyncSession,
    product: Product,
    quantity: int,
    total_price: Decimal,
) -> None:
    """Executa compra via mensagem."""
    result = await _do_purchase(session, user, product, quantity, total_price)

    if not result.get("success"):
        await message.answer(
            f"❌ <b>Erro na compra</b>\n\n{result.get('error', 'Erro desconhecido.')}"
        )
        return

    await _deliver(
        bot=message.bot,
        session=session,
        user=user,
        order=result["order"],
        items=result["items"],
        product=product,
        message=message,
    )


# ============================================
# 🧠 LÓGICA CENTRAL DA COMPRA
# ============================================
async def _do_purchase(
    session: AsyncSession,
    user: User,
    product: Product,
    quantity: int,
    total_price: Decimal,
) -> dict:
    """Executa a transação de compra."""
    try:
        # 1. Reserva estoque
        items = await stock_service.reserve_items(
            session=session,
            product_id=product.id,
            quantity=quantity,
            user_telegram_id=user.telegram_id,
            reserve_minutes=15,
        )

        if len(items) < quantity:
            return {
                "success": False,
                "error": "Não foi possível reservar o estoque. Tente novamente.",
            }

        # 2. Cria pedido
        order_code = _generate_order_code()
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=product.duration_days)

        order = Order(
            order_code=order_code,
            user_id=user.id,
            user_telegram_id=user.telegram_id,
            product_id=product.id,
            product_name=product.name,
            quantity=quantity,
            unit_price=product.price,
            total_price=total_price,
            status=OrderStatus.PAID,
            delivery_method="telegram",
            delivery_target=str(user.telegram_id),
            expires_at=expires_at,
        )
        session.add(order)
        await session.flush()

        # 3. Marca itens como vendidos
        item_ids = [item.id for item in items]
        await stock_service.mark_as_sold(
            session=session,
            item_ids=item_ids,
            user_telegram_id=user.telegram_id,
            order_id=order.id,
            duration_days=product.duration_days,
        )

        # 4. Debita saldo
        user.balance = (user.balance or Decimal("0.00")) - total_price
        user.total_spent = (user.total_spent or Decimal("0.00")) + total_price
        user.purchases_count = (user.purchases_count or 0) + quantity
        session.add(user)

        # 5. Incrementa total_sold no produto
        product.total_sold = (product.total_sold or 0) + quantity
        session.add(product)

        await session.flush()

        logger.info(
            f"✅ Compra realizada: {order.order_code} | "
            f"user={user.telegram_id} | {quantity}x {product.name} | "
            f"R$ {total_price}"
        )

        return {
            "success": True,
            "order": order,
            "items": items,
        }

    except Exception as e:
        logger.exception(f"❌ Erro na compra: {e}")
        return {"success": False, "error": str(e)[:150]}


# ============================================
# 📤 ENTREGA
# ============================================
async def _deliver(
    bot,
    session: AsyncSession,
    user: User,
    order: Order,
    items: list,
    product: Product,
    callback: CallbackQuery | None = None,
    message: Message | None = None,
) -> None:
    """Entrega o produto no Telegram."""
    # Marca items como delivered
    item_ids = [item.id for item in items]
    await stock_service.mark_as_delivered(session, item_ids)

    # Monta texto de entrega
    date_str = order.created_at.strftime("%d/%m/%Y") if order.created_at else "N/A"
    exp_str = order.expires_at.strftime("%d/%m/%Y") if order.expires_at else "N/A"

    header = (
        f"🎉 <b>COMPRA REALIZADA</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⏰ Data da compra: {date_str}\n"
        f"📆 Vencimento: {exp_str}\n"
        f"💰 Valor: <b>R$ {_format_brl(order.total_price)}</b>\n"
        f"🎫 ID da compra: <code>{order.order_code}</code>\n"
        f"⚜️ Serviço: <b>{order.product_name}</b>\n"
        f"📦 Quantidade: <b>{order.quantity}</b>\n"
    )

    blocks = [header]

    for idx, item in enumerate(items, start=1):
        email = item.email or "N/A"
        password = item.password or "N/A"
        code = item.code or ""
        note = item.note or ""

        block = (
            f"\n🔐 <b>Login {idx}/{len(items)}</b>\n"
            f"📧 Email: <code>{email}</code>\n"
            f"🔑 Senha: <code>{password}</code>"
        )
        if code:
            block += f"\n🔗 Código: <code>{code}</code>"
        if note:
            block += f"\n📃 Nota: {note}"
        blocks.append(block)

    blocks.append(
        f"\n\n💡 Guarde esses dados. Em caso de dúvidas, use /atendimento."
    )

    full_text = "\n".join(blocks)

    if len(full_text) > 4000:
        full_text = full_text[:4000] + "\n\n<i>... (truncado)</i>"

    # Keyboard
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🛍 Comprar mais",
                callback_data="menu:comprar",
            )],
            [InlineKeyboardButton(
                text="👤 Meu Perfil",
                callback_data="menu:perfil",
            )],
            [InlineKeyboardButton(
                text="🏠 Início",
                callback_data="menu:voltar",
            )],
        ]
    )

    # Envia (sempre nova mensagem — compra concluída é evento)
    try:
        await bot.send_message(
            chat_id=user.telegram_id,
            text=full_text,
            reply_markup=keyboard,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.error(f"❌ Erro ao enviar entrega: {e}")

    # Notifica canal de logs
    try:
        from bot.handlers.admin.notifications import notify_purchase
        await notify_purchase(
            bot=bot,
            session=session,
            order_code=order.order_code,
            user_id=user.telegram_id,
            product_name=order.product_name,
            amount=float(order.total_price),
            quantity=order.quantity,
        )
    except Exception as e:
        logger.debug(f"⚠️ Falha ao notificar canal: {e}")

    # Verifica se estoque ficou baixo
    try:
        from bot.handlers.admin.alerts import notify_stock_low
        from core.services import config as config_service

        remaining = await _count_available_stock(session, product.id)
        threshold = await config_service.get_int(session, "stock_alert_threshold", 3)

        if 0 <= remaining <= threshold:
            await notify_stock_low(
                bot=bot,
                session=session,
                product_name=product.name,
                remaining=remaining,
                threshold=threshold,
            )
    except Exception as e:
        logger.debug(f"⚠️ Falha ao checar estoque baixo: {e}")


# ============================================
# 🔘 NOOP
# ============================================
@router.callback_query(F.data == "buy:noop")
async def cb_buy_noop(callback: CallbackQuery) -> None:
    await callback.answer()

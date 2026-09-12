# ============================================
# 🔔 ADMIN ALERTS — Larizinha Store
# ============================================
# Configuração REAL dos alertas de estoque.
# Todos os botões funcionam de verdade.
#
# Cobre:
#   - LIGAR/DESLIGAR alertas de estoque
#   - Limite mínimo para alerta
#   - Mensagem do alerta
#   - Lista de usuários com alertas ativos
#   - Disparar alerta manual para usuários
# ============================================

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

from bot.states.states import AdminStates
from core.models import (
    Admin,
    AuditLog,
    Product,
    ProductStatus,
    StockAlert,
    StockItem,
    StockStatus,
    User,
)
from core.services import config as config_service


router = Router(name="admin_alerts")


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


def _cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_alerts:menu")]
        ]
    )


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_alerts:menu")
async def cb_alerts_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    enabled = await config_service.get_bool(session, "stock_alerts_enabled", True)
    threshold = await config_service.get_str(session, "stock_alert_threshold", "3")

    # Conta alertas ativos
    total_alerts = await session.scalar(
        select(func.count(StockAlert.id)).where(StockAlert.is_active.is_(True))
    ) or 0

    # Conta produtos com estoque baixo
    low_stock = await session.scalar(
        select(func.count(Product.id)).where(
            Product.status == ProductStatus.ACTIVE,
            Product.stock_alert_enabled.is_(True),
        )
    ) or 0

    status = "🟢 LIGADO" if enabled else "🔴 DESLIGADO"

    text = (
        "🔔 <b>ALERTAS DE ESTOQUE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚙️ Sistema: <b>{status}</b>\n"
        f"📊 Limite de alerta: <b>{threshold}</b> unidades\n"
        f"👥 Assinaturas ativas: <b>{total_alerts}</b>\n"
        f"📦 Produtos monitorados: <b>{low_stock}</b>\n\n"
        "Escolha uma opção:"
    )

    toggle_text = "🔴 DESLIGAR" if enabled else "🟢 LIGAR"
    toggle_cb = "adm_alerts:off" if enabled else "adm_alerts:on"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle_text, callback_data=toggle_cb)],
            [InlineKeyboardButton(
                text=f"📊 Limite de Alerta ({threshold})",
                callback_data="adm_alerts:set_threshold",
            )],
            [InlineKeyboardButton(
                text="📝 Mensagem do Alerta",
                callback_data="adm_msg:view:stock_alert:0",
            )],
            [InlineKeyboardButton(
                text="👥 Ver Assinaturas",
                callback_data="adm_alerts:list",
            )],
            [InlineKeyboardButton(
                text="📢 Disparar Alerta Manual",
                callback_data="adm_alerts:fire_manual",
            )],
            [InlineKeyboardButton(
                text="🔔 Alertas por Produto",
                callback_data="adm_alerts:by_product",
            )],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:config")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 🟢 / 🔴 TOGGLE SISTEMA
# ============================================
@router.callback_query(F.data == "adm_alerts:on")
async def cb_alerts_on(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await config_service.set_config(session, "stock_alerts_enabled", "true")
    await _log_audit(session, callback.from_user.id, "alerts_on")
    await callback.answer("🟢 Alertas ativados", show_alert=True)
    await cb_alerts_menu(callback, session)


@router.callback_query(F.data == "adm_alerts:off")
async def cb_alerts_off(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await config_service.set_config(session, "stock_alerts_enabled", "false")
    await _log_audit(session, callback.from_user.id, "alerts_off")
    await callback.answer("🔴 Alertas desativados", show_alert=True)
    await cb_alerts_menu(callback, session)


# ============================================
# 📊 LIMITE DE ALERTA
# ============================================
@router.callback_query(F.data == "adm_alerts:set_threshold")
async def cb_alerts_set_threshold(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    current = await config_service.get_str(session, "stock_alert_threshold", "3")

    await callback.message.answer(
        "📊 <b>LIMITE DE ALERTA</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Atual:</b> {current} unidades\n\n"
        "Quando o estoque de um produto ficar abaixo deste número, "
        "o sistema envia uma notificação pro canal de logs.\n\n"
        "Envie o novo limite (1-100):",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(alerts_field="stock_alert_threshold")
    await callback.answer()


@router.message(AdminStates.editing_config_value)
async def msg_alerts_save(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    data = await state.get_data()
    field = data.get("alerts_field")

    if not field:
        await state.clear()
        return

    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("❌ Envie apenas números.")
        return

    val = int(raw)
    if not 1 <= val <= 100:
        await message.answer("❌ Valor deve ser entre 1 e 100.")
        return

    old = await config_service.get_str(session, field, "3")
    await config_service.set_config(session, field, str(val))

    await _log_audit(
        session,
        message.from_user.id,
        "edit_stock_alert_threshold",
        old_value={field: old},
        new_value={field: str(val)},
    )

    await message.answer(f"✅ Limite de alerta: <b>{val}</b> unidades")
    await state.clear()


# ============================================
# 👥 LISTA DE ASSINATURAS
# ============================================
@router.callback_query(F.data == "adm_alerts:list")
async def cb_alerts_list(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    # Agrupa assinaturas por produto
    stmt = (
        select(
            StockAlert.product_id,
            func.count(StockAlert.id).label("total"),
        )
        .where(StockAlert.is_active.is_(True))
        .group_by(StockAlert.product_id)
        .order_by(func.count(StockAlert.id).desc())
        .limit(30)
    )
    result = await session.execute(stmt)
    rows_data = list(result.all())

    if not rows_data:
        text = (
            "👥 <b>ASSINATURAS DE ALERTA</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Nenhum usuário assinou alertas ainda."
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_alerts:menu")]
            ]
        )
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except Exception:
            await callback.message.answer(text, reply_markup=keyboard)
        await callback.answer()
        return

    lines = [
        "👥 <b>ASSINATURAS DE ALERTA</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    total_users = 0

    for row in rows_data:
        product = await session.get(Product, row.product_id)
        if product is None:
            continue

        emoji = product.emoji or "🎬"
        lines.append(
            f"{emoji} <b>{product.name}</b> — "
            f"<b>{row.total}</b> usuário(s) assinando"
        )
        total_users += row.total

    lines.append("")
    lines.append(f"📊 Total geral: <b>{total_users}</b> assinaturas")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Atualizar", callback_data="adm_alerts:list")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_alerts:menu")],
        ]
    )

    try:
        await callback.message.edit_text("\n".join(lines), reply_markup=keyboard)
    except Exception:
        await callback.message.answer("\n".join(lines), reply_markup=keyboard)

    await callback.answer()


# ============================================
# 🔔 ALERTAS POR PRODUTO
# ============================================
@router.callback_query(F.data == "adm_alerts:by_product")
async def cb_alerts_by_product(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    stmt = (
        select(Product)
        .where(Product.status != ProductStatus.DELETED)
        .order_by(Product.name)
        .limit(30)
    )
    result = await session.execute(stmt)
    products = list(result.scalars().all())

    lines = [
        "🔔 <b>ALERTAS POR PRODUTO</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "Toque para ligar/desligar alerta de estoque baixo:",
        "",
    ]

    rows: list[list[InlineKeyboardButton]] = []

    for p in products:
        stock = await session.scalar(
            select(func.count(StockItem.id)).where(
                StockItem.product_id == p.id,
                StockItem.status == StockStatus.AVAILABLE,
            )
        ) or 0

        icon = "🔔" if p.stock_alert_enabled else "🔕"
        emoji = p.emoji or "🎬"
        status_icon = "🟢" if stock > 0 else "🔴"

        rows.append([
            InlineKeyboardButton(
                text=f"{icon} {emoji} {p.name} ({status_icon} {stock})",
                callback_data=f"adm_alerts:toggle_product:{p.id}",
            )
        ])

    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_alerts:menu")
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

    try:
        await callback.message.edit_text("\n".join(lines), reply_markup=keyboard)
    except Exception:
        await callback.message.answer("\n".join(lines), reply_markup=keyboard)

    await callback.answer()


@router.callback_query(F.data.startswith("adm_alerts:toggle_product:"))
async def cb_alerts_toggle_product(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    try:
        product_id = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Valor inválido.", show_alert=True)
        return

    product = await session.get(Product, product_id)
    if product is None:
        await callback.answer("❌ Produto não encontrado.", show_alert=True)
        return

    product.stock_alert_enabled = not product.stock_alert_enabled
    session.add(product)

    await _log_audit(
        session,
        callback.from_user.id,
        "toggle_stock_alert_product",
        new_value={
            "product_id": product_id,
            "enabled": product.stock_alert_enabled,
        },
    )

    status = "🔔 Ligado" if product.stock_alert_enabled else "🔕 Desligado"
    await callback.answer(f"{status} para {product.name}", show_alert=True)

    callback.data = "adm_alerts:by_product"
    await cb_alerts_by_product(callback, session)


# ============================================
# 📢 DISPARAR ALERTA MANUAL
# ============================================
@router.callback_query(F.data == "adm_alerts:fire_manual")
async def cb_alerts_fire_manual(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    # Lista produtos com assinaturas ativas
    stmt = (
        select(
            StockAlert.product_id,
            func.count(StockAlert.id).label("total"),
        )
        .where(StockAlert.is_active.is_(True))
        .group_by(StockAlert.product_id)
    )
    result = await session.execute(stmt)
    rows_data = list(result.all())

    if not rows_data:
        await callback.answer("❌ Nenhum produto com assinaturas.", show_alert=True)
        return

    lines = [
        "📢 <b>DISPARAR ALERTA MANUAL</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "Escolha qual produto vai ser notificado:",
        "",
    ]

    rows: list[list[InlineKeyboardButton]] = []

    for row in rows_data:
        product = await session.get(Product, row.product_id)
        if product is None:
            continue
        stock = await session.scalar(
            select(func.count(StockItem.id)).where(
                StockItem.product_id == product.id,
                StockItem.status == StockStatus.AVAILABLE,
            )
        ) or 0
        rows.append([
            InlineKeyboardButton(
                text=f"{product.emoji or '🎬'} {product.name} ({row.total} subs, estoque: {stock})",
                callback_data=f"adm_alerts:confirm_fire:{product.id}",
            )
        ])

    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_alerts:menu")
    ])

    try:
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
    except Exception:
        await callback.message.answer(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )

    await callback.answer()


@router.callback_query(F.data.startswith("adm_alerts:confirm_fire:"))
async def cb_alerts_confirm_fire(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    try:
        product_id = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Valor inválido.", show_alert=True)
        return

    product = await session.get(Product, product_id)
    if product is None:
        await callback.answer("❌ Produto não encontrado.", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="✅ Sim, disparar",
                callback_data=f"adm_alerts:do_fire:{product_id}",
            )],
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_alerts:fire_manual")],
        ]
    )

    await callback.message.edit_text(
        f"📢 <b>DISPARAR ALERTA</b>\n\n"
        f"Produto: <b>{product.name}</b>\n\n"
        f"Todos os usuários que assinaram esse produto vão receber "
        f"uma notificação.\n\n"
        f"Confirma?",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_alerts:do_fire:"))
async def cb_alerts_do_fire(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    try:
        product_id = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Valor inválido.", show_alert=True)
        return

    product = await session.get(Product, product_id)
    if product is None:
        await callback.answer("❌ Produto não encontrado.", show_alert=True)
        return

    # Busca assinantes
    stmt = select(StockAlert).where(
        StockAlert.product_id == product_id,
        StockAlert.is_active.is_(True),
    )
    result = await session.execute(stmt)
    alerts = list(result.scalars().all())

    if not alerts:
        await callback.answer("❌ Nenhum assinante.", show_alert=True)
        return

    # Conta estoque
    stock = await session.scalar(
        select(func.count(StockItem.id)).where(
            StockItem.product_id == product_id,
            StockItem.status == StockStatus.AVAILABLE,
        )
    ) or 0

    price = f"{product.price:.2f}".replace(".", ",")

    # Notifica todos
    import asyncio

    sent = 0
    failed = 0

    await callback.answer("📢 Disparando alertas...", show_alert=False)

    message_text = (
        f"🔔 <b>PRODUTO DISPONÍVEL!</b>\n\n"
        f"{product.emoji or '🎬'} <b>{product.name}</b>\n"
        f"💵 Preço: <b>R$ {price}</b>\n"
        f"📦 Estoque: <b>{stock}</b> unidade(s)\n\n"
        f"⚡ Corre que é por tempo limitado!"
    )

    keyboard_notif = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🛍 Comprar Agora",
                callback_data=f"prod:view:{product_id}:0",
            )],
        ]
    )

    for alert in alerts:
        try:
            await callback.bot.send_message(
                chat_id=alert.user_telegram_id,
                text=message_text,
                reply_markup=keyboard_notif,
                parse_mode="HTML",
            )
            sent += 1
        except Exception as e:
            failed += 1
            logger.debug(f"Falha ao notificar {alert.user_telegram_id}: {e}")

        await asyncio.sleep(0.05)

    await _log_audit(
        session,
        callback.from_user.id,
        "fire_stock_alert",
        new_value={
            "product_id": product_id,
            "sent": sent,
            "failed": failed,
        },
    )

    text = (
        f"📢 <b>ALERTA DISPARADO</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 Produto: <b>{product.name}</b>\n"
        f"👥 Assinantes: <b>{len(alerts)}</b>\n\n"
        f"✅ Enviados: <b>{sent}</b>\n"
        f"❌ Falhas: <b>{failed}</b>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_alerts:menu")]
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)


# ============================================
# 🔔 ENVIO AUTOMÁTICO DE ALERTA
# ============================================
async def fire_stock_alert_to_users(
    bot,
    product_id: int,
    session: AsyncSession,
) -> dict:
    """
    Função utilitária que envia alertas de estoque
    para os usuários assinantes. Chamada pelo serviço
    de estoque quando adiciona novas unidades.
    """
    enabled = await config_service.get_bool(session, "stock_alerts_enabled", True)
    if not enabled:
        return {"sent": 0, "failed": 0, "skipped": True}

    product = await session.get(Product, product_id)
    if product is None:
        return {"sent": 0, "failed": 0, "error": "produto não encontrado"}

    stock = await session.scalar(
        select(func.count(StockItem.id)).where(
            StockItem.product_id == product_id,
            StockItem.status == StockStatus.AVAILABLE,
        )
    ) or 0

    if stock <= 0:
        return {"sent": 0, "failed": 0, "skipped": True}

    stmt = select(StockAlert).where(
        StockAlert.product_id == product_id,
        StockAlert.is_active.is_(True),
    )
    result = await session.execute(stmt)
    alerts = list(result.scalars().all())

    if not alerts:
        return {"sent": 0, "failed": 0, "skipped": True}

    price = f"{product.price:.2f}".replace(".", ",")

    message_text = (
        f"🔔 <b>PRODUTO DISPONÍVEL!</b>\n\n"
        f"{product.emoji or '🎬'} <b>{product.name}</b>\n"
        f"💵 Preço: <b>R$ {price}</b>\n"
        f"📦 Estoque: <b>{stock}</b> unidade(s)\n\n"
        f"⚡ Corre que é por tempo limitado!"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🛍 Comprar Agora",
                callback_data=f"prod:view:{product_id}:0",
            )],
        ]
    )

    import asyncio

    sent = 0
    failed = 0
    for alert in alerts:
        try:
            await bot.send_message(
                chat_id=alert.user_telegram_id,
                text=message_text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            sent += 1
            # Marca como processado (opcional — evita reenvio)
            alert.is_active = False
            session.add(alert)
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    return {"sent": sent, "failed": failed}

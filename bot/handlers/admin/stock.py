# ============================================
# 🔐 ADMIN STOCK — Larizinha Store
# ============================================
# Gerenciamento REAL de estoque/logins pelo painel.
# Todos os botões funcionam de verdade.
#
# Comandos suportados:
#   - ADICIONAR LOGIN (em massa com separador)
#   - REMOVER LOGIN (por produto + email)
#   - REMOVER POR PLATAFORMA
#   - ESTOQUE DETALHADO
#   - ZERAR ESTOQUE
#   - MUDAR VALOR DO SERVIÇO
#   - MUDAR VALOR DE TODOS
# ============================================

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
    Product,
    ProductStatus,
    StockItem,
    StockStatus,
)
from core.services import config as config_service
from core.services import stock as stock_service


router = Router(name="admin_stock")


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


def _cancel_keyboard(back_data: str = "adm_stock:menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancelar", callback_data=back_data)]
        ]
    )


# ============================================
# 📦 MENU PRINCIPAL DO ESTOQUE
# ============================================
@router.callback_query(F.data == "adm_stock:menu")
async def cb_stock_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    total = await stock_service.count_total_stock(session)

    text = (
        "🔐 <b>CONFIGURAR LOGINS / ESTOQUE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 LOGINS NO ESTOQUE: <b>{total}</b>\n\n"
        "Use os botões abaixo para gerenciar o estoque:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Adicionar Login", callback_data="adm_stock:add")],
            [InlineKeyboardButton(text="➖ Remover Login", callback_data="adm_stock:remove")],
            [InlineKeyboardButton(text="🗑 Remover por Plataforma", callback_data="adm_stock:remove_platform")],
            [InlineKeyboardButton(text="📋 Estoque Detalhado", callback_data="adm_stock:details")],
            [InlineKeyboardButton(text="💥 Zerar Estoque", callback_data="adm_stock:clear")],
            [InlineKeyboardButton(text="💵 Mudar Valor do Serviço", callback_data="adm_stock:change_price")],
            [InlineKeyboardButton(text="💵 Mudar Valor de Todos", callback_data="adm_stock:change_all")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:config")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# ➕ ADICIONAR LOGIN
# ============================================
@router.callback_query(F.data == "adm_stock:add")
async def cb_stock_add(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    separator = await config_service.get_str(session, "separator", "===")

    text = (
        "➕ <b>ADICIONAR LOGIN</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Primeiro, envie o <b>nome do produto/serviço</b>\n"
        "que deseja abastecer.\n\n"
        "Exemplo: <code>HBO MAX</code>\n\n"
        f"💡 O separador atual é: <code>{separator}</code>"
    )

    await callback.message.answer(text, reply_markup=_cancel_keyboard("adm_stock:menu"))
    await state.set_state(AdminStates.adding_stock)
    await callback.answer()


@router.message(AdminStates.adding_stock)
async def msg_stock_product_name(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    product_name = (message.text or "").strip()
    if not product_name:
        await message.answer("❌ Nome vazio. Envie novamente.")
        return

    # Busca produto
    stmt = select(Product).where(Product.name == product_name)
    result = await session.execute(stmt)
    product = result.scalar_one_or_none()

    if product is None:
        await message.answer(
            f"❌ Produto <b>{product_name}</b> não encontrado.\n\n"
            f"Use o botão abaixo para ver os produtos disponíveis.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📋 Ver produtos", callback_data="adm_prod:list:0")],
                    [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_stock:menu")],
                ]
            ),
        )
        return

    separator = await config_service.get_str(session, "separator", "===")

    await state.update_data(product_id=product.id, product_name=product.name)

    text = (
        f"📦 Produto: <b>{product.name}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Agora envie os logins no formato:\n\n"
        f"<code>EMAIL{separator}SENHA{separator}CODIGO{separator}NOTA</code>\n\n"
        "• Campos vazios podem ficar em branco\n"
        f"• Envie <b>vários logins</b> um por linha (pulando linha entre eles)\n"
        f"• Separador: <code>{separator}</code>\n\n"
        "Exemplo:\n"
        f"<code>email1@x.com{separator}senha123{separator}{separator}Use o link</code>\n"
        f"<code>email2@x.com{separator}senha456{separator}{separator}</code>"
    )

    await message.answer(text)
    await state.set_state(AdminStates.adding_stock)


@router.message(AdminStates.adding_stock)
async def msg_stock_add_lines(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    data = await state.get_data()
    product_id = data.get("product_id")
    product_name = data.get("product_name", "")

    if not product_id:
        # Ainda não escolheu produto — reenvia
        await msg_stock_product_name(message, state, session)
        return

    raw = message.text or message.caption or ""
    if not raw.strip():
        await message.answer("❌ Texto vazio. Envie os logins.")
        return

    separator = await config_service.get_str(session, "separator", "===")
    lines = [line.strip() for line in raw.split("\n") if line.strip()]

    added = await stock_service.add_stock_bulk(
        session=session,
        product_id=product_id,
        lines=lines,
        separator=separator,
    )

    if added == 0:
        await message.answer(
            "⚠️ Nenhum login foi adicionado. Verifique o formato e tente novamente."
        )
        return

    # Estoque atual
    total = await stock_service.count_available(session, product_id)

    await _log_audit(
        session, message.from_user.id, "add_stock",
        new_value={"product_id": product_id, "quantity": added},
    )

    await message.answer(
        f"✅ <b>{added}</b> login(s) adicionado(s) em <b>{product_name}</b>!\n\n"
        f"📦 Estoque disponível agora: <b>{total}</b>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="➕ Adicionar mais", callback_data="adm_stock:add")],
                [InlineKeyboardButton(text="📋 Detalhes", callback_data=f"adm_stock:view:{product_id}")],
                [InlineKeyboardButton(text="🔙 Menu Estoque", callback_data="adm_stock:menu")],
            ]
        ),
    )
    await state.clear()


# ============================================
# 👁️ VER ESTOQUE DE UM PRODUTO
# ============================================
@router.callback_query(F.data.startswith("adm_stock:view:"))
async def cb_stock_view(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    product_id = int(callback.data.split(":")[2])
    product = await session.get(Product, product_id)
    if product is None:
        await callback.answer("❌ Produto não encontrado.", show_alert=True)
        return

    counts = await stock_service.count_all_by_status(session, product_id)
    total = sum(counts.values())
    available = counts.get("available", 0)

    text = (
        f"📦 <b>Estoque: {product.name}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 Total: <b>{total}</b>\n"
        f"🟢 Disponível: <b>{available}</b>\n"
        f"🔒 Reservado: <b>{counts.get('reserved', 0)}</b>\n"
        f"✅ Vendido: <b>{counts.get('sold', 0)}</b>\n"
        f"📤 Entregue: <b>{counts.get('delivered', 0)}</b>\n"
        f"⏰ Expirado: <b>{counts.get('expired', 0)}</b>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Adicionar mais logins", callback_data="adm_stock:add")],
            [InlineKeyboardButton(text="📋 Listar disponíveis", callback_data=f"adm_stock:list:{product_id}")],
            [InlineKeyboardButton(text="🗑 Remover todos disponíveis", callback_data=f"adm_stock:clear_one:{product_id}")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_stock:menu")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


@router.callback_query(F.data.startswith("adm_stock:list:"))
async def cb_stock_list(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    product_id = int(callback.data.split(":")[2])
    items = await stock_service.list_stock_by_product(
        session, product_id, status=StockStatus.AVAILABLE, limit=30
    )

    if not items:
        await callback.answer("📦 Nenhum login disponível.", show_alert=True)
        return

    product = await session.get(Product, product_id)

    lines = [
        f"📋 <b>Logins disponíveis: {product.name}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    for i, item in enumerate(items, start=1):
        email = item.email or "—"
        password = item.password or "—"
        lines.append(f"{i}. <code>{email}</code> | <code>{password}</code>")

    text = "\n".join(lines)

    # Telegram tem limite de 4096 caracteres
    if len(text) > 3800:
        text = text[:3800] + "\n\n<i>... (truncado)</i>"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Voltar", callback_data=f"adm_stock:view:{product_id}")]
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# ➖ REMOVER LOGIN
# ============================================
@router.callback_query(F.data == "adm_stock:remove")
async def cb_stock_remove(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    separator = await config_service.get_str(session, "separator", "===")

    text = (
        "➖ <b>REMOVER LOGIN</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Envie o <b>produto e o email</b> separados pelo separador.\n\n"
        f"Formato: <code>PRODUTO{separator}EMAIL</code>\n\n"
        f"Exemplo: <code>NETFLIX{separator}teste@email.com</code>"
    )

    await callback.message.answer(text, reply_markup=_cancel_keyboard("adm_stock:menu"))
    await state.set_state(AdminStates.removing_stock)
    await callback.answer()


@router.message(AdminStates.removing_stock)
async def msg_stock_remove(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    separator = await config_service.get_str(session, "separator", "===")
    raw = (message.text or "").strip()

    if separator not in raw:
        await message.answer(
            f"❌ Formato inválido. Use: <code>PRODUTO{separator}EMAIL</code>"
        )
        return

    parts = raw.split(separator)
    if len(parts) < 2:
        await message.answer("❌ Faltam dados. Use: <code>PRODUTO{separator}EMAIL</code>")
        return

    product_name = parts[0].strip()
    email = parts[1].strip()

    stmt = select(Product).where(Product.name == product_name)
    result = await session.execute(stmt)
    product = result.scalar_one_or_none()

    if product is None:
        await message.answer(f"❌ Produto <b>{product_name}</b> não encontrado.")
        return

    removed = await stock_service.remove_by_email(session, product.id, email)

    if removed == 0:
        await message.answer(
            f"⚠️ Nenhum login disponível com email <code>{email}</code> "
            f"no produto <b>{product_name}</b>."
        )
        return

    await _log_audit(
        session, message.from_user.id, "remove_stock_by_email",
        old_value={"product": product_name, "email": email, "removed": removed},
    )

    await message.answer(
        f"✅ <b>{removed}</b> login(s) removido(s) de <b>{product_name}</b>."
    )
    await state.clear()


# ============================================
# 🗑 REMOVER POR PLATAFORMA
# ============================================
@router.callback_query(F.data == "adm_stock:remove_platform")
async def cb_stock_remove_platform(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text = (
        "🗑 <b>REMOVER POR PLATAFORMA</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Envie o <b>nome exato do produto</b> e TODOS os\n"
        "logins disponíveis dele serão removidos.\n\n"
        "⚠️ <b>Esta ação não pode ser desfeita.</b>"
    )
    await callback.message.answer(text, reply_markup=_cancel_keyboard("adm_stock:menu"))
    await state.set_state(AdminStates.removing_stock_by_platform)
    await callback.answer()


@router.message(AdminStates.removing_stock_by_platform)
async def msg_stock_remove_platform(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    name = (message.text or "").strip()
    if not name:
        await message.answer("❌ Nome vazio.")
        return

    stmt = select(Product).where(Product.name == name)
    result = await session.execute(stmt)
    product = result.scalar_one_or_none()

    if product is None:
        await message.answer(f"❌ Produto <b>{name}</b> não encontrado.")
        return

    removed = await stock_service.remove_all_by_product(
        session, product.id, only_available=True
    )

    await _log_audit(
        session, message.from_user.id, "remove_stock_by_platform",
        old_value={"product": name, "removed": removed},
    )

    await message.answer(
        f"✅ <b>{removed}</b> login(s) removido(s) de <b>{name}</b>."
    )
    await state.clear()


# ============================================
# 📋 ESTOQUE DETALHADO
# ============================================
@router.callback_query(F.data == "adm_stock:details")
async def cb_stock_details(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    summary = await stock_service.count_by_product_summary(session)

    if not summary:
        text = (
            "📋 <b>ESTOQUE DETALHADO</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📦 Nenhum logins em estoque."
        )
    else:
        lines = [
            "📋 <b>ESTOQUE DETALHADO</b>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "",
        ]
        total_geral = 0
        for row in summary:
            lines.append(
                f"• <b>{row['product_name']}</b>: {row['available']} login(s)"
            )
            total_geral += row["available"]

        lines.append("")
        lines.append(f"📊 <b>Total geral: {total_geral}</b>")
        text = "\n".join(lines)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_stock:menu")]
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 💥 ZERAR ESTOQUE
# ============================================
@router.callback_query(F.data == "adm_stock:clear")
async def cb_stock_clear(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    total = await stock_service.count_total_stock(session)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ SIM, ZERAR TUDO", callback_data="adm_stock:clear_confirm")],
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_stock:menu")],
        ]
    )

    await callback.message.edit_text(
        "⚠️ <b>ZERAR ESTOQUE</b>\n\n"
        f"Você vai remover <b>{total}</b> login(s) disponíveis.\n\n"
        "⚠️ <b>Esta ação não pode ser desfeita.</b>\n\n"
        "Tem certeza?",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data == "adm_stock:clear_confirm")
async def cb_stock_clear_confirm(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    removed = await stock_service.clear_all_stock(session)

    await _log_audit(
        session, callback.from_user.id, "clear_all_stock",
        old_value={"removed": removed},
    )

    await callback.answer(f"💥 {removed} logins removidos!", show_alert=True)

    callback.data = "adm_stock:menu"
    await cb_stock_menu(callback, session)


# ============================================
# 💵 MUDAR VALOR DO SERVIÇO
# ============================================
@router.callback_query(F.data == "adm_stock:change_price")
async def cb_stock_change_price(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    separator = await config_service.get_str(session, "separator", "===")

    text = (
        "💵 <b>MUDAR VALOR DO SERVIÇO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Envie o <b>nome do serviço e o novo valor</b>\n"
        "separados pelo separador.\n\n"
        f"Formato: <code>SERVICO{separator}VALOR</code>\n\n"
        f"Exemplo: <code>HBO MAX{separator}8.00</code>"
    )
    await callback.message.answer(text, reply_markup=_cancel_keyboard("adm_stock:menu"))
    await state.set_state(AdminStates.changing_service_price)
    await callback.answer()


@router.message(AdminStates.changing_service_price)
async def msg_stock_change_price(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    separator = await config_service.get_str(session, "separator", "===")
    raw = (message.text or "").strip()

    if separator not in raw:
        await message.answer(
            f"❌ Formato inválido. Use: <code>SERVICO{separator}VALOR</code>"
        )
        return

    parts = raw.split(separator, 1)
    if len(parts) < 2:
        await message.answer("❌ Faltam dados.")
        return

    product_name = parts[0].strip()
    value_raw = parts[1].strip().replace(",", ".")

    try:
        new_price = Decimal(value_raw)
        if new_price < 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer("❌ Valor inválido. Ex: <code>8.00</code>")
        return

    ok = await stock_service.change_product_price(
        session, product_name, new_price.quantize(Decimal("0.01"))
    )

    if not ok:
        await message.answer(f"❌ Produto <b>{product_name}</b> não encontrado.")
        return

    await _log_audit(
        session, message.from_user.id, "change_product_price",
        new_value={"product": product_name, "new_price": str(new_price)},
    )

    await message.answer(
        f"✅ Preço de <b>{product_name}</b> alterado para "
        f"<b>R$ {new_price:.2f}</b>."
    )
    await state.clear()


# ============================================
# 💵 MUDAR VALOR DE TODOS
# ============================================
@router.callback_query(F.data == "adm_stock:change_all")
async def cb_stock_change_all(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text = (
        "💵 <b>MUDAR VALOR DE TODOS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Envie o <b>novo valor</b> e TODOS os produtos ativos\n"
        "terão seus preços alterados.\n\n"
        "⚠️ Útil para queima de estoque.\n\n"
        "Exemplo: <code>5.00</code>"
    )
    await callback.message.answer(text, reply_markup=_cancel_keyboard("adm_stock:menu"))
    await state.set_state(AdminStates.changing_all_prices)
    await callback.answer()


@router.message(AdminStates.changing_all_prices)
async def msg_stock_change_all(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    raw = (message.text or "").strip().replace(",", ".")
    try:
        new_price = Decimal(raw)
        if new_price < 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer("❌ Valor inválido. Ex: <code>5.00</code>")
        return

    count = await stock_service.change_all_prices(
        session, new_price.quantize(Decimal("0.01"))
    )

    await _log_audit(
        session, message.from_user.id, "change_all_prices",
        new_value={"new_price": str(new_price), "affected": count},
    )

    await message.answer(
        f"✅ Preço de <b>{count}</b> produto(s) alterado para "
        f"<b>R$ {new_price:.2f}</b>."
    )
    await state.clear()


# ============================================
# 🗑 ZERAR ESTOQUE DE UM PRODUTO
# ============================================
@router.callback_query(F.data.startswith("adm_stock:clear_one:"))
async def cb_stock_clear_one(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    product_id = int(callback.data.split(":")[2])
    product = await session.get(Product, product_id)
    if product is None:
        await callback.answer("❌ Produto não encontrado.", show_alert=True)
        return

    removed = await stock_service.remove_all_by_product(
        session, product_id, only_available=True
    )

    await _log_audit(
        session, callback.from_user.id, "clear_stock_one",
        old_value={"product_id": product_id, "removed": removed},
    )

    await callback.answer(f"💥 {removed} login(s) removido(s)!", show_alert=True)

    callback.data = f"adm_stock:view:{product_id}"
    await cb_stock_view(callback, session)

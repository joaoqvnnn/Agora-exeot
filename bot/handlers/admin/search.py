# ============================================
# 🔎 ADMIN SEARCH — Larizinha Store
# ============================================
# Configuração REAL da pesquisa de serviços.
# Todos os botões funcionam de verdade.
#
# Cobre:
#   - LIGAR/DESLIGAR sistema de pesquisa
#   - MÁXIMO de resultados
#   - MENSAGEM de "nenhum resultado"
#   - IMAGEM da pesquisa
#   - PREVIEW de como a pesquisa aparece
# ============================================

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.states import AdminStates
from core.models import Admin, AuditLog, ImageTemplate, Product, ProductStatus
from core.services import config as config_service


router = Router(name="admin_search")


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
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_search:menu")]
        ]
    )


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_cfg:pesquisa")
async def cb_search_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    enabled = await config_service.get_bool(session, "search_enabled", True)
    max_results = await config_service.get_int(session, "search_max_results", 10)

    # Conta produtos pesquisáveis
    searchable = await session.scalar(
        select(func.count(Product.id)).where(
            Product.status == ProductStatus.ACTIVE,
            Product.allow_search.is_(True),
        )
    ) or 0

    total_products = await session.scalar(
        select(func.count(Product.id)).where(
            Product.status == ProductStatus.ACTIVE,
        )
    ) or 0

    # Imagem configurada
    img_stmt = select(ImageTemplate).where(
        ImageTemplate.key == "pesquisa_image",
        ImageTemplate.is_active.is_(True),
    )
    img = (await session.execute(img_stmt)).scalar_one_or_none()
    img_status = "🟢 Configurada" if img else "⚪ Não configurada"

    status = "🟢 ATIVO" if enabled else "🔴 DESATIVADO"

    text = (
        "🔎 <b>CONFIGURAÇÃO DA PESQUISA</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚙️ Sistema: <b>{status}</b>\n"
        f"📊 Máx. resultados: <b>{max_results}</b>\n"
        f"📦 Produtos pesquisáveis: <b>{searchable}/{total_products}</b>\n"
        f"🖼️ Imagem: <b>{img_status}</b>\n\n"
        "Escolha uma opção:"
    )

    toggle_text = "🔴 DESATIVAR" if enabled else "🟢 ATIVAR"
    toggle_cb = "adm_search:off" if enabled else "adm_search:on"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle_text, callback_data=toggle_cb)],
            [InlineKeyboardButton(
                text=f"📊 Máximo de Resultados ({max_results})",
                callback_data="adm_search:max_results",
            )],
            [InlineKeyboardButton(
                text="🖼️ Imagem da Pesquisa",
                callback_data="adm_img:view:pesquisa_image",
            )],
            [InlineKeyboardButton(
                text="📝 Mensagem 'Nenhum Resultado'",
                callback_data="adm_msg:view:search_empty",
            )],
            [InlineKeyboardButton(
                text="👁 Preview da Pesquisa",
                callback_data="adm_search:preview",
            )],
            [InlineKeyboardButton(
                text="📦 Gerenciar Produtos Pesquisáveis",
                callback_data="adm_search:manage_searchable",
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
# 🟢 / 🔴 TOGGLE
# ============================================
@router.callback_query(F.data == "adm_search:on")
async def cb_search_on(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await config_service.set_config(session, "search_enabled", "true")
    await _log_audit(session, callback.from_user.id, "search_on")
    await callback.answer("🟢 Pesquisa ativada", show_alert=True)
    await cb_search_menu(callback, session)


@router.callback_query(F.data == "adm_search:off")
async def cb_search_off(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await config_service.set_config(session, "search_enabled", "false")
    await _log_audit(session, callback.from_user.id, "search_off")
    await callback.answer("🔴 Pesquisa desativada", show_alert=True)
    await cb_search_menu(callback, session)


# ============================================
# 📊 MÁXIMO DE RESULTADOS
# ============================================
@router.callback_query(F.data == "adm_search:max_results")
async def cb_search_max_results(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    current = await config_service.get_int(session, "search_max_results", 10)

    text = (
        "📊 <b>MÁXIMO DE RESULTADOS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Atual: <b>{current}</b>\n\n"
        "Escolha ou envie um valor personalizado (1-50):"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="5", callback_data="adm_search:max:5"),
                InlineKeyboardButton(text="10", callback_data="adm_search:max:10"),
                InlineKeyboardButton(text="15", callback_data="adm_search:max:15"),
            ],
            [
                InlineKeyboardButton(text="20", callback_data="adm_search:max:20"),
                InlineKeyboardButton(text="30", callback_data="adm_search:max:30"),
                InlineKeyboardButton(text="50", callback_data="adm_search:max:50"),
            ],
            [InlineKeyboardButton(text="✏️ Personalizado", callback_data="adm_search:max_custom")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_cfg:pesquisa")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


@router.callback_query(F.data.startswith("adm_search:max:"))
async def cb_search_max_set(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    try:
        val = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Valor inválido.", show_alert=True)
        return

    old = await config_service.get_str(session, "search_max_results", "10")
    await config_service.set_config(session, "search_max_results", str(val))

    await _log_audit(
        session,
        callback.from_user.id,
        "edit_search_max",
        old_value={"max": old},
        new_value={"max": str(val)},
    )

    await callback.answer(f"✅ Máx.: {val}", show_alert=True)

    callback.data = "adm_cfg:pesquisa"
    await cb_search_menu(callback, session)


@router.callback_query(F.data == "adm_search:max_custom")
async def cb_search_max_custom(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "📊 Envie o número de resultados (1 a 50):",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_search_message)
    await callback.answer()


# ============================================
# 👁 PREVIEW
# ============================================
@router.callback_query(F.data == "adm_search:preview")
async def cb_search_preview(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    # Pega 3 produtos aleatórios ativos
    stmt = (
        select(Product)
        .where(Product.status == ProductStatus.ACTIVE)
        .limit(3)
    )
    result = await session.execute(stmt)
    products = list(result.scalars().all())

    lines = [
        "👁 <b>PREVIEW DA PESQUISA</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "É assim que aparece quando o usuário pesquisa:",
        "",
        "🔎 <b>Resultados:</b>",
        "",
    ]

    if not products:
        lines.append("📭 Nenhum produto cadastrado para mostrar preview.")
    else:
        for p in products:
            emoji = p.emoji or "🎬"
            price = f"{p.price:.2f}".replace(".", ",")
            lines.append(f"{emoji} <b>{p.name}</b>")
            lines.append(f"💲 Valor: <b>R$ {price}</b>")
            desc = (p.description or "Sem descrição.")[:80]
            lines.append(f"📝 {desc}...")
            lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("<i>Este é apenas um preview. O bot mostra no chat.</i>")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="✏️ Editar Mensagem",
                callback_data="adm_msg:view:search_empty",
            )],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_cfg:pesquisa")],
        ]
    )

    try:
        await callback.message.edit_text("\n".join(lines), reply_markup=keyboard)
    except Exception:
        await callback.message.answer("\n".join(lines), reply_markup=keyboard)

    await callback.answer()


# ============================================
# 📦 GERENCIAR PRODUTOS PESQUISÁVEIS
# ============================================
@router.callback_query(F.data == "adm_search:manage_searchable")
async def cb_search_manage(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    stmt = (
        select(Product)
        .where(Product.status == ProductStatus.ACTIVE)
        .order_by(Product.position, Product.name)
        .limit(30)
    )
    result = await session.execute(stmt)
    products = list(result.scalars().all())

    if not products:
        text = "📦 Nenhum produto ativo."
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_cfg:pesquisa")]
            ]
        )
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except Exception:
            await callback.message.answer(text, reply_markup=keyboard)
        await callback.answer()
        return

    lines = [
        "📦 <b>PRODUTOS PESQUISÁVEIS</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "Toque para LIGAR/DESLIGAR na pesquisa:",
        "",
    ]

    rows: list[list[InlineKeyboardButton]] = []

    for p in products:
        icon = "✅" if p.allow_search else "❌"
        emoji = p.emoji or "🎬"
        rows.append([
            InlineKeyboardButton(
                text=f"{icon} {emoji} {p.name[:30]}",
                callback_data=f"adm_search:toggle_product:{p.id}",
            )
        ])

    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_cfg:pesquisa")
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

    try:
        await callback.message.edit_text("\n".join(lines), reply_markup=keyboard)
    except Exception:
        await callback.message.answer("\n".join(lines), reply_markup=keyboard)

    await callback.answer()


@router.callback_query(F.data.startswith("adm_search:toggle_product:"))
async def cb_search_toggle_product(
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

    product.allow_search = not product.allow_search
    session.add(product)

    await _log_audit(
        session,
        callback.from_user.id,
        "toggle_search_product",
        new_value={"product_id": product_id, "allow_search": product.allow_search},
    )

    status = "ativado" if product.allow_search else "desativado"
    await callback.answer(f"✅ {product.name} {status} na pesquisa", show_alert=True)

    callback.data = "adm_search:manage_searchable"
    await cb_search_manage(callback, session)


# ============================================
# 💾 SALVAR MÁXIMO CUSTOM
# ============================================
@router.message(AdminStates.editing_search_message)
async def msg_search_max_save(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    try:
        val = int((message.text or "").strip())
        if not 1 <= val <= 50:
            raise ValueError
    except ValueError:
        await message.answer("❌ Valor inválido. Use 1 a 50.")
        return

    old = await config_service.get_str(session, "search_max_results", "10")
    await config_service.set_config(session, "search_max_results", str(val))

    await _log_audit(
        session,
        message.from_user.id,
        "edit_search_max",
        old_value={"max": old},
        new_value={"max": str(val)},
    )

    await message.answer(f"✅ Máximo de resultados: <b>{val}</b>")
    await state.clear()

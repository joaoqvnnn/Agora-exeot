# ============================================
# 🖼️ ADMIN IMAGES — Larizinha Store
# ============================================
# Gerenciador REAL de imagens do bot.
# Todas as imagens do sistema são editáveis por aqui.
#
# Todos os botões funcionam:
#   - LISTAR imagens por categoria
#   - ADICIONAR imagem (upload)
#   - VER / PREVIEW
#   - ALTERAR
#   - REMOVER
#   - ATIVAR/DESATIVAR
# ============================================

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.states import AdminStates
from core.models import Admin, AuditLog, ImageTemplate


router = Router(name="admin_images")


# ============================================
# 📚 CATEGORIAS DE IMAGENS
# ============================================
IMAGE_KEYS: dict[str, str] = {
    "start_image": "🏠 /start",
    "catalogo_image": "📱 Catálogo",
    "produto_image": "📦 Produto",
    "pix_image": "💳 Pix / Recarga",
    "pagamento_ok_image": "✅ Pagamento aprovado",
    "pagamento_exp_image": "❌ Pagamento expirado",
    "manutencao_image": "🔧 Manutenção",
    "perfil_image": "👤 Perfil",
    "ranking_image": "🏆 Ranking",
    "atendimento_image": "🎧 Atendimento",
    "afiliado_image": "🤝 Afiliados",
    "gift_image": "🎁 Gift Card",
    "pesquisa_image": "🔎 Pesquisa",
    "webapp_image": "🌐 Mini App",
    "entrega_image": "📦 Entrega",
    "compra_image": "🛒 Compra",
}


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


async def _get_image(
    session: AsyncSession,
    key: str,
) -> ImageTemplate | None:
    stmt = select(ImageTemplate).where(ImageTemplate.key == key)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _cancel_keyboard(back_data: str = "adm_cfg:images") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancelar", callback_data=back_data)]
        ]
    )


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_cfg:images")
async def cb_images_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    # Conta imagens configuradas
    stmt = select(ImageTemplate).where(ImageTemplate.is_active.is_(True))
    result = await session.execute(stmt)
    configured = list(result.scalars().all())

    total_possible = len(IMAGE_KEYS)
    total_configured = len(configured)

    lines = [
        "🖼️ <b>GERENCIADOR DE IMAGENS</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"📊 Configuradas: <b>{total_configured}/{total_possible}</b>",
        "",
        "<b>Status por categoria:</b>",
    ]

    rows: list[list[InlineKeyboardButton]] = []

    for key, label in IMAGE_KEYS.items():
        img = await _get_image(session, key)
        if img and img.is_active:
            status = "🟢"
        elif img:
            status = "🟡"
        else:
            status = "⚪"

        rows.append([
            InlineKeyboardButton(
                text=f"{status} {label}",
                callback_data=f"adm_img:view:{key}",
            )
        ])

    rows.append([
        InlineKeyboardButton(text="📸 Adicionar Imagem", callback_data="adm_img:add_menu"),
    ])
    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:config"),
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    text = "\n".join(lines)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 📸 ADICIONAR — ESCOLHER SLOT
# ============================================
@router.callback_query(F.data == "adm_img:add_menu")
async def cb_images_add_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text = (
        "📸 <b>ADICIONAR IMAGEM</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Escolha em qual <b>categoria</b> a imagem vai aparecer:"
    )

    rows: list[list[InlineKeyboardButton]] = []
    items = list(IMAGE_KEYS.items())
    for i in range(0, len(items), 2):
        row: list[InlineKeyboardButton] = []
        for key, label in items[i : i + 2]:
            row.append(
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"adm_img:add:{key}",
                )
            )
        rows.append(row)

    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_cfg:images")
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 👁️ VER IMAGEM
# ============================================
@router.callback_query(F.data.startswith("adm_img:view:"))
async def cb_images_view(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    key = callback.data.split(":")[2]
    img = await _get_image(session, key)

    label = IMAGE_KEYS.get(key, key)

    if img is None:
        # Não configurada ainda
        text = (
            f"🖼️ <b>{label}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "⚪ <b>Nenhuma imagem configurada</b>\n\n"
            "O bot não mostra imagem nessa tela."
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📸 Adicionar imagem", callback_data=f"adm_img:add:{key}")],
                [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_cfg:images")],
            ]
        )
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except Exception:
            await callback.message.answer(text, reply_markup=keyboard)
        await callback.answer()
        return

    # Existe — mostra preview
    status = "🟢 Ativa" if img.is_active else "🔴 Inativa"

    text = (
        f"🖼️ <b>{label}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔑 Chave: <code>{img.key}</code>\n"
        f"📊 Status: <b>{status}</b>\n"
        f"🏷 Título: <b>{img.title or '—'}</b>\n"
    )

    if img.telegram_file_id:
        text += "📦 Armazenamento: <b>Telegram (file_id)</b>\n"
    else:
        text += f"🔗 URL: <code>{img.image_url[:60]}...</code>\n"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Alterar imagem", callback_data=f"adm_img:add:{key}")],
            [InlineKeyboardButton(
                text="🔴 Desativar" if img.is_active else "🟢 Ativar",
                callback_data=f"adm_img:toggle:{key}",
            )],
            [InlineKeyboardButton(text="🗑 Remover", callback_data=f"adm_img:delete:{key}")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_cfg:images")],
        ]
    )

    # Tenta editar a mensagem com a imagem
    try:
        if img.telegram_file_id:
            from aiogram.types import InputMediaPhoto

            await callback.message.edit_media(
                media=InputMediaPhoto(
                    media=img.telegram_file_id,
                    caption=text,
                ),
                reply_markup=keyboard,
            )
        else:
            from aiogram.types import InputMediaPhoto

            await callback.message.edit_media(
                media=InputMediaPhoto(
                    media=img.image_url,
                    caption=text,
                ),
                reply_markup=keyboard,
            )
    except Exception:
        # Se falhar, envia como nova mensagem
        try:
            if img.telegram_file_id:
                await callback.message.answer_photo(
                    photo=img.telegram_file_id,
                    caption=text,
                    reply_markup=keyboard,
                )
            else:
                await callback.message.answer_photo(
                    photo=img.image_url,
                    caption=text,
                    reply_markup=keyboard,
                )
        except Exception:
            await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 📸 ADICIONAR/ALTERAR IMAGEM
# ============================================
@router.callback_query(F.data.startswith("adm_img:add:"))
async def cb_images_add(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    key = callback.data.split(":")[2]
    label = IMAGE_KEYS.get(key, key)

    text = (
        f"📸 <b>ADICIONAR IMAGEM — {label}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Envie a <b>imagem</b> que deseja usar.\n\n"
        "💡 Você pode:\n"
        "• Enviar uma foto\n"
        "• Enviar uma imagem como documento\n\n"
        "A imagem será usada nesta categoria do bot."
    )

    await callback.message.answer(
        text,
        reply_markup=_cancel_keyboard("adm_cfg:images"),
    )

    await state.update_data(img_key=key)
    await state.set_state(AdminStates.editing_image)
    await callback.answer()


@router.message(AdminStates.editing_image, F.photo | F.document)
async def msg_images_save(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    data = await state.get_data()
    key = data.get("img_key")
    if not key:
        await message.answer("❌ Chave não encontrada.")
        await state.clear()
        return

    # Pega o file_id
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
        file_id = message.document.file_id
    else:
        await message.answer("❌ Envie uma imagem válida.")
        return

    label = IMAGE_KEYS.get(key, key)

    # Busca imagem existente
    existing = await _get_image(session, key)

    if existing:
        old_file_id = existing.telegram_file_id
        existing.telegram_file_id = file_id
        existing.image_url = ""  # Limpa URL antiga
        existing.is_active = True
        session.add(existing)
        action = "edit_image"
        old_value = {"file_id": old_file_id}
    else:
        new_img = ImageTemplate(
            key=key,
            title=label,
            image_url="",  # Sem URL — só file_id
            telegram_file_id=file_id,
            is_active=True,
        )
        session.add(new_img)
        action = "add_image"
        old_value = None

    await _log_audit(
        session,
        message.from_user.id,
        action,
        old_value=old_value,
        new_value={"key": key, "file_id": file_id[:30] + "..."},
    )

    await message.answer_photo(
        photo=file_id,
        caption=(
            f"✅ <b>Imagem salva!</b>\n\n"
            f"📂 Categoria: <b>{label}</b>\n"
            f"🔑 Chave: <code>{key}</code>\n\n"
            "A imagem já está sendo usada no bot."
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="👁 Ver", callback_data=f"adm_img:view:{key}")],
                [InlineKeyboardButton(text="🖼️ Menu imagens", callback_data="adm_cfg:images")],
            ]
        ),
    )

    await state.clear()


@router.message(AdminStates.editing_image)
async def msg_images_invalid(
    message: Message,
) -> None:
    await message.answer(
        "❌ Envie uma <b>imagem</b> (foto ou arquivo de imagem)."
    )


# ============================================
# 🟢 / 🔴 TOGGLE ATIVA
# ============================================
@router.callback_query(F.data.startswith("adm_img:toggle:"))
async def cb_images_toggle(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    key = callback.data.split(":")[2]
    img = await _get_image(session, key)
    if img is None:
        await callback.answer("❌ Imagem não encontrada.", show_alert=True)
        return

    img.is_active = not img.is_active
    session.add(img)

    await _log_audit(
        session,
        callback.from_user.id,
        "toggle_image",
        new_value={"key": key, "is_active": img.is_active},
    )

    status = "ativada" if img.is_active else "desativada"
    await callback.answer(f"✅ Imagem {status}!", show_alert=True)

    callback.data = f"adm_img:view:{key}"
    await cb_images_view(callback, session)


# ============================================
# 🗑 REMOVER
# ============================================
@router.callback_query(F.data.startswith("adm_img:delete:"))
async def cb_images_delete(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    key = callback.data.split(":")[2]
    img = await _get_image(session, key)
    if img is None:
        await callback.answer("❌ Imagem não encontrada.", show_alert=True)
        return

    label = IMAGE_KEYS.get(key, key)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="✅ Sim, remover",
                callback_data=f"adm_img:confirm_del:{key}",
            )],
            [InlineKeyboardButton(
                text="❌ Cancelar",
                callback_data=f"adm_img:view:{key}",
            )],
        ]
    )

    await callback.message.answer(
        f"⚠️ <b>REMOVER IMAGEM</b>\n\n"
        f"📂 Categoria: <b>{label}</b>\n\n"
        "A imagem será removida e o bot deixará de mostrá-la "
        "nessa tela.\n\n"
        "Confirma?",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_img:confirm_del:"))
async def cb_images_confirm_delete(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    key = callback.data.split(":")[2]
    img = await _get_image(session, key)
    if img is None:
        await callback.answer("❌ Imagem não encontrada.", show_alert=True)
        return

    await _log_audit(
        session,
        callback.from_user.id,
        "delete_image",
        old_value={
            "key": key,
            "title": img.title,
        },
    )

    await session.delete(img)

    await callback.answer("🗑 Imagem removida!", show_alert=True)

    callback.data = "adm_cfg:images"
    await cb_images_menu(callback, session)

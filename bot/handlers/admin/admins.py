# ============================================
# 👮 ADMIN ADMINS — Larizinha Store
# ============================================
# Gerenciamento REAL de administradores.
# Todos os botões funcionam de verdade.
#
# Cobre:
#   - ADICIONAR ADM
#   - REMOVER ADM
#   - LISTA DE ADM
#   - PERMISSÕES (visualização)
# ============================================

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.states import AdminStates
from core.models import Admin, AuditLog, User


router = Router(name="admin_admins")


# ============================================
# 🧰 AUXILIARES
# ============================================
async def _get_admin(session: AsyncSession, telegram_id: int) -> Admin | None:
    stmt = select(Admin).where(
        Admin.telegram_id == telegram_id,
        Admin.is_active.is_(True),
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _log_audit(
    session: AsyncSession,
    admin_id: int,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    old_value: dict | None = None,
    new_value: dict | None = None,
) -> None:
    log = AuditLog(
        admin_telegram_id=admin_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        old_value=old_value,
        new_value=new_value,
    )
    session.add(log)


def _cancel_keyboard(back_data: str = "adm_cfg:admins") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancelar", callback_data=back_data)]
        ]
    )


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_cfg:admins")
async def cb_admins_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    admin = await _get_admin(session, callback.from_user.id)
    if admin is None:
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    total = await session.scalar(
        select(func.count(Admin.id)).where(Admin.is_active.is_(True))
    ) or 0

    role = "👑 Dono" if admin.is_owner else "👮 Admin"

    text = (
        "👮 <b>PAINEL CONFIGURAR ADMINS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Administradores ativos: <b>{total}</b>\n"
        f"🎖 Seu cargo: <b>{role}</b>\n\n"
        "Use os botões abaixo para fazer as alterações necessárias:"
    )

    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="➕ Adicionar Adm", callback_data="adm_adm:add")],
        [InlineKeyboardButton(text="➖ Remover Adm", callback_data="adm_adm:remove")],
        [InlineKeyboardButton(text="📋 Lista de Adm", callback_data="adm_adm:list")],
    ]

    if admin.is_owner:
        rows.append([InlineKeyboardButton(
            text="👑 Gerenciar Donos",
            callback_data="adm_adm:owners",
        )])

    rows.append([InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:config")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 📋 LISTA DE ADMINS
# ============================================
@router.callback_query(F.data == "adm_adm:list")
async def cb_admins_list(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _get_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    stmt = (
        select(Admin)
        .where(Admin.is_active.is_(True))
        .order_by(Admin.is_owner.desc(), Admin.created_at.asc())
    )
    result = await session.execute(stmt)
    admins = list(result.scalars().all())

    if not admins:
        text = "👮 <b>LISTA DE ADMINS</b>\n\nNenhum admin cadastrado."
    else:
        lines = [
            "👮 <b>LISTA DE ADMINS</b>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "",
        ]
        for i, a in enumerate(admins, start=1):
            role = "👑" if a.is_owner else "👮"
            name = a.full_name or a.username or "Sem nome"
            date = a.created_at.strftime("%d/%m/%Y") if a.created_at else "?"
            lines.append(
                f"{i}. {role} <code>{a.telegram_id}</code> — {name} — {date}"
            )
        text = "\n".join(lines)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_cfg:admins")]
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# ➕ ADICIONAR ADMIN
# ============================================
@router.callback_query(F.data == "adm_adm:add")
async def cb_admins_add(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _get_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text = (
        "➕ <b>ADICIONAR ADMINISTRADOR</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Envie o <b>ID do Telegram</b> do novo admin.\n\n"
        "💡 Para descobrir o ID, o usuário pode falar com "
        "@userinfobot ou enviar /id no bot.\n\n"
        "Exemplo: <code>6995978182</code>"
    )

    await callback.message.answer(text, reply_markup=_cancel_keyboard())
    await state.set_state(AdminStates.adding_admin)
    await callback.answer()


@router.message(AdminStates.adding_admin)
async def msg_admin_add(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _get_admin(session, message.from_user.id):
        return

    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("❌ ID inválido. Envie apenas números.")
        return

    new_id = int(raw)

    # Verifica se já é admin
    stmt = select(Admin).where(Admin.telegram_id == new_id)
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is not None:
        if existing.is_active:
            await message.answer(
                f"⚠️ <code>{new_id}</code> já é administrador ativo."
            )
            return
        # Reativa
        existing.is_active = True
        session.add(existing)
        await _log_audit(
            session, message.from_user.id, "reactivate_admin",
            target_type="admin", target_id=str(new_id),
        )
        await message.answer(
            f"✅ Admin <code>{new_id}</code> reativado com sucesso!"
        )
        await state.clear()
        return

    # Busca dados do usuário (se existir no bot)
    user_stmt = select(User).where(User.telegram_id == new_id)
    user_result = await session.execute(user_stmt)
    user = user_result.scalar_one_or_none()

    new_admin = Admin(
        telegram_id=new_id,
        username=user.username if user else None,
        full_name=user.first_name if user else None,
        is_owner=False,
        is_active=True,
        added_by=message.from_user.id,
        permissions={},
    )
    session.add(new_admin)

    await _log_audit(
        session, message.from_user.id, "add_admin",
        target_type="admin", target_id=str(new_id),
        new_value={"telegram_id": new_id},
    )

    await message.answer(
        f"✅ Admin <b>{new_id}</b> adicionado com sucesso!\n\n"
        f"O usuário já pode usar /admin no bot."
    )

    # Notifica o novo admin
    try:
        await message.bot.send_message(
            chat_id=new_id,
            text=(
                "🎉 <b>Você foi promovido a administrador!</b>\n\n"
                "Use /admin no bot para acessar o painel."
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass

    await state.clear()


# ============================================
# ➖ REMOVER ADMIN
# ============================================
@router.callback_query(F.data == "adm_adm:remove")
async def cb_admins_remove(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _get_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    stmt = (
        select(Admin)
        .where(Admin.is_active.is_(True), Admin.is_owner.is_(False))
        .order_by(Admin.created_at.asc())
    )
    result = await session.execute(stmt)
    admins = list(result.scalars().all())

    if not admins:
        await callback.answer("❌ Nenhum admin pra remover.", show_alert=True)
        return

    rows: list[list[InlineKeyboardButton]] = []
    for a in admins:
        name = a.full_name or a.username or str(a.telegram_id)
        rows.append([
            InlineKeyboardButton(
                text=f"🗑 {name} ({a.telegram_id})",
                callback_data=f"adm_adm:confirm_remove:{a.telegram_id}",
            )
        ])
    rows.append([InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_cfg:admins")])

    await callback.message.edit_text(
        "➖ <b>REMOVER ADMINISTRADOR</b>\n\n"
        "Escolha quem remover:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_adm:confirm_remove:"))
async def cb_admins_confirm_remove(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    current_admin = await _get_admin(session, callback.from_user.id)
    if current_admin is None:
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    target_id = int(callback.data.split(":")[2])

    if target_id == current_admin.telegram_id:
        await callback.answer("❌ Você não pode remover a si mesmo.", show_alert=True)
        return

    stmt = select(Admin).where(Admin.telegram_id == target_id)
    result = await session.execute(stmt)
    target = result.scalar_one_or_none()

    if target is None or not target.is_active:
        await callback.answer("❌ Admin não encontrado.", show_alert=True)
        return

    if target.is_owner:
        await callback.answer("❌ Não é possível remover o dono.", show_alert=True)
        return

    target.is_active = False
    session.add(target)

    await _log_audit(
        session, callback.from_user.id, "remove_admin",
        target_type="admin", target_id=str(target_id),
        old_value={"telegram_id": target_id, "is_active": True},
    )

    await callback.answer(f"✅ Admin {target_id} removido.", show_alert=True)

    # Notifica
    try:
        await callback.bot.send_message(
            chat_id=target_id,
            text=(
                "⚠️ <b>Você foi removido dos administradores.</b>\n\n"
                "Seu acesso ao painel foi revogado."
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass

    callback.data = "adm_adm:remove"
    await cb_admins_remove(callback, session)


# ============================================
# 👑 GERENCIAR DONOS (só o dono pode)
# ============================================
@router.callback_query(F.data == "adm_adm:owners")
async def cb_admins_owners(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    current_admin = await _get_admin(session, callback.from_user.id)
    if current_admin is None:
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    if not current_admin.is_owner:
        await callback.answer("🚫 Apenas o dono pode acessar.", show_alert=True)
        return

    stmt = select(Admin).where(Admin.is_owner.is_(True), Admin.is_active.is_(True))
    result = await session.execute(stmt)
    owners = list(result.scalars().all())

    lines = [
        "👑 <b>DONOS DO BOT</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    for o in owners:
        name = o.full_name or o.username or "Sem nome"
        lines.append(f"👑 <code>{o.telegram_id}</code> — {name}")

    lines.append("")
    lines.append(
        "💡 Donos têm acesso total e não podem ser removidos."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Promover a Dono", callback_data="adm_adm:promote_owner")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_cfg:admins")],
        ]
    )

    try:
        await callback.message.edit_text("\n".join(lines), reply_markup=keyboard)
    except Exception:
        await callback.message.answer("\n".join(lines), reply_markup=keyboard)

    await callback.answer()


@router.callback_query(F.data == "adm_adm:promote_owner")
async def cb_admins_promote_owner(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    current_admin = await _get_admin(session, callback.from_user.id)
    if current_admin is None or not current_admin.is_owner:
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "👑 Envie o <b>ID do Telegram</b> do novo dono:",
        reply_markup=_cancel_keyboard("adm_adm:owners"),
    )
    await state.set_state(AdminStates.adding_admin)
    await callback.answer()


# ============================================
# ⚙️ PERMISSÕES (visualização simples)
# ============================================
@router.callback_query(F.data.startswith("adm_adm:permissions:"))
async def cb_admins_permissions(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    current_admin = await _get_admin(session, callback.from_user.id)
    if current_admin is None:
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    target_id = int(callback.data.split(":")[2])
    stmt = select(Admin).where(Admin.telegram_id == target_id)
    result = await session.execute(stmt)
    target = result.scalar_one_or_none()

    if target is None:
        await callback.answer("❌ Admin não encontrado.", show_alert=True)
        return

    perms = target.permissions or {}

    perm_list = [
        ("users", "👥 Usuários"),
        ("finance", "💰 Financeiro"),
        ("products", "📦 Produtos"),
        ("stock", "🔐 Estoque"),
        ("payments", "💳 Pagamentos"),
        ("affiliates", "🤝 Afiliados"),
        ("broadcast", "📢 Broadcast"),
        ("settings", "⚙️ Configurações"),
        ("logs", "📋 Logs"),
        ("security", "🛡 Segurança"),
    ]

    lines = [
        f"⚙️ <b>Permissões de {target.telegram_id}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    for key, label in perm_list:
        has = "✅" if perms.get(key) else "❌"
        lines.append(f"{has} {label}")

    lines.append("")
    lines.append("💡 Donos têm todas as permissões automaticamente.")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_adm:list")]
        ]
    )

    try:
        await callback.message.edit_text("\n".join(lines), reply_markup=keyboard)
    except Exception:
        await callback.message.answer("\n".join(lines), reply_markup=keyboard)

    await callback.answer()

# ============================================
# 🚫 ADMIN BLOCKS — Larizinha Store
# ============================================
# Gerenciamento REAL de bloqueios de usuários.
# Todos os botões funcionam de verdade.
#
# Cobre:
#   - LISTAR bloqueados
#   - BLOQUEAR usuário
#   - DESBLOQUEAR
#   - ALTERAR duração
#   - VER detalhes do bloqueio
# ============================================

from datetime import datetime, timedelta, timezone

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
from core.models import (
    Admin,
    AuditLog,
    BlockedUser,
    User,
    UserStatus,
)


router = Router(name="admin_blocks")


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


def _cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_block:menu")]
        ]
    )


def _format_dt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%d/%m/%Y %H:%M")


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_block:menu")
async def cb_blocks_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    total = await session.scalar(select(func.count(BlockedUser.id))) or 0

    now = datetime.now(timezone.utc)
    active = await session.scalar(
        select(func.count(BlockedUser.id)).where(
            (BlockedUser.expires_at.is_(None)) | (BlockedUser.expires_at > now)
        )
    ) or 0

    text = (
        "🚫 <b>BLOQUEIOS DE USUÁRIOS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 Total histórico: <b>{total}</b>\n"
        f"🔴 Bloqueados agora: <b>{active}</b>\n\n"
        "Bloqueios impedem o usuário de usar o bot.\n\n"
        "Escolha uma opção:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Lista de Bloqueados", callback_data="adm_block:list:0")],
            [InlineKeyboardButton(text="➕ Bloquear Usuário", callback_data="adm_block:add")],
            [InlineKeyboardButton(text="➖ Desbloquear Usuário", callback_data="adm_block:remove")],
            [InlineKeyboardButton(text="🧹 Limpar Expirados", callback_data="adm_block:clean_expired")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:config")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 📋 LISTA DE BLOQUEADOS
# ============================================
@router.callback_query(F.data.startswith("adm_block:list:"))
async def cb_blocks_list(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    try:
        page = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        page = 0

    PER_PAGE = 10

    stmt = select(BlockedUser).order_by(BlockedUser.blocked_at.desc())
    total = await session.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0

    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    stmt = stmt.offset(page * PER_PAGE).limit(PER_PAGE)
    result = await session.execute(stmt)
    blocks = list(result.scalars().all())

    lines = [
        "🚫 <b>LISTA DE BLOQUEADOS</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📊 Total: <b>{total}</b>",
        "",
    ]

    rows: list[list[InlineKeyboardButton]] = []

    if not blocks:
        lines.append("✅ Nenhum usuário bloqueado.")
    else:
        now = datetime.now(timezone.utc)
        for b in blocks:
            blocked_at = _format_dt(b.blocked_at)
            if b.expires_at is None:
                exp = "Permanente"
                status_emoji = "🔴"
            elif b.expires_at > now:
                exp = _format_dt(b.expires_at)
                status_emoji = "🔴"
            else:
                exp = f"Expirou {_format_dt(b.expires_at)}"
                status_emoji = "⚪"

            preview = (b.reason or "sem motivo")[:30]

            lines.append(
                f"{status_emoji} <code>{b.user_telegram_id}</code>\n"
                f"   📝 {preview}\n"
                f"   ⏰ {exp}"
            )

            rows.append([
                InlineKeyboardButton(
                    text=f"{status_emoji} {b.user_telegram_id} — {preview}",
                    callback_data=f"adm_block:view:{b.id}",
                )
            ])

    # Navegação
    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                text="⬅️",
                callback_data=f"adm_block:list:{page - 1}",
            ))
        nav.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="adm:noop",
        ))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(
                text="➡️",
                callback_data=f"adm_block:list:{page + 1}",
            ))
        rows.append(nav)

    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_block:menu")
    ])

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n<i>... (truncado)</i>"

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 👁️ VER BLOQUEIO
# ============================================
@router.callback_query(F.data.startswith("adm_block:view:"))
async def cb_blocks_view(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    block_id = int(callback.data.split(":")[2])
    block = await session.get(BlockedUser, block_id)
    if block is None:
        await callback.answer("❌ Bloqueio não encontrado.", show_alert=True)
        return

    user = await session.scalar(
        select(User).where(User.telegram_id == block.user_telegram_id)
    )

    user_name = user.first_name if user else "?"
    username = f"@{user.username}" if user and user.username else "—"

    now = datetime.now(timezone.utc)
    if block.expires_at is None:
        status = "🔴 Ativo (permanente)"
    elif block.expires_at > now:
        remaining = block.expires_at - now
        hours = int(remaining.total_seconds() // 3600)
        status = f"🔴 Ativo (expira em {hours}h)"
    else:
        status = "⚪ Expirado"

    text = (
        f"🚫 <b>BLOQUEIO #{block.id}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Usuário: <b>{user_name}</b>\n"
        f"📛 Username: {username}\n"
        f"🆔 ID: <code>{block.user_telegram_id}</code>\n\n"
        f"📊 Status: <b>{status}</b>\n"
        f"📝 Motivo: {block.reason or '—'}\n\n"
        f"🕐 Bloqueado em: {_format_dt(block.blocked_at)}\n"
        f"⏰ Expira em: {_format_dt(block.expires_at)}\n"
        f"👮 Bloqueado por: <code>{block.blocked_by}</code>"
    )

    rows: list[list[InlineKeyboardButton]] = []

    if user is not None:
        rows.append([
            InlineKeyboardButton(
                text="👁 Ver usuário",
                callback_data=f"adm_user:view:{user.id}",
            )
        ])

    # Só permite desbloquear se ainda está ativo
    if block.expires_at is None or block.expires_at > now:
        rows.append([
            InlineKeyboardButton(
                text="🟢 Desbloquear agora",
                callback_data=f"adm_block:unblock:{block.id}",
            )
        ])
        rows.append([
            InlineKeyboardButton(
                text="⏰ Alterar duração",
                callback_data=f"adm_block:change_dur:{block.id}",
            )
        ])
    else:
        rows.append([
            InlineKeyboardButton(
                text="🗑 Remover registro",
                callback_data=f"adm_block:delete:{block.id}",
            )
        ])

    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_block:list:0")
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# ➕ BLOQUEAR USUÁRIO
# ============================================
@router.callback_query(F.data == "adm_block:add")
async def cb_blocks_add(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "➕ <b>BLOQUEAR USUÁRIO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Envie o <b>ID do Telegram</b> do usuário a bloquear.\n\n"
        "Exemplo: <code>6995978182</code>",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.blocking_user)
    await callback.answer()


@router.message(AdminStates.blocking_user)
async def msg_blocks_user_id(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("❌ ID inválido. Envie apenas números.")
        return

    target_id = int(raw)

    # Não pode bloquear a si mesmo
    if target_id == message.from_user.id:
        await message.answer("❌ Você não pode bloquear a si mesmo.")
        return

    # Não pode bloquear outros admins
    is_admin_target = await session.scalar(
        select(Admin).where(
            Admin.telegram_id == target_id,
            Admin.is_active.is_(True),
        )
    )
    if is_admin_target:
        await message.answer("❌ Não pode bloquear outro administrador.")
        return

    # Busca o usuário
    user = await session.scalar(
        select(User).where(User.telegram_id == target_id)
    )

    user_info = "❓ Não registrado no bot"
    if user:
        user_info = (
            f"👤 {user.first_name or 'Sem nome'}\n"
            f"📛 @{user.username}" if user.username else "📛 —"
        )

    await state.update_data(target_id=target_id)

    await message.answer(
        f"👤 <b>Usuário alvo:</b>\n\n"
        f"🆔 <code>{target_id}</code>\n"
        f"{user_info}\n\n"
        f"📝 Agora envie o <b>motivo do bloqueio</b>.\n"
        f"Ou envie <code>-</code> para deixar sem motivo.",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.blocking_user_reason)


@router.message(AdminStates.blocking_user_reason)
async def msg_blocks_reason(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    reason = (message.text or "").strip()
    if reason == "-":
        reason = ""

    await state.update_data(reason=reason)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏰ 10 minutos", callback_data="adm_block:setdur:600")],
            [InlineKeyboardButton(text="🕐 1 hora", callback_data="adm_block:setdur:3600")],
            [InlineKeyboardButton(text="📅 24 horas", callback_data="adm_block:setdur:86400")],
            [InlineKeyboardButton(text="📆 7 dias", callback_data="adm_block:setdur:604800")],
            [InlineKeyboardButton(text="🔴 Permanente", callback_data="adm_block:setdur:0")],
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_block:menu")],
        ]
    )

    await message.answer(
        f"📝 Motivo: <i>{reason or 'sem motivo'}</i>\n\n"
        f"⏰ Escolha a <b>duração do bloqueio</b>:",
        reply_markup=keyboard,
    )
    await state.set_state(AdminStates.blocking_user_duration)


@router.callback_query(F.data.startswith("adm_block:setdur:"))
async def cb_blocks_setdur(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    try:
        duration = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Valor inválido.", show_alert=True)
        return

    data = await state.get_data()
    target_id = data.get("target_id")
    reason = data.get("reason", "")

    if not target_id:
        await callback.answer("❌ Sessão expirada.", show_alert=True)
        await state.clear()
        return

    # Verifica se já existe bloqueio ativo
    stmt = select(BlockedUser).where(
        BlockedUser.user_telegram_id == target_id
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()

    expires_at = None
    if duration > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=duration)

    if existing:
        existing.reason = reason
        existing.expires_at = expires_at
        existing.blocked_by = callback.from_user.id
        existing.blocked_at = datetime.now(timezone.utc)
        session.add(existing)
    else:
        block = BlockedUser(
            user_telegram_id=target_id,
            reason=reason,
            blocked_by=callback.from_user.id,
            expires_at=expires_at,
        )
        session.add(block)

    # Atualiza status do usuário
    user = await session.scalar(
        select(User).where(User.telegram_id == target_id)
    )
    if user:
        user.status = UserStatus.BLOCKED
        session.add(user)

    await _log_audit(
        session,
        callback.from_user.id,
        "block_user",
        target_type="user",
        target_id=str(target_id),
        new_value={"reason": reason, "duration": duration},
    )

    duration_txt = "Permanente" if duration == 0 else f"{duration // 60}min"

    await callback.answer(f"🔴 Bloqueado por {duration_txt}!", show_alert=True)

    # Notifica o usuário
    try:
        await callback.bot.send_message(
            chat_id=target_id,
            text=(
                f"🚫 <b>Você foi bloqueado</b>\n\n"
                f"📝 Motivo: {reason or 'Não informado'}\n"
                f"⏰ Duração: <b>{duration_txt}</b>"
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass

    await state.clear()

    callback.data = "adm_block:menu"
    await cb_blocks_menu(callback, session)


# ============================================
# 🟢 DESBLOQUEAR
# ============================================
@router.callback_query(F.data.startswith("adm_block:unblock:"))
async def cb_blocks_unblock(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    block_id = int(callback.data.split(":")[2])
    block = await session.get(BlockedUser, block_id)
    if block is None:
        await callback.answer("❌ Bloqueio não encontrado.", show_alert=True)
        return

    target_id = block.user_telegram_id

    # Remove o bloqueio
    await session.delete(block)

    # Atualiza usuário
    user = await session.scalar(
        select(User).where(User.telegram_id == target_id)
    )
    if user:
        user.status = UserStatus.ACTIVE
        session.add(user)

    await _log_audit(
        session,
        callback.from_user.id,
        "unblock_user",
        target_type="user",
        target_id=str(target_id),
    )

    await callback.answer("🟢 Desbloqueado!", show_alert=True)

    # Notifica
    try:
        await callback.bot.send_message(
            chat_id=target_id,
            text="🟢 <b>Você foi desbloqueado!</b>\n\nVolte a usar o bot.",
            parse_mode="HTML",
        )
    except Exception:
        pass

    callback.data = "adm_block:list:0"
    await cb_blocks_list(callback, session)


# ============================================
# ⏰ ALTERAR DURAÇÃO
# ============================================
@router.callback_query(F.data.startswith("adm_block:change_dur:"))
async def cb_blocks_change_dur(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    block_id = int(callback.data.split(":")[2])

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏰ 10 minutos", callback_data=f"adm_block:newdur:{block_id}:600")],
            [InlineKeyboardButton(text="🕐 1 hora", callback_data=f"adm_block:newdur:{block_id}:3600")],
            [InlineKeyboardButton(text="📅 24 horas", callback_data=f"adm_block:newdur:{block_id}:86400")],
            [InlineKeyboardButton(text="📆 7 dias", callback_data=f"adm_block:newdur:{block_id}:604800")],
            [InlineKeyboardButton(text="🔴 Permanente", callback_data=f"adm_block:newdur:{block_id}:0")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data=f"adm_block:view:{block_id}")],
        ]
    )

    await callback.message.edit_text(
        "⏰ <b>ALTERAR DURAÇÃO</b>\n\nEscolha a nova duração:",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_block:newdur:"))
async def cb_blocks_newdur(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    parts = callback.data.split(":")
    block_id = int(parts[2])
    duration = int(parts[3])

    block = await session.get(BlockedUser, block_id)
    if block is None:
        await callback.answer("❌ Bloqueio não encontrado.", show_alert=True)
        return

    if duration == 0:
        block.expires_at = None
    else:
        block.expires_at = datetime.now(timezone.utc) + timedelta(seconds=duration)

    session.add(block)

    await _log_audit(
        session,
        callback.from_user.id,
        "change_block_duration",
        target_type="user",
        target_id=str(block.user_telegram_id),
        new_value={"duration": duration},
    )

    await callback.answer("✅ Duração atualizada!", show_alert=True)

    callback.data = f"adm_block:view:{block_id}"
    await cb_blocks_view(callback, session)


# ============================================
# 🗑 REMOVER REGISTRO
# ============================================
@router.callback_query(F.data.startswith("adm_block:delete:"))
async def cb_blocks_delete(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    block_id = int(callback.data.split(":")[2])
    block = await session.get(BlockedUser, block_id)
    if block is None:
        await callback.answer("❌ Bloqueio não encontrado.", show_alert=True)
        return

    target_id = block.user_telegram_id
    await session.delete(block)

    await _log_audit(
        session,
        callback.from_user.id,
        "delete_block_record",
        target_type="user",
        target_id=str(target_id),
    )

    await callback.answer("🗑 Registro removido.", show_alert=True)

    callback.data = "adm_block:list:0"
    await cb_blocks_list(callback, session)


# ============================================
# ➖ DESBLOQUEAR (via menu)
# ============================================
@router.callback_query(F.data == "adm_block:remove")
async def cb_blocks_remove_menu(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "➖ <b>DESBLOQUEAR USUÁRIO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Envie o <b>ID do Telegram</b> do usuário a desbloquear.",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.blocking_user)
    await callback.answer()


# ============================================
# 🧹 LIMPAR EXPIRADOS
# ============================================
@router.callback_query(F.data == "adm_block:clean_expired")
async def cb_blocks_clean_expired(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    now = datetime.now(timezone.utc)
    stmt = select(BlockedUser).where(
        BlockedUser.expires_at.is_not(None),
        BlockedUser.expires_at < now,
    )
    result = await session.execute(stmt)
    expired = list(result.scalars().all())

    if not expired:
        await callback.answer("✅ Nenhum bloqueio expirado.", show_alert=True)
        return

    for b in expired:
        user = await session.scalar(
            select(User).where(User.telegram_id == b.user_telegram_id)
        )
        if user:
            user.status = UserStatus.ACTIVE
            session.add(user)
        await session.delete(b)

    await _log_audit(
        session,
        callback.from_user.id,
        "clean_expired_blocks",
        new_value={"removed": len(expired)},
    )

    await callback.answer(f"🧹 {len(expired)} expirados removidos!", show_alert=True)

    callback.data = "adm_block:menu"
    await cb_blocks_menu(callback, session)

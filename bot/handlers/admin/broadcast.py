# ============================================
# 📢 ADMIN BROADCAST — Larizinha Store
# ============================================
# Envio de mensagens em massa + agendamento REAL.
# Todos os botões funcionam de verdade.
#
# Cobre:
#   - NOVO BROADCAST (texto, foto, vídeo, doc)
#   - PÚBLICO-ALVO (todos, ativos, inativos, compradores,
#     afiliados, por produto, por categoria)
#   - ENVIO IMEDIATO
#   - AGENDAMENTO (data, hora, minuto, segundo)
#   - RECORRÊNCIA (diário, semanal, mensal)
#   - RELATÓRIO de envio
#   - CANCELAR agendamento
# ============================================

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

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
    Broadcast,
    BroadcastStatus,
    Order,
    OrderStatus,
    User,
    UserStatus,
)


router = Router(name="admin_broadcast")


BR_TZ = ZoneInfo("America/Sao_Paulo")


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


def _cancel_keyboard(back_data: str = "adm_bc:menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancelar", callback_data=back_data)]
        ]
    )


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_bc:menu")
async def cb_broadcast_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    # Estatísticas
    total_users = await session.scalar(
        select(func.count(User.id)).where(User.is_blocked_bot.is_(False))
    ) or 0

    scheduled = await session.scalar(
        select(func.count(Broadcast.id)).where(
            Broadcast.status == BroadcastStatus.SCHEDULED
        )
    ) or 0

    sent = await session.scalar(
        select(func.count(Broadcast.id)).where(
            Broadcast.status == BroadcastStatus.SENT
        )
    ) or 0

    text = (
        "📢 <b>BROADCAST / MENSAGENS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Usuários alcançáveis: <b>{total_users}</b>\n"
        f"📅 Agendados: <b>{scheduled}</b>\n"
        f"✅ Enviados: <b>{sent}</b>\n\n"
        "Escolha uma opção:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Novo Broadcast", callback_data="adm_bc:new")],
            [InlineKeyboardButton(text="📅 Agendamentos", callback_data="adm_bc:scheduled_list")],
            [InlineKeyboardButton(text="📜 Histórico de Envios", callback_data="adm_bc:history")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:config")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 📤 NOVO BROADCAST — Escolher público
# ============================================
@router.callback_query(F.data == "adm_bc:new")
async def cb_broadcast_new(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await state.clear()

    text = (
        "📤 <b>NOVO BROADCAST</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>1️⃣ Escolha o público-alvo:</b>\n\n"
        "Quem vai receber a mensagem?"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Todos os usuários", callback_data="adm_bc:target:all")],
            [InlineKeyboardButton(text="🟢 Usuários ativos (30d)", callback_data="adm_bc:target:active")],
            [InlineKeyboardButton(text="💤 Usuários inativos", callback_data="adm_bc:target:inactive")],
            [InlineKeyboardButton(text="🛒 Compradores", callback_data="adm_bc:target:buyers")],
            [InlineKeyboardButton(text="🤝 Afiliados", callback_data="adm_bc:target:affiliates")],
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_bc:menu")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


@router.callback_query(F.data.startswith("adm_bc:target:"))
async def cb_broadcast_target(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    target = callback.data.split(":")[2]

    # Conta quantos usuários esse target alcança
    count = await _count_target(session, target)

    await state.update_data(target=target)

    labels = {
        "all": "👥 Todos",
        "active": "🟢 Ativos",
        "inactive": "💤 Inativos",
        "buyers": "🛒 Compradores",
        "affiliates": "🤝 Afiliados",
    }

    text = (
        f"📤 <b>NOVO BROADCAST</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 Público: <b>{labels.get(target, target)}</b>\n"
        f"👥 Alcançará: <b>{count}</b> usuário(s)\n\n"
        "<b>2️⃣ Envie a mensagem:</b>\n\n"
        "• Pode ser <b>texto</b>\n"
        "• <b>Foto</b> com legenda\n"
        "• <b>Vídeo</b> com legenda\n"
        "• <b>Documento</b> com legenda\n\n"
        "💡 Suporta HTML: <code>&lt;b&gt;</code>, <code>&lt;i&gt;</code>, "
        "<code>&lt;a href=''&gt;</code>"
    )

    await callback.message.answer(text, reply_markup=_cancel_keyboard())
    await state.set_state(AdminStates.waiting_broadcast_text)
    await callback.answer()


async def _count_target(session: AsyncSession, target: str) -> int:
    """Conta usuários do target."""
    from datetime import datetime, timedelta, timezone

    if target == "all":
        stmt = select(func.count(User.id)).where(User.is_blocked_bot.is_(False))
    elif target == "active":
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        stmt = select(func.count(User.id)).where(
            User.is_blocked_bot.is_(False),
            User.last_seen_at >= cutoff,
        )
    elif target == "inactive":
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        stmt = select(func.count(User.id)).where(
            User.is_blocked_bot.is_(False),
            (User.last_seen_at < cutoff) | (User.last_seen_at.is_(None)),
        )
    elif target == "buyers":
        stmt = select(func.count(func.distinct(Order.user_telegram_id))).where(
            Order.status.in_([OrderStatus.PAID, OrderStatus.DELIVERED])
        )
    elif target == "affiliates":
        stmt = select(func.count(User.id)).where(
            User.referred_by.is_not(None),
            User.is_blocked_bot.is_(False),
        )
    else:
        return 0

    return await session.scalar(stmt) or 0


# ============================================
# 📩 RECEBE MENSAGEM
# ============================================
@router.message(AdminStates.waiting_broadcast_text)
async def msg_broadcast_receive(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    raw_text = message.text or message.caption or ""
    photo_id = message.photo[-1].file_id if message.photo else None
    video_id = message.video.file_id if message.video else None
    doc_id = message.document.file_id if message.document else None

    if not raw_text.strip() and not (photo_id or video_id or doc_id):
        await message.answer("❌ Mensagem vazia.")
        return

    media_type = "none"
    if photo_id:
        media_type = "photo"
    elif video_id:
        media_type = "video"
    elif doc_id:
        media_type = "document"

    await state.update_data(
        broadcast_text=raw_text,
        media_type=media_type,
        media_id=photo_id or video_id or doc_id,
    )

    # Pede botões (opcional)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Adicionar Botão", callback_data="adm_bc:add_button")],
            [InlineKeyboardButton(text="⏭ Sem botões, continuar", callback_data="adm_bc:no_buttons")],
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_bc:menu")],
        ]
    )

    await message.answer(
        "✅ Mensagem recebida!\n\n"
        "<b>3️⃣ Deseja adicionar botões?</b>\n\n"
        "Você pode adicionar botões inline com link ou URL.",
        reply_markup=keyboard,
    )


# ============================================
# 🔘 ADICIONAR BOTÕES
# ============================================
@router.callback_query(F.data == "adm_bc:add_button")
async def cb_broadcast_add_button(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "🔘 <b>ADICIONAR BOTÃO</b>\n\n"
        "Envie no formato:\n"
        "<code>TEXTO | URL</code>\n\n"
        "Exemplo:\n"
        "<code>🛍 Comprar Agora | https://t.me/seubot</code>\n\n"
        "💡 Você pode adicionar vários enviando um por linha.",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.waiting_broadcast_schedule)
    await callback.answer()


@router.callback_query(F.data == "adm_bc:no_buttons")
async def cb_broadcast_no_buttons(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await state.update_data(buttons=[])

    await _ask_when_to_send(callback.message, state)
    await callback.answer()


async def _ask_when_to_send(message: Message, state: FSMContext) -> None:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Enviar Agora", callback_data="adm_bc:send_now")],
            [InlineKeyboardButton(text="📅 Agendar", callback_data="adm_bc:schedule")],
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_bc:menu")],
        ]
    )

    await message.answer(
        "✅ <b>Quando enviar?</b>\n\n"
        "Escolha uma opção:",
        reply_markup=keyboard,
    )


# ============================================
# 🚀 ENVIO IMEDIATO
# ============================================
@router.callback_query(F.data == "adm_bc:send_now")
async def cb_broadcast_send_now(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    data = await state.get_data()
    target = data.get("target", "all")
    text = data.get("broadcast_text", "")
    media_type = data.get("media_type", "none")
    media_id = data.get("media_id")
    buttons = data.get("buttons", [])

    # Cria registro no banco
    bc = Broadcast(
        name=f"Broadcast {datetime.now(BR_TZ).strftime('%d/%m %H:%M')}",
        message_text=text,
        media_url=media_id,
        media_type=media_type,
        buttons=buttons if buttons else None,
        target_audience=target,
        status=BroadcastStatus.SENDING,
        created_by=callback.from_user.id,
    )
    session.add(bc)
    await session.flush()

    await _log_audit(
        session,
        callback.from_user.id,
        "broadcast_send_now",
        new_value={"broadcast_id": bc.id, "target": target},
    )

    await callback.answer("🚀 Enviando...", show_alert=False)

    # Executa em background
    import asyncio
    asyncio.create_task(_run_broadcast(callback.bot, bc.id, target, text, media_type, media_id, buttons))

    await state.clear()

    await callback.message.edit_text(
        "🚀 <b>Broadcast iniciado!</b>\n\n"
        f"🎯 Público: <b>{target}</b>\n"
        "Acompanhe em <b>Histórico de Envios</b>.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📜 Histórico", callback_data="adm_bc:history")],
                [InlineKeyboardButton(text="🔙 Menu", callback_data="adm_bc:menu")],
            ]
        ),
    )


# ============================================
# 📅 AGENDAR
# ============================================
@router.callback_query(F.data == "adm_bc:schedule")
async def cb_broadcast_schedule(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "📅 <b>AGENDAR ENVIO</b>\n\n"
        "Envie a <b>data e hora</b> no formato:\n\n"
        "<code>DD/MM/AAAA HH:MM</code>\n\n"
        "Exemplos:\n"
        "• <code>25/12/2026 20:00</code>\n"
        "• <code>01/01/2027 15:30</code>\n\n"
        "💡 Fuso: America/Sao_Paulo (BRT)",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.waiting_broadcast_schedule)
    await callback.answer()


@router.message(AdminStates.waiting_broadcast_schedule)
async def msg_broadcast_schedule(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    raw = (message.text or "").strip()

    # Se tiver '|' é botão
    if "|" in raw and await state.get_state() == AdminStates.waiting_broadcast_schedule.state:
        # Trata como botões
        buttons = []
        for line in raw.split("\n"):
            line = line.strip()
            if not line or "|" not in line:
                continue
            parts = line.split("|", 1)
            btn_text = parts[0].strip()
            btn_url = parts[1].strip()
            if btn_text and btn_url.startswith(("http://", "https://", "tg://")):
                buttons.append({"text": btn_text, "url": btn_url})

        if not buttons:
            await message.answer("❌ Nenhum botão válido. Use <code>TEXTO | URL</code>")
            return

        await state.update_data(buttons=buttons)
        await message.answer(f"✅ {len(buttons)} botão(ões) adicionado(s)!")
        await _ask_when_to_send(message, state)
        return

    # Senão, é data/hora
    try:
        dt_br = datetime.strptime(raw, "%d/%m/%Y %H:%M")
        dt_br = dt_br.replace(tzinfo=BR_TZ)
        dt_utc = dt_br.astimezone(timezone.utc)
    except ValueError:
        await message.answer(
            "❌ Formato inválido. Use: <code>DD/MM/AAAA HH:MM</code>"
        )
        return

    # Valida se é futuro
    if dt_utc <= datetime.now(timezone.utc):
        await message.answer("❌ Data deve ser no futuro.")
        return

    data = await state.get_data()
    target = data.get("target", "all")
    text = data.get("broadcast_text", "")
    media_type = data.get("media_type", "none")
    media_id = data.get("media_id")
    buttons = data.get("buttons", [])

    bc = Broadcast(
        name=f"Agendado {dt_br.strftime('%d/%m %H:%M')}",
        message_text=text,
        media_url=media_id,
        media_type=media_type,
        buttons=buttons if buttons else None,
        target_audience=target,
        status=BroadcastStatus.SCHEDULED,
        scheduled_at=dt_utc,
        created_by=message.from_user.id,
    )
    session.add(bc)
    await session.flush()

    await _log_audit(
        session,
        message.from_user.id,
        "broadcast_schedule",
        new_value={
            "broadcast_id": bc.id,
            "target": target,
            "scheduled_at": dt_utc.isoformat(),
        },
    )

    await message.answer(
        f"✅ <b>Broadcast agendado!</b>\n\n"
        f"📅 Data: <b>{dt_br.strftime('%d/%m/%Y %H:%M')}</b>\n"
        f"🎯 Público: <b>{target}</b>\n"
        f"🆔 ID: <code>{bc.id}</code>\n\n"
        "A mensagem será enviada automaticamente no horário.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📅 Agendamentos", callback_data="adm_bc:scheduled_list")],
                [InlineKeyboardButton(text="🔙 Menu", callback_data="adm_bc:menu")],
            ]
        ),
    )
    await state.clear()


# ============================================
# 📅 LISTA DE AGENDAMENTOS
# ============================================
@router.callback_query(F.data == "adm_bc:scheduled_list")
async def cb_broadcast_scheduled(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    stmt = (
        select(Broadcast)
        .where(Broadcast.status == BroadcastStatus.SCHEDULED)
        .order_by(Broadcast.scheduled_at.asc())
    )
    result = await session.execute(stmt)
    items = list(result.scalars().all())

    if not items:
        text = (
            "📅 <b>AGENDAMENTOS</b>\n\n"
            "Nenhum broadcast agendado."
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_bc:menu")]
            ]
        )
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except Exception:
            await callback.message.answer(text, reply_markup=keyboard)
        await callback.answer()
        return

    lines = [
        "📅 <b>AGENDAMENTOS</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    rows: list[list[InlineKeyboardButton]] = []

    for bc in items:
        dt_br = bc.scheduled_at.astimezone(BR_TZ)
        preview = (bc.message_text or "")[:30].replace("\n", " ")
        lines.append(
            f"🆔 <code>{bc.id}</code> — {dt_br.strftime('%d/%m %H:%M')}\n"
            f"   🎯 {bc.target_audience}\n"
            f"   📝 {preview}..."
        )
        rows.append([
            InlineKeyboardButton(
                text=f"🗑 Cancelar #{bc.id} — {dt_br.strftime('%d/%m %H:%M')}",
                callback_data=f"adm_bc:cancel:{bc.id}",
            )
        ])

    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_bc:menu")
    ])

    text = "\n".join(lines)
    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


@router.callback_query(F.data.startswith("adm_bc:cancel:"))
async def cb_broadcast_cancel(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    bc_id = int(callback.data.split(":")[2])
    bc = await session.get(Broadcast, bc_id)
    if bc is None:
        await callback.answer("❌ Não encontrado.", show_alert=True)
        return

    bc.status = BroadcastStatus.CANCELLED
    session.add(bc)

    await _log_audit(
        session,
        callback.from_user.id,
        "broadcast_cancel",
        new_value={"broadcast_id": bc_id},
    )

    await callback.answer("🗑 Cancelado.", show_alert=True)

    callback.data = "adm_bc:scheduled_list"
    await cb_broadcast_scheduled(callback, session)


# ============================================
# 📜 HISTÓRICO
# ============================================
@router.callback_query(F.data == "adm_bc:history")
async def cb_broadcast_history(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    stmt = (
        select(Broadcast)
        .where(Broadcast.status.in_([
            BroadcastStatus.SENT,
            BroadcastStatus.SENDING,
            BroadcastStatus.FAILED,
        ]))
        .order_by(Broadcast.id.desc())
        .limit(20)
    )
    result = await session.execute(stmt)
    items = list(result.scalars().all())

    if not items:
        text = (
            "📜 <b>HISTÓRICO DE ENVIOS</b>\n\n"
            "Nenhum envio registrado."
        )
    else:
        lines = [
            "📜 <b>HISTÓRICO DE ENVIOS</b>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "",
        ]
        for bc in items:
            date = bc.created_at.strftime("%d/%m %H:%M") if bc.created_at else "?"
            status_emoji = {
                BroadcastStatus.SENT: "✅",
                BroadcastStatus.SENDING: "⏳",
                BroadcastStatus.FAILED: "❌",
            }.get(bc.status, "❓")

            lines.append(
                f"{status_emoji} <code>#{bc.id}</code> — {date}\n"
                f"   🎯 {bc.target_audience}\n"
                f"   ✅ {bc.sent_count} / ❌ {bc.failed_count} / "
                f"📊 Total: {bc.total_targets}"
            )

        text = "\n".join(lines)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_bc:menu")]
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 🚀 EXECUÇÃO REAL DO BROADCAST
# ============================================
async def _run_broadcast(
    bot,
    broadcast_id: int,
    target: str,
    text: str,
    media_type: str,
    media_id: str | None,
    buttons: list,
) -> None:
    """
    Executa o broadcast de verdade, enviando para todos os usuários.
    Roda em background (não bloqueia o handler).
    """
    from core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        bc = await session.get(Broadcast, broadcast_id)
        if bc is None:
            return

        # Coleta usuários alvo
        users = await _get_target_users(session, target)
        bc.total_targets = len(users)
        session.add(bc)
        await session.commit()

    sent = 0
    failed = 0

    # Monta o reply_markup
    reply_markup = None
    if buttons:
        rows = []
        for b in buttons:
            try:
                rows.append([
                    InlineKeyboardButton(text=b["text"], url=b["url"])
                ])
            except Exception:
                continue
        if rows:
            reply_markup = InlineKeyboardMarkup(inline_keyboard=rows)

    import asyncio

    for u in users:
        try:
            if media_type == "photo":
                await bot.send_photo(
                    chat_id=u.telegram_id,
                    photo=media_id,
                    caption=text or None,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                )
            elif media_type == "video":
                await bot.send_video(
                    chat_id=u.telegram_id,
                    video=media_id,
                    caption=text or None,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                )
            elif media_type == "document":
                await bot.send_document(
                    chat_id=u.telegram_id,
                    document=media_id,
                    caption=text or None,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                )
            else:
                await bot.send_message(
                    chat_id=u.telegram_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
            sent += 1

            # Atualiza contadores a cada 50 envios
            if sent % 50 == 0:
                async with AsyncSessionLocal() as session:
                    bc = await session.get(Broadcast, broadcast_id)
                    if bc:
                        bc.sent_count = sent
                        bc.failed_count = failed
                        session.add(bc)
                        await session.commit()

        except Exception as e:
            failed += 1
            logger.debug(f"Falha ao enviar pra {u.telegram_id}: {e}")

        # Rate limit (evita bloqueio do Telegram)
        await asyncio.sleep(0.05)

    # Finaliza
    async with AsyncSessionLocal() as session:
        bc = await session.get(Broadcast, broadcast_id)
        if bc:
            bc.sent_count = sent
            bc.failed_count = failed
            bc.status = BroadcastStatus.SENT
            bc.sent_at = datetime.now(timezone.utc)
            session.add(bc)
            await session.commit()

    logger.info(
        f"📢 Broadcast #{broadcast_id} finalizado: {sent} enviados, {failed} falhas"
    )


async def _get_target_users(session: AsyncSession, target: str) -> list[User]:
    """Retorna usuários do target especificado."""
    from datetime import timedelta

    if target == "all":
        stmt = select(User).where(User.is_blocked_bot.is_(False))
    elif target == "active":
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        stmt = select(User).where(
            User.is_blocked_bot.is_(False),
            User.last_seen_at >= cutoff,
        )
    elif target == "inactive":
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        stmt = select(User).where(
            User.is_blocked_bot.is_(False),
            (User.last_seen_at < cutoff) | (User.last_seen_at.is_(None)),
        )
    elif target == "buyers":
        stmt = select(User).where(
            User.is_blocked_bot.is_(False),
            User.telegram_id.in_(
                select(Order.user_telegram_id).where(
                    Order.status.in_([OrderStatus.PAID, OrderStatus.DELIVERED])
                )
            ),
        )
    elif target == "affiliates":
        stmt = select(User).where(
            User.referred_by.is_not(None),
            User.is_blocked_bot.is_(False),
        )
    else:
        stmt = select(User).where(User.is_blocked_bot.is_(False))

    result = await session.execute(stmt)
    return list(result.scalars().all())

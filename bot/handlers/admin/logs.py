# ============================================
# 📋 ADMIN LOGS — Larizinha Store
# ============================================
# Auditoria REAL: registra TUDO que o admin faz.
# Todos os botões funcionam de verdade.
#
# Cobre:
#   - LISTAR últimos logs
#   - FILTRAR por ação
#   - FILTRAR por admin
#   - VER detalhes (antes/depois)
#   - EXPORTAR em arquivo
#   - LIMPAR logs antigos
# ============================================

from datetime import datetime, timedelta, timezone
from io import BytesIO

from aiogram import F, Router
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Admin, AuditLog


router = Router(name="admin_logs")


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


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_logs:menu")
async def cb_logs_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)

    total = await session.scalar(select(func.count(AuditLog.id))) or 0
    today = await session.scalar(
        select(func.count(AuditLog.id)).where(AuditLog.created_at >= today_start)
    ) or 0
    last_week = await session.scalar(
        select(func.count(AuditLog.id)).where(AuditLog.created_at >= week_ago)
    ) or 0

    text = (
        "📋 <b>AUDITORIA / LOGS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 Total de registros: <b>{total}</b>\n"
        f"📅 Hoje: <b>{today}</b>\n"
        f"📆 Últimos 7 dias: <b>{last_week}</b>\n\n"
        "Todas as ações de admin são registradas aqui.\n\n"
        "Escolha uma opção:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Últimos 50 Logs", callback_data="adm_logs:list:0")],
            [InlineKeyboardButton(text="📅 Filtros de Período", callback_data="adm_logs:filters")],
            [InlineKeyboardButton(text="👮 Filtrar por Admin", callback_data="adm_logs:by_admin")],
            [InlineKeyboardButton(text="🔍 Filtrar por Ação", callback_data="adm_logs:by_action")],
            [InlineKeyboardButton(text="📥 Exportar (TXT)", callback_data="adm_logs:export")],
            [InlineKeyboardButton(text="🗑 Limpar Logs Antigos", callback_data="adm_logs:clean")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:config")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 📋 LISTAR LOGS
# ============================================
@router.callback_query(F.data.startswith("adm_logs:list:"))
async def cb_logs_list(
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

    await _show_logs(callback, session, page=page, filter_type="all")


async def _show_logs(
    callback: CallbackQuery,
    session: AsyncSession,
    page: int = 0,
    filter_type: str = "all",
    filter_value: str | None = None,
) -> None:
    PER_PAGE = 15

    base = select(AuditLog)

    if filter_type == "today":
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        base = base.where(AuditLog.created_at >= today_start)
    elif filter_type == "week":
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        base = base.where(AuditLog.created_at >= cutoff)
    elif filter_type == "month":
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        base = base.where(AuditLog.created_at >= cutoff)
    elif filter_type == "admin" and filter_value:
        try:
            base = base.where(AuditLog.admin_telegram_id == int(filter_value))
        except ValueError:
            pass
    elif filter_type == "action" and filter_value:
        base = base.where(AuditLog.action.ilike(f"%{filter_value}%"))

    total = await session.scalar(
        select(func.count()).select_from(base.subquery())
    ) or 0

    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    stmt = (
        base.order_by(AuditLog.created_at.desc())
        .offset(page * PER_PAGE)
        .limit(PER_PAGE)
    )
    result = await session.execute(stmt)
    logs = list(result.scalars().all())

    filter_labels = {
        "all": "📋 Todos",
        "today": "📅 Hoje",
        "week": "📆 7 dias",
        "month": "📅 30 dias",
        "admin": f"👮 Admin {filter_value}",
        "action": f"🔍 {filter_value}",
    }

    lines = [
        "📋 <b>LOGS DE AUDITORIA</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"Filtro: <b>{filter_labels.get(filter_type, filter_type)}</b>",
        f"Total: <b>{total}</b>",
        "",
    ]

    rows: list[list[InlineKeyboardButton]] = []

    if not logs:
        lines.append("Nenhum log encontrado neste filtro.")
    else:
        for log in logs:
            date = log.created_at.strftime("%d/%m %H:%M") if log.created_at else "?"
            action = log.action[:35]
            admin = log.admin_telegram_id

            lines.append(
                f"🕐 {date} | 👮 <code>{admin}</code>\n"
                f"   🎬 <b>{action}</b>"
            )
            if log.target_id:
                lines.append(f"   🎯 Alvo: <code>{log.target_id}</code>")

            rows.append([
                InlineKeyboardButton(
                    text=f"{date} — {action}",
                    callback_data=f"adm_logs:view:{log.id}",
                )
            ])

    # Navegação
    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                text="⬅️",
                callback_data=f"adm_logs:list:{page - 1}",
            ))
        nav.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="adm:noop",
        ))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(
                text="➡️",
                callback_data=f"adm_logs:list:{page + 1}",
            ))
        rows.append(nav)

    rows.append([
        InlineKeyboardButton(text="📅 Filtros", callback_data="adm_logs:filters")
    ])
    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_logs:menu")
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
# 👁️ VER DETALHE DE UM LOG
# ============================================
@router.callback_query(F.data.startswith("adm_logs:view:"))
async def cb_logs_view(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    log_id = int(callback.data.split(":")[2])
    log = await session.get(AuditLog, log_id)
    if log is None:
        await callback.answer("❌ Log não encontrado.", show_alert=True)
        return

    date = log.created_at.strftime("%d/%m/%Y %H:%M:%S") if log.created_at else "?"

    text = (
        f"📋 <b>LOG #{log.id}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🕐 Data: <b>{date}</b>\n"
        f"👮 Admin: <code>{log.admin_telegram_id}</code>\n"
        f"🎬 Ação: <b>{log.action}</b>\n"
    )

    if log.target_type:
        text += f"🎯 Tipo: <b>{log.target_type}</b>\n"
    if log.target_id:
        text += f"🆔 Alvo: <code>{log.target_id}</code>\n"

    text += "\n"

    if log.old_value:
        text += f"📤 <b>Antes:</b>\n<pre>{_format_dict(log.old_value)}</pre>\n\n"
    if log.new_value:
        text += f"📥 <b>Depois:</b>\n<pre>{_format_dict(log.new_value)}</pre>\n\n"

    if log.ip_or_session:
        text += f"🌐 Sessão: <code>{log.ip_or_session}</code>"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_logs:list:0")]
        ]
    )

    if len(text) > 4000:
        text = text[:4000] + "\n\n<i>... (truncado)</i>"

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


def _format_dict(d: dict) -> str:
    """Formata dict pra exibição."""
    if not d:
        return "—"
    lines = []
    for k, v in d.items():
        v_str = str(v)[:100]
        lines.append(f"• {k}: {v_str}")
    return "\n".join(lines)


# ============================================
# 📅 FILTROS
# ============================================
@router.callback_query(F.data == "adm_logs:filters")
async def cb_logs_filters(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text = (
        "📅 <b>FILTROS DE LOGS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Escolha o período:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 Hoje", callback_data="adm_logs:filter:today")],
            [InlineKeyboardButton(text="📆 Últimos 7 dias", callback_data="adm_logs:filter:week")],
            [InlineKeyboardButton(text="📅 Últimos 30 dias", callback_data="adm_logs:filter:month")],
            [InlineKeyboardButton(text="📋 Todos os logs", callback_data="adm_logs:list:0")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_logs:menu")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


@router.callback_query(F.data.startswith("adm_logs:filter:"))
async def cb_logs_filter_apply(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    filter_type = callback.data.split(":")[2]
    await _show_logs(callback, session, page=0, filter_type=filter_type)


# ============================================
# 👮 FILTRAR POR ADMIN
# ============================================
@router.callback_query(F.data == "adm_logs:by_admin")
async def cb_logs_by_admin(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    # Lista admins com logs
    stmt = (
        select(
            AuditLog.admin_telegram_id,
            func.count(AuditLog.id).label("total"),
        )
        .group_by(AuditLog.admin_telegram_id)
        .order_by(func.count(AuditLog.id).desc())
        .limit(20)
    )
    result = await session.execute(stmt)
    rows_data = list(result.all())

    if not rows_data:
        await callback.answer("Nenhum admin com logs.", show_alert=True)
        return

    lines = [
        "👮 <b>FILTRAR POR ADMIN</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    rows: list[list[InlineKeyboardButton]] = []

    for row in rows_data:
        admin_id = row.admin_telegram_id
        total = row.total

        admin = await session.scalar(
            select(Admin).where(Admin.telegram_id == admin_id)
        )
        name = admin.full_name or admin.username or str(admin_id) if admin else str(admin_id)

        rows.append([
            InlineKeyboardButton(
                text=f"👮 {name} ({total})",
                callback_data=f"adm_logs:show_admin:{admin_id}:0",
            )
        ])
        lines.append(f"• <code>{admin_id}</code> — {name} — <b>{total}</b>")

    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_logs:menu")
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


@router.callback_query(F.data.startswith("adm_logs:show_admin:"))
async def cb_logs_show_admin(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    parts = callback.data.split(":")
    admin_id = parts[2]
    page = int(parts[3]) if len(parts) > 3 else 0

    await _show_logs(
        callback, session,
        page=page,
        filter_type="admin",
        filter_value=admin_id,
    )


# ============================================
# 🔍 FILTRAR POR AÇÃO
# ============================================
@router.callback_query(F.data == "adm_logs:by_action")
async def cb_logs_by_action(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    # Lista ações mais comuns
    stmt = (
        select(
            AuditLog.action,
            func.count(AuditLog.id).label("total"),
        )
        .group_by(AuditLog.action)
        .order_by(func.count(AuditLog.id).desc())
        .limit(25)
    )
    result = await session.execute(stmt)
    rows_data = list(result.all())

    if not rows_data:
        await callback.answer("Nenhuma ação registrada.", show_alert=True)
        return

    lines = [
        "🔍 <b>FILTRAR POR AÇÃO</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    rows: list[list[InlineKeyboardButton]] = []

    for row in rows_data:
        action = row.action
        total = row.total
        rows.append([
            InlineKeyboardButton(
                text=f"{action[:35]} ({total})",
                callback_data=f"adm_logs:show_action:{action}:0",
            )
        ])

    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_logs:menu")
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


@router.callback_query(F.data.startswith("adm_logs:show_action:"))
async def cb_logs_show_action(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    parts = callback.data.split(":")
    action = parts[2]
    page = int(parts[3]) if len(parts) > 3 else 0

    await _show_logs(
        callback, session,
        page=page,
        filter_type="action",
        filter_value=action,
    )


# ============================================
# 📥 EXPORTAR
# ============================================
@router.callback_query(F.data == "adm_logs:export")
async def cb_logs_export(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.answer("📥 Gerando arquivo...", show_alert=False)

    # Últimos 500 logs
    stmt = (
        select(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(500)
    )
    result = await session.execute(stmt)
    logs = list(result.scalars().all())

    lines = [
        "LARIZINHA STORE - RELATÓRIO DE AUDITORIA",
        "=" * 60,
        f"Gerado em: {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M:%S')} UTC",
        f"Total de registros: {len(logs)}",
        "=" * 60,
        "",
    ]

    for log in logs:
        date = log.created_at.strftime("%d/%m/%Y %H:%M:%S") if log.created_at else "?"
        lines.append(f"[{date}]")
        lines.append(f"  ID: {log.id}")
        lines.append(f"  Admin: {log.admin_telegram_id}")
        lines.append(f"  Ação: {log.action}")
        if log.target_type:
            lines.append(f"  Tipo: {log.target_type}")
        if log.target_id:
            lines.append(f"  Alvo: {log.target_id}")
        if log.old_value:
            lines.append(f"  Antes: {log.old_value}")
        if log.new_value:
            lines.append(f"  Depois: {log.new_value}")
        lines.append("")

    content = "\n".join(lines).encode("utf-8")

    file = BufferedInputFile(
        content,
        filename=f"audit_logs_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
    )

    await callback.message.answer_document(
        file,
        caption=(
            f"📥 <b>Logs exportados</b>\n\n"
            f"📊 Total: <b>{len(logs)}</b> registros\n"
            f"📅 Período: últimos 500"
        ),
    )


# ============================================
# 🗑 LIMPAR LOGS ANTIGOS
# ============================================
@router.callback_query(F.data == "adm_logs:clean")
async def cb_logs_clean(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text = (
        "🗑 <b>LIMPAR LOGS ANTIGOS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Escolha o período para deletar logs mais antigos que:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📆 30 dias", callback_data="adm_logs:clean_do:30")],
            [InlineKeyboardButton(text="📆 60 dias", callback_data="adm_logs:clean_do:60")],
            [InlineKeyboardButton(text="📆 90 dias", callback_data="adm_logs:clean_do:90")],
            [InlineKeyboardButton(text="📆 180 dias", callback_data="adm_logs:clean_do:180")],
            [InlineKeyboardButton(text="⚠️ TODOS os logs", callback_data="adm_logs:clean_do:0")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_logs:menu")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


@router.callback_query(F.data.startswith("adm_logs:clean_do:"))
async def cb_logs_clean_do(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    days = int(callback.data.split(":")[2])

    # Confirma
    label = "TODOS os logs" if days == 0 else f"logs com mais de {days} dias"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="✅ SIM, LIMPAR",
                callback_data=f"adm_logs:clean_confirm:{days}",
            )],
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_logs:menu")],
        ]
    )

    await callback.message.edit_text(
        f"⚠️ <b>CONFIRMAR LIMPEZA</b>\n\n"
        f"Vou remover {label}.\n\n"
        f"⚠️ <b>Esta ação não pode ser desfeita.</b>",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_logs:clean_confirm:"))
async def cb_logs_clean_confirm(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    days = int(callback.data.split(":")[2])

    stmt = select(AuditLog)
    if days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = stmt.where(AuditLog.created_at < cutoff)

    result = await session.execute(stmt)
    logs = list(result.scalars().all())

    removed = len(logs)
    for log in logs:
        await session.delete(log)

    await callback.answer(f"🗑 {removed} log(s) removido(s)!", show_alert=True)

    callback.data = "adm_logs:menu"
    await cb_logs_menu(callback, session)

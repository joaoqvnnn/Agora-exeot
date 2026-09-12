# ============================================
# 📲 ADMIN WHATSAPP FLOW — Larizinha Store
# ============================================
# Painel admin específico pra configurar a
# ATIVAÇÃO via WhatsApp (link web seguro).
#
# Complementa o `whatsapp.py` (que cuida da
# conexão Baileys), focando em:
#   - Configuração do link de ativação
#   - Tempo de expiração do link
#   - Tentativas de senha
#   - Bloqueio por brute-force
#   - Estatísticas de ativação
#   - Reenvio manual de links
#   - Teste da página
#   - Auditoria de tentativas
# ============================================

from datetime import datetime, timedelta, timezone
from typing import Any

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
from core.config import settings
from core.models import (
    Admin,
    AuditLog,
    Order,
    OrderStatus,
    User,
)
from core.services import config as config_service
from core.services import wa_client


router = Router(name="admin_whatsapp_flow")


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


def _cancel_keyboard(back_data: str = "adm_waflow:menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancelar", callback_data=back_data)]
        ]
    )


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_waflow:menu")
async def cb_waflow_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    # Configs
    link_days = await config_service.get_int(session, "activation_link_days", 30)
    max_attempts = await config_service.get_int(session, "activation_max_attempts", 5)
    lockout_minutes = await config_service.get_int(
        session, "activation_lockout_minutes", 30
    )
    require_password = await config_service.get_bool(
        session, "wa_flow_require_password", True
    )
    show_link_direct = await config_service.get_bool(
        session, "wa_flow_show_link_direct", True
    )

    # Status WhatsApp
    wa_status = await wa_client.get_status()
    wa_connected = wa_status.get("connected", False)
    wa_phone = wa_status.get("phone_number")

    wa_line = (
        f"🟢 Conectado ({wa_phone})"
        if wa_connected
        else "🔴 Desconectado"
    )

    # Estatísticas (últimos 30 dias)
    stats = await _get_activation_stats(session, days=30)

    text = (
        "📲 <b>ATIVAÇÃO VIA WHATSAPP (FLOW)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔐 <b>Como funciona:</b>\n"
        "Cliente compra → recebe link → clica → digita senha → libera produto\n\n"
        "⚙️ <b>Configurações atuais:</b>\n\n"
        f"📅 Validade do link: <b>{link_days} dias</b>\n"
        f"🔢 Tentativas de senha: <b>{max_attempts}</b>\n"
        f"⏰ Bloqueio após exceder: <b>{lockout_minutes} min</b>\n"
        f"🔐 Exigir senha: <b>{'🟢 SIM' if require_password else '🔴 NÃO'}</b>\n"
        f"🔗 Enviar link direto: <b>{'🟢 SIM' if show_link_direct else '🔴 NÃO'}</b>\n\n"
        "📊 <b>WhatsApp:</b> " + wa_line + "\n\n"
        "📈 <b>Últimos 30 dias:</b>\n"
        f"├ ✅ Ativações: <b>{stats['total']}</b>\n"
        f"├ 🎯 Taxa de sucesso: <b>{stats['success_rate']:.1f}%</b>\n"
        f"└ 🚫 Bloqueios: <b>{stats['lockouts']}</b>\n\n"
        "Escolha uma opção:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"📅 Validade do Link ({link_days} dias)",
                callback_data="adm_waflow:set_link_days",
            )],
            [InlineKeyboardButton(
                text=f"🔢 Tentativas de Senha ({max_attempts})",
                callback_data="adm_waflow:set_max_attempts",
            )],
            [InlineKeyboardButton(
                text=f"⏰ Bloqueio ({lockout_minutes} min)",
                callback_data="adm_waflow:set_lockout",
            )],
            [InlineKeyboardButton(
                text=f"🔐 Exigir Senha: {'🟢 SIM' if require_password else '🔴 NÃO'}",
                callback_data="adm_waflow:toggle_password",
            )],
            [InlineKeyboardButton(
                text=f"🔗 Enviar Link Direto: {'🟢 SIM' if show_link_direct else '🔴 NÃO'}",
                callback_data="adm_waflow:toggle_link_direct",
            )],
            [InlineKeyboardButton(
                text="📊 Ver Estatísticas Detalhadas",
                callback_data="adm_waflow:stats",
            )],
            [InlineKeyboardButton(
                text="🎯 Auditoria de Tentativas",
                callback_data="adm_waflow:audit",
            )],
            [InlineKeyboardButton(
                text="🔄 Reenviar Link por Pedido",
                callback_data="adm_waflow:resend",
            )],
            [InlineKeyboardButton(
                text="👁 Abrir Página de Teste",
                callback_data="adm_waflow:test_page",
            )],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:config")],
        ]
    )

    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )

    await callback.answer()


# ============================================
# 📅 VALIDADE DO LINK
# ============================================
@router.callback_query(F.data == "adm_waflow:set_link_days")
async def cb_waflow_set_link_days(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    current = await config_service.get_str(session, "activation_link_days", "30")

    await callback.message.answer(
        "📅 <b>VALIDADE DO LINK DE ATIVAÇÃO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Atual:</b> {current} dias\n\n"
        "Por quantos dias o link enviado no WhatsApp ficará válido?\n\n"
        "💡 <b>Recomendado:</b> <code>30</code> dias\n\n"
        "• <code>0</code> = sem expiração (não recomendado)\n"
        "• <code>1</code> a <code>365</code> = dias de validade",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(waflow_field="activation_link_days")
    await callback.answer()


# ============================================
# 🔢 TENTATIVAS DE SENHA
# ============================================
@router.callback_query(F.data == "adm_waflow:set_max_attempts")
async def cb_waflow_set_max_attempts(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    current = await config_service.get_str(session, "activation_max_attempts", "5")

    await callback.message.answer(
        "🔢 <b>TENTATIVAS DE SENHA</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Atual:</b> {current}\n\n"
        "Quantas tentativas de senha antes de bloquear o link?\n\n"
        "💡 <b>Recomendado:</b> <code>5</code>\n\n"
        "• <code>3</code> a <code>10</code> = valor ideal\n"
        "• Menos = mais seguro (mas chato pro cliente)\n"
        "• Mais = mais prático (mas arriscado)",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(waflow_field="activation_max_attempts")
    await callback.answer()


# ============================================
# ⏰ DURAÇÃO DO BLOQUEIO
# ============================================
@router.callback_query(F.data == "adm_waflow:set_lockout")
async def cb_waflow_set_lockout(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "⏰ <b>DURAÇÃO DO BLOQUEIO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Por quantos minutos bloquear após exceder o limite?\n\n"
        "💡 <b>Recomendado:</b> <code>30</code> minutos\n\n"
        "• <code>5</code> a <code>60</code> = minutos\n"
        "• <code>1440</code> = 24 horas\n\n"
        "Envie um número (minutos):",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(waflow_field="activation_lockout_minutes")
    await callback.answer()


# ============================================
# 💾 SALVAR VALOR
# ============================================
@router.message(AdminStates.editing_config_value)
async def msg_waflow_save(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    data = await state.get_data()
    field = data.get("waflow_field")

    if not field:
        return  # Deixa outro handler pegar

    raw = (message.text or "").strip()

    if raw.startswith("/cancelar") or raw.startswith("/start"):
        await state.clear()
        await message.answer("❌ Operação cancelada.")
        return

    # Valida
    try:
        value = int(raw)
    except ValueError:
        await message.answer("❌ Envie um número válido.")
        return

    # Valida faixa por campo
    if field == "activation_link_days":
        if not 0 <= value <= 365:
            await message.answer("❌ Use entre 0 e 365.")
            return
    elif field == "activation_max_attempts":
        if not 1 <= value <= 20:
            await message.answer("❌ Use entre 1 e 20.")
            return
    elif field == "activation_lockout_minutes":
        if not 1 <= value <= 1440:
            await message.answer("❌ Use entre 1 e 1440 (24h).")
            return

    # Salva
    old = await config_service.get_str(session, field, "")
    await config_service.set_config(session, field, str(value))

    await _log_audit(
        session,
        message.from_user.id,
        f"edit_waflow_{field}",
        old_value={field: old},
        new_value={field: str(value)},
    )

    label = {
        "activation_link_days": "Validade do Link",
        "activation_max_attempts": "Tentativas de Senha",
        "activation_lockout_minutes": "Bloqueio",
    }.get(field, field)

    await message.answer(f"✅ <b>{label}</b> atualizado: <b>{value}</b>")
    await state.clear()

    # Volta pro menu
    try:
        callback = CallbackQuery(
            id="dummy",
            from_user=message.from_user,
            chat_instance="dummy",
            message=message,
            data="adm_waflow:menu",
        )
        await cb_waflow_menu(callback, session)
    except Exception:
        pass


# ============================================
# 🔐 TOGGLE EXIGIR SENHA
# ============================================
@router.callback_query(F.data == "adm_waflow:toggle_password")
async def cb_waflow_toggle_password(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    current = await config_service.get_bool(
        session, "wa_flow_require_password", True
    )
    new = not current

    await config_service.set_config(
        session, "wa_flow_require_password", "true" if new else "false"
    )

    await _log_audit(
        session,
        callback.from_user.id,
        "toggle_waflow_password",
        new_value={"enabled": new},
    )

    status = "🟢 LIGADO" if new else "🔴 DESLIGADO"
    await callback.answer(f"Exigir senha: {status}", show_alert=True)

    callback.data = "adm_waflow:menu"
    await cb_waflow_menu(callback, session)


# ============================================
# 🔗 TOGGLE ENVIAR LINK DIRETO
# ============================================
@router.callback_query(F.data == "adm_waflow:toggle_link_direct")
async def cb_waflow_toggle_link_direct(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    current = await config_service.get_bool(
        session, "wa_flow_show_link_direct", True
    )
    new = not current

    await config_service.set_config(
        session, "wa_flow_show_link_direct", "true" if new else "false"
    )

    await _log_audit(
        session,
        callback.from_user.id,
        "toggle_waflow_link_direct",
        new_value={"enabled": new},
    )

    status = "🟢 LIGADO" if new else "🔴 DESLIGADO"
    await callback.answer(f"Link direto: {status}", show_alert=True)

    callback.data = "adm_waflow:menu"
    await cb_waflow_menu(callback, session)


# ============================================
# 📊 ESTATÍSTICAS DETALHADAS
# ============================================
@router.callback_query(F.data == "adm_waflow:stats")
async def cb_waflow_stats(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    # Estatísticas por período
    stats_7 = await _get_activation_stats(session, days=7)
    stats_30 = await _get_activation_stats(session, days=30)

    text = (
        "📊 <b>ESTATÍSTICAS DE ATIVAÇÃO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📅 <b>ÚLTIMOS 7 DIAS</b>\n"
        f"├ ✅ Sucessos: <b>{stats_7['success']}</b>\n"
        f"├ ❌ Falhas: <b>{stats_7['failed']}</b>\n"
        f"├ 🔗 Total gerados: <b>{stats_7['total']}</b>\n"
        f"└ 🎯 Taxa: <b>{stats_7['success_rate']:.1f}%</b>\n\n"
        "📆 <b>ÚLTIMOS 30 DIAS</b>\n"
        f"├ ✅ Sucessos: <b>{stats_30['success']}</b>\n"
        f"├ ❌ Falhas: <b>{stats_30['failed']}</b>\n"
        f"├ 🔗 Total gerados: <b>{stats_30['total']}</b>\n"
        f"└ 🎯 Taxa: <b>{stats_30['success_rate']:.1f}%</b>\n\n"
        "💡 <b>O que significa:</b>\n"
        "• <b>Sucessos:</b> cliente ativou o produto\n"
        "• <b>Falhas:</b> errou a senha ou link expirou\n"
        "• <b>Taxa:</b> % de sucesso nas ativações\n\n"
    )

    # Top 5 pedidos mais ativados
    try:
        top_stmt = (
            select(
                AuditLog.target_id,
                func.count(AuditLog.id).label("total"),
            )
            .where(
                AuditLog.action == "wa_activation_success",
                AuditLog.created_at >= datetime.now(timezone.utc) - timedelta(days=30),
            )
            .group_by(AuditLog.target_id)
            .order_by(func.count(AuditLog.id).desc())
            .limit(5)
        )
        top_result = await session.execute(top_stmt)
        top = list(top_result.all())

        if top:
            text += "🏆 <b>Pedidos mais ativados (30d):</b>\n"
            for i, row in enumerate(top, 1):
                order_code = (row.target_id or "?")[:16]
                text += f"{i}º <code>{order_code}</code> — {row.total}x\n"
    except Exception:
        pass

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🔄 Atualizar",
                callback_data="adm_waflow:stats",
            )],
            [InlineKeyboardButton(
                text="🔙 Voltar",
                callback_data="adm_waflow:menu",
            )],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 🎯 AUDITORIA DE TENTATIVAS
# ============================================
@router.callback_query(F.data == "adm_waflow:audit")
async def cb_waflow_audit(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    # Busca últimas tentativas
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    stmt = (
        select(AuditLog)
        .where(
            AuditLog.action.in_([
                "wa_activation_success",
                "wa_activation_failed",
                "wa_activation_locked",
            ]),
            AuditLog.created_at >= cutoff,
        )
        .order_by(AuditLog.created_at.desc())
        .limit(30)
    )
    result = await session.execute(stmt)
    logs = list(result.scalars().all())

    if not logs:
        text = (
            "🎯 <b>AUDITORIA DE TENTATIVAS</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📭 Nenhuma tentativa nos últimos 7 dias."
        )
    else:
        text_lines = [
            "🎯 <b>AUDITORIA DE TENTATIVAS</b>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "📅 Últimos 7 dias",
            "",
        ]

        for log in logs[:20]:
            date = log.created_at.strftime("%d/%m %H:%M") if log.created_at else "?"

            emoji = {
                "wa_activation_success": "✅",
                "wa_activation_failed": "❌",
                "wa_activation_locked": "🚫",
            }.get(log.action, "❓")

            target = (log.target_id or "?")[:12]

            text_lines.append(f"{emoji} {date} — <code>{target}</code>")

            # Extra: motivo se tiver
            if log.new_value and isinstance(log.new_value, dict):
                reason = log.new_value.get("reason")
                if reason:
                    text_lines.append(f"   ↳ {reason[:40]}")

        text = "\n".join(text_lines)

        if len(text) > 4000:
            text = text[:4000] + "\n\n<i>... (truncado)</i>"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🔄 Atualizar",
                callback_data="adm_waflow:audit",
            )],
            [InlineKeyboardButton(
                text="🔙 Voltar",
                callback_data="adm_waflow:menu",
            )],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# 🔄 REENVIAR LINK POR PEDIDO
# ============================================
@router.callback_query(F.data == "adm_waflow:resend")
async def cb_waflow_resend_start(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text = (
        "🔄 <b>REENVIAR LINK POR PEDIDO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Envie o <b>código do pedido</b> (order_code) que deseja reenviar.\n\n"
        "O cliente receberá um novo link de ativação via WhatsApp.\n\n"
        "💡 Você pode encontrar o código no histórico do cliente."
    )

    await callback.message.answer(text, reply_markup=_cancel_keyboard())
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(waflow_action="resend")
    await callback.answer()


@router.message(AdminStates.editing_config_value, F.text.regexp(r"^[a-f0-9\-]{20,}$"))
async def msg_waflow_resend(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """
    Handler específico pra reenvio (detecta UUID de order_code).
    """
    if not await _is_admin(session, message.from_user.id):
        return

    data = await state.get_data()
    if data.get("waflow_action") != "resend":
        return

    order_code = (message.text or "").strip()

    # Busca o pedido
    stmt = select(Order).where(Order.order_code == order_code)
    result = await session.execute(stmt)
    order = result.scalar_one_or_none()

    if order is None:
        await message.answer(
            f"❌ Pedido <code>{order_code[:16]}...</code> não encontrado."
        )
        return

    # Busca o usuário
    user = await session.get(User, order.user_id)
    if user is None or not user.whatsapp:
        await message.answer(
            "❌ Usuário não tem WhatsApp cadastrado. "
            "O cliente precisa cadastrar o número primeiro."
        )
        await state.clear()
        return

    # Verifica WhatsApp conectado
    wa_status = await wa_client.get_status()
    if not wa_status.get("connected"):
        await message.answer(
            "❌ WhatsApp não está conectado. "
            "Acesse o painel do Baileys pra conectar."
        )
        await state.clear()
        return

    # Gera novo token
    try:
        from api.routes.activation import generate_activation_token

        token = generate_activation_token(order.order_code)
        activation_url = (
            f"{settings.base_url.rstrip('/')}/api/wa/activate/{token}"
        )

        message_text = (
            f"🔐 *Link de ativação - {order.product_name}*\n\n"
            f"🎫 Pedido: `{order.order_code[:16]}`\n\n"
            f"Clique no link abaixo pra acessar seu produto:\n\n"
            f"👉 {activation_url}\n\n"
            f"_Você precisará digitar sua senha de saque._"
        )

        send_result = await wa_client.send_message(
            phone=user.whatsapp,
            message=message_text,
        )

        if send_result.get("success"):
            await _log_audit(
                session,
                message.from_user.id,
                "resend_waflow_link",
                new_value={
                    "order_code": order.order_code,
                    "sent_to": user.whatsapp,
                },
            )

            await message.answer(
                f"✅ <b>Link reenviado!</b>\n\n"
                f"📱 Para: <code>{user.whatsapp}</code>\n"
                f"🎫 Pedido: <code>{order.order_code[:16]}...</code>"
            )
        else:
            await message.answer(
                f"❌ <b>Falha ao enviar</b>\n\n"
                f"<code>{send_result.get('error', 'Erro desconhecido')}</code>"
            )

    except Exception as e:
        logger.exception(f"❌ Erro ao reenviar: {e}")
        await message.answer(f"❌ Erro: <code>{str(e)[:150]}</code>")

    await state.clear()


# ============================================
# 👁 ABRIR PÁGINA DE TESTE
# ============================================
@router.callback_query(F.data == "adm_waflow:test_page")
async def cb_waflow_test_page(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    # Pega um pedido de exemplo (o mais recente pago)
    stmt = (
        select(Order)
        .where(Order.status.in_([OrderStatus.PAID, OrderStatus.DELIVERED]))
        .order_by(Order.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    sample_order = result.scalar_one_or_none()

    if sample_order is None:
        await callback.message.answer(
            "❌ Nenhum pedido pago encontrado pra gerar exemplo.\n\n"
            "Faça uma compra de teste primeiro."
        )
        await callback.answer()
        return

    # Gera token de exemplo
    try:
        from api.routes.activation import generate_activation_token

        token = generate_activation_token(sample_order.order_code)
        test_url = f"{settings.base_url.rstrip('/')}/api/wa/activate/{token}"

        text = (
            "👁 <b>PÁGINA DE TESTE</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎫 Pedido: <code>{sample_order.order_code[:16]}...</code>\n"
            f"📦 Produto: <b>{sample_order.product_name}</b>\n\n"
            "Toque no botão abaixo pra abrir a página que o cliente vê:\n\n"
            "💡 <b>Como testar:</b>\n"
            "1. Abra o link\n"
            "2. Veja o design (cores, logo, animações)\n"
            "3. Digite uma senha errada (pra ver o erro)\n"
            "4. Digite a senha correta (pra ver o sucesso)\n\n"
            "⚠️ <b>Atenção:</b> uma ativação bem-sucedida será registrada."
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="👁 Abrir Página",
                    url=test_url,
                )],
                [InlineKeyboardButton(
                    text="🔙 Voltar",
                    callback_data="adm_waflow:menu",
                )],
            ]
        )

        try:
            await callback.message.edit_text(
                text,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
        except Exception:
            await callback.message.answer(
                text,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )

    except Exception as e:
        logger.exception(f"❌ Erro ao gerar link de teste: {e}")
        await callback.message.answer(f"❌ Erro: <code>{str(e)[:150]}</code>")

    await callback.answer()


# ============================================
# 📊 FUNÇÃO AUXILIAR: ESTATÍSTICAS
# ============================================
async def _get_activation_stats(
    session: AsyncSession,
    days: int = 30,
) -> dict[str, Any]:
    """
    Retorna estatísticas de ativação via WhatsApp.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Conta sucessos
    success = await session.scalar(
        select(func.count(AuditLog.id)).where(
            AuditLog.action == "wa_activation_success",
            AuditLog.created_at >= cutoff,
        )
    ) or 0

    # Conta falhas
    failed = await session.scalar(
        select(func.count(AuditLog.id)).where(
            AuditLog.action == "wa_activation_failed",
            AuditLog.created_at >= cutoff,
        )
    ) or 0

    # Conta bloqueios
    lockouts = await session.scalar(
        select(func.count(AuditLog.id)).where(
            AuditLog.action == "wa_activation_locked",
            AuditLog.created_at >= cutoff,
        )
    ) or 0

    total = success + failed
    success_rate = (success / total * 100) if total > 0 else 0.0

    return {
        "success": success,
        "failed": failed,
        "total": total,
        "success_rate": success_rate,
        "lockouts": lockouts,
    }

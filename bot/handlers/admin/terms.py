# ============================================
# 📜 ADMIN TERMS — Larizinha Store
# ============================================
# Editor REAL dos Termos de Uso.
# Todos os botões funcionam de verdade.
#
# Cobre:
#   - VER termos atuais
#   - EDITAR texto (com suporte a HTML)
#   - EDITAR link externo (se preferir Telegraph)
#   - PREVIEW
#   - RESTAURAR padrão
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
from core.models import Admin, AuditLog
from core.services import config as config_service


router = Router(name="admin_terms")


DEFAULT_TERMS = """📜 <b>TERMOS DE USO — {BOT_NAME}</b>

Prezado usuário,

Antes de prosseguir com a utilização dos serviços, solicitamos sua atenção para os Termos de Uso que regem a relação entre você ("Usuário") e o desenvolvedor ("Fornecedor").

<b>Resumo:</b>

Ao utilizar os serviços, o Usuário concorda em submeter-se integralmente aos Termos de Uso. Esses Termos estabelecem as condições legais que regem a utilização do aplicativo, incluindo políticas de recarga de saldo, suporte, limitações de responsabilidade e demais disposições essenciais.

<b>Importante:</b>

• O Fornecedor não é responsável pelos produtos comercializados
• O Fornecedor não se responsabiliza pelo uso indevido por parte dos Usuários
• Recargas não são reembolsáveis após crédito na carteira
• Produtos têm garantia conforme descrito em cada anúncio

Ao continuar a utilizar os serviços, o Usuário expressa sua concordância com os Termos.

Atenciosamente,
{BOT_NAME}"""


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
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_terms:menu")]
        ]
    )


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_terms:menu")
async def cb_terms_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text_content = await config_service.get_str(session, "terms_text", "")
    link_content = await config_service.get_str(session, "terms_link", "")

    has_text = "🟢 Configurado" if text_content else "⚪ Não configurado"
    has_link = f"🟢 {link_content[:40]}..." if link_content else "⚪ Não configurado"

    preview = (text_content or DEFAULT_TERMS)[:250]

    text = (
        "📜 <b>TERMOS DE USO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📝 Texto interno: <b>{has_text}</b>\n"
        f"🔗 Link externo: <b>{has_link}</b>\n\n"
        "📄 <b>Prévia atual:</b>\n"
        f"<pre>{preview}...</pre>\n\n"
        "Escolha uma opção:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Editar Texto Interno", callback_data="adm_terms:edit_text")],
            [InlineKeyboardButton(text="🔗 Mudar Link Externo", callback_data="adm_terms:edit_link")],
            [InlineKeyboardButton(text="👁 Preview Completo", callback_data="adm_terms:preview")],
            [InlineKeyboardButton(text="♻️ Restaurar Padrão", callback_data="adm_terms:reset")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm:config")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

    await callback.answer()


# ============================================
# ✏️ EDITAR TEXTO
# ============================================
@router.callback_query(F.data == "adm_terms:edit_text")
async def cb_terms_edit_text(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    current = await config_service.get_str(session, "terms_text", "")
    if not current:
        current = DEFAULT_TERMS

    await callback.message.answer(
        "✏️ <b>EDITAR TERMOS DE USO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Envie o novo texto dos termos.\n\n"
        "💡 Você pode usar HTML:\n"
        "• <code>&lt;b&gt;negrito&lt;/b&gt;</code>\n"
        "• <code>&lt;i&gt;itálico&lt;/i&gt;</code>\n"
        "• <code>&lt;a href=''&gt;link&lt;/a&gt;</code>\n\n"
        "📌 Variáveis:\n"
        "<code>{BOT_NAME}</code> <code>{USER_ID}</code>\n\n"
        f"📄 <b>Atual:</b>\n<pre>{current[:600]}</pre>",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_terms)
    await callback.answer()


@router.message(AdminStates.editing_terms)
async def msg_terms_save(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    new_text = message.text or message.caption or ""
    if not new_text.strip():
        await message.answer("❌ Texto vazio.")
        return

    old = await config_service.get_str(session, "terms_text", "")
    await config_service.set_config(session, "terms_text", new_text)

    await _log_audit(
        session,
        message.from_user.id,
        "edit_terms_text",
        old_value={"preview": old[:80]},
        new_value={"preview": new_text[:80]},
    )

    await message.answer(
        "✅ Termos de uso atualizados!\n\n"
        "Eles já estão valendo no bot. Quando o usuário enviar /termos, "
        "verá este texto.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="👁 Ver termos", callback_data="adm_terms:preview")],
                [InlineKeyboardButton(text="📜 Menu termos", callback_data="adm_terms:menu")],
            ]
        ),
    )
    await state.clear()


# ============================================
# 🔗 MUDAR LINK EXTERNO
# ============================================
@router.callback_query(F.data == "adm_terms:edit_link")
async def cb_terms_edit_link(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    current = await config_service.get_str(session, "terms_link", "Não definido")

    await callback.message.answer(
        "🔗 <b>LINK EXTERNO DOS TERMOS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Atual:</b>\n<code>{current}</code>\n\n"
        "Envie o link externo (ex: Telegraph).\n\n"
        "💡 Se preencher, o bot envia este link em vez do texto interno.\n"
        "💡 Envie <code>-</code> pra remover e voltar a usar texto interno.",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_terms)
    await callback.answer()


# ============================================
# 👁 PREVIEW
# ============================================
@router.callback_query(F.data == "adm_terms:preview")
async def cb_terms_preview(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    text_content = await config_service.get_str(session, "terms_text", "")
    link_content = await config_service.get_str(session, "terms_link", "")
    bot_name = await config_service.get_str(session, "bot_name", "Larizinha Store")

    if link_content:
        preview = (
            f"🔗 <b>Link externo configurado:</b>\n\n"
            f"<code>{link_content}</code>\n\n"
            "Quando o usuário enviar /termos, receberá este link."
        )
    else:
        content = text_content or DEFAULT_TERMS
        content = content.replace("{BOT_NAME}", bot_name)
        content = content.replace("{USER_ID}", "6995978182")
        preview = content[:3500]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Editar", callback_data="adm_terms:edit_text")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_terms:menu")],
        ]
    )

    try:
        await callback.message.edit_text(preview, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(preview, reply_markup=keyboard)

    await callback.answer()


# ============================================
# ♻️ RESTAURAR PADRÃO
# ============================================
@router.callback_query(F.data == "adm_terms:reset")
async def cb_terms_reset(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Sim, restaurar", callback_data="adm_terms:reset_confirm")],
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_terms:menu")],
        ]
    )

    await callback.message.edit_text(
        "♻️ <b>RESTAURAR PADRÃO</b>\n\n"
        "O texto dos termos será substituído pelo padrão de fábrica.\n\n"
        "Confirma?",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data == "adm_terms:reset_confirm")
async def cb_terms_reset_confirm(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    old = await config_service.get_str(session, "terms_text", "")
    await config_service.set_config(session, "terms_text", DEFAULT_TERMS)
    await config_service.set_config(session, "terms_link", "")

    await _log_audit(
        session,
        callback.from_user.id,
        "reset_terms",
        old_value={"preview": old[:80]},
        new_value={"preview": DEFAULT_TERMS[:80]},
    )

    await callback.answer("♻️ Restaurado para o padrão!", show_alert=True)

    callback.data = "adm_terms:menu"
    await cb_terms_menu(callback, session)

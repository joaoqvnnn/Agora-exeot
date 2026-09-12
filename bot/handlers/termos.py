# ============================================
# 📜 TERMOS DE USO (CLIENTE) — Larizinha Store
# ============================================
# Exibe os Termos de Uso para o cliente.
# Texto e link vêm do painel admin (banco).
# ============================================

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import User
from core.services import config as config_service


router = Router(name="termos")


# ============================================
# 🧰 AUXILIARES
# ============================================
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


async def _edit_or_send(callback: CallbackQuery, text: str, keyboard) -> None:
    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
    except Exception:
        try:
            await callback.message.answer(
                text,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
        except Exception as e:
            logger.warning(f"⚠️ Falha ao exibir termos: {e}")


# ============================================
# 📜 COMANDO /termos
# ============================================
@router.message(Command("termos"))
async def cmd_termos(
    message: Message,
    user: User,
    session: AsyncSession,
) -> None:
    await _show_terms(message, session)


# ============================================
# 🔘 BOTÃO "Termos" (callback)
# ============================================
@router.callback_query(F.data == "terms:view")
async def cb_terms_view(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    await _show_terms(callback, session)
    await callback.answer()


# ============================================
# 📜 EXIBIR TERMOS
# ============================================
async def _show_terms(
    target: Message | CallbackQuery,
    session: AsyncSession,
) -> None:
    """Exibe os termos configurados pelo admin."""
    terms_text = await config_service.get_str(session, "terms_text", "")
    terms_link = await config_service.get_str(session, "terms_link", "")
    bot_name = await config_service.get_str(session, "bot_name", "Larizinha Store")

    # Prepara botões
    rows: list[list[InlineKeyboardButton]] = []

    if terms_link and terms_link.startswith(("http://", "https://", "tg://")):
        rows.append([
            InlineKeyboardButton(
                text="🔗 Acessar termos completos",
                url=terms_link,
            )
        ])

    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="menu:voltar")
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

    # Se tem link externo E não tem texto, mostra só o link
    if terms_link and not terms_text:
        text = (
            f"📜 <b>Termos de Uso</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Os termos de uso estão disponíveis no link abaixo.\n\n"
            f"🔗 <b>Acesse:</b>\n<code>{terms_link}</code>"
        )
        await _send_or_edit(target, text, keyboard)
        return

    # Se tem texto (ou padrão), mostra
    if not terms_text:
        terms_text = DEFAULT_TERMS

    # Substitui variáveis
    terms_text = terms_text.replace("{BOT_NAME}", bot_name)

    # Telegram tem limite de 4096 chars
    if len(terms_text) > 4000:
        # Se o texto é longo, sugere link
        if terms_link:
            text = (
                f"📜 <b>Termos de Uso</b>\n\n"
                f"O texto completo está disponível em:\n\n"
                f"🔗 <code>{terms_link}</code>"
            )
            await _send_or_edit(target, text, keyboard)
            return
        else:
            terms_text = terms_text[:4000] + "\n\n<i>... (truncado)</i>"

    await _send_or_edit(target, terms_text, keyboard)


async def _send_or_edit(
    target: Message | CallbackQuery,
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> None:
    """Envia como mensagem nova (não edita se for comando)."""
    if isinstance(target, CallbackQuery):
        await _edit_or_send(target, text, keyboard)
    else:
        # É Message (comando /termos) — envia nova
        try:
            await target.answer(
                text,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
        except Exception as e:
            logger.warning(f"⚠️ Falha ao enviar termos: {e}")


# ============================================
# 🔘 NOOP
# ============================================
@router.callback_query(F.data == "terms:noop")
async def cb_terms_noop(callback: CallbackQuery) -> None:
    await callback.answer()

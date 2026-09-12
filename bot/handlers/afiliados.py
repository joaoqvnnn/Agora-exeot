# ============================================
# 🤝 AFILIADOS (CLIENTE) — Larizinha Store
# ============================================
# Programa de afiliados + saques + cadastro de senha/banco/e-mail.
# Mensagem única (edita, não acumula).
#
# ✨ ATUALIZADO:
#   - Usa `email_verification` (persistente no banco)
#   - Códigos sobrevivem a restart
#   - Cooldown de 60s entre reenvios
#   - Recuperação de senha completa (nova senha)
#   - Auditoria de ações
# ============================================

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

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

from bot.keyboards.afiliados import (
    build_affiliate_keyboard,
    build_bank_data_keyboard,
    build_bank_withdrawal_confirm_keyboard,
    build_email_register_keyboard,
    build_password_keyboard,
    build_password_recovery_keyboard,
    build_pix_type_keyboard,
    build_withdrawal_confirm_keyboard,
    build_withdrawal_final_keyboard,
    build_withdrawal_history_keyboard,
    build_withdrawal_method_keyboard,
)
from bot.states.states import AffiliateStates, WithdrawalStates
from core.models import (
    AffiliateCommission,
    BankAccount,
    User,
    VerificationCodeType,
    Withdrawal,
    WithdrawalMethod,
    WithdrawalStatus,
)
from core.services import config as config_service
from core.services import email_verification
from core.services import withdrawal as withdrawal_service


router = Router(name="afiliados")


# ============================================
# 🧰 AUXILIARES
# ============================================
def _format_brl(v) -> str:
    if v is None:
        return "0,00"
    return f"{float(v):.2f}".replace(".", ",")


def _format_date(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%d/%m/%Y %H:%M")


async def _edit_or_send(callback: CallbackQuery, text: str, keyboard) -> None:
    try:
        await callback.message.edit_text(
            text, reply_markup=keyboard, disable_web_page_preview=True
        )
    except Exception:
        try:
            await callback.message.answer(
                text, reply_markup=keyboard, disable_web_page_preview=True
            )
        except Exception as e:
            logger.warning(f"⚠️ Falha ao exibir: {e}")


def _get_bot_username() -> str:
    from core.config import settings
    return settings.telegram_bot_username or "meu_bot"


def _mask_email(email: str) -> str:
    """Mascara e-mail parcialmente."""
    try:
        local, domain = email.split("@", 1)
        if len(local) <= 2:
            local_m = local[0] + "*"
        else:
            local_m = local[0] + "*" * (len(local) - 2) + local[-1]
        return f"{local_m}@{domain}"
    except Exception:
        return email


# ============================================
# 🏠 MENU PRINCIPAL DE AFILIADOS
# ============================================
@router.callback_query(F.data == "menu:afiliados")
async def cb_affiliate_menu(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    enabled = await config_service.get_bool(session, "affiliate_enabled", True)

    if not enabled:
        await callback.answer(
            "⚠️ O programa de afiliados está temporariamente desativado.",
            show_alert=True,
        )
        return

    await _show_affiliate_menu(callback, user, session)
    await callback.answer()


async def _show_affiliate_menu(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    # Configs
    commission = await config_service.get_str(session, "affiliate_commission", "20.0")
    min_withdrawal = await config_service.get_str(
        session, "affiliate_min_withdrawal", "20.00"
    )

    # Indicações
    referrals = await session.scalar(
        select(func.count(User.id)).where(User.referred_by == user.telegram_id)
    ) or 0

    # Comissões recebidas
    total_earned = await session.scalar(
        select(func.coalesce(func.sum(AffiliateCommission.commission), 0)).where(
            AffiliateCommission.affiliate_telegram_id == user.telegram_id
        )
    ) or Decimal("0.00")

    # Média
    media = (
        (total_earned / referrals).quantize(Decimal("0.01"))
        if referrals > 0
        else Decimal("0.00")
    )

    # Nível
    if referrals < 5:
        level = "🌱 Iniciante"
        next_goal = f"5 ({5 - referrals} restantes)"
    elif referrals < 20:
        level = "🌿 Bronze"
        next_goal = f"20 ({20 - referrals} restantes)"
    elif referrals < 50:
        level = "🌳 Prata"
        next_goal = f"50 ({50 - referrals} restantes)"
    elif referrals < 100:
        level = "💎 Ouro"
        next_goal = f"100 ({100 - referrals} restantes)"
    else:
        level = "👑 Diamante"
        next_goal = "Meta máxima atingida!"

    # Link de afiliado real
    bot_username = _get_bot_username()
    referral_link = f"https://t.me/{bot_username}?start={user.telegram_id}"

    # Status do e-mail
    email_status = (
        f"📧 {_mask_email(user.email)}"
        if user.email and user.email_verified
        else "📧 Não cadastrado"
    )

    # Status da senha
    password_status = (
        "🔐 Cadastrada"
        if user.withdrawal_password_hash
        else "🔓 Não cadastrada"
    )

    text = (
        f"💰 <b>PROGRAMA DE AFILIADOS</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚙️ Status: <b>🟢 Ativo</b>\n"
        f"🧲 Sua comissão: <b>{commission}%</b> (de todas recargas do indicado)\n\n"
        f"👥 Indicações: <b>{referrals}</b>\n"
        f"🪙 Total ganho: <b>R$ {_format_brl(total_earned)}</b>\n"
        f"📊 Média: <b>R$ {_format_brl(media)}</b>\n"
        f"💰 Saque mínimo: <b>R$ {min_withdrawal}</b>\n\n"
        f"🔥 Saldo de comissões: <b>R$ {_format_brl(user.affiliate_balance)}</b>\n\n"
        f"🌱| Nível: <b>{level}</b>\n"
        f"🎯 Próxima meta: {next_goal}\n\n"
        f"🔐 <b>Segurança:</b>\n"
        f"├ {password_status}\n"
        f"└ {email_status}\n\n"
        f"ℹ️ <b>INFO:</b> Seus indicados continuarão gerando comissão para sempre.\n"
        f"A comissão pode ser alterada a qualquer momento, fique atento aos avisos.\n"
        f"🔗 Seu link:\n<code>{referral_link}</code>"
    )

    keyboard = build_affiliate_keyboard(
        has_password=bool(user.withdrawal_password_hash),
        has_email=bool(user.email and user.email_verified),
    )

    await _edit_or_send(callback, text, keyboard)

    user.last_menu = "afiliados"
    session.add(user)


# ============================================
# 🔙 VOLTAR
# ============================================
@router.callback_query(F.data == "aff:voltar")
async def cb_aff_back(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    await cb_affiliate_menu(callback, user, session)


# ============================================
# 📊 HISTÓRICO DE SAQUES
# ============================================
@router.callback_query(F.data.startswith("aff:historico"))
async def cb_withdrawal_history(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    parts = callback.data.split(":")
    page = 0
    if len(parts) > 2 and parts[2].isdigit():
        page = int(parts[2])

    # Busca saques
    stmt = (
        select(Withdrawal)
        .where(Withdrawal.user_id == user.id)
        .order_by(Withdrawal.created_at.desc())
        .limit(30)
    )
    result = await session.execute(stmt)
    withdrawals = list(result.scalars().all())

    min_withdrawal = await config_service.get_str(
        session, "affiliate_min_withdrawal", "20.00"
    )

    if not withdrawals:
        text = (
            f"📊 <b>HISTÓRICO DE SAQUES</b>\n\n"
            f"Você ainda não solicitou nenhum saque.\n\n"
            f"📉 Saque mínimo atual: <b>R$ {min_withdrawal}</b>"
        )
    else:
        lines = [
            f"📊 <b>HISTÓRICO DE SAQUES</b>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "",
        ]

        for w in withdrawals[:10]:
            date = _format_date(w.created_at)
            emoji = {
                WithdrawalStatus.PENDING: "⏳",
                WithdrawalStatus.PROCESSING: "🔄",
                WithdrawalStatus.PAID: "✅",
                WithdrawalStatus.REJECTED: "❌",
                WithdrawalStatus.REFUNDED: "↩️",
                WithdrawalStatus.CANCELLED: "🚫",
            }.get(w.status, "❓")

            lines.append(
                f"{emoji} R$ {_format_brl(w.amount)} — "
                f"{w.method.value.upper()} — {date}"
            )

        text = "\n".join(lines)

    keyboard = build_withdrawal_history_keyboard()

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()


# ============================================
# 💸 SOLICITAR SAQUE
# ============================================
@router.callback_query(F.data == "aff:saque")
async def cb_withdrawal_start(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    min_withdrawal = await config_service.get_decimal(
        session, "affiliate_min_withdrawal", "20.00"
    )

    balance = user.affiliate_balance or Decimal("0.00")

    if balance < min_withdrawal:
        await callback.answer(
            f"❌ Saldo insuficiente.\n"
            f"Você tem R$ {_format_brl(balance)} e o mínimo é R$ {_format_brl(min_withdrawal)}.",
            show_alert=True,
        )
        return

    # Verifica se tem senha cadastrada
    if not user.withdrawal_password_hash:
        text = (
            f"🔐 <b>Você ainda não cadastrou uma senha de saque.</b>\n\n"
            f"Para sua segurança, é necessário cadastrar uma senha antes de "
            f"solicitar o primeiro saque."
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="🔐 Cadastrar Senha",
                    callback_data="aff:cadastrar_senha",
                )],
                [InlineKeyboardButton(text="🔙 Voltar", callback_data="aff:voltar")],
            ]
        )
        await _edit_or_send(callback, text, keyboard)
        await callback.answer()
        return

    text = (
        f"💸 <b>SOLICITAR SAQUE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 Saldo disponível: <b>R$ {_format_brl(balance)}</b>\n"
        f"📉 Mínimo: <b>R$ {_format_brl(min_withdrawal)}</b>\n\n"
        f"Escolha o método:"
    )

    keyboard = build_withdrawal_method_keyboard()

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()


# ============================================
# 🔐 CADASTRAR SENHA DE SAQUE
# ============================================
@router.callback_query(F.data.in_(["aff:cadastrar_senha", "aff:alterar_senha"]))
async def cb_register_password(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    has_password = bool(user.withdrawal_password_hash)
    action = "alterar" if has_password else "cadastrar"

    text = (
        f"🔐 <b>{action.upper()} SENHA DE SAQUE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Envie uma senha de 4 a 8 dígitos (apenas números).\n\n"
        f"⚠️ <b>Esta senha será solicitada em todos os saques.</b>\n"
        f"Guarde bem, pois não pode ser recuperada sem o e-mail.\n\n"
        f"Exemplo: <code>1234</code>"
    )

    keyboard = build_password_keyboard()

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()

    await state.set_state(AffiliateStates.registering_password)


@router.message(AffiliateStates.registering_password)
async def msg_save_password(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    raw = (message.text or "").strip()

    if raw.startswith("/cancelar") or raw.startswith("/start"):
        await state.clear()
        await message.answer("❌ Operação cancelada.")
        return

    if not raw.isdigit() or not (4 <= len(raw) <= 8):
        await message.answer(
            "❌ Senha inválida.\n\n"
            "Use de 4 a 8 dígitos numéricos.\n"
            "Exemplo: <code>1234</code>"
        )
        return

    # Hasheia
    try:
        from passlib.hash import bcrypt
        hashed = bcrypt.hash(raw)
    except Exception as e:
        logger.exception(f"❌ Erro ao hashear senha: {e}")
        await message.answer("❌ Erro ao salvar senha. Tente novamente.")
        return

    user.withdrawal_password_hash = hashed
    session.add(user)

    await state.clear()

    # Tenta deletar a mensagem com a senha (por segurança)
    try:
        await message.delete()
    except Exception:
        pass

    await message.answer(
        "✅ <b>Senha de saque cadastrada com sucesso!</b>\n\n"
        "Sua senha está segura (armazenada com criptografia)."
    )


# ============================================
# 📧 CADASTRAR E-MAIL (persistente)
# ============================================
@router.callback_query(F.data.in_(["aff:cadastrar_email", "aff:alterar_email"]))
async def cb_register_email(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    text = (
        f"📧 <b>CADASTRAR E-MAIL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"O e-mail é usado para recuperar sua senha de saque "
        f"caso você esqueça.\n\n"
        f"Envie seu e-mail:\n"
        f"Exemplo: <code>seuemail@gmail.com</code>"
    )

    keyboard = build_email_register_keyboard()

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()

    await state.set_state(AffiliateStates.registering_email)


@router.message(AffiliateStates.registering_email)
async def msg_save_recovery_email(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    raw = (message.text or "").strip().lower()

    if raw.startswith("/cancelar") or raw.startswith("/start"):
        await state.clear()
        await message.answer("❌ Operação cancelada.")
        return

    if not re.match(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", raw):
        await message.answer(
            "❌ E-mail inválido.\n"
            "Exemplo: <code>seuemail@gmail.com</code>"
        )
        return

    # Envia código (persistente no banco)
    result = await email_verification.send_email_verification(
        session=session,
        user=user,
        new_email=raw,
    )

    if not result.get("success"):
        error = result.get("error", "Erro desconhecido")
        cooldown = result.get("cooldown_seconds")

        if cooldown:
            await message.answer(
                f"⏰ <b>Aguarde {cooldown}s</b> antes de solicitar outro código."
            )
        else:
            await message.answer(
                f"❌ <b>Erro ao enviar o e-mail.</b>\n\n"
                f"<code>{error}</code>"
            )
        return

    # Salva no state
    await state.update_data(recovery_email=raw)

    expiration = result.get("expiration_minutes", 15)

    await message.answer(
        f"📩 <b>Enviamos um código para seu e-mail.</b>\n\n"
        f"📧 E-mail: <b>{_mask_email(raw)}</b>\n\n"
        f"Digite o <b>código de 6 dígitos</b> que você recebeu:\n\n"
        f"<i>O código expira em {expiration} minutos.</i>"
    )

    await state.set_state(AffiliateStates.waiting_recovery_code)


@router.message(AffiliateStates.waiting_recovery_code)
async def msg_verify_recovery_code(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    raw = (message.text or "").strip()

    if raw.startswith("/cancelar") or raw.startswith("/start"):
        await state.clear()
        await message.answer("❌ Operação cancelada.")
        return

    # Extrai só dígitos
    code_typed = "".join(c for c in raw if c.isdigit())

    if len(code_typed) != 6:
        await message.answer(
            "❌ <b>Código inválido.</b>\n"
            "Envie os 6 dígitos recebidos no e-mail."
        )
        return

    data = await state.get_data()
    email = data.get("recovery_email")

    if not email:
        await message.answer("❌ Sessão expirada.")
        await state.clear()
        return

    # Valida (persistente)
    result = await email_verification.verify_email_change(
        session=session,
        user=user,
        email=email,
        code=code_typed,
    )

    if not result.get("success"):
        error = result.get("error", "Código incorreto")
        attempts = result.get("attempts_remaining")
        locked = result.get("locked")
        expired = result.get("expired")

        if locked:
            await message.answer(f"🚫 {error}")
            await state.clear()
            return

        if expired:
            await message.answer(
                f"⏰ {error}\n\nEnvie /start e refaça o processo."
            )
            await state.clear()
            return

        extra = ""
        if attempts is not None:
            extra = f"\n\nTentativas restantes: <b>{attempts}</b>"

        await message.answer(f"❌ {error}{extra}")
        return

    # ✓ Sucesso
    await state.clear()

    await message.answer(
        f"✅ <b>E-mail cadastrado com sucesso!</b>\n\n"
        f"📧 <code>{email}</code>\n\n"
        f"💡 Agora você pode recuperar sua senha de saque "
        f"caso esqueça."
    )


# ============================================
# 💠 SAQUE POR PIX — ESCOLHER TIPO DE CHAVE
# ============================================
@router.callback_query(F.data == "wd:pix:")
async def cb_withdraw_pix(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    text = (
        f"💠 <b>SAQUE POR PIX</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Escolha o tipo da sua chave Pix:"
    )

    keyboard = build_pix_type_keyboard()

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()

    await state.set_state(WithdrawalStates.choosing_pix_type)


@router.callback_query(F.data.startswith("wd:pix_"))
async def cb_choose_pix_type(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    raw = callback.data.split(":")[1]
    pix_type = raw.replace("pix_", "")

    await state.update_data(pix_type=pix_type)

    examples = {
        "cpf": "12345678900",
        "cnpj": "12345678000100",
        "email": "seuemail@gmail.com",
        "phone": "11999998888",
        "random": "chave-aleatoria-com-32-caracteres",
    }

    labels = {
        "cpf": "🆔 CPF",
        "cnpj": "🏢 CNPJ",
        "email": "📧 E-mail",
        "phone": "📱 Telefone",
        "random": "🎲 Chave Aleatória",
    }

    text = (
        f"💠 <b>CHAVE PIX</b>\n\n"
        f"Tipo: <b>{labels.get(pix_type, pix_type)}</b>\n\n"
        f"Envie sua chave Pix.\n\n"
        f"Exemplo: <code>{examples.get(pix_type, 'chave')}</code>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="wd:cancelar")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="aff:saque")],
        ]
    )

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()

    await state.set_state(WithdrawalStates.waiting_pix_key)


@router.message(WithdrawalStates.waiting_pix_key)
async def msg_save_pix_key(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    raw = (message.text or "").strip()

    if raw.startswith("/cancelar") or raw.startswith("/start"):
        await state.clear()
        await message.answer("❌ Operação cancelada.")
        return

    data = await state.get_data()
    pix_type = data.get("pix_type")

    if not pix_type:
        await message.answer("❌ Sessão expirada.")
        await state.clear()
        return

    # Valida
    if not withdrawal_service.is_valid_pix_key(raw, pix_type):
        await message.answer(
            "❌ Chave inválida para o tipo escolhido.\n"
            "Tente novamente ou /cancelar."
        )
        return

    await state.update_data(pix_key=raw)

    balance = user.affiliate_balance or Decimal("0.00")

    label = withdrawal_service.get_pix_type_label(pix_type)

    text = (
        f"💠 <b>CONFIRME SUA CHAVE PIX</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Tipo: <b>{label}</b>\n"
        f"Chave: <code>{raw}</code>\n"
        f"Valor do saque: <b>R$ {_format_brl(balance)}</b>\n\n"
        f"Confirma o saque?"
    )

    keyboard = build_withdrawal_confirm_keyboard(
        has_password=bool(user.withdrawal_password_hash)
    )

    await message.answer(text, reply_markup=keyboard)
    await state.set_state(WithdrawalStates.confirming_withdrawal)


# ============================================
# ✏️ EDITAR CHAVE PIX
# ============================================
@router.callback_query(F.data == "wd:editar_chave")
async def cb_edit_pix_key(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    await callback.answer()
    callback.data = "wd:pix:"
    await cb_withdraw_pix(callback, state, user, session)


# ============================================
# ✅ CONFIRMAR SAQUE
# ============================================
@router.callback_query(F.data == "wd:confirmar")
async def cb_confirm_withdrawal(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    if not user.withdrawal_password_hash:
        await callback.answer(
            "🔐 Cadastre uma senha de saque primeiro.",
            show_alert=True,
        )
        return

    text = (
        f"🔐 <b>CONFIRMAÇÃO DE SEGURANÇA</b>\n\n"
        f"Digite sua <b>senha de saque</b> para confirmar:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="wd:cancelar")],
            [InlineKeyboardButton(
                text="🔑 Esqueci a senha",
                callback_data="aff:recuperar_senha",
            )],
        ]
    )

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()

    await state.set_state(WithdrawalStates.waiting_password)


@router.message(WithdrawalStates.waiting_password)
async def msg_verify_withdrawal_password(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    raw = (message.text or "").strip()

    if raw.startswith("/cancelar") or raw.startswith("/start"):
        await state.clear()
        await message.answer("❌ Operação cancelada.")
        return

    # Verifica senha
    try:
        from passlib.hash import bcrypt
        valid = bcrypt.verify(raw, user.withdrawal_password_hash or "")
    except Exception:
        valid = False

    if not valid:
        await message.answer("❌ Senha incorreta. Tente novamente.")
        return

    data = await state.get_data()
    pix_key = data.get("pix_key")
    pix_type = data.get("pix_type")

    if not pix_key or not pix_type:
        await message.answer("❌ Sessão expirada.")
        await state.clear()
        return

    balance = user.affiliate_balance or Decimal("0.00")
    min_withdrawal = await config_service.get_decimal(
        session, "affiliate_min_withdrawal", "20.00"
    )

    if balance < min_withdrawal:
        await message.answer(
            f"❌ Saldo insuficiente (mínimo R$ {_format_brl(min_withdrawal)})."
        )
        await state.clear()
        return

    # Cria solicitação de saque
    withdrawal = await withdrawal_service.create_withdrawal_request(
        session=session,
        user=user,
        amount=balance,
        method=WithdrawalMethod.PIX,
        pix_key=pix_key,
        pix_key_type=pix_type,
    )

    # Debita saldo do afiliado imediatamente
    user.affiliate_balance = Decimal("0.00")
    session.add(user)

    await state.clear()

    # Tenta deletar a mensagem com a senha
    try:
        await message.delete()
    except Exception:
        pass

    await message.answer(
        f"✅ <b>Solicitação de saque enviada!</b>\n\n"
        f"💰 Valor: <b>R$ {_format_brl(balance)}</b>\n"
        f"💠 Chave: <code>{pix_key}</code>\n"
        f"🆔 ID: <code>#{withdrawal.id}</code>\n\n"
        f"⏳ Seu saque está pendente de aprovação.\n"
        f"Você será notificado quando for processado."
    )

    # Notifica canal de logs
    try:
        from bot.handlers.admin.notifications import notify_withdrawal_request

        await notify_withdrawal_request(
            bot=message.bot,
            session=session,
            user_id=user.telegram_id,
            amount=float(balance),
            method="pix",
        )
    except Exception as e:
        logger.debug(f"⚠️ Falha ao notificar saque: {e}")


# ============================================
# 🔑 RECUPERAÇÃO DE SENHA (persistente)
# ============================================
@router.callback_query(F.data == "aff:recuperar_senha")
async def cb_recover_password(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """
    Cliente quer recuperar a senha de saque.
    Envia código pro e-mail cadastrado.
    """
    if not user.email or not user.email_verified:
        text = (
            f"❌ <b>E-mail não cadastrado.</b>\n\n"
            f"Cadastre um e-mail antes de recuperar a senha."
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="📧 Cadastrar E-mail",
                    callback_data="aff:cadastrar_email",
                )],
                [InlineKeyboardButton(text="🔙 Voltar", callback_data="aff:voltar")],
            ]
        )
        await _edit_or_send(callback, text, keyboard)
        await callback.answer()
        return

    # Envia código de recuperação (persistente)
    result = await email_verification.send_password_recovery(
        session=session,
        email=user.email,
        telegram_id=user.telegram_id,
    )

    if not result.get("success"):
        error = result.get("error", "Erro desconhecido")
        cooldown = result.get("cooldown_seconds")

        if cooldown:
            await callback.answer(
                f"⏰ Aguarde {cooldown}s", show_alert=True
            )
        else:
            await callback.answer(f"❌ {error}", show_alert=True)
        return

    expiration = result.get("expiration_minutes", 15)

    text = (
        f"📩 <b>Código enviado!</b>\n\n"
        f"Enviamos um código para:\n"
        f"📧 <b>{_mask_email(user.email)}</b>\n\n"
        f"Digite o código de <b>6 dígitos</b> recebido:\n\n"
        f"<i>O código expira em {expiration} minutos.</i>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="wd:cancelar")],
        ]
    )

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()

    await state.set_state(AffiliateStates.waiting_recovery_code)


# ============================================
# 🔑 VALIDAR CÓDIGO DE RECUPERAÇÃO
# ============================================
@router.message(AffiliateStates.waiting_recovery_code, F.text.regexp(r"^\d{6}$"))
async def msg_verify_password_recovery(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """
    Valida o código e pede a nova senha.
    """
    raw = (message.text or "").strip()

    if not user.email:
        await message.answer("❌ Sessão expirada.")
        await state.clear()
        return

    # Valida código (persistente)
    result = await email_verification.verify_password_recovery(
        session=session,
        email=user.email,
        code=raw,
    )

    if not result.get("success"):
        error = result.get("error", "Código incorreto")
        attempts = result.get("attempts_remaining")
        locked = result.get("locked")
        expired = result.get("expired")

        if locked:
            await message.answer(f"🚫 {error}")
            await state.clear()
            return

        if expired:
            await message.answer(
                f"⏰ {error}\n\nEnvie /start e refaça o processo."
            )
            await state.clear()
            return

        extra = ""
        if attempts is not None:
            extra = f"\n\nTentativas restantes: <b>{attempts}</b>"

        await message.answer(f"❌ {error}{extra}")
        return

    # ✓ Código válido → pede nova senha
    await message.answer(
        f"✅ <b>Código validado!</b>\n\n"
        f"🔐 Agora envie sua <b>nova senha de saque</b>.\n\n"
        f"Use de 4 a 8 dígitos numéricos.\n"
        f"Exemplo: <code>1234</code>"
    )

    await state.set_state(AffiliateStates.waiting_new_password)


# ============================================
# 🔐 SALVAR NOVA SENHA (após recuperação)
# ============================================
@router.message(AffiliateStates.waiting_new_password)
async def msg_save_new_password(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    raw = (message.text or "").strip()

    if raw.startswith("/cancelar") or raw.startswith("/start"):
        await state.clear()
        await message.answer("❌ Operação cancelada.")
        return

    if not raw.isdigit() or not (4 <= len(raw) <= 8):
        await message.answer(
            "❌ Senha inválida.\n\n"
            "Use de 4 a 8 dígitos numéricos.\n"
            "Exemplo: <code>1234</code>"
        )
        return

    # Hasheia
    try:
        from passlib.hash import bcrypt
        hashed = bcrypt.hash(raw)
    except Exception as e:
        logger.exception(f"❌ Erro ao hashear senha: {e}")
        await message.answer("❌ Erro ao salvar. Tente novamente.")
        return

    user.withdrawal_password_hash = hashed
    session.add(user)

    await state.clear()

    # Tenta deletar a mensagem com a senha
    try:
        await message.delete()
    except Exception:
        pass

    await message.answer(
        f"✅ <b>Senha de saque redefinida!</b>\n\n"
        f"Sua nova senha está ativa.\n"
        f"Guarde-a em local seguro."
    )


# ============================================
# ❌ CANCELAR
# ============================================
@router.callback_query(F.data == "wd:cancelar")
async def cb_cancel_withdrawal(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    await state.clear()
    await callback.answer("❌ Operação cancelada.", show_alert=True)

    callback.data = "menu:afiliados"
    await cb_affiliate_menu(callback, user, session)


# ============================================
# 🏦 CADASTRAR BANCO
# ============================================
@router.callback_query(F.data == "aff:cadastrar_banco")
async def cb_register_bank(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    # Verifica se já tem conta salva
    stmt = select(BankAccount).where(
        BankAccount.user_id == user.id,
        BankAccount.is_default.is_(True),
    )
    result = await session.execute(stmt)
    account = result.scalar_one_or_none()

    # URL do Mini App
    webapp_url = await config_service.get_str(session, "webapp_url", "")
    bank_form_url = f"{webapp_url.rstrip('/')}/banco" if webapp_url else ""

    text = (
        f"🏦 <b>CONTA BANCÁRIA</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    if account:
        text += (
            f"✅ <b>Conta cadastrada:</b>\n\n"
            f"🏦 Banco: <b>{account.bank_name or '—'}</b>\n"
            f"🏷 Agência: <code>{account.agency or '—'}</code>\n"
            f"💳 Conta: <code>{account.account or '—'}</code>\n"
            f"👤 Titular: <b>{account.holder_name or '—'}</b>\n\n"
        )

    text += (
        f"Para cadastrar ou alterar seus dados bancários, "
        f"abre o formulário seguro:"
    )

    rows: list[list[InlineKeyboardButton]] = []

    if bank_form_url:
        rows.append([
            InlineKeyboardButton(
                text="🏦 Abrir formulário",
                url=bank_form_url,
            )
        ])
    else:
        rows.append([
            InlineKeyboardButton(
                text="⚠️ Formulário não configurado",
                callback_data="aff:noop",
            )
        ])

    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="aff:voltar")
    ])

    await _edit_or_send(
        callback, text, InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await callback.answer()


# ============================================
# 🏦 SAQUE POR BANCO
# ============================================
@router.callback_query(F.data == "wd:banco:")
async def cb_withdraw_bank(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    # Verifica se tem conta cadastrada
    stmt = select(BankAccount).where(
        BankAccount.user_id == user.id,
        BankAccount.is_default.is_(True),
    )
    result = await session.execute(stmt)
    account = result.scalar_one_or_none()

    if not account:
        text = (
            f"❌ <b>Nenhuma conta bancária cadastrada.</b>\n\n"
            f"Cadastre uma conta antes de solicitar o saque."
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="🏦 Cadastrar Conta",
                    callback_data="aff:cadastrar_banco",
                )],
                [InlineKeyboardButton(text="🔙 Voltar", callback_data="aff:saque")],
            ]
        )
        await _edit_or_send(callback, text, keyboard)
        await callback.answer()
        return

    balance = user.affiliate_balance or Decimal("0.00")

    text = (
        f"🏦 <b>SAQUE POR BANCO</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏦 Banco: <b>{account.bank_name or '—'}</b>\n"
        f"🏷 Agência: <code>{account.agency or '—'}</code>\n"
        f"💳 Conta: <code>{account.account or '—'}</code>\n"
        f"👤 Titular: <b>{account.holder_name or '—'}</b>\n\n"
        f"💰 Valor do saque: <b>R$ {_format_brl(balance)}</b>\n\n"
        f"⚠️ Será solicitada sua senha de saque."
    )

    keyboard = build_bank_withdrawal_confirm_keyboard()

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "wd:confirmar_banco")
async def cb_confirm_bank_withdrawal(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    if not user.withdrawal_password_hash:
        await callback.answer(
            "🔐 Cadastre uma senha de saque primeiro.",
            show_alert=True,
        )
        return

    text = (
        f"🔐 <b>CONFIRMAÇÃO DE SEGURANÇA</b>\n\n"
        f"Digite sua <b>senha de saque</b> para confirmar:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="wd:cancelar")],
        ]
    )

    await _edit_or_send(callback, text, keyboard)
    await callback.answer()

    await state.update_data(method="bank")
    await state.set_state(WithdrawalStates.waiting_bank_password)


@router.message(WithdrawalStates.waiting_bank_password)
async def msg_bank_password(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    raw = (message.text or "").strip()

    if raw.startswith("/cancelar") or raw.startswith("/start"):
        await state.clear()
        await message.answer("❌ Operação cancelada.")
        return

    try:
        from passlib.hash import bcrypt
        valid = bcrypt.verify(raw, user.withdrawal_password_hash or "")
    except Exception:
        valid = False

    if not valid:
        await message.answer("❌ Senha incorreta.")
        return

    # Busca conta padrão
    stmt = select(BankAccount).where(
        BankAccount.user_id == user.id,
        BankAccount.is_default.is_(True),
    )
    result = await session.execute(stmt)
    account = result.scalar_one_or_none()

    if not account:
        await message.answer("❌ Conta bancária não encontrada.")
        await state.clear()
        return

    balance = user.affiliate_balance or Decimal("0.00")

    bank_data = {
        "bank_code": account.bank_code,
        "bank_name": account.bank_name,
        "agency": account.agency,
        "account": account.account,
        "account_type": account.account_type,
        "holder_name": account.holder_name,
        "holder_document": account.holder_document,
    }

    withdrawal = await withdrawal_service.create_withdrawal_request(
        session=session,
        user=user,
        amount=balance,
        method=WithdrawalMethod.BANK,
        bank_data=bank_data,
    )

    user.affiliate_balance = Decimal("0.00")
    session.add(user)

    await state.clear()

    try:
        await message.delete()
    except Exception:
        pass

    await message.answer(
        f"✅ <b>Solicitação de saque bancário enviada!</b>\n\n"
        f"💰 Valor: <b>R$ {_format_brl(balance)}</b>\n"
        f"🏦 Banco: <b>{account.bank_name or '—'}</b>\n"
        f"🆔 ID: <code>#{withdrawal.id}</code>\n\n"
        f"⏳ Aguardando aprovação."
    )

    # Notifica canal
    try:
        from bot.handlers.admin.notifications import notify_withdrawal_request
        await notify_withdrawal_request(
            bot=message.bot,
            session=session,
            user_id=user.telegram_id,
            amount=float(balance),
            method="bank",
        )
    except Exception:
        pass


# ============================================
# 🔘 NOOP
# ============================================
@router.callback_query(F.data == "aff:noop")
async def cb_aff_noop(callback: CallbackQuery) -> None:
    await callback.answer()

# ============================================
# 🤖 ADMIN AI — Larizinha Store
# ============================================
# Configuração REAL da IA (OpenAI).
# Todos os botões funcionam de verdade.
#
# Cobre:
#   - LIGAR/DESLIGAR IA
#   - Definir chave OpenAI
#   - Definir modelo (gpt-4o-mini, gpt-4o, etc)
#   - Ajustar temperatura
#   - Editar instruções da IA (system prompt)
#   - Testar conexão
#   - Ver últimas conversas (tickets)
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
from core.config import settings
from core.models import Admin, AuditLog, Ticket, TicketStatus
from core.services import ai as ai_service
from core.services import config as config_service


router = Router(name="admin_ai")


# ============================================
# 🤖 MODELOS DISPONÍVEIS
# ============================================
AVAILABLE_MODELS = [
    ("gpt-4o-mini", "GPT-4o Mini (rápido/barato)"),
    ("gpt-4o", "GPT-4o (mais inteligente)"),
    ("gpt-4-turbo", "GPT-4 Turbo"),
    ("gpt-3.5-turbo", "GPT-3.5 Turbo (econômico)"),
]


DEFAULT_PROMPT = (
    "Você é a assistente virtual da {BOT_NAME}, uma loja de streamings "
    "e contas premium.\n\n"
    "Seu papel:\n"
    "- Atender clientes com educação, clareza e objetividade\n"
    "- Tirar dúvidas sobre produtos, pagamento, entrega e garantia\n"
    "- NUNCA invente informações — se não souber, diga que vai chamar "
    "um atendente\n"
    "- Quando o cliente pedir humano, diga: "
    "\"Vou chamar um atendente humano para te ajudar. Um momento! 🙋\"\n\n"
    "Regras:\n"
    "- Pagamento via Pix, entrega automática\n"
    "- Não compartilhe dados de outros clientes\n"
    "- Seja breve (2-4 parágrafos curtos)"
)


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
            [InlineKeyboardButton(text="❌ Cancelar", callback_data="adm_ai:menu")]
        ]
    )


def _mask(v: str | None, show: int = 8) -> str:
    if not v:
        return "—"
    if len(v) <= show * 2:
        return "•" * 8
    return f"{v[:show]}...{v[-4:]}"


# ============================================
# 📋 MENU PRINCIPAL
# ============================================
@router.callback_query(F.data == "adm_ai:menu")
async def cb_ai_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    enabled = await config_service.get_bool(session, "ai_enabled", True)
    api_key = await config_service.get_str(session, "openai_api_key", settings.openai_api_key or "")
    model = await config_service.get_str(session, "openai_model", settings.openai_model)
    temperature = await config_service.get_str(session, "openai_temperature", str(settings.openai_temperature))
    max_tokens = await config_service.get_str(session, "openai_max_tokens", str(settings.openai_max_tokens))

    status = "🟢 LIGADA" if enabled else "🔴 DESLIGADA"
    configured = "🟢 OK" if api_key else "🔴 Não configurada"

    # Conta tickets recentes
    open_tickets = await session.scalar(
        select(func.count(Ticket.id)).where(
            Ticket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS])
        )
    ) or 0

    text = (
        "🤖 <b>CONFIGURAÇÃO DA IA</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚙️ Status: <b>{status}</b>\n"
        f"🔑 Chave: <b>{configured}</b>\n\n"
        f"🧠 Modelo: <code>{model}</code>\n"
        f"🌡 Temperatura: <code>{temperature}</code>\n"
        f"📊 Max tokens: <code>{max_tokens}</code>\n\n"
        f"🎫 Tickets abertos: <b>{open_tickets}</b>\n\n"
        "Use os botões para configurar:"
    )

    toggle_text = "🔴 DESLIGAR" if enabled else "🟢 LIGAR"
    toggle_cb = "adm_ai:off" if enabled else "adm_ai:on"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle_text, callback_data=toggle_cb)],
            [InlineKeyboardButton(text=f"🔑 Chave OpenAI ({_mask(api_key)})", callback_data="adm_ai:set_key")],
            [InlineKeyboardButton(text=f"🧠 Modelo ({model})", callback_data="adm_ai:set_model")],
            [InlineKeyboardButton(text=f"🌡 Temperatura ({temperature})", callback_data="adm_ai:set_temp")],
            [InlineKeyboardButton(text=f"📊 Max Tokens ({max_tokens})", callback_data="adm_ai:set_tokens")],
            [InlineKeyboardButton(text="📝 Instruções da IA", callback_data="adm_ai:set_prompt")],
            [InlineKeyboardButton(text="🧪 Testar Conexão", callback_data="adm_ai:test")],
            [InlineKeyboardButton(text="🎫 Ver Tickets", callback_data="adm_sup:tickets")],
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
@router.callback_query(F.data == "adm_ai:on")
async def cb_ai_on(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await config_service.set_config(session, "ai_enabled", "true")
    await _log_audit(session, callback.from_user.id, "ai_on")
    await callback.answer("🟢 IA ativada", show_alert=True)
    await cb_ai_menu(callback, session)


@router.callback_query(F.data == "adm_ai:off")
async def cb_ai_off(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return
    await config_service.set_config(session, "ai_enabled", "false")
    await _log_audit(session, callback.from_user.id, "ai_off")
    await callback.answer("🔴 IA desligada", show_alert=True)
    await cb_ai_menu(callback, session)


# ============================================
# 🔑 CHAVE OPENAI
# ============================================
@router.callback_query(F.data == "adm_ai:set_key")
async def cb_ai_set_key(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "🔑 <b>CHAVE OPENAI</b>\n\n"
        "Envie sua chave de API da OpenAI.\n\n"
        "Formato: <code>sk-proj-...</code> ou <code>sk-...</code>\n\n"
        "💡 Obtenha em: https://platform.openai.com/api-keys",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(ai_field="openai_api_key")
    await callback.answer()


# ============================================
# 🧠 MODELO
# ============================================
@router.callback_query(F.data == "adm_ai:set_model")
async def cb_ai_set_model(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    rows: list[list[InlineKeyboardButton]] = []
    for model_id, label in AVAILABLE_MODELS:
        rows.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"adm_ai:model:{model_id}",
            )
        ])
    rows.append([
        InlineKeyboardButton(text="✏️ Outro modelo", callback_data="adm_ai:model_custom")
    ])
    rows.append([
        InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_ai:menu")
    ])

    await callback.message.edit_text(
        "🧠 <b>ESCOLHER MODELO</b>\n\n"
        "Escolha o modelo da IA:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_ai:model:"))
async def cb_ai_model_set(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    model_id = callback.data.split(":", 2)[2]

    old = await config_service.get_str(session, "openai_model", settings.openai_model)
    await config_service.set_config(session, "openai_model", model_id)
    settings.openai_model = model_id

    await _log_audit(
        session,
        callback.from_user.id,
        "edit_ai_model",
        old_value={"model": old},
        new_value={"model": model_id},
    )

    await callback.answer(f"✅ Modelo: {model_id}", show_alert=True)

    callback.data = "adm_ai:menu"
    await cb_ai_menu(callback, session)


@router.callback_query(F.data == "adm_ai:model_custom")
async def cb_ai_model_custom(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "🧠 Envie o <b>ID do modelo</b> desejado.\n\n"
        "Exemplo: <code>gpt-4o-mini</code>",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(ai_field="openai_model")
    await callback.answer()


# ============================================
# 🌡 TEMPERATURA
# ============================================
@router.callback_query(F.data == "adm_ai:set_temp")
async def cb_ai_set_temp(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "🌡 <b>TEMPERATURA</b>\n\n"
        "Controla a criatividade da IA.\n\n"
        "• <code>0.0</code> = Objetiva e direta\n"
        "• <code>0.5</code> = Equilibrada\n"
        "• <code>1.0</code> = Criativa\n"
        "• <code>2.0</code> = Muito criativa\n\n"
        "Envie um valor entre <code>0</code> e <code>2</code>:",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(ai_field="openai_temperature")
    await callback.answer()


# ============================================
# 📊 MAX TOKENS
# ============================================
@router.callback_query(F.data == "adm_ai:set_tokens")
async def cb_ai_set_tokens(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.message.answer(
        "📊 <b>MAX TOKENS</b>\n\n"
        "Limite de tokens por resposta.\n\n"
        "• <code>150</code> = Respostas curtas\n"
        "• <code>300</code> = Médio\n"
        "• <code>500</code> = Padrão\n"
        "• <code>1000</code> = Longo\n\n"
        "Envie um valor entre <code>50</code> e <code>4000</code>:",
        reply_markup=_cancel_keyboard(),
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(ai_field="openai_max_tokens")
    await callback.answer()


# ============================================
# 📝 INSTRUÇÕES DA IA (SYSTEM PROMPT)
# ============================================
@router.callback_query(F.data == "adm_ai:set_prompt")
async def cb_ai_set_prompt(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    current = await config_service.get_str(session, "ai_system_prompt", "")
    bot_name = await config_service.get_str(session, "bot_name", "Larizinha Store")

    if not current:
        current = DEFAULT_PROMPT.replace("{BOT_NAME}", bot_name)

    await callback.message.answer(
        "📝 <b>INSTRUÇÕES DA IA (PERSONALIDADE)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Atual:</b>\n<pre>{current[:800]}</pre>\n\n"
        "Envie as novas instruções.\n\n"
        "💡 Variáveis: <code>{BOT_NAME}</code>"
    )
    await state.set_state(AdminStates.editing_config_value)
    await state.update_data(ai_field="ai_system_prompt")
    await callback.answer()


# ============================================
# 💾 SALVAR VALOR
# ============================================
@router.message(AdminStates.editing_config_value)
async def msg_ai_save(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, message.from_user.id):
        return

    data = await state.get_data()
    field = data.get("ai_field")

    if not field:
        await state.clear()
        return

    raw = (message.text or message.caption or "").strip()
    if not raw:
        await message.answer("❌ Valor vazio.")
        return

    # Validações
    if field == "openai_api_key":
        if not raw.startswith(("sk-", "sk-proj-")):
            await message.answer("❌ Chave inválida. Deve começar com sk- ou sk-proj-")
            return

    if field == "openai_temperature":
        try:
            v = float(raw.replace(",", "."))
            if not 0 <= v <= 2:
                raise ValueError
            raw = str(v)
        except ValueError:
            await message.answer("❌ Temperatura deve ser entre 0 e 2.")
            return

    if field == "openai_max_tokens":
        try:
            v = int(raw)
            if not 50 <= v <= 4000:
                raise ValueError
        except ValueError:
            await message.answer("❌ Tokens deve ser entre 50 e 4000.")
            return

    old = await config_service.get_str(session, field, "")
    await config_service.set_config(session, field, raw)

    # Atualiza settings em runtime
    try:
        if field == "openai_api_key":
            settings.openai_api_key = raw
        elif field == "openai_model":
            settings.openai_model = raw
        elif field == "openai_temperature":
            settings.openai_temperature = float(raw)
        elif field == "openai_max_tokens":
            settings.openai_max_tokens = int(raw)
    except Exception:
        pass

    await _log_audit(
        session,
        message.from_user.id,
        f"edit_ai_{field}",
        old_value={field: _mask(old)},
        new_value={field: _mask(raw)},
    )

    label = field.replace("openai_", "").replace("ai_", "").upper()
    await message.answer(f"✅ <b>{label}</b> atualizado!")
    await state.clear()


# ============================================
# 🧪 TESTAR CONEXÃO
# ============================================
@router.callback_query(F.data == "adm_ai:test")
async def cb_ai_test(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _is_admin(session, callback.from_user.id):
        await callback.answer("🚫 Sem acesso.", show_alert=True)
        return

    await callback.answer("🧪 Testando...", show_alert=False)

    # Carrega chave do banco
    key = await config_service.get_str(session, "openai_api_key", "")
    if key:
        settings.openai_api_key = key

    result = await ai_service.test_connection()

    if result.get("ok"):
        text = (
            "🧪 <b>TESTE OPENAI</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "✅ <b>Conexão OK!</b>\n\n"
            f"🧠 Modelo: <code>{result.get('model')}</code>\n"
            f"💬 Resposta teste: <code>{result.get('reply')}</code>"
        )
    else:
        text = (
            "🧪 <b>TESTE OPENAI</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "❌ <b>Falha</b>\n\n"
            f"<code>{result.get('error')}</code>\n\n"
            "Verifique a chave da API."
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Testar novamente", callback_data="adm_ai:test")],
            [InlineKeyboardButton(text="🔙 Voltar", callback_data="adm_ai:menu")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard)

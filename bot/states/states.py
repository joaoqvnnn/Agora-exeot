# ============================================
# 🧠 STATES — Larizinha Store
# ============================================
# Todos os estados FSM do bot.
#
# ✨ ATUALIZADO:
#   - Adiciona TODOS os estados que os handlers usam
#   - Corrige "AdminStates.waiting_message"
#   - Organizado por fluxo
# ============================================

from aiogram.fsm.state import State, StatesGroup


# ============================================
# 💳 RECARGA DE SALDO
# ============================================
class RechargeStates(StatesGroup):
    waiting_amount = State()
    waiting_custom_amount = State()
    waiting_bonus_confirm = State()


# ============================================
# 🛒 COMPRA DE PRODUTO
# ============================================
class PurchaseStates(StatesGroup):
    waiting_quantity = State()
    confirming = State()
    choosing_delivery = State()
    waiting_email = State()
    waiting_whatsapp = State()
    waiting_email_code = State()


# ============================================
# 🎁 GIFT CARD
# ============================================
class GiftCardStates(StatesGroup):
    waiting_code = State()


# ============================================
# 👤 PERFIL / ALTERAÇÃO DE DADOS
# ============================================
class ProfileStates(StatesGroup):
    changing_whatsapp = State()
    changing_email = State()
    waiting_email_code = State()


# ============================================
# 🤝 AFILIADOS
# ============================================
class AffiliateStates(StatesGroup):
    registering_password = State()
    confirming_password = State()
    registering_email = State()
    waiting_recovery_code = State()
    waiting_new_password = State()


# ============================================
# 💸 SAQUES
# ============================================
class WithdrawalStates(StatesGroup):
    choosing_method = State()
    choosing_pix_type = State()
    waiting_pix_key = State()
    confirming_withdrawal = State()
    waiting_password = State()
    waiting_email_code = State()
    filling_bank_data = State()
    waiting_bank_password = State()


# ============================================
# 🔎 PESQUISA
# ============================================
class SearchStates(StatesGroup):
    waiting_query = State()


# ============================================
# 🎧 ATENDIMENTO
# ============================================
class SupportStates(StatesGroup):
    in_chat = State()
    waiting_message = State()
    human_handoff = State()


# ============================================
# 🔔 ALERTAS
# ============================================
class AlertStates(StatesGroup):
    managing = State()


# ============================================
# 👮 ADMIN — ESTADOS DO PAINEL
# ============================================
class AdminStates(StatesGroup):
    # ─── Gerais ───
    waiting_broadcast_text = State()
    waiting_broadcast_target = State()
    waiting_broadcast_schedule = State()

    # ─── Configurações ───
    editing_config_value = State()
    editing_separator = State()
    editing_logs_channel = State()
    editing_support_link = State()

    # ─── Admins ───
    adding_admin = State()
    removing_admin = State()

    # ─── Produtos ───
    creating_product = State()
    editing_product_name = State()
    editing_product_price = State()
    editing_product_description = State()
    editing_product_image = State()
    editing_product_warranty = State()
    editing_product_duration = State()
    editing_product_min_qty = State()
    editing_product_max_qty = State()

    # ─── Categorias ───
    creating_category = State()
    editing_category = State()

    # ─── Estoque ───
    adding_stock = State()
    removing_stock = State()
    removing_stock_by_platform = State()
    changing_service_price = State()
    changing_all_prices = State()

    # ─── Usuários ───
    searching_user = State()
    editing_user_balance = State()
    editing_user_data = State()
    sending_broadcast_user = State()

    # ─── Pix ───
    editing_mp_token = State()
    editing_pix_min = State()
    editing_pix_max = State()
    editing_pix_expiration = State()
    editing_pix_bonus = State()
    editing_pix_bonus_min = State()

    # ─── Afiliados ───
    editing_affiliate_points_per_recharge = State()
    editing_affiliate_min_points = State()
    editing_affiliate_multiplier = State()
    editing_affiliate_commission = State()
    editing_affiliate_min_withdrawal = State()

    # ─── Gift cards ───
    creating_gift_card = State()
    creating_gift_cards_bulk = State()

    # ─── Mensagens / Botões / Imagens ───
    editing_message_text = State()
    editing_message_image = State()
    editing_button_text = State()
    editing_button_url = State()
    editing_image = State()

    # ─── Broadcast / Agendador ───
    scheduling_broadcast = State()

    # ─── Manutenção ───
    editing_maintenance_message = State()
    editing_maintenance_return_message = State()

    # ─── Anti-flood ───
    editing_antiflood_limit = State()
    editing_antiflood_window = State()
    editing_antiflood_block = State()

    # ─── Bloqueios ───
    blocking_user = State()
    blocking_user_reason = State()
    blocking_user_duration = State()

    # ─── Saques ───
    approving_withdrawal = State()
    rejecting_withdrawal = State()
    rejection_reason = State()

    # ─── Configuração bancária ───
    editing_bank_config = State()

    # ─── Pesquisa ───
    editing_search_message = State()
    adding_search_image = State()

    # ─── Termos ───
    editing_terms = State()

    # ─── Atendimento ───
    # ⚠️ CORREÇÃO: support.py usa este estado
    editing_support_message = State()
    waiting_message = State()  # ← ESTE FALTAVA

    # ─── Canal obrigatório ───
    editing_required_channel = State()
    editing_required_channel_message = State()

    # ─── Comandos ───
    editing_command = State()

    # ─── Confirmação genérica ───
    confirming_action = State()

    # ─── WhatsApp Flow ───
    editing_waflow = State()

    # ─── Aparência ───
    editing_appearance = State()

    # ─── Notificações ───
    editing_notification = State()
